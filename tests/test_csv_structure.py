"""Property-based tests for CSV structure invariants.

Feature: sedimental-analysis-tool
Property: 11 - CSV Structure Invariants
Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

import csv
import tempfile
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.csv_writer import CSVWriter, COLUMNS
from sedimental.models import (
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    SampleMetadata,
)

# ---------------------------------------------------------------------------
# Required columns per design spec
# ---------------------------------------------------------------------------

REQUIRED_MEASUREMENT_COLUMNS = {
    "area",
    "perimeter",
    "circularity",
    "roundness",
    "feret_diameter",
    "major_axis",
    "minor_axis",
    "units",
}

# ---------------------------------------------------------------------------
# Strategies (reused from test_csv_roundtrip pattern)
# ---------------------------------------------------------------------------


@st.composite
def grain_measurement_strategy(draw, grain_id: int, scale_ppm=None):
    if scale_ppm is not None:
        unit = draw(st.sampled_from([MeasurementUnit.PIXELS, MeasurementUnit.MILLIMETERS]))
    else:
        unit = MeasurementUnit.PIXELS
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
def sample_metadata_strategy(draw):
    return SampleMetadata(
        sample_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")))),
        location_lat=draw(st.one_of(st.none(), st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False))),
        location_lon=draw(st.one_of(st.none(), st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False))),
        capture_date=draw(st.one_of(st.none(), st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))),
        scale_ppm=draw(st.one_of(st.none(), st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))),
        submitted_by=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="@._-")))),
    )


@st.composite
def image_result_list_strategy(draw):
    """Generate a list of ImageResult objects with unique source files."""
    num_images = draw(st.integers(min_value=1, max_value=5))
    source_files = draw(
        st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")).map(lambda s: s + ".jpg"),
            min_size=num_images,
            max_size=num_images,
            unique=True,
        )
    )
    results = []
    for sf in source_files:
        metadata = draw(sample_metadata_strategy())
        num_grains = draw(st.integers(min_value=1, max_value=8))
        measurements = [
            draw(grain_measurement_strategy(grain_id=i + 1, scale_ppm=metadata.scale_ppm))
            for i in range(num_grains)
        ]
        results.append(ImageResult(source_file=sf, metadata=metadata, measurements=measurements))
    return results


# ---------------------------------------------------------------------------
# Helper: read raw CSV rows from a file
# ---------------------------------------------------------------------------


def read_raw_csv(path: Path):
    """Return (header_row, data_rows) from a CSV file as plain dicts."""
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = list(reader)
    return header, rows


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


class TestCSVStructureInvariants:
    """
    Property 11: CSV Structure Invariants

    For any Results_CSV produced by CSVWriter:
    - The first row SHALL be a header row containing all required column names
    - The number of data rows SHALL equal the total grain count across all images
    - Every row SHALL have a non-empty source_file value
    - Every row SHALL have a scale_factor value (may be empty/null if no scale)
    - All required columns (area, perimeter, circularity, roundness,
      feret_diameter, major_axis, minor_axis, units) SHALL be present

    Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_header_contains_all_required_columns(self, results):
        """
        Property 11a: The CSV header SHALL contain all required column names.
        Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.7
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            header, _ = read_raw_csv(csv_path)
            header_set = set(header)
            for col in REQUIRED_MEASUREMENT_COLUMNS:
                assert col in header_set, f"Required column '{col}' missing from header: {header}"
            # source_file and scale_factor are also required
            assert "source_file" in header_set, "Column 'source_file' missing from header"
            assert "scale_factor" in header_set, "Column 'scale_factor' missing from header"
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_data_row_count_equals_total_grain_count(self, results):
        """
        Property 11b: The number of data rows SHALL equal the total grain
        count across all processed images.
        Validates: Requirement 4.2 (one row per grain)
        """
        total_grains = sum(len(r.measurements) for r in results)
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            _, data_rows = read_raw_csv(csv_path)
            assert len(data_rows) == total_grains, (
                f"Expected {total_grains} data rows, got {len(data_rows)}"
            )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_every_row_has_non_empty_source_file(self, results):
        """
        Property 11c: Every data row SHALL have a non-empty source_file value.
        Validates: Requirement 4.4 (source image filename per grain)
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            _, data_rows = read_raw_csv(csv_path)
            for i, row in enumerate(data_rows):
                assert row.get("source_file", ""), (
                    f"Row {i} has empty or missing source_file"
                )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_scale_factor_column_present_in_every_row(self, results):
        """
        Property 11d: Every data row SHALL have a scale_factor column
        (value may be empty when no scale is provided).
        Validates: Requirement 4.6
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            _, data_rows = read_raw_csv(csv_path)
            for i, row in enumerate(data_rows):
                assert "scale_factor" in row, (
                    f"Row {i} is missing the scale_factor column"
                )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_all_required_measurement_columns_present_in_every_row(self, results):
        """
        Property 11e: All required measurement columns SHALL be present in
        every data row.
        Validates: Requirements 4.3, 4.5, 4.7
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            _, data_rows = read_raw_csv(csv_path)
            for i, row in enumerate(data_rows):
                for col in REQUIRED_MEASUREMENT_COLUMNS:
                    assert col in row, f"Row {i} missing required column '{col}'"
                    assert row[col] != "", f"Row {i} has empty value for required column '{col}'"
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_header_row_is_first_row(self, results):
        """
        Property 11f: The first row of the CSV SHALL be a header row
        (not a data row).
        Validates: Requirement 4.7
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            with csv_path.open("r", newline="", encoding="utf-8") as fh:
                first_line = fh.readline().strip()
            # The first line should contain column names, not numeric data
            assert "source_file" in first_line, (
                f"First line does not look like a header row: {first_line!r}"
            )
            # Verify it matches the expected COLUMNS list
            first_row_fields = [f.strip() for f in first_line.split(",")]
            assert first_row_fields == COLUMNS, (
                f"Header row fields {first_row_fields} != expected {COLUMNS}"
            )
        finally:
            csv_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_single_image_structure(self):
        """Concrete: single image with 3 grains produces correct structure."""
        metadata = SampleMetadata(sample_id="S001", scale_ppm=10.0)
        measurements = [
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
        ]
        results = [ImageResult(source_file="sample.jpg", metadata=metadata, measurements=measurements)]

        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            header, data_rows = read_raw_csv(csv_path)

            # Header contains all required columns
            for col in REQUIRED_MEASUREMENT_COLUMNS | {"source_file", "scale_factor"}:
                assert col in header, f"Missing column: {col}"

            # Exactly 3 data rows (one per grain)
            assert len(data_rows) == 3

            # Every row has non-empty source_file
            for row in data_rows:
                assert row["source_file"] == "sample.jpg"
        finally:
            csv_path.unlink(missing_ok=True)

    def test_concrete_no_scale_scale_factor_is_empty(self):
        """Concrete: when no scale_ppm, scale_factor column is present but empty."""
        results = [
            ImageResult(
                source_file="no_scale.jpg",
                metadata=SampleMetadata(),  # no scale_ppm
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
            _, data_rows = read_raw_csv(csv_path)

            assert len(data_rows) == 1
            assert "scale_factor" in data_rows[0]
            # Empty string when no scale provided
            assert data_rows[0]["scale_factor"] == ""
        finally:
            csv_path.unlink(missing_ok=True)

    def test_concrete_multi_image_row_count(self):
        """Concrete: 3 images with 2, 5, 1 grains → 8 total data rows."""
        grain_counts = [2, 5, 1]
        results = []
        for i, count in enumerate(grain_counts):
            results.append(
                ImageResult(
                    source_file=f"img{i}.jpg",
                    metadata=SampleMetadata(),
                    measurements=[
                        GrainMeasurement(
                            grain_id=j + 1,
                            area=10.0,
                            perimeter=12.0,
                            circularity=0.8,
                            roundness=0.75,
                            feret_diameter=4.0,
                            major_axis=3.5,
                            minor_axis=3.0,
                            unit=MeasurementUnit.PIXELS,
                            scale_factor=None,
                        )
                        for j in range(count)
                    ],
                )
            )

        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            _, data_rows = read_raw_csv(csv_path)
            assert len(data_rows) == sum(grain_counts)
        finally:
            csv_path.unlink(missing_ok=True)
