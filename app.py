import html
import json
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import gradio as gr

ROOT_DIR = Path(__file__).parent.resolve()
BIN_DIR = ROOT_DIR / "bin"
MSX1PQ_BIN = BIN_DIR / "msx1pq_cli"
BASIC_VIEWER_BIN = BIN_DIR / "basic_sc2_viewer.bin"
ROM_CREATOR_BIN = BIN_DIR / "create_sc2_32k_rom.bin"
SETTINGS_JSON = ROOT_DIR / "settings.json"

BASE_TEMP = Path(tempfile.mkdtemp(prefix="msx1pq_app_"))
UPLOAD_DIR = BASE_TEMP / "uploads"
OUTPUT_DIR = BASE_TEMP / "outputs"
ZIP_DIR = BASE_TEMP / "zips"
for path in (UPLOAD_DIR, OUTPUT_DIR, ZIP_DIR):
    path.mkdir(parents=True, exist_ok=True)

DISK_SIZE_BYTES = 720 * 1024
COLOR_CHOICES = [str(i) for i in range(1, 16)]

PALETTE_COLORS: List[Tuple[int, int, int]] = [
    (0, 0, 0),
    (62, 184, 73),
    (116, 208, 125),
    (89, 85, 224),
    (128, 118, 241),
    (185, 94, 81),
    (101, 219, 239),
    (219, 101, 89),
    (255, 137, 125),
    (204, 195, 94),
    (222, 208, 135),
    (58, 162, 65),
    (183, 102, 181),
    (204, 204, 204),
    (255, 255, 255),
]

def palette_text_color(r: int, g: int, b: int) -> str:
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#FFFFFF" if luminance < 140 else "#000000"


def build_palette_css() -> str:
    base_css = """
.palette-checkboxes label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 6px;
    font-weight: 600;
    transition: filter 0.15s ease;
}

.palette-checkboxes label:hover {
    filter: brightness(0.95);
}

.palette-checkboxes input[type='checkbox'] {
    accent-color: currentColor;
}

.overlay-container {
    position: fixed;
    top: 12px;
    right: 12px;
    z-index: 1100;
    pointer-events: none;
}

.overlay-card {
    min-width: 240px;
    max-width: min(520px, 80vw);
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid #cbd5e1;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
    font-weight: 600;
    display: flex;
    gap: 10px;
    align-items: center;
    pointer-events: auto;
}

.overlay-icon {
    width: 18px;
    height: 18px;
}

.overlay-info {
    background: #ecfeff;
    color: #0ea5e9;
}

.overlay-error {
    background: #fff1f2;
    color: #e11d48;
    border-color: #fecdd3;
}
"""
    color_blocks = []
    for idx, (r, g, b) in enumerate(PALETTE_COLORS, start=1):
        text_color = palette_text_color(r, g, b)
        color_blocks.append(
            f"""
.palette-checkboxes label:has(input[value=\"{idx}\"]) {{
    background: rgb({r}, {g}, {b});
    color: {text_color};
}}

.palette-checkboxes label:has(input[value=\"{idx}\"]) * {{
            color: {text_color};
        }}
"""
        )
    return base_css + "\n".join(color_blocks)


CUSTOM_CSS = build_palette_css()


SETTINGS_FORMAT_VERSION = 1


@dataclass
class SettingProfile:
    key: str
    name: str
    description: str
    values: Dict[str, Union[str, bool, float, List[Union[str, int]], None]]
    enabled: bool = True


class SettingManager:
    BOOL_KEYS = {"dither", "dark_dither", "preprocess"}
    NUMERIC_KEYS = {
        "posterize",
        "saturation",
        "gamma",
        "contrast",
        "hue",
        "weight_h",
        "weight_s",
        "weight_v",
        "weight_r",
        "weight_g",
        "weight_b",
    }
    LIST_KEYS = {"use_colors"}
    STRING_KEYS = {"color_system", "eight_dot", "distance"}
    KNOWN_KEYS = BOOL_KEYS | NUMERIC_KEYS | LIST_KEYS | STRING_KEYS

    def __init__(self, profiles: List[SettingProfile], errors: Optional[List[str]] = None):
        self.profiles = profiles
        self.profile_map = {profile.key: profile for profile in profiles}
        self.errors = errors or []

    @classmethod
    def from_file(cls, path: Path) -> "SettingManager":
        errors: List[str] = []
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get("format_version", 1)
        if version != SETTINGS_FORMAT_VERSION:
            errors.append(
                f"Unsupported settings format version: {version} (expected {SETTINGS_FORMAT_VERSION}). Continuing with available data."
            )

        profiles: List[SettingProfile] = []
        for idx, raw in enumerate(data.get("profiles", [])):
            if raw.get("enabled", True) is False:
                continue
            values = cls._sanitize_values(raw.get("values", {}), errors, raw.get("name") or f"Profile {idx + 1}")
            profiles.append(
                SettingProfile(
                    key=raw.get("key", ""),
                    name=raw.get("name", ""),
                    description=raw.get("description", ""),
                    values=values,
                    enabled=raw.get("enabled", True),
                )
            )
        return cls(profiles, errors)

    @classmethod
    def _sanitize_values(
        cls, values: Dict[str, Union[str, bool, float, List[Union[str, int]]]], errors: List[str], profile_name: str
    ) -> Dict[str, Union[str, bool, float, List[Union[str, int]], None]]:
        if not isinstance(values, dict):
            errors.append(f"[{profile_name}] Values must be an object. Ignoring provided values.")
            return {}

        sanitized: Dict[str, Union[str, bool, float, List[Union[str, int]], None]] = {}
        for key, val in values.items():
            if key not in cls.KNOWN_KEYS:
                errors.append(f"[{profile_name}] Unknown parameter '{key}' was ignored.")
                continue

            if val is None:
                sanitized[key] = None
                continue

            if key in cls.BOOL_KEYS:
                if isinstance(val, bool):
                    sanitized[key] = val
                else:
                    errors.append(f"[{profile_name}] '{key}' expects a boolean. Value '{val}' was skipped.")
            elif key in cls.NUMERIC_KEYS:
                try:
                    sanitized[key] = int(val) if key == "posterize" else float(val)
                except (TypeError, ValueError):
                    errors.append(f"[{profile_name}] '{key}' expects a number. Value '{val}' was skipped.")
            elif key in cls.LIST_KEYS:
                if isinstance(val, list):
                    cleaned: List[int] = []
                    for idx, item in enumerate(val):
                        try:
                            cleaned.append(int(item))
                        except (TypeError, ValueError):
                            errors.append(
                                f"[{profile_name}] '{key}' entry at position {idx} is not a number ('{item}') and was skipped."
                            )
                    sanitized[key] = cleaned or None
                else:
                    errors.append(f"[{profile_name}] '{key}' expects a list. Value '{val}' was skipped.")
            else:
                sanitized[key] = str(val)

        return sanitized

    def get_profile(self, key: str) -> Optional[SettingProfile]:
        return self.profile_map.get(key)

    @property
    def default_profile(self) -> SettingProfile:
        if "default" in self.profile_map:
            return self.profile_map["default"]
        if not self.profiles:
            raise ValueError("No setting profiles available")
        return self.profiles[0]

    @property
    def choices(self) -> List[Tuple[str, str]]:
        return [(profile.name, profile.key) for profile in self.profiles]

    def values_for(self, profile: Optional[SettingProfile]) -> Dict[str, Union[str, bool, float, List[Union[str, int]], None]]:
        if profile is None:
            return self.default_profile.values
        merged = self.default_profile.values.copy()
        merged.update(profile.values)
        return merged


SETTINGS_MANAGER = SettingManager.from_file(SETTINGS_JSON)

I18N = {
    "heading_title": {
        "en": "# MMSXX MSX1 Palette Quantizer for Hugging Face Spaces",
        "ja": "# MMSXX MSX1 Palette Quantizer for Hugging Face Spaces",
    },
    "heading_basic": {"en": "### BASIC Parameters", "ja": "### BASICパラメーターズ"},
    "upload_section": {"en": "Upload images", "ja": "画像アップロード"},
    "images_section": {
        "en": "Images and results",
        "ja": "画像一覧と変換結果",
    },
    "language_label": {"en": "Language", "ja": "言語"},
    "color_system_label": {"en": "Color System", "ja": "カラーシステム"},
    "color_system_info": {"en": "CLI default is msx1", "ja": "CLI デフォルトは msx1"},
    "eight_dot_label": {"en": "8dot", "ja": "8dot"},
    "eight_dot_info": {"en": "CLI default is best", "ja": "CLI デフォルトは best"},
    "distance_label": {"en": "Distance", "ja": "距離計測"},
    "distance_info": {"en": "CLI default is rgb", "ja": "CLI デフォルトは rgb"},
    "dither_label": {"en": "Dither", "ja": "ディザー"},
    "dither_info": {"en": "Default ON (CLI)", "ja": "CLI デフォルト ON"},
    "dark_dither_label": {"en": "Dark dither", "ja": "ダークディザー"},
    "dark_dither_info": {"en": "Default ON (CLI)", "ja": "CLI デフォルト ON"},
    "preprocess_section": {"en": "Preprocess adjustments", "ja": "前処理"},
    "preprocessing_label": {"en": "Preprocessing", "ja": "前処理"},
    "preprocessing_info": {
        "en": "Default ON (CLI). Turn off to skip preprocessing (--no-preprocess).",
        "ja": "CLI デフォルト ON。OFF で前処理をスキップ (--no-preprocess)",
    },
    "posterize_label": {"en": "Posterize before processing", "ja": "処理前ポスタライズ"},
    "posterize_info": {
        "en": "CLI default 16 (ignored if <=1)",
        "ja": "CLI デフォルト 16 (1 以下で無効)",
    },
    "saturation_label": {"en": "Pre-saturation", "ja": "処理前彩度"},
    "saturation_info": {"en": "CLI default 0.0", "ja": "CLI デフォルト 0.0"},
    "gamma_label": {"en": "Pre-gamma", "ja": "処理前ガンマ"},
    "gamma_info": {"en": "CLI default 1.0", "ja": "CLI デフォルト 1.0"},
    "contrast_label": {"en": "Pre-contrast", "ja": "処理前コントラスト"},
    "contrast_info": {"en": "CLI default 1.0", "ja": "CLI デフォルト 1.0"},
    "hue_label": {"en": "Pre-hue", "ja": "処理前色相"},
    "hue_info": {"en": "CLI default 0.0", "ja": "CLI デフォルト 0.0"},
    "lut_section": {"en": "Optional LUT", "ja": "LUT (任意)"},
    "lut_label": {"en": "LUT file (optional)", "ja": "LUT ファイル (任意)"},
    "weights_section": {"en": "Weights", "ja": "重み"},
    "weight_h_label": {"en": "HSV weight H", "ja": "HSV 重み H"},
    "weight_s_label": {"en": "HSV weight S", "ja": "HSV 重み S"},
    "weight_v_label": {"en": "HSV weight V", "ja": "HSV 重み V"},
    "weight_r_label": {"en": "RGB weight R", "ja": "RGB 重み R"},
    "weight_g_label": {"en": "RGB weight G", "ja": "RGB 重み G"},
    "weight_b_label": {"en": "RGB weight B", "ja": "RGB 重み B"},
    "weight_info": {"en": "0-1", "ja": "0-1"},
    "palette_label": {"en": "Palette", "ja": "パレット"},
    "color_label": {"en": "Color", "ja": "カラー"},
    "upload_label": {
        "en": "Upload images (PNG, up to 32)",
        "ja": "画像をアップロード (PNG, 最大 32)",
    },
    "gallery_label": {"en": "Images", "ja": "画像"},
    "orig_label": {"en": "Original", "ja": "オリジナル"},
    "result_label": {"en": "Converted (PNG)", "ja": "変換結果 (PNG)"},
    "update_button": {"en": "Update", "ja": "更新"},
    "batch_button": {"en": "Batch convert", "ja": "バッチ実行"},
    "download_png": {"en": "Download PNG", "ja": "PNG をダウンロード"},
    "download_sc2": {"en": "Download SC2", "ja": "SC2 をダウンロード"},
    "batch_section": {"en": "Batch download", "ja": "バッチダウンロード"},
    "batch_type_label": {"en": "Download type", "ja": "ダウンロード種類"},
    "batch_zip_png": {"en": "zip(png)", "ja": "zip(png)"},
    "batch_zip_sc2": {"en": "zip(sc2)", "ja": "zip(sc2)"},
    "batch_zip_dsk": {"en": "zip(dsk)", "ja": "zip(dsk)"},
    "batch_zip_rom32k": {"en": "zip(32krom)", "ja": "zip(32krom)"},
    "batch_download": {"en": "Download batch ZIP", "ja": "バッチ ZIP ダウンロード"},
    "batch_status": {"en": "Batch status", "ja": "バッチ状態"},
    "logs": {"en": "Logs", "ja": "ログ"},
    "no_images_uploaded": {"en": "No images uploaded.", "ja": "画像がアップロードされていません。"},
    "no_selected_image": {"en": "No selected image.", "ja": "選択された画像がありません。"},
    "no_images_process": {"en": "No images to process.", "ja": "処理する画像がありません。"},
    "status_ok": {"en": "ok", "ja": "成功"},
    "status_failed": {"en": "failed", "ja": "失敗"},
    "no_images_converted": {"en": "No images converted.", "ja": "変換済みの画像がありません。"},
    "no_png_outputs": {"en": "No PNG outputs available.", "ja": "PNG 出力がありません。"},
    "zip_png_ready": {"en": "ZIP (PNG) ready.", "ja": "ZIP (PNG) の準備ができました。"},
    "no_sc2_outputs": {"en": "No SC2 outputs available.", "ja": "SC2 出力がありません。"},
    "zip_sc2_ready": {"en": "ZIP (SC2) ready.", "ja": "ZIP (SC2) の準備ができました。"},
    "no_sc2_pack": {"en": "No SC2 outputs to pack.", "ja": "パックする SC2 出力がありません。"},
    "all_sc2_exceed": {
        "en": "All SC2 files exceed disk capacity.",
        "ja": "すべての SC2 ファイルがディスク容量を超えています。",
    },
    "failed_create_dsk": {"en": "Failed to create DSK", "ja": "DSK 作成に失敗"},
    "excluded_size": {"en": "Excluded due to size", "ja": "サイズ超過で除外"},
    "zip_dsk_ready": {"en": "ZIP (DSK) ready.", "ja": "ZIP (DSK) の準備ができました。"},
    "rom_limit": {
        "en": "Only the first two SC2 files are used for 32K ROM.",
        "ja": "32K ROM では最初の 2 つの SC2 ファイルのみ使用します。",
    },
    "failed_create_rom": {"en": "Failed to create ROM", "ja": "ROM 作成に失敗"},
    "zip_rom_ready": {"en": "ZIP (32K ROM) ready.", "ja": "ZIP (32K ROM) の準備ができました。"},
    "not_implemented": {
        "en": "Selected output is not implemented.",
        "ja": "選択された出力は未対応です。",
    },
    "profile_loaded": {"en": "Profile loaded.", "ja": "設定を読み込みました。"},
}


def t(key: str, lang: str) -> str:
    return I18N.get(key, {}).get(lang, key)


def palette_choices(lang: str) -> List[Tuple[str, str]]:
    return [(f"#{i}", str(i)) for i in range(1, len(PALETTE_COLORS) + 1)]


def profile_summary(profile: SettingProfile) -> str:
    return f"**{profile.name}** — {profile.description}"


def to_use_colors(value: Optional[List[Union[str, int]]]) -> List[str]:
    if value is None:
        return COLOR_CHOICES
    return [str(v) for v in value]


def profile_value(values: Dict[str, Union[str, bool, float, List[Union[str, int]], None]], key: str, fallback):
    if key not in values:
        return fallback
    return values.get(key)


def append_log(log_text: str, level: str, message: str) -> str:
    prefix = "[ERROR]" if level == "error" else "[INFO]"
    line = f"{prefix} {message}"
    if not log_text:
        return line
    return f"{log_text.rstrip()}\n{line}"


def render_overlay(message: Optional[str], level: str = "info") -> str:
    if not message:
        return ""
    level_class = "overlay-error" if level == "error" else "overlay-info"
    icon = "⚠️" if level == "error" else "ℹ️"
    overlay_id = f"overlay-{uuid.uuid4().hex}"
    safe_message = html.escape(message)
    return (
        f"<div id=\"{overlay_id}\" class=\"overlay-container\" data-level=\"{level}\">"
        f"<div class=\"overlay-card {level_class}\">"
        f"<span class=\"overlay-icon\">{icon}</span>"
        f"<span>{safe_message}</span>"
        "</div></div>"
        f"<script>(() => {{const el = document.getElementById('{overlay_id}');if(!el) return;"
        "const close=() => el.remove();el.addEventListener('click', close);"
        f"if('{level}' !== 'error'){{setTimeout(close, 5000);}}}})();</script>"
    )


def overlay_update(message: Optional[str], level: str = "info"):
    return gr.update(value=render_overlay(message, level))


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
    language: str = "ja"
    profile_key: str = "default"

    def has_images(self) -> bool:
        return bool(self.images)

    def current_image(self) -> Optional[ImageRecord]:
        if not self.images:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.images):
            self.selected_index = 0
        return self.images[self.selected_index]


def build_cli_args(params: Dict[str, Optional[Union[str, bool, float, List[int]]]], lut_path: Optional[Path]) -> List[str]:
    args: List[str] = []
    color_system = params.get("color_system")
    if color_system:
        args.extend(["--color-system", color_system])

    dither = params.get("dither")
    if dither is False:
        args.append("--no-dither")

    dark_dither = params.get("dark_dither")
    if dark_dither is False:
        args.append("--no-dark-dither")

    eight_dot = params.get("eight_dot")
    if eight_dot:
        args.extend(["--8dot", eight_dot])

    distance = params.get("distance")
    if distance:
        args.extend(["--distance", distance])

    if params.get("no_preprocess"):
        args.append("--no-preprocess")

    for weight_key, flag in [
        ("weight_h", "--weight-h"),
        ("weight_s", "--weight-s"),
        ("weight_v", "--weight-v"),
        ("weight_r", "--weight-r"),
        ("weight_g", "--weight-g"),
        ("weight_b", "--weight-b"),
    ]:
        weight_val = params.get(weight_key)
        if weight_val is not None:
            args.extend([flag, str(weight_val)])

    preprocess_params = {
        "posterize": "--pre-posterize",
        "saturation": "--pre-sat",
        "gamma": "--pre-gamma",
        "contrast": "--pre-contrast",
        "hue": "--pre-hue",
    }
    for key, flag in preprocess_params.items():
        val = params.get(key)
        if val is not None:
            args.extend([flag, str(val)])

    disabled_colors: List[int] = params.get("disable_colors") or []
    if disabled_colors:
        csv = ",".join(str(idx) for idx in disabled_colors)
        args.extend(["--disable-colors", csv])

    if lut_path:
        args.extend(["--pre-lut", str(lut_path)])

    return args


def to_disabled_colors(selected_use_colors: Optional[List[str]]) -> List[int]:
    selected_set = set(selected_use_colors or [])
    return [int(color) for color in COLOR_CHOICES if color not in selected_set]


def convert_image(
    record: ImageRecord,
    params: Dict[str, Optional[Union[str, bool, float, List[int]]]],
    lut_path: Optional[Path],
) -> Tuple[Optional[Path], Optional[Path], str]:
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


def handle_upload(
    files,
    color_system,
    dither,
    dark_dither,
    eight_dot,
    distance,
    preprocess,
    weight_h,
    weight_s,
    weight_v,
    weight_r,
    weight_g,
    weight_b,
    posterize,
    saturation,
    gamma,
    contrast,
    hue,
    use_colors,
    lut_file,
    state: AppState,
):
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
            gr.update(open=True),
            gr.update(open=False),
        )

    state.images = save_uploads(files)
    state.selected_index = 0
    if lut_file is not None:
        lut_dest = UPLOAD_DIR / f"lut_{uuid.uuid4()}_{Path(lut_file.name).name}"
        shutil.copy(lut_file.name, lut_dest)
        state.lut_path = lut_dest
    else:
        state.lut_path = None

    selected_disable_colors = to_disabled_colors(use_colors)

    params = {
        "color_system": color_system,
        "dither": dither,
        "dark_dither": dark_dither,
        "eight_dot": eight_dot,
        "distance": distance,
        "no_preprocess": not preprocess,
        "weight_h": weight_h,
        "weight_s": weight_s,
        "weight_v": weight_v,
        "weight_r": weight_r,
        "weight_g": weight_g,
        "weight_b": weight_b,
        "posterize": posterize,
        "saturation": saturation,
        "gamma": gamma,
        "contrast": contrast,
        "hue": hue,
        "disable_colors": selected_disable_colors,
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
        gr.update(open=False),
        gr.update(open=True),
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


def update_single(
    color_system,
    dither,
    dark_dither,
    eight_dot,
    distance,
    preprocess,
    weight_h,
    weight_s,
    weight_v,
    weight_r,
    weight_g,
    weight_b,
    posterize,
    saturation,
    gamma,
    contrast,
    hue,
    use_colors,
    lut_file,
    state: AppState,
):
    if not state.images:
        return None, t("no_images_uploaded", state.language)

    if lut_file is not None:
        lut_dest = UPLOAD_DIR / f"lut_{uuid.uuid4()}_{Path(lut_file.name).name}"
        shutil.copy(lut_file.name, lut_dest)
        state.lut_path = lut_dest
    else:
        state.lut_path = None

    selected_disable_colors = to_disabled_colors(use_colors)

    params = {
        "color_system": color_system,
        "dither": dither,
        "dark_dither": dark_dither,
        "eight_dot": eight_dot,
        "distance": distance,
        "no_preprocess": not preprocess,
        "weight_h": weight_h,
        "weight_s": weight_s,
        "weight_v": weight_v,
        "weight_r": weight_r,
        "weight_g": weight_g,
        "weight_b": weight_b,
        "posterize": posterize,
        "saturation": saturation,
        "gamma": gamma,
        "contrast": contrast,
        "hue": hue,
        "disable_colors": selected_disable_colors,
    }
    record = state.current_image()
    if record is None:
        return None, t("no_selected_image", state.language)
    png_path, _, logs = convert_image(record, params, state.lut_path)
    return str(png_path) if png_path else None, logs


def convert_all(
    params: Dict[str, Optional[Union[str, bool, float, List[int]]]], state: AppState
) -> Tuple[str, List[ImageRecord]]:
    logs = []
    if not state.images:
        return t("no_images_process", state.language), state.images

    for record in state.images:
        png_path, sc2_path, rec_logs = convert_image(record, params, state.lut_path)
        status = t("status_ok", state.language) if png_path else t("status_failed", state.language)
        logs.append(f"{record.name}: {status}\n{rec_logs}")
    return "\n\n".join(logs), state.images


def batch_run(
    color_system,
    dither,
    dark_dither,
    eight_dot,
    distance,
    preprocess,
    weight_h,
    weight_s,
    weight_v,
    weight_r,
    weight_g,
    weight_b,
    posterize,
    saturation,
    gamma,
    contrast,
    hue,
    use_colors,
    lut_file,
    state: AppState,
):
    if lut_file is not None:
        lut_dest = UPLOAD_DIR / f"lut_{uuid.uuid4()}_{Path(lut_file.name).name}"
        shutil.copy(lut_file.name, lut_dest)
        state.lut_path = lut_dest
    else:
        state.lut_path = None

    selected_disable_colors = to_disabled_colors(use_colors)

    params = {
        "color_system": color_system,
        "dither": dither,
        "dark_dither": dark_dither,
        "eight_dot": eight_dot,
        "distance": distance,
        "no_preprocess": not preprocess,
        "weight_h": weight_h,
        "weight_s": weight_s,
        "weight_v": weight_v,
        "weight_r": weight_r,
        "weight_g": weight_g,
        "weight_b": weight_b,
        "posterize": posterize,
        "saturation": saturation,
        "gamma": gamma,
        "contrast": contrast,
        "hue": hue,
        "disable_colors": selected_disable_colors,
    }
    log_text, _ = convert_all(params, state)
    return log_text, gr.update(interactive=True)


def change_language(lang: str, state: AppState):
    state.language = lang
    palette = palette_choices(lang)
    batch_choices = [
        (t("batch_zip_png", lang), "png"),
        (t("batch_zip_sc2", lang), "sc2"),
        (t("batch_zip_dsk", lang), "dsk"),
        (t("batch_zip_rom32k", lang), "rom32k"),
    ]
    return (
        state,
        gr.update(value=t("heading_title", lang)),
        gr.update(label=t("upload_section", lang)),
        gr.update(label=t("upload_label", lang)),
        gr.update(label=t("preprocess_section", lang)),
        gr.update(label=t("preprocessing_label", lang), info=t("preprocessing_info", lang)),
        gr.update(label=t("posterize_label", lang), info=t("posterize_info", lang)),
        gr.update(label=t("saturation_label", lang), info=t("saturation_info", lang)),
        gr.update(label=t("gamma_label", lang), info=t("gamma_info", lang)),
        gr.update(label=t("contrast_label", lang), info=t("contrast_info", lang)),
        gr.update(label=t("hue_label", lang), info=t("hue_info", lang)),
        gr.update(label=t("lut_section", lang)),
        gr.update(label=t("lut_label", lang)),
        gr.update(label=t("heading_basic", lang)),
        gr.update(label=t("color_system_label", lang), info=t("color_system_info", lang)),
        gr.update(label=t("eight_dot_label", lang), info=t("eight_dot_info", lang)),
        gr.update(label=t("distance_label", lang), info=t("distance_info", lang)),
        gr.update(label=t("dither_label", lang), info=t("dither_info", lang)),
        gr.update(label=t("dark_dither_label", lang), info=t("dark_dither_info", lang)),
        gr.update(label=t("weights_section", lang)),
        gr.update(label=t("weight_h_label", lang), info=t("weight_info", lang)),
        gr.update(label=t("weight_s_label", lang), info=t("weight_info", lang)),
        gr.update(label=t("weight_v_label", lang), info=t("weight_info", lang)),
        gr.update(label=t("weight_r_label", lang), info=t("weight_info", lang)),
        gr.update(label=t("weight_g_label", lang), info=t("weight_info", lang)),
        gr.update(label=t("weight_b_label", lang), info=t("weight_info", lang)),
        gr.update(label=t("palette_label", lang), choices=palette),
        gr.update(label=t("images_section", lang)),
        gr.update(label=t("gallery_label", lang)),
        gr.update(label=t("orig_label", lang)),
        gr.update(label=t("result_label", lang)),
        gr.update(value=t("update_button", lang)),
        gr.update(value=t("batch_button", lang)),
        gr.update(label=t("download_png", lang)),
        gr.update(label=t("download_sc2", lang)),
        gr.update(label=t("batch_section", lang)),
        gr.update(label=t("batch_type_label", lang), choices=batch_choices),
        gr.update(label=t("batch_download", lang)),
        gr.update(label=t("batch_status", lang)),
        gr.update(label=t("logs", lang)),
        gr.update(label=""),
    )


def apply_profile(profile_key: str, state: AppState, logs_text: str):
    profile = SETTINGS_MANAGER.get_profile(profile_key) or SETTINGS_MANAGER.default_profile
    state.profile_key = profile.key
    values = SETTINGS_MANAGER.values_for(profile)
    message = f"{t('profile_loaded', state.language)}: {profile.name}"
    return (
        state,
        profile_summary(profile),
        gr.update(value=profile_value(values, "color_system", "msx1")),
        gr.update(value=profile_value(values, "eight_dot", "best")),
        gr.update(value=profile_value(values, "distance", "rgb")),
        gr.update(value=profile_value(values, "dither", True)),
        gr.update(value=profile_value(values, "dark_dither", True)),
        gr.update(value=profile_value(values, "preprocess", True)),
        gr.update(value=profile_value(values, "posterize", 16)),
        gr.update(value=profile_value(values, "saturation", 0.0)),
        gr.update(value=profile_value(values, "gamma", 1.0)),
        gr.update(value=profile_value(values, "contrast", 1.0)),
        gr.update(value=profile_value(values, "hue", 0.0)),
        gr.update(value=profile_value(values, "weight_h", 1.0)),
        gr.update(value=profile_value(values, "weight_s", 1.0)),
        gr.update(value=profile_value(values, "weight_v", 1.0)),
        gr.update(value=profile_value(values, "weight_r", 1.0)),
        gr.update(value=profile_value(values, "weight_g", 1.0)),
        gr.update(value=profile_value(values, "weight_b", 1.0)),
        gr.update(value=to_use_colors(values.get("use_colors"))),
        overlay_update(message, "info"),
        gr.update(value=append_log(logs_text, "info", message)),
    )


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
        return None, t("no_images_converted", state.language)
    msgs = []
    selection = selection or ""
    if selection == "png":
        paths = [rec.output_png() for rec in state.images if rec.output_png()]
        if not paths:
            return None, t("no_png_outputs", state.language)
        zip_path = zip_files([Path(p) for p in paths], "batch_png.zip")
        return str(zip_path), t("zip_png_ready", state.language)
    elif selection == "sc2":
        paths = [rec.output_sc2() for rec in state.images if rec.output_sc2()]
        if not paths:
            return None, t("no_sc2_outputs", state.language)
        zip_path = zip_files([Path(p) for p in paths], "batch_sc2.zip")
        return str(zip_path), t("zip_sc2_ready", state.language)
    elif selection == "dsk":
        sc2_paths = [rec.output_sc2() for rec in state.images if rec.output_sc2()]
        sc2_paths = [Path(p) for p in sc2_paths if p]
        if not sc2_paths:
            return None, t("no_sc2_pack", state.language)
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
            return None, t("all_sc2_exceed", state.language)
        dsk_out = OUTPUT_DIR / f"disk_{uuid.uuid4()}.dsk"
        args = [str(BASIC_VIEWER_BIN), "-o", str(dsk_out)] + [str(p) for p in included]
        try:
            result = subprocess.run(args, check=True, capture_output=True, text=True)
            msgs.append(result.stdout)
            if result.stderr:
                msgs.append(result.stderr)
        except subprocess.CalledProcessError as exc:
            msgs.append(f"{t('failed_create_dsk', state.language)}: {exc.stderr or exc.stdout}")
            return None, "\n".join(msgs)
        if excluded:
            msgs.append(f"{t('excluded_size', state.language)}: {', '.join(excluded)}")
        zip_path = zip_files([dsk_out], "batch_dsk.zip")
        return str(zip_path), "\n".join(msgs) or t("zip_dsk_ready", state.language)
    elif selection == "rom32k":
        sc2_paths = [rec.output_sc2() for rec in state.images if rec.output_sc2()]
        sc2_paths = [Path(p) for p in sc2_paths if p]
        if not sc2_paths:
            return None, t("no_sc2_pack", state.language)
        if len(sc2_paths) > 2:
            msgs.append(t("rom_limit", state.language))
            sc2_paths = sc2_paths[:2]
        rom_out = OUTPUT_DIR / f"rom32k_{uuid.uuid4()}.rom"
        args = [str(ROM_CREATOR_BIN), "-o", str(rom_out)] + [str(p) for p in sc2_paths]
        try:
            result = subprocess.run(args, check=True, capture_output=True, text=True)
            msgs.append(result.stdout)
            if result.stderr:
                msgs.append(result.stderr)
        except subprocess.CalledProcessError as exc:
            msgs.append(f"{t('failed_create_rom', state.language)}: {exc.stderr or exc.stdout}")
            return None, "\n".join(msgs)
        zip_path = zip_files([rom_out], "batch_rom32k.zip")
        return str(zip_path), "\n".join(msgs) or t("zip_rom_ready", state.language)
    else:
        return None, t("not_implemented", state.language)


def launch_app():
    ensure_executables()

    default_lang = "ja"
    default_profile = SETTINGS_MANAGER.default_profile
    default_values = SETTINGS_MANAGER.values_for(default_profile)

    with gr.Blocks(title="MMSXX MSX1 Palette Quantizer", css=CUSTOM_CSS) as demo:
        state = gr.State(AppState(language=default_lang, profile_key=default_profile.key))

        with gr.Row():
            settings_selector = gr.Dropdown(
                label="設定セット",
                choices=SETTINGS_MANAGER.choices,
                value=default_profile.key,
            )
            profile_label = gr.Markdown(profile_summary(default_profile))
            language_selector = gr.Dropdown(
                label="",
                show_label=False,
                choices=[("lang:ja", "ja"), ("lang:en", "en")],
                value=default_lang,
            )

        initial_overlay = render_overlay("; ".join(SETTINGS_MANAGER.errors), "error") if SETTINGS_MANAGER.errors else ""
        overlay_box = gr.HTML(value=initial_overlay, show_label=False)

        heading = gr.Markdown(t("heading_title", default_lang))

        with gr.Accordion(t("upload_section", default_lang), open=True) as upload_section:
            upload = gr.File(
                label=t("upload_label", default_lang),
                file_count="multiple",
                file_types=["image"],
            )

        with gr.Accordion(t("preprocess_section", default_lang), open=False) as preprocess_section:
            with gr.Row():
                preprocessing = gr.Checkbox(
                    label=t("preprocessing_label", default_lang),
                    value=profile_value(default_values, "preprocess", True),
                    info=t("preprocessing_info", default_lang),
                )
                posterize = gr.Number(
                    label=t("posterize_label", default_lang),
                    value=profile_value(default_values, "posterize", 16),
                    minimum=0,
                    maximum=255,
                    step=1,
                    info=t("posterize_info", default_lang),
                )
                saturation = gr.Number(
                    label=t("saturation_label", default_lang),
                    value=profile_value(default_values, "saturation", 0.0),
                    minimum=0,
                    maximum=10,
                    step=0.01,
                    info=t("saturation_info", default_lang),
                )
                gamma = gr.Number(
                    label=t("gamma_label", default_lang),
                    value=profile_value(default_values, "gamma", 1.0),
                    minimum=0,
                    maximum=10,
                    step=0.01,
                    info=t("gamma_info", default_lang),
                )
                contrast = gr.Number(
                    label=t("contrast_label", default_lang),
                    value=profile_value(default_values, "contrast", 1.0),
                    minimum=0,
                    maximum=10,
                    step=0.01,
                    info=t("contrast_info", default_lang),
                )
                hue = gr.Number(
                    label=t("hue_label", default_lang),
                    value=profile_value(default_values, "hue", 0.0),
                    minimum=-180,
                    maximum=180,
                    step=1,
                    info=t("hue_info", default_lang),
                )

            with gr.Accordion(t("lut_section", default_lang), open=False) as lut_section:
                lut_upload = gr.File(
                    label=t("lut_label", default_lang),
                    file_types=[".cube", ".txt", ".lut", ".csv"],
                    file_count="single",
                )

        with gr.Accordion(t("heading_basic", default_lang), open=True) as basic_section:
            with gr.Row():
                color_system = gr.Dropdown(
                    label=t("color_system_label", default_lang),
                    choices=["msx1", "msx2"],
                    value=profile_value(default_values, "color_system", "msx1"),
                    info=t("color_system_info", default_lang),
                )
                eight_dot = gr.Dropdown(
                    label=t("eight_dot_label", default_lang),
                    choices=["none", "fast", "basic", "best", "best-attr", "best-trans"],
                    value=profile_value(default_values, "eight_dot", "best"),
                    info=t("eight_dot_info", default_lang),
                )
                distance = gr.Dropdown(
                    label=t("distance_label", default_lang),
                    choices=["rgb", "hsv"],
                    value=profile_value(default_values, "distance", "rgb"),
                    info=t("distance_info", default_lang),
                )
                dither = gr.Checkbox(
                    label=t("dither_label", default_lang),
                    value=profile_value(default_values, "dither", True),
                    info=t("dither_info", default_lang),
                )
                dark_dither = gr.Checkbox(
                    label=t("dark_dither_label", default_lang),
                    value=profile_value(default_values, "dark_dither", True),
                    info=t("dark_dither_info", default_lang),
                )

            with gr.Accordion(t("weights_section", default_lang), open=False) as weights_section:
                with gr.Row():
                    weight_h = gr.Number(
                        label=t("weight_h_label", default_lang),
                        value=profile_value(default_values, "weight_h", 1.0),
                        minimum=0,
                        maximum=1,
                        step=0.01,
                        info=t("weight_info", default_lang),
                    )
                    weight_s = gr.Number(
                        label=t("weight_s_label", default_lang),
                        value=profile_value(default_values, "weight_s", 1.0),
                        minimum=0,
                        maximum=1,
                        step=0.01,
                        info=t("weight_info", default_lang),
                    )
                    weight_v = gr.Number(
                        label=t("weight_v_label", default_lang),
                        value=profile_value(default_values, "weight_v", 1.0),
                        minimum=0,
                        maximum=1,
                        step=0.01,
                        info=t("weight_info", default_lang),
                    )
                with gr.Row():
                    weight_r = gr.Number(
                        label=t("weight_r_label", default_lang),
                        value=profile_value(default_values, "weight_r", 1.0),
                        minimum=0,
                        maximum=1,
                        step=0.01,
                        info=t("weight_info", default_lang),
                    )
                    weight_g = gr.Number(
                        label=t("weight_g_label", default_lang),
                        value=profile_value(default_values, "weight_g", 1.0),
                        minimum=0,
                        maximum=1,
                        step=0.01,
                        info=t("weight_info", default_lang),
                    )
                    weight_b = gr.Number(
                        label=t("weight_b_label", default_lang),
                        value=profile_value(default_values, "weight_b", 1.0),
                        minimum=0,
                        maximum=1,
                        step=0.01,
                        info=t("weight_info", default_lang),
                    )

        use_colors = gr.CheckboxGroup(
            label=t("palette_label", default_lang),
            choices=palette_choices(default_lang),
            value=to_use_colors(default_values.get("use_colors")),
            elem_classes=["palette-checkboxes"],
        )

        with gr.Accordion(t("images_section", default_lang), open=False) as images_section:
            with gr.Row():
                gallery = gr.Gallery(label=t("gallery_label", default_lang), columns=4, height=200)

            with gr.Row():
                with gr.Column():
                    orig_preview = gr.Image(label=t("orig_label", default_lang), interactive=False)
                with gr.Column():
                    result_preview = gr.Image(label=t("result_label", default_lang), interactive=False)

        with gr.Row():
            update_btn = gr.Button(t("update_button", default_lang), variant="primary", interactive=False)
            batch_btn = gr.Button(t("batch_button", default_lang), variant="secondary", interactive=False)

        with gr.Row():
            download_png = gr.DownloadButton(label=t("download_png", default_lang), interactive=False)
            download_sc2 = gr.DownloadButton(label=t("download_sc2", default_lang), interactive=False)

        with gr.Accordion(t("batch_section", default_lang), open=True) as batch_section:
            batch_type = gr.Radio(
                label=t("batch_type_label", default_lang),
                choices=[
                    (t("batch_zip_png", default_lang), "png"),
                    (t("batch_zip_sc2", default_lang), "sc2"),
                    (t("batch_zip_dsk", default_lang), "dsk"),
                    (t("batch_zip_rom32k", default_lang), "rom32k"),
                ],
                value="png",
            )
            batch_download = gr.DownloadButton(label=t("batch_download", default_lang), interactive=False)
            batch_message = gr.Textbox(label=t("batch_status", default_lang), interactive=False)

        initial_logs = ""
        for err in SETTINGS_MANAGER.errors:
            initial_logs = append_log(initial_logs, "error", err)
        logs_box = gr.Textbox(label=t("logs", default_lang), lines=10, interactive=False, value=initial_logs)

        upload.change(
            handle_upload,
            inputs=[
                upload,
                color_system,
                dither,
                dark_dither,
                eight_dot,
                distance,
                preprocessing,
                weight_h,
                weight_s,
                weight_v,
                weight_r,
                weight_g,
                weight_b,
                posterize,
                saturation,
                gamma,
                contrast,
                hue,
                use_colors,
                lut_upload,
                state,
            ],
            outputs=[
                state,
                gallery,
                orig_preview,
                result_preview,
                logs_box,
                update_btn,
                batch_btn,
                download_png,
                download_sc2,
                upload_section,
                images_section,
            ],
        )

        gallery.select(
            select_image,
            inputs=[state],
            outputs=[orig_preview, result_preview, logs_box],
        )

        update_btn.click(
            update_single,
            inputs=[
                color_system,
                dither,
                dark_dither,
                eight_dot,
                distance,
                preprocessing,
                weight_h,
                weight_s,
                weight_v,
                weight_r,
                weight_g,
                weight_b,
                posterize,
                saturation,
                gamma,
                contrast,
                hue,
                use_colors,
                lut_upload,
                state,
            ],
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
            inputs=[
                color_system,
                dither,
                dark_dither,
                eight_dot,
                distance,
                preprocessing,
                weight_h,
                weight_s,
                weight_v,
                weight_r,
                weight_g,
                weight_b,
                posterize,
                saturation,
                gamma,
                contrast,
                hue,
                use_colors,
                lut_upload,
                state,
            ],
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

        settings_selector.change(
            apply_profile,
            inputs=[settings_selector, state, logs_box],
            outputs=[
                state,
                profile_label,
                color_system,
                eight_dot,
                distance,
                dither,
                dark_dither,
                preprocessing,
                posterize,
                saturation,
                gamma,
                contrast,
                hue,
                weight_h,
                weight_s,
                weight_v,
                weight_r,
                weight_g,
                weight_b,
                use_colors,
                overlay_box,
                logs_box,
            ],
        )

        language_selector.change(
            change_language,
            inputs=[language_selector, state],
            outputs=[
                state,
                heading,
                upload_section,
                upload,
                preprocess_section,
                preprocessing,
                posterize,
                saturation,
                gamma,
                contrast,
                hue,
                lut_section,
                lut_upload,
                basic_section,
                color_system,
                eight_dot,
                distance,
                dither,
                dark_dither,
                weights_section,
                weight_h,
                weight_s,
                weight_v,
                weight_r,
                weight_g,
                weight_b,
                use_colors,
                images_section,
                gallery,
                orig_preview,
                result_preview,
                update_btn,
                batch_btn,
                download_png,
                download_sc2,
                batch_section,
                batch_type,
                batch_download,
                batch_message,
                logs_box,
                language_selector,
            ],
        )

    return demo


def main():
    demo = launch_app()
    demo.queue().launch()


if __name__ == "__main__":
    main()
