"""Configuration models for MSX1 palette quantization.

The options here are shared by the Python and C++ execution paths so that
future output formats (e.g., SC4, DSK, ROM, MegaROM) can reuse a single
source of truth for option parsing and CLI argument generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class OutputFormat(str, Enum):
    """Supported (and planned) output formats."""

    PNG = "png"
    SC2 = "sc2"
    SC4 = "sc4"  # TODO: implement SC4 support in processing/output handlers.


@dataclass
class QuantizerOptions:
    """Container for quantization options.

    Attributes:
        output_format: Desired output format. SC4 is currently a placeholder.
        palette_mode: Palette handling mode (e.g., "default", "msx1", "fixed").
        dithering: Dithering strength or strategy identifier.
        color_distance: Name of the color distance metric.
        extra_args: Free-form options reserved for future compatibility with
            the upstream tool.
    """

    output_format: OutputFormat = OutputFormat.PNG
    palette_mode: str = "default"
    dithering: str = "floyd-steinberg"
    color_distance: str = "euclidean"
    extra_args: Dict[str, str] = field(default_factory=dict)

    def to_cli_args(self) -> List[str]:
        """Translate options into CLI arguments for the C++ executable.

        Returns a list that can be appended to a subprocess argument vector.
        Unknown values are passed through via ``--key value`` pairs so that
        new options can be introduced without changing the call site.
        """

        args: List[str] = []
        args.extend(["--format", self.output_format.value])
        args.extend(["--palette", self.palette_mode])
        args.extend(["--dither", self.dithering])
        args.extend(["--distance", self.color_distance])

        for key, value in self.extra_args.items():
            args.extend([f"--{key}", str(value)])
        return args

    def to_python_kwargs(self) -> Dict[str, str]:
        """Translate options into keyword arguments for the PyPI module.

        The returned dictionary mirrors the CLI parameters, making it easy to
        keep Python and C++ execution paths in sync.
        """

        kwargs: Dict[str, str] = {
            "output_format": self.output_format.value,
            "palette_mode": self.palette_mode,
            "dithering": self.dithering,
            "color_distance": self.color_distance,
        }
        kwargs.update(self.extra_args)
        return kwargs
