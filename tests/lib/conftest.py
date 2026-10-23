"""Import the vendored device library on its own, without Home Assistant."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(
    0, str(Path(__file__).parents[2] / "custom_components" / "cfos_powerbrain")
)
