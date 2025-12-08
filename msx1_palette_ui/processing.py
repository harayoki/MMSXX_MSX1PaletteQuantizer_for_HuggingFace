"""Image processing helpers built around the PyPI MSX1PaletteQuantizer module."""

from __future__ import annotations

import importlib
import importlib.util
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from PIL import Image

from .config import OutputFormat, QuantizerOptions


def _load_quantizer_module():
    """Load the PyPI module if it is available.

    The import is optional during development so that the UI can still start
    even if the dependency is not installed locally. On Spaces it will be
    installed via ``requirements.txt``.
    """

    spec = importlib.util.find_spec("msx1palettequantizer")
    if spec is None:
        return None
    return importlib.import_module("msx1palettequantizer")


def _apply_python_quantizer(image: Image.Image, options: QuantizerOptions) -> Image.Image:
    """Apply quantization using the PyPI module when possible.

    The function attempts to call a few common entry points from the upstream
    package. If none are available, a Pillow-based fallback is used so that the
    UI remains functional.
    """

    module = _load_quantizer_module()
    kwargs = options.to_python_kwargs()

    if module is not None:
        # Prefer a high-level helper when available.
        if hasattr(module, "quantize_image"):
            return module.quantize_image(image, **kwargs)
        if hasattr(module, "quantize"):
            return module.quantize(image, **kwargs)
        if hasattr(module, "convert_image"):
            return module.convert_image(image, **kwargs)
        if hasattr(module, "MSX1PaletteQuantizer"):
            quantizer_cls = module.MSX1PaletteQuantizer
            quantizer = quantizer_cls(**kwargs)
            if hasattr(quantizer, "convert"):
                return quantizer.convert(image)

    # Fallback: adaptive palette using Pillow so the preview still works.
    palette_image = image.convert("P", palette=Image.ADAPTIVE, colors=16, dither=Image.FLOYDSTEINBERG)
    return palette_image.convert("RGBA")


def generate_preview(image_file, options: QuantizerOptions) -> Tuple[Image.Image, Image.Image, str]:
    """Generate a preview for a single image."""

    original = Image.open(image_file.name).convert("RGBA")
    converted = _apply_python_quantizer(original, options)
    message = "Preview generated with MSX1PaletteQuantizer."
    if options.output_format == OutputFormat.SC4:
        message = "SC4 output is not implemented yet. Showing PNG preview."  # TODO: wire real SC4 support.
    return original, converted, message


def _save_image_variant(image: Image.Image, target_path: Path, output_format: OutputFormat) -> Path:
    """Save an image according to the requested format."""

    if output_format == OutputFormat.PNG:
        image.save(target_path.with_suffix(".png"))
    elif output_format == OutputFormat.SC2:
        # For SC2 we store a placeholder PNG; real SC2 export would be added here.
        image.save(target_path.with_suffix(".png"))
    elif output_format == OutputFormat.SC4:
        # TODO: save SC4-specific output.
        image.save(target_path.with_suffix(".png"))
    else:
        image.save(target_path)
    return target_path.with_suffix(".png")


def batch_quantize_with_python(files: Iterable, options: QuantizerOptions) -> List[Path]:
    """Process multiple files with the PyPI module.

    Returns paths to generated files that can be zipped or shared in the UI.
    """

    outputs: List[Path] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="msx1pq_batch_"))

    for file_obj in files:
        input_path = Path(file_obj.name)
        image = Image.open(input_path).convert("RGBA")
        converted = _apply_python_quantizer(image, options)
        target_path = temp_dir / input_path.stem
        saved = _save_image_variant(converted, target_path, options.output_format)
        outputs.append(saved)

    return outputs
