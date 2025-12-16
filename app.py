import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gradio as gr

ROOT_DIR = Path(__file__).parent.resolve()
BIN_DIR = ROOT_DIR / "bin"
MSX1PQ_BIN = BIN_DIR / "msx1pq_cli"
BASIC_VIEWER_BIN = BIN_DIR / "basic_sc2_viewer.bin"
ROM_CREATOR_BIN = BIN_DIR / "create_sc2_32k_rom.bin"

BASE_TEMP = Path(tempfile.mkdtemp(prefix="msx1pq_app_"))
UPLOAD_DIR = BASE_TEMP / "uploads"
OUTPUT_DIR = BASE_TEMP / "outputs"
ZIP_DIR = BASE_TEMP / "zips"
for path in (UPLOAD_DIR, OUTPUT_DIR, ZIP_DIR):
    path.mkdir(parents=True, exist_ok=True)

DISK_SIZE_BYTES = 720 * 1024


def ensure_executables() -> None:
    for binary in [MSX1PQ_BIN, BASIC_VIEWER_BIN, ROM_CREATOR_BIN]:
        if binary.exists():
            binary.chmod(binary.stat().st_mode | 0o111)


@dataclass
class ImageRecord:
    image_id: str
    name: str
    orig_path: Path
    outputs: Dict[str, Path] = field(default_factory=dict)
    logs: str = ""

    def output_png(self) -> Optional[Path]:
        return self.outputs.get("png")

    def output_sc2(self) -> Optional[Path]:
        return self.outputs.get("sc2")


@dataclass
class AppState:
    images: List[ImageRecord] = field(default_factory=list)
    selected_index: int = 0
    lut_path: Optional[Path] = None

    def has_images(self) -> bool:
        return bool(self.images)

    def current_image(self) -> Optional[ImageRecord]:
        if not self.images:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.images):
            self.selected_index = 0
        return self.images[self.selected_index]


def build_cli_args(params: Dict[str, Optional[str]], lut_path: Optional[Path]) -> List[str]:
    args: List[str] = []
    color_system = params.get("color_system")
    if color_system:
        args.extend(["--color-system", color_system])

    dither = params.get("dither")
    if dither == "dither":
        args.append("--dither")
    elif dither == "no-dither":
        args.append("--no-dither")

    dark_dither = params.get("dark_dither")
    if dark_dither == "dark-dither":
        args.append("--dark-dither")
    elif dark_dither == "no-dark-dither":
        args.append("--no-dark-dither")

    eight_dot = params.get("eight_dot")
    if eight_dot:
        args.extend(["--8dot", eight_dot])

    distance = params.get("distance")
    if distance:
        args.extend(["--distance", distance])

    if lut_path:
        args.extend(["--pre-lut", str(lut_path)])

    return args


def convert_image(record: ImageRecord, params: Dict[str, Optional[str]], lut_path: Optional[Path]) -> Tuple[Optional[Path], Optional[Path], str]:
    out_dir = OUTPUT_DIR / record.image_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    args = [str(MSX1PQ_BIN), "--input", str(record.orig_path), "--output", str(out_dir), "--out-sc2"]
    args.extend(build_cli_args(params, lut_path))

    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        record.outputs = {}
        record.logs = f"Command: {' '.join(args)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        return None, None, record.logs

    png_files = sorted(out_dir.glob("*.png"))
    sc2_files = sorted(out_dir.glob("*.sc2"))
    png_path = png_files[0] if png_files else None
    sc2_path = sc2_files[0] if sc2_files else None
    record.outputs = {}
    if png_path:
        record.outputs["png"] = png_path
    if sc2_path:
        record.outputs["sc2"] = sc2_path
    record.logs = f"Command: {' '.join(args)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    return png_path, sc2_path, record.logs


def save_uploads(files: List[gr.File]) -> List[ImageRecord]:
    records: List[ImageRecord] = []
    for idx, file in enumerate(files[:32]):
        image_id = str(uuid.uuid4())
        dest = UPLOAD_DIR / f"{image_id}_{Path(file.name).name}"
        shutil.copy(file.name, dest)
        records.append(ImageRecord(image_id=image_id, name=dest.name, orig_path=dest))
    return records


def update_gallery(state: AppState) -> List[Tuple[str, str]]:
    return [(str(rec.orig_path), rec.name) for rec in state.images]


def handle_upload(files, color_system, dither, dark_dither, eight_dot, distance, lut_file, state: AppState):
    if not files:
        disable = gr.update(interactive=False)
        return (
            state,
            [],
            None,
            None,
            "",
            disable,
            disable,
            disable,
            disable,
            disable,
            disable,
            disable,
            disable,
        )

    state.images = save_uploads(files)
    state.selected_index = 0
    if lut_file is not None:
        lut_dest = UPLOAD_DIR / f"lut_{uuid.uuid4()}_{Path(lut_file.name).name}"
        shutil.copy(lut_file.name, lut_dest)
        state.lut_path = lut_dest
    else:
        state.lut_path = None

    params = {
        "color_system": color_system,
        "dither": dither,
        "dark_dither": dark_dither,
        "eight_dot": eight_dot,
        "distance": distance,
    }

    png_path = None
    logs = ""
    if state.images:
        png_path, _, logs = convert_image(state.images[0], params, state.lut_path)

    gallery = update_gallery(state)
    enable = gr.update(interactive=True)
    return (
        state,
        gallery,
        str(state.images[0].orig_path) if state.images else None,
        str(png_path) if png_path else None,
        logs,
        enable,
        enable,
        enable,
        enable,
        enable,
        enable,
        enable,
        enable,
    )


def select_image(evt: gr.SelectData, state: AppState):
    if not state.images:
        return None, None, ""
    idx = int(evt.index) if evt and evt.index is not None else 0
    idx = max(0, min(idx, len(state.images) - 1))
    state.selected_index = idx
    record = state.current_image()
    png_path = record.output_png()
    return str(record.orig_path), str(png_path) if png_path else None, record.logs


def update_single(color_system, dither, dark_dither, eight_dot, distance, lut_file, state: AppState):
    if not state.images:
        return None, "No images uploaded."

    if lut_file is not None:
        lut_dest = UPLOAD_DIR / f"lut_{uuid.uuid4()}_{Path(lut_file.name).name}"
        shutil.copy(lut_file.name, lut_dest)
        state.lut_path = lut_dest
    else:
        state.lut_path = None

    params = {
        "color_system": color_system,
        "dither": dither,
        "dark_dither": dark_dither,
        "eight_dot": eight_dot,
        "distance": distance,
    }
    record = state.current_image()
    if record is None:
        return None, "No selected image."
    png_path, _, logs = convert_image(record, params, state.lut_path)
    return str(png_path) if png_path else None, logs


def convert_all(params: Dict[str, Optional[str]], state: AppState) -> Tuple[str, List[ImageRecord]]:
    logs = []
    if not state.images:
        return "No images to process.", state.images

    for record in state.images:
        png_path, sc2_path, rec_logs = convert_image(record, params, state.lut_path)
        status = "ok" if png_path else "failed"
        logs.append(f"{record.name}: {status}\n{rec_logs}")
    return "\n\n".join(logs), state.images


def batch_run(color_system, dither, dark_dither, eight_dot, distance, lut_file, state: AppState):
    if lut_file is not None:
        lut_dest = UPLOAD_DIR / f"lut_{uuid.uuid4()}_{Path(lut_file.name).name}"
        shutil.copy(lut_file.name, lut_dest)
        state.lut_path = lut_dest
    else:
        state.lut_path = None

    params = {
        "color_system": color_system,
        "dither": dither,
        "dark_dither": dark_dither,
        "eight_dot": eight_dot,
        "distance": distance,
    }
    log_text, _ = convert_all(params, state)
    return log_text, gr.update(interactive=True)


def zip_files(file_paths: List[Path], zip_name: str) -> Path:
    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = ZIP_DIR / zip_name
    if zip_path.exists():
        zip_path.unlink()
    import zipfile

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in file_paths:
            zf.write(path, arcname=path.name)
    return zip_path


def prepare_zip(selection: str, state: AppState) -> Tuple[Optional[str], str]:
    if not state.images:
        return None, "No images converted."
    msgs = []
    selection = selection or ""
    if selection == "png":
        paths = [rec.output_png() for rec in state.images if rec.output_png()]
        if not paths:
            return None, "No PNG outputs available."
        zip_path = zip_files([Path(p) for p in paths], "batch_png.zip")
        return str(zip_path), "ZIP (PNG) ready."
    elif selection == "sc2":
        paths = [rec.output_sc2() for rec in state.images if rec.output_sc2()]
        if not paths:
            return None, "No SC2 outputs available."
        zip_path = zip_files([Path(p) for p in paths], "batch_sc2.zip")
        return str(zip_path), "ZIP (SC2) ready."
    elif selection == "dsk":
        sc2_paths = [rec.output_sc2() for rec in state.images if rec.output_sc2()]
        sc2_paths = [Path(p) for p in sc2_paths if p]
        if not sc2_paths:
            return None, "No SC2 outputs to pack."
        included: List[Path] = []
        total = 0
        excluded = []
        for path in sc2_paths:
            size = path.stat().st_size
            if total + size > DISK_SIZE_BYTES:
                excluded.append(path.name)
                continue
            included.append(path)
            total += size
        if not included:
            return None, "All SC2 files exceed disk capacity."
        dsk_out = OUTPUT_DIR / f"disk_{uuid.uuid4()}.dsk"
        args = [str(BASIC_VIEWER_BIN), "-o", str(dsk_out)] + [str(p) for p in included]
        try:
            result = subprocess.run(args, check=True, capture_output=True, text=True)
            msgs.append(result.stdout)
            if result.stderr:
                msgs.append(result.stderr)
        except subprocess.CalledProcessError as exc:
            msgs.append(f"Failed to create DSK: {exc.stderr or exc.stdout}")
            return None, "\n".join(msgs)
        if excluded:
            msgs.append(f"Excluded due to size: {', '.join(excluded)}")
        zip_path = zip_files([dsk_out], "batch_dsk.zip")
        return str(zip_path), "\n".join(msgs) or "ZIP (DSK) ready."
    elif selection == "rom32k":
        sc2_paths = [rec.output_sc2() for rec in state.images if rec.output_sc2()]
        sc2_paths = [Path(p) for p in sc2_paths if p]
        if not sc2_paths:
            return None, "No SC2 outputs to pack."
        if len(sc2_paths) > 2:
            msgs.append("Only the first two SC2 files are used for 32K ROM.")
            sc2_paths = sc2_paths[:2]
        rom_out = OUTPUT_DIR / f"rom32k_{uuid.uuid4()}.rom"
        args = [str(ROM_CREATOR_BIN), "-o", str(rom_out)] + [str(p) for p in sc2_paths]
        try:
            result = subprocess.run(args, check=True, capture_output=True, text=True)
            msgs.append(result.stdout)
            if result.stderr:
                msgs.append(result.stderr)
        except subprocess.CalledProcessError as exc:
            msgs.append(f"Failed to create ROM: {exc.stderr or exc.stdout}")
            return None, "\n".join(msgs)
        zip_path = zip_files([rom_out], "batch_rom32k.zip")
        return str(zip_path), "\n".join(msgs) or "ZIP (32K ROM) ready."
    else:
        return None, "Selected output is not implemented."


def launch_app():
    ensure_executables()

    with gr.Blocks(title="MMSXX MSX1 Palette Quantizer") as demo:
        state = gr.State(AppState())

        gr.Markdown("# MMSXX MSX1 Palette Quantizer for Hugging Face Spaces")
        with gr.Row():
            upload = gr.File(label="Upload images (PNG, up to 32)", file_count="multiple", file_types=["image"])
            lut_upload = gr.File(label="Optional LUT", file_types=[".cube", ".txt", ".lut", ".csv"], file_count="single")

        with gr.Row():
            gallery = gr.Gallery(label="Images", columns=4, height=200)

        with gr.Row():
            with gr.Column():
                orig_preview = gr.Image(label="Original", interactive=False)
            with gr.Column():
                result_preview = gr.Image(label="Converted (PNG)", interactive=False)

        with gr.Accordion("Conversion Parameters", open=True):
            with gr.Row():
                color_system = gr.Dropdown(
                    label="Color System",
                    choices=["msx1", "msx2"],
                    value=None,
                    interactive=False,
                    info="Leave empty for CLI default",
                )
                eight_dot = gr.Dropdown(
                    label="8dot",
                    choices=["fast", "basic", "best", "best-attr", "best-trans"],
                    value=None,
                    interactive=False,
                    info="CLI default applies when empty",
                )
            with gr.Row():
                dither = gr.Radio(
                    label="Dither",
                    choices=[("CLI default", None), ("Dither", "dither"), ("No dither", "no-dither")],
                    value=None,
                    interactive=False,
                )
                dark_dither = gr.Radio(
                    label="Dark dither",
                    choices=[("CLI default", None), ("Use dark dither", "dark-dither"), ("No dark dither", "no-dark-dither")],
                    value=None,
                    interactive=False,
                )
            with gr.Row():
                distance = gr.Dropdown(
                    label="Distance",
                    choices=[None, "rgb", "hsv"],
                    value=None,
                    interactive=False,
                    info="Leave empty for CLI default",
                )
            update_btn = gr.Button("更新 / Update", variant="primary", interactive=False)
            batch_btn = gr.Button("バッチ実行 / Batch convert", variant="secondary", interactive=False)

        with gr.Row():
            download_png = gr.DownloadButton(label="Download PNG", interactive=False)
            download_sc2 = gr.DownloadButton(label="Download SC2", interactive=False)

        with gr.Accordion("Batch download", open=True):
            batch_type = gr.Radio(
                label="Download type",
                choices=[("zip(png)", "png"), ("zip(sc2)", "sc2"), ("zip(dsk)", "dsk"), ("zip(32krom)", "rom32k")],
                value="png",
            )
            batch_download = gr.DownloadButton(label="Download batch ZIP", interactive=False)
            batch_message = gr.Textbox(label="Batch status", interactive=False)
            gr.Markdown("zip(メガロム) - 未実装 (coming soon)")

        logs_box = gr.Textbox(label="Logs", lines=10, interactive=False)

        upload.change(
            handle_upload,
            inputs=[upload, color_system, dither, dark_dither, eight_dot, distance, lut_upload, state],
            outputs=[
                state,
                gallery,
                orig_preview,
                result_preview,
                logs_box,
                color_system,
                eight_dot,
                dither,
                dark_dither,
                update_btn,
                batch_btn,
                download_png,
                download_sc2,
            ],
        )

        gallery.select(
            select_image,
            inputs=[state],
            outputs=[orig_preview, result_preview, logs_box],
        )

        update_btn.click(
            update_single,
            inputs=[color_system, dither, dark_dither, eight_dot, distance, lut_upload, state],
            outputs=[result_preview, logs_box],
        )

        download_png.click(
            lambda state: str(state.current_image().output_png()) if state.current_image() and state.current_image().output_png() else None,
            inputs=state,
            outputs=download_png,
        )
        download_sc2.click(
            lambda state: str(state.current_image().output_sc2()) if state.current_image() and state.current_image().output_sc2() else None,
            inputs=state,
            outputs=download_sc2,
        )

        batch_btn.click(
            batch_run,
            inputs=[color_system, dither, dark_dither, eight_dot, distance, lut_upload, state],
            outputs=[logs_box, batch_download],
        )

        def prepare_batch_zip(selection, state: AppState):
            path, msg = prepare_zip(selection, state)
            return path, msg

        batch_download.click(
            prepare_batch_zip,
            inputs=[batch_type, state],
            outputs=[batch_download, batch_message],
        )

    return demo


def main():
    demo = launch_app()
    demo.queue().launch()


if __name__ == "__main__":
    main()
