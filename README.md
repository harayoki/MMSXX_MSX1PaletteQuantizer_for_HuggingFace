# MMSXX_MSX1PaletteQuantizer_for_HuggingFace

MMSXX MSX1 Palette Quantizer running on Hugging Face Spaces (CPU, Gradio). This app wraps prebuilt CLI tools to convert images into MSX1-friendly formats.

## Features
- Upload up to 32 PNG images and preview conversions side-by-side.
- Adjust important conversion parameters (color system, dithering, dark dithering, 8dot mode, distance) and re-run per-image or batch conversions.
- Optional LUT upload passed directly to the converter.
- Download per-image PNG/SC2 or batch ZIPs (png/sc2/dsk/32krom). MegaROM download is displayed as not implemented.

## Requirements
- Python 3.9+
- The bundled binaries under `bin/` (Linux) must be executable.
- Install dependencies: `pip install -r requirements.txt`

## Running locally
1. Ensure the binaries are executable:
   ```bash
   chmod +x bin/msx1pq_cli bin/basic_sc2_viewer.bin bin/create_sc2_32k_rom.bin
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch the Gradio app:
   ```bash
   python app.py
   ```
4. Open the local Gradio URL shown in the terminal.

## Hugging Face Spaces
The Space uses the prebuilt binaries under `bin/` directly from Python (no build step). The entrypoint is `app.py`, which ensures binaries are executable at startup.

## Notes
- Conversion options left empty follow the CLI defaults; the app only forwards arguments that are explicitly selected.
- Batch DSK generation stops adding SC2 files if the estimated disk capacity (720KB) would be exceeded and reports excluded files.
- 32KB ROM creation uses at most two SC2 files; extra files are skipped with a warning.
