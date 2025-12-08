"""Gradio app entry point for MSX1 Palette Quantizer batch UI."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import gradio as gr
from PIL import Image

from msx1_palette_ui import (
    OutputFormat,
    QuantizerOptions,
    batch_quantize_with_python,
    create_output_bundle,
    generate_preview,
)

MAX_UPLOADS = 32


def _build_options(
    output_format: str, palette_mode: str, dithering: str, color_distance: str, extra: Optional[str]
) -> QuantizerOptions:
    extra_args = {}
    if extra:
        for chunk in extra.split(","):
            if "=" in chunk:
                key, value = chunk.split("=", 1)
                extra_args[key.strip()] = value.strip()
    return QuantizerOptions(
        output_format=OutputFormat(output_format),
        palette_mode=palette_mode,
        dithering=dithering,
        color_distance=color_distance,
        extra_args=extra_args,
    )


def _limit_files(files: Optional[List[gr.File]]) -> List[gr.File]:
    if not files:
        return []
    return list(files)[:MAX_UPLOADS]


def update_preview(
    files: List[gr.File],
    target_name: str,
    output_format: str,
    palette_mode: str,
    dithering: str,
    color_distance: str,
    extra: str,
) -> Tuple[Image.Image, Image.Image, str, str]:
    limited_files = _limit_files(files)
    if not limited_files:
        raise gr.Error("アップロードされた画像がありません。")

    target_file = next((f for f in limited_files if Path(f.name).name == target_name), limited_files[0])
    options = _build_options(output_format, palette_mode, dithering, color_distance, extra)
    original, converted, message = generate_preview(target_file, options)

    temp_dir = Path(tempfile.mkdtemp(prefix="msx1pq_preview_"))
    download_path = temp_dir / "preview.png"
    converted.save(download_path)
    if options.output_format == OutputFormat.SC4:
        message += "\nSC4 書き出しは未実装のため PNG でのプレビューになります。"
    return original, converted, message, str(download_path)


def run_batch(
    files: List[gr.File],
    output_format: str,
    palette_mode: str,
    dithering: str,
    color_distance: str,
    extra: str,
) -> str:
    limited_files = _limit_files(files)
    if not limited_files:
        raise gr.Error("アップロードされた画像がありません。")

    options = _build_options(output_format, palette_mode, dithering, color_distance, extra)
    processed = batch_quantize_with_python(limited_files, options)
    bundle = create_output_bundle(processed, options.output_format)
    return str(bundle.archive_path)


def update_selection(files: List[gr.File]):
    limited_files = _limit_files(files)
    choices = [Path(f.name).name for f in limited_files]
    value = choices[0] if choices else None
    return gr.Dropdown(choices=choices, value=value)


def build_interface():
    with gr.Blocks(title="MSX1 Palette Quantizer") as demo:
        gr.Markdown(
            """
            # MSX1 Palette Quantizer for Hugging Face Spaces
            アップロードした画像を MSX1 風パレットに変換します。PyPI 版の
            `msx1palettequantizer` モジュールを利用し、将来的には C++ 実行ファイルや
            SC4/DSK/ROM/MegaROM 出力にも拡張できる構成です。
            """
        )

        with gr.Row():
            upload = gr.Files(
                label=f"画像をアップロード（最大 {MAX_UPLOADS} 枚）",
                file_count="multiple",
                file_types=["image"],
            )
            with gr.Column():
                format_dd = gr.Radio(
                    label="出力フォーマット",
                    choices=[OutputFormat.PNG.value, OutputFormat.SC2.value, OutputFormat.SC4.value],
                    value=OutputFormat.PNG.value,
                )
                palette_dd = gr.Dropdown(
                    label="パレットモード",
                    choices=["default", "msx1", "fixed"],
                    value="default",
                )
                dithering_dd = gr.Dropdown(
                    label="ディザ",
                    choices=["floyd-steinberg", "none", "bayer"],
                    value="floyd-steinberg",
                )
                distance_dd = gr.Dropdown(
                    label="色距離",
                    choices=["euclidean", "cie76", "cie94"],
                    value="euclidean",
                )
                extra_text = gr.Textbox(
                    label="追加オプション（key=value をカンマ区切り）",
                    placeholder="gamma=2.2,contrast=high",
                )

        with gr.Row():
            selection = gr.Dropdown(label="プレビュー対象", choices=[], interactive=True)
            preview_btn = gr.Button("プレビュー更新")

        with gr.Row():
            original_img = gr.Image(label="元画像", interactive=False)
            converted_img = gr.Image(label="変換後プレビュー", interactive=False)

        preview_status = gr.Markdown()
        preview_download = gr.File(label="プレビューを PNG でダウンロード")

        with gr.Row():
            batch_btn = gr.Button("すべて一括変換")
            zip_output = gr.File(label="結果 ZIP")

        upload.change(fn=update_selection, inputs=upload, outputs=selection)
        preview_btn.click(
            fn=update_preview,
            inputs=[upload, selection, format_dd, palette_dd, dithering_dd, distance_dd, extra_text],
            outputs=[original_img, converted_img, preview_status, preview_download],
        )
        batch_btn.click(
            fn=run_batch,
            inputs=[upload, format_dd, palette_dd, dithering_dd, distance_dd, extra_text],
            outputs=zip_output,
        )

    return demo


demo = build_interface()

if __name__ == "__main__":
    demo.launch()
