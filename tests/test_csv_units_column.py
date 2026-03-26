"""Property-based tests for CSV units column correctness.

Feature: sedimental-analysis-tool
Property: 20 - Units Column Correctness
Validates: Requirements 10.3, 10.4
"""

import csv
import tempfile
from datetime import date
from pathlib import Path

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.csv_writer import CSVWriter
from sedimental.models import (
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    SampleMetadata,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def grain_measurement_strategy(draw, grain_id: int, unit: MeasurementUnit, scale_ppm=None):
    """Generate a GrainMeasurement with an explicit unit."""
    scale_factor = scale_ppm if unit == MeasurementUnit.MILLIMETERS else None
    return GrainMeasurement(
        grain_id=grain_id,
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


@st.composite
def image_result_with_scale_strategy(draw):
    """Generate an ImageResult where all grains use MILLIMETERS (scale_ppm provided)."""
    scale_ppm = draw(st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))
    metadata = SampleMetadata(
        sample_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")))),
        scale_ppm=scale_ppm,
        capture_date=draw(st.one_of(st.none(), st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))),
    )
    num_grains = draw(st.integers(min_value=1, max_value=8))
    measurements = [
        draw(grain_measurement_strategy(grain_id=i + 1, unit=MeasurementUnit.MILLIMETERS, scale_ppm=scale_ppm))
        for i in range(num_grains)
    ]
    source_file = draw(
        st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"))
        .map(lambda s: s + ".jpg")
    )
    return ImageResult(source_file=source_file, metadata=metadata, measurements=measurements)


@st.composite
def image_result_without_scale_strategy(draw):
    """Generate an ImageResult where all grains use PIXELS (no scale_ppm)."""
    metadata = SampleMetadata(
        sample_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")))),
        scale_ppm=None,
        capture_date=draw(st.one_of(st.none(), st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))),
    )
    num_grains = draw(st.integers(min_value=1, max_value=8))
    measurements = [
        draw(grain_measurement_strategy(grain_id=i + 1, unit=MeasurementUnit.PIXELS, scale_ppm=None))
        for i in range(num_grains)
    ]
    source_file = draw(
        st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"))
        .map(lambda s: s + ".jpg")
    )
    return ImageResult(source_file=source_file, metadata=metadata, measurements=measurements)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def read_units_column(path: Path) -> list[str]:
    """Return the list of 'units' values from all data rows in the CSV."""
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [row["units"] for row in reader]


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


class TestUnitsColumnCorrectness:
    """
    Property 20: Units Column Correctness

    For any Results_CSV:
    - If scale_ppm was provided, units column SHALL contain "mm" for all rows
    - If no scale_ppm was provided, units column SHALL contain "pixels" for all rows
    - All rows in a single CSV SHALL have the same units value

    Validates: Requirements 10.3, 10.4
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(image_result=image_result_with_scale_strategy())
    def test_property_units_is_mm_when_scale_provided(self, image_result):
        """
        Property 20a: When scale_ppm is provided and grains are converted,
        the units column SHALL contain "mm" for all rows.
        Validates: Requirement 10.3
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write([image_result], csv_path)
            units_values = read_units_column(csv_path)
            assert len(units_values) > 0, "Expected at least one data row"
            for i, units in enumerate(units_values):
                assert units == MeasurementUnit.MILLIMETERS.value, (
                    f"Row {i}: expected units='mm', got '{units}'"
                )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(image_result=image_result_without_scale_strategy())
    def test_property_units_is_pixels_when_no_scale(self, image_result):
        """
        Property 20b: When no scale_ppm is provided, the units column
        SHALL contain "pixels" for all rows.
        Validates: Requirement 10.4
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write([image_result], csv_path)
            units_values = read_units_column(csv_path)
            assert len(units_values) > 0, "Expected at least one data row"
            for i, units in enumerate(units_values):
                assert units == MeasurementUnit.PIXELS.value, (
                    f"Row {i}: expected units='pixels', got '{units}'"
                )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(image_result=image_result_with_scale_strategy())
    def test_property_all_rows_same_units_with_scale(self, image_result):
        """
        Property 20c: All rows in a single CSV SHALL have the same units value
        (when scale is provided).
        Validates: Requirements 10.3, 10.4
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write([image_result], csv_path)
            units_values = read_units_column(csv_path)
            assert len(set(units_values)) == 1, (
                f"Expected all rows to have the same units, got: {set(units_values)}"
            )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(image_result=image_result_without_scale_strategy())
    def test_property_all_rows_same_units_without_scale(self, image_result):
        """
        Property 20d: All rows in a single CSV SHALL have the same units value
        (when no scale is provided).
        Validates: Requirements 10.3, 10.4
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write([image_result], csv_path)
            units_values = read_units_column(csv_path)
            assert len(set(units_values)) == 1, (
                f"Expected all rows to have the same units, got: {set(units_values)}"
            )
        finally:
            csv_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_mm_units_when_scale_provided(self):
        """Concrete: grains measured in mm produce units='mm' in every row."""
        scale_ppm = 10.0
        results = [
            ImageResult(
                source_file="scaled.jpg",
                metadata=SampleMetadata(scale_ppm=scale_ppm),
                measurements=[
                    GrainMeasurement(
                        grain_id=i,
                        area=float(100 * i),
                        perimeter=float(40 * i),
                        circularity=0.9,
                        roundness=0.85,
                        feret_diameter=float(12 * i),
                        major_axis=float(11 * i),
                        minor_axis=float(10 * i),
                        unit=MeasurementUnit.MILLIMETERS,
                        scale_factor=scale_ppm,
                    )
                    for i in range(1, 4)
                ],
            )
        ]
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            units_values = read_units_column(csv_path)
            assert units_values == ["mm", "mm", "mm"]
        finally:
            csv_path.unlink(missing_ok=True)

    def test_concrete_pixels_units_when_no_scale(self):
        """Concrete: grains measured in pixels produce units='pixels' in every row."""
        results = [
            ImageResult(
                source_file="unscaled.jpg",
                metadata=SampleMetadata(),  # no scale_ppm
                measurements=[
                    GrainMeasurement(
                        grain_id=i,
                        area=float(100 * i),
                        perimeter=float(40 * i),
                        circularity=0.9,
                        roundness=0.85,
                        feret_diameter=float(12 * i),
                        major_axis=float(11 * i),
                        minor_axis=float(10 * i),
                        unit=MeasurementUnit.PIXELS,
                        scale_factor=None,
                    )
                    for i in range(1, 4)
                ],
            )
        ]
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            units_values = read_units_column(csv_path)
            assert units_values == ["pixels", "pixels", "pixels"]
        finally:
            csv_path.unlink(missing_ok=True)

    def test_concrete_units_column_is_present(self):
        """Concrete: the 'units' column is always present in the CSV header."""
        results = [
            ImageResult(
                source_file="any.jpg",
                metadata=SampleMetadata(),
                measurements=[
                    GrainMeasurement(
                        grain_id=1,
                        area=50.0,
                        perimeter=30.0,
                        circularity=0.7,
                        roundness=0.65,
                        feret_diameter=9.0,
                        major_axis=8.5,
                        minor_axis=7.0,
                        unit=MeasurementUnit.PIXELS,
                        scale_factor=None,
                    )
                ],
            )
        ]
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            with csv_path.open("r", newline="", encoding="utf-8") as fh:
                header = csv.DictReader(fh).fieldnames or []
            assert "units" in header, f"'units' column missing from header: {header}"
        finally:
            csv_path.unlink(missing_ok=True)
