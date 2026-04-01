"""
Shared pytest fixtures and Hypothesis strategies for the sedimental test suite.

Fixtures
--------
valid_jpeg_file      - tmp_path JPEG file (10×8 px, valid)
valid_jpeg_bytes     - raw bytes of a minimal valid JPEG
corrupted_image_file - tmp_path file with invalid/corrupted image bytes
sample_metadata_file - tmp_path metadata.json with "default" and "images" sections

Hypothesis strategies (importable from tests.strategies or this module)
------------------------------------------------------------------------
st_sample_metadata()      - SampleMetadata instances
st_grain_measurement()    - GrainMeasurement instances
st_segmentation_mask()    - 2-D int32 numpy arrays with integer grain labels
st_image_result()         - ImageResult instances
st_image_result_list()    - list of ImageResult instances with unique source files
st_metadata_dict()        - JSON-serialisable metadata dicts for MetadataParser tests
st_jpeg_filename()        - plausible JPEG filename strings
st_valid_jpeg_bytes()     - raw bytes of a randomly-sized valid JPEG
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

# Re-export all strategies so tests can import them from conftest or strategies
from tests.strategies import (  # noqa: F401  (re-exported for convenience)
    st_grain_measurement,
    st_image_result,
    st_image_result_list,
    st_jpeg_filename,
    st_metadata_dict,
    st_sample_metadata,
    st_segmentation_mask,
    st_valid_jpeg_bytes,
)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_jpeg_bytes() -> bytes:
    """Return raw bytes of a minimal valid JPEG image (10×8 px, solid colour)."""
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 8), color=(100, 150, 200))
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def valid_jpeg_file(tmp_path: Path, valid_jpeg_bytes: bytes) -> Path:
    """Write a minimal valid JPEG to a tmp_path file and return the Path."""
    p = tmp_path / "sample.jpg"
    p.write_bytes(valid_jpeg_bytes)
    return p


@pytest.fixture()
def corrupted_image_file(tmp_path: Path) -> Path:
    """Write a file with a JPEG magic header followed by garbage bytes.

    The file has a .jpg extension but is not a valid JPEG — useful for
    testing error-handling paths in ImageLoader.
    """
    p = tmp_path / "corrupted.jpg"
    # JPEG SOI marker + garbage that will fail Pillow's verify()
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10 + b"not a real jpeg body")
    return p


@pytest.fixture()
def sample_metadata_file(tmp_path: Path) -> Path:
    """Write a sample metadata.json with both 'default' and 'images' sections."""
    data = {
        "default": {
            "sample_id": "SAMPLE001",
            "location": {
                "lat": 39.5,
                "lon": -106.5,
                "description": "Colorado River, Mile 42",
            },
            "capture_date": "2024-06-15",
            "scale_ppm": 12.5,
            "submitted_by": "researcher@example.com",
        },
        "images": {
            "sample_a.jpg": {
                "sample_id": "SAMPLE001-A",
                "location": {"lat": 39.6, "lon": -106.6},
            },
            "sample_b.jpg": {
                "scale_ppm": 20.0,
            },
        },
    }
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p
