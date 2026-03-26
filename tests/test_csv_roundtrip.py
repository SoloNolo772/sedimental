"""Property-based tests for CSV round-trip.

Feature: sedimental-analysis-tool
Property: 10 - CSV Round-Trip
Validates: Requirements 4.8
"""

import tempfile
from datetime import date
from pathlib import Path

import pytest
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
def grain_measurement_strategy(draw, grain_id: int, scale_ppm=None):
    """Generate a valid GrainMeasurement with the given grain_id.

    Invariant: scale_factor is set iff unit == MILLIMETERS, and when set
    it equals scale_ppm (the image-level calibration). If scale_ppm is None,
    the grain must use PIXELS (no conversion possible).
    """
    if scale_ppm is not None:
        unit = draw(st.sampled_from([MeasurementUnit.PIXELS, MeasurementUnit.MILLIMETERS]))
    else:
        unit = MeasurementUnit.PIXELS
    scale_factor = scale_ppm if unit == MeasurementUnit.MILLIMETERS else None
    area = draw(st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    perimeter = draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False))
    circularity = draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False))
    roundness = draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False))
    feret_diameter = draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False))
    major_axis = draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False))
    minor_axis = draw(st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False))
    return GrainMeasurement(
        grain_id=grain_id,
        area=area,
        perimeter=perimeter,
        circularity=circularity,
        roundness=roundness,
        feret_diameter=feret_diameter,
        major_axis=major_axis,
        minor_axis=minor_axis,
        unit=unit,
        scale_factor=scale_factor,
    )


@st.composite
def sample_metadata_strategy(draw):
    """Generate a SampleMetadata with CSV-serialisable fields."""
    return SampleMetadata(
        sample_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")))),
        location_lat=draw(st.one_of(st.none(), st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False))),
        location_lon=draw(st.one_of(st.none(), st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False))),
        capture_date=draw(st.one_of(st.none(), st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))),
        scale_ppm=draw(st.one_of(st.none(), st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))),
        submitted_by=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="@._-")))),
    )


@st.composite
def image_result_strategy(draw):
    """Generate a valid ImageResult with at least one grain measurement.

    Invariant: if any grain uses MILLIMETERS, meta.scale_ppm equals that
    grain's scale_factor (they are always the same value in real data).
    """
    source_file = draw(
        st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-."))
        .map(lambda s: s + ".jpg")
    )
    metadata = draw(sample_metadata_strategy())
    num_grains = draw(st.integers(min_value=1, max_value=10))
    measurements = [draw(grain_measurement_strategy(grain_id=i + 1, scale_ppm=metadata.scale_ppm)) for i in range(num_grains)]
    return ImageResult(
        source_file=source_file,
        metadata=metadata,
        measurements=measurements,
    )


@st.composite
def image_result_list_strategy(draw):
    """Generate a list of ImageResult objects with unique source_files."""
    num_images = draw(st.integers(min_value=1, max_value=5))
    # Generate unique source file names
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
        measurements = [draw(grain_measurement_strategy(grain_id=i + 1, scale_ppm=metadata.scale_ppm)) for i in range(num_grains)]
        results.append(ImageResult(
            source_file=sf,
            metadata=metadata,
            measurements=measurements,
        ))
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def floats_equal(a, b, tol=1e-9):
    """Compare two optional floats for near-equality."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def assert_measurements_equal(orig: GrainMeasurement, parsed: GrainMeasurement):
    """Assert two GrainMeasurement objects are equivalent after CSV round-trip."""
    assert orig.grain_id == parsed.grain_id, f"grain_id mismatch: {orig.grain_id} != {parsed.grain_id}"
    assert floats_equal(orig.area, parsed.area), f"area mismatch: {orig.area} != {parsed.area}"
    assert floats_equal(orig.perimeter, parsed.perimeter), f"perimeter mismatch: {orig.perimeter} != {parsed.perimeter}"
    assert floats_equal(orig.circularity, parsed.circularity), f"circularity mismatch: {orig.circularity} != {parsed.circularity}"
    assert floats_equal(orig.roundness, parsed.roundness), f"roundness mismatch: {orig.roundness} != {parsed.roundness}"
    assert floats_equal(orig.feret_diameter, parsed.feret_diameter), f"feret_diameter mismatch: {orig.feret_diameter} != {parsed.feret_diameter}"
    assert floats_equal(orig.major_axis, parsed.major_axis), f"major_axis mismatch: {orig.major_axis} != {parsed.major_axis}"
    assert floats_equal(orig.minor_axis, parsed.minor_axis), f"minor_axis mismatch: {orig.minor_axis} != {parsed.minor_axis}"
    assert orig.unit == parsed.unit, f"unit mismatch: {orig.unit} != {parsed.unit}"
    assert floats_equal(orig.scale_factor, parsed.scale_factor), f"scale_factor mismatch: {orig.scale_factor} != {parsed.scale_factor}"


def assert_metadata_equal(orig: SampleMetadata, parsed: SampleMetadata):
    """Assert CSV-serialisable metadata fields are equivalent after round-trip."""
    assert orig.sample_id == parsed.sample_id, f"sample_id mismatch: {orig.sample_id!r} != {parsed.sample_id!r}"
    assert floats_equal(orig.location_lat, parsed.location_lat), f"location_lat mismatch: {orig.location_lat} != {parsed.location_lat}"
    assert floats_equal(orig.location_lon, parsed.location_lon), f"location_lon mismatch: {orig.location_lon} != {parsed.location_lon}"
    assert orig.capture_date == parsed.capture_date, f"capture_date mismatch: {orig.capture_date} != {parsed.capture_date}"
    assert orig.submitted_by == parsed.submitted_by, f"submitted_by mismatch: {orig.submitted_by!r} != {parsed.submitted_by!r}"
    # scale_ppm is stored in the scale_factor column; check it round-trips
    assert floats_equal(orig.scale_ppm, parsed.scale_ppm), f"scale_ppm mismatch: {orig.scale_ppm} != {parsed.scale_ppm}"


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestCSVRoundTrip:
    """
    Property 10: CSV Round-Trip

    For any list of valid ImageResult objects, writing to CSV via
    CSVWriter.write() then parsing via CSVWriter.parse() SHALL produce
    an equivalent list of ImageResult objects (same measurements, same
    metadata, same source files).

    **Validates: Requirements 4.8**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_round_trip_preserves_image_count(self, results):
        """
        Property 10a: The number of ImageResult objects is preserved after
        write → parse round-trip.
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)
            assert len(parsed) == len(results), (
                f"Expected {len(results)} ImageResult(s), got {len(parsed)}"
            )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_round_trip_preserves_source_files(self, results):
        """
        Property 10b: The source_file for each ImageResult is preserved
        after write → parse round-trip.
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)

            orig_sources = [r.source_file for r in results]
            parsed_sources = [r.source_file for r in parsed]
            assert orig_sources == parsed_sources, (
                f"source_file order/values changed: {orig_sources} != {parsed_sources}"
            )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_round_trip_preserves_grain_count(self, results):
        """
        Property 10c: The number of grain measurements per ImageResult is
        preserved after write → parse round-trip.
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)

            for orig, pars in zip(results, parsed):
                assert len(orig.measurements) == len(pars.measurements), (
                    f"source_file={orig.source_file}: "
                    f"expected {len(orig.measurements)} grains, got {len(pars.measurements)}"
                )
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_round_trip_preserves_measurements(self, results):
        """
        Property 10d: All grain measurement values (area, perimeter,
        circularity, roundness, feret_diameter, major_axis, minor_axis,
        unit, scale_factor) are preserved after write → parse round-trip.
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)

            for orig_img, parsed_img in zip(results, parsed):
                for orig_m, parsed_m in zip(orig_img.measurements, parsed_img.measurements):
                    assert_measurements_equal(orig_m, parsed_m)
        finally:
            csv_path.unlink(missing_ok=True)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(results=image_result_list_strategy())
    def test_property_round_trip_preserves_metadata(self, results):
        """
        Property 10e: Metadata fields (sample_id, location_lat, location_lon,
        capture_date, submitted_by, scale_ppm) are preserved after
        write → parse round-trip.
        """
        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)

            for orig_img, parsed_img in zip(results, parsed):
                assert_metadata_equal(orig_img.metadata, parsed_img.metadata)
        finally:
            csv_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_single_image_round_trip(self):
        """Concrete example: single image with known values round-trips correctly."""
        metadata = SampleMetadata(
            sample_id="SAMPLE001",
            location_lat=39.5,
            location_lon=-106.5,
            capture_date=date(2024, 6, 15),
            scale_ppm=12.5,
            submitted_by="researcher@example.com",
        )
        measurements = [
            GrainMeasurement(
                grain_id=1,
                area=314.159,
                perimeter=62.832,
                circularity=0.998,
                roundness=0.995,
                feret_diameter=20.0,
                major_axis=20.0,
                minor_axis=19.8,
                unit=MeasurementUnit.PIXELS,
                scale_factor=None,
            ),
            GrainMeasurement(
                grain_id=2,
                area=200.0,
                perimeter=55.0,
                circularity=0.83,
                roundness=0.79,
                feret_diameter=17.0,
                major_axis=16.5,
                minor_axis=15.0,
                unit=MeasurementUnit.MILLIMETERS,
                scale_factor=12.5,
            ),
        ]
        results = [ImageResult(source_file="test_image.jpg", metadata=metadata, measurements=measurements)]

        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)

            assert len(parsed) == 1
            assert parsed[0].source_file == "test_image.jpg"
            assert len(parsed[0].measurements) == 2

            assert_metadata_equal(metadata, parsed[0].metadata)
            for orig_m, parsed_m in zip(measurements, parsed[0].measurements):
                assert_measurements_equal(orig_m, parsed_m)
        finally:
            csv_path.unlink(missing_ok=True)

    def test_concrete_multiple_images_round_trip(self):
        """Concrete example: multiple images preserve ordering and isolation."""
        results = [
            ImageResult(
                source_file=f"image_{i}.jpg",
                metadata=SampleMetadata(sample_id=f"S{i:03d}", scale_ppm=float(i + 1)),
                measurements=[
                    GrainMeasurement(
                        grain_id=1,
                        area=float(100 * (i + 1)),
                        perimeter=float(40 * (i + 1)),
                        circularity=0.9,
                        roundness=0.85,
                        feret_diameter=float(12 * (i + 1)),
                        major_axis=float(11 * (i + 1)),
                        minor_axis=float(10 * (i + 1)),
                        unit=MeasurementUnit.PIXELS,
                        scale_factor=None,
                    )
                ],
            )
            for i in range(3)
        ]

        writer = CSVWriter()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)
        try:
            writer.write(results, csv_path)
            parsed = writer.parse(csv_path)

            assert len(parsed) == 3
            for i, (orig, pars) in enumerate(zip(results, parsed)):
                assert pars.source_file == f"image_{i}.jpg"
                assert pars.metadata.sample_id == f"S{i:03d}"
                assert_measurements_equal(orig.measurements[0], pars.measurements[0])
        finally:
            csv_path.unlink(missing_ok=True)

    def test_concrete_none_metadata_fields_round_trip(self):
        """Concrete example: None metadata fields survive the round-trip as None."""
        results = [
            ImageResult(
                source_file="sparse.jpg",
                metadata=SampleMetadata(),  # all None
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
            parsed = writer.parse(csv_path)

            assert parsed[0].metadata.sample_id is None
            assert parsed[0].metadata.location_lat is None
            assert parsed[0].metadata.location_lon is None
            assert parsed[0].metadata.capture_date is None
            assert parsed[0].metadata.submitted_by is None
            assert parsed[0].metadata.scale_ppm is None
        finally:
            csv_path.unlink(missing_ok=True)
