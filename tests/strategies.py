"""
Reusable Hypothesis strategies for the sedimental test suite.

All strategies are importable directly from this module:

    from tests.strategies import (
        st_sample_metadata,
        st_grain_measurement,
        st_segmentation_mask,
        st_image_result,
        st_image_result_list,
        st_metadata_dict,
        st_jpeg_filename,
    )

They are also re-exported via conftest.py so pytest fixtures can use them.
"""

from __future__ import annotations

import io
from datetime import date
from typing import Optional

import numpy as np
from hypothesis import strategies as st
from PIL import Image

from sedimental.models import (
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    SampleMetadata,
)


# ---------------------------------------------------------------------------
# SampleMetadata strategy
# ---------------------------------------------------------------------------

@st.composite
def st_sample_metadata(draw) -> SampleMetadata:
    """Generate a valid SampleMetadata instance.

    All float fields are finite and within their valid ranges.
    capture_date is between 2000-01-01 and 2030-12-31.
    """
    return SampleMetadata(
        sample_id=draw(
            st.one_of(
                st.none(),
                st.text(
                    min_size=1,
                    max_size=50,
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        whitelist_characters="_-",
                    ),
                ),
            )
        ),
        location_lat=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False),
            )
        ),
        location_lon=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False),
            )
        ),
        location_description=draw(
            st.one_of(st.none(), st.text(min_size=1, max_size=100))
        ),
        capture_date=draw(
            st.one_of(
                st.none(),
                st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)),
            )
        ),
        scale_ppm=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
            )
        ),
        submitted_by=draw(
            st.one_of(
                st.none(),
                st.text(
                    min_size=1,
                    max_size=50,
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        whitelist_characters="@._-",
                    ),
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# GrainMeasurement strategy
# ---------------------------------------------------------------------------

@st.composite
def st_grain_measurement(
    draw,
    grain_id: Optional[int] = None,
    scale_ppm: Optional[float] = None,
) -> GrainMeasurement:
    """Generate a valid GrainMeasurement.

    Parameters
    ----------
    grain_id:
        If provided, use this grain_id; otherwise draw a random positive int.
    scale_ppm:
        If provided, the unit may be PIXELS or MILLIMETERS (with scale_factor
        set to scale_ppm when MILLIMETERS).  If None, unit is always PIXELS.
    """
    gid = grain_id if grain_id is not None else draw(st.integers(min_value=1, max_value=10_000))

    if scale_ppm is not None:
        unit = draw(st.sampled_from([MeasurementUnit.PIXELS, MeasurementUnit.MILLIMETERS]))
    else:
        unit = MeasurementUnit.PIXELS

    scale_factor = scale_ppm if unit == MeasurementUnit.MILLIMETERS else None

    return GrainMeasurement(
        grain_id=gid,
        area=draw(st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False)),
        perimeter=draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False)),
        circularity=draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)),
        roundness=draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)),
        feret_diameter=draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False)),
        major_axis=draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False)),
        minor_axis=draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False)),
        unit=unit,
        scale_factor=scale_factor,
    )


# ---------------------------------------------------------------------------
# Segmentation mask strategy
# ---------------------------------------------------------------------------

@st.composite
def st_segmentation_mask(draw) -> np.ndarray:
    """Generate a valid 2-D int32 segmentation mask.

    The mask has shape (H, W) where H and W are between 4 and 64.
    Label 0 is background; positive integer labels identify grains.
    The number of distinct grain labels is between 0 and 10.
    """
    height = draw(st.integers(min_value=4, max_value=64))
    width = draw(st.integers(min_value=4, max_value=64))
    grain_count = draw(st.integers(min_value=0, max_value=10))

    mask = np.zeros((height, width), dtype=np.int32)
    if grain_count == 0:
        return mask

    total_pixels = height * width
    flat = mask.ravel()
    pixels_per_grain = max(1, total_pixels // (grain_count + 1))
    for label in range(1, grain_count + 1):
        start = (label - 1) * pixels_per_grain
        end = min(start + pixels_per_grain, total_pixels)
        flat[start:end] = label

    return mask


# ---------------------------------------------------------------------------
# ImageResult strategy
# ---------------------------------------------------------------------------

@st.composite
def st_image_result(draw) -> ImageResult:
    """Generate a valid ImageResult with at least one grain measurement.

    Invariant: if any grain uses MILLIMETERS, metadata.scale_ppm equals
    that grain's scale_factor (they are always the same value in real data).
    """
    source_file = draw(
        st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                whitelist_characters="_-.",
            ),
        ).map(lambda s: s + ".jpg")
    )
    metadata = draw(st_sample_metadata())
    num_grains = draw(st.integers(min_value=1, max_value=10))
    measurements = [
        draw(st_grain_measurement(grain_id=i + 1, scale_ppm=metadata.scale_ppm))
        for i in range(num_grains)
    ]
    return ImageResult(
        source_file=source_file,
        metadata=metadata,
        measurements=measurements,
    )


# ---------------------------------------------------------------------------
# ImageResult list strategy (unique source files)
# ---------------------------------------------------------------------------

@st.composite
def st_image_result_list(draw) -> list[ImageResult]:
    """Generate a list of 1–5 ImageResult objects with unique source_files."""
    num_images = draw(st.integers(min_value=1, max_value=5))
    source_files = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="_-",
                ),
            ).map(lambda s: s + ".jpg"),
            min_size=num_images,
            max_size=num_images,
            unique=True,
        )
    )
    results = []
    for sf in source_files:
        metadata = draw(st_sample_metadata())
        num_grains = draw(st.integers(min_value=1, max_value=8))
        measurements = [
            draw(st_grain_measurement(grain_id=i + 1, scale_ppm=metadata.scale_ppm))
            for i in range(num_grains)
        ]
        results.append(
            ImageResult(source_file=sf, metadata=metadata, measurements=measurements)
        )
    return results


# ---------------------------------------------------------------------------
# Metadata dict strategy (JSON-serialisable, for MetadataParser tests)
# ---------------------------------------------------------------------------

@st.composite
def st_metadata_dict(draw) -> dict:
    """Generate a valid metadata dict suitable for JSON serialisation.

    Produces the same structure that MetadataParser.parse() expects inside
    the "default" or per-image sections.
    """
    d: dict = {}

    if draw(st.booleans()):
        d["sample_id"] = draw(st.text(min_size=1, max_size=40))

    if draw(st.booleans()):
        loc: dict = {}
        if draw(st.booleans()):
            loc["lat"] = draw(
                st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
            )
        if draw(st.booleans()):
            loc["lon"] = draw(
                st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)
            )
        if draw(st.booleans()):
            loc["description"] = draw(st.text(min_size=1, max_size=80))
        if loc:
            d["location"] = loc

    if draw(st.booleans()):
        d["capture_date"] = draw(
            st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31))
        ).isoformat()

    if draw(st.booleans()):
        d["scale_ppm"] = draw(
            st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False)
        )

    if draw(st.booleans()):
        d["submitted_by"] = draw(st.text(min_size=1, max_size=40))

    return d


# ---------------------------------------------------------------------------
# JPEG filename strategy
# ---------------------------------------------------------------------------

@st.composite
def st_jpeg_filename(draw) -> str:
    """Generate a plausible JPEG filename (stem + .jpg/.jpeg extension)."""
    stem = draw(st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True))
    ext = draw(st.sampled_from([".jpg", ".jpeg", ".JPG", ".JPEG"]))
    return stem + ext


# ---------------------------------------------------------------------------
# Valid JPEG bytes strategy
# ---------------------------------------------------------------------------

@st.composite
def st_valid_jpeg_bytes(draw) -> bytes:
    """Generate raw bytes of a valid JPEG image with random dimensions and colour."""
    width = draw(st.integers(min_value=1, max_value=256))
    height = draw(st.integers(min_value=1, max_value=256))
    r = draw(st.integers(min_value=0, max_value=255))
    g = draw(st.integers(min_value=0, max_value=255))
    b = draw(st.integers(min_value=0, max_value=255))
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(r, g, b)).save(buf, format="JPEG")
    return buf.getvalue()
