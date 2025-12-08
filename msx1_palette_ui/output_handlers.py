"""Output bundling helpers for future extensibility."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List

from .config import OutputFormat


class OutputBundle:
    """Represents a downloadable bundle.

    Currently this is a ZIP archive, but the class can be expanded to support
    DSK/ROM/MegaROM outputs in the future.
    """

    def __init__(self, archive_path: Path):
        self.archive_path = archive_path


def create_output_bundle(files: Iterable[Path], output_format: OutputFormat) -> OutputBundle:
    """Create a ZIP archive for processed files.

    Args:
        files: List of processed file paths.
        output_format: Currently unused but reserved for format-specific
            bundling logic (e.g., DSK/ROM packaging).
    """

    temp_dir = Path(tempfile.mkdtemp(prefix="msx1pq_zip_"))
    archive_path = temp_dir / "results.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files:
            zipf.write(file_path, arcname=file_path.name)

    # TODO: support DSK, ROM, and MegaROM outputs.
    return OutputBundle(archive_path)
