"""
Script to (re-)generate the static test fixture files in this directory.

Run once from the project root (Pillow must be available):
    docker compose run --rm sedimental test tests/fixtures/generate_fixtures.py

Or locally if Pillow is installed:
    python tests/fixtures/generate_fixtures.py

Files produced
--------------
tests/fixtures/sample.jpg        - minimal valid JPEG (20x16 px)
tests/fixtures/metadata.json     - sample metadata with default + images sections
tests/fixtures/corrupted.jpg     - invalid bytes with a .jpg extension
"""

from __future__ import annotations

import io
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def generate_jpeg(path: Path, width: int = 20, height: int = 16) -> None:
    """Write a minimal valid JPEG to *path* using Pillow."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(120, 160, 200))
    img.save(path, format="JPEG")
    print(f"Created {path} ({width}x{height} JPEG)")


def generate_metadata(path: Path) -> None:
    """Write a sample metadata.json to *path*."""
    data = {
        "default": {
            "sample_id": "FIXTURE-001",
            "location": {
                "lat": 39.5,
                "lon": -106.5,
                "description": "Colorado River, Mile 42",
            },
            "capture_date": "2024-06-15",
            "scale_ppm": 12.5,
            "submitted_by": "fixture-generator",
        },
        "images": {
            "sample_a.jpg": {
                "sample_id": "FIXTURE-001-A",
                "location": {"lat": 39.6, "lon": -106.6},
            },
            "sample_b.jpg": {
                "scale_ppm": 20.0,
            },
        },
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Created {path}")


def generate_corrupted(path: Path) -> None:
    """Write a file with a JPEG magic header followed by garbage bytes."""
    # SOI marker + APP0 marker + garbage — will fail Pillow's verify()
    path.write_bytes(
        b"\xff\xd8\xff\xe0"
        + b"\x00" * 10
        + b"THIS IS NOT A VALID JPEG BODY - CORRUPTED FOR TESTING"
    )
    print(f"Created {path} (corrupted JPEG)")


if __name__ == "__main__":
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    generate_jpeg(FIXTURES_DIR / "sample.jpg")
    generate_metadata(FIXTURES_DIR / "metadata.json")
    generate_corrupted(FIXTURES_DIR / "corrupted.jpg")
    print("Done.")
