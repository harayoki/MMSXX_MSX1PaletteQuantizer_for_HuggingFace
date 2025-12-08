"""Helpers to call the C++ MSX1PaletteQuantizer executable."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from .config import QuantizerOptions


class CPPExecutionError(RuntimeError):
    """Raised when the C++ executable returns a non-zero exit code."""


def run_cpp_quantizer(input_path: Path, output_path: Path, options: QuantizerOptions) -> None:
    """Execute the C++ quantizer binary with the provided options.

    The function assumes that the executable is located under ``bin/`` and is
    named ``msx1palettequantizer``. Adjust as necessary when placing the actual
    binary.
    """

    binary_path = Path("bin/msx1palettequantizer").resolve()
    if not binary_path.exists():
        raise FileNotFoundError(
            "C++ executable not found. Place it under bin/ as msx1palettequantizer."
        )

    args = [str(binary_path), "--input", str(input_path), "--output", str(output_path)]
    args.extend(options.to_cli_args())

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise CPPExecutionError(result.stderr or result.stdout)
