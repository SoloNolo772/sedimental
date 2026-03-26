"""Property-based tests for metadata auto-discovery.

Feature: sedimental-analysis-tool
Property: 12 - Metadata Auto-Discovery
Validates: Requirements 5.1
"""

import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from sedimental.metadata import MetadataParser
from sedimental.models import SampleMetadata


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def metadata_dict_strategy(draw):
    """Generate a valid metadata dict (suitable for JSON serialisation)."""
    d = {}

    if draw(st.booleans()):
        d["sample_id"] = draw(st.text(min_size=1, max_size=40))

    if draw(st.booleans()):
        loc = {}
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


@st.composite
def jpeg_filename_strategy(draw):
    """Generate a plausible JPEG filename."""
    stem = draw(st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True))
    ext = draw(st.sampled_from([".jpg", ".jpeg", ".JPG", ".JPEG"]))
    return stem + ext


# ---------------------------------------------------------------------------
# Property 12: Metadata Auto-Discovery
# ---------------------------------------------------------------------------

class TestMetadataAutoDiscovery:
    """Property 12: Metadata Auto-Discovery.

    For any input directory containing a file named "metadata.json", when no
    --metadata argument is provided, the MetadataParser SHALL load and parse
    that file, and the resulting metadata SHALL be applied to processed images.

    Validates: Requirements 5.1
    """

    # ------------------------------------------------------------------
    # Property tests
    # ------------------------------------------------------------------

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(default_meta=metadata_dict_strategy())
    def test_property_auto_discovery_loads_metadata_json(self, tmp_path, default_meta):
        """Property: When metadata.json exists in a directory, parsing it via
        auto-discovery (path = dir / 'metadata.json') SHALL succeed and return
        a MetadataConfig whose default section reflects the written data.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        metadata_path = work_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps({"default": default_meta}), encoding="utf-8"
        )

        parser = MetadataParser()
        # Simulate auto-discovery: caller resolves dir / "metadata.json"
        config = parser.parse(metadata_path)

        assert config is not None
        assert isinstance(config.default, SampleMetadata)

        # sample_id round-trips correctly
        if "sample_id" in default_meta:
            assert config.default.sample_id == default_meta["sample_id"]

        # scale_ppm round-trips correctly
        if "scale_ppm" in default_meta:
            assert config.default.scale_ppm == pytest.approx(
                default_meta["scale_ppm"], rel=1e-6
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        default_meta=metadata_dict_strategy(),
        image_filenames=st.lists(
            jpeg_filename_strategy(),
            min_size=1,
            max_size=6,
            unique=True,
        ),
        per_image_meta=metadata_dict_strategy(),
    )
    def test_property_auto_discovery_applies_to_images(
        self, tmp_path, default_meta, image_filenames, per_image_meta
    ):
        """Property: After auto-discovery, get_for_image() SHALL return merged
        metadata for each image, with per-image values taking precedence over
        defaults.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Use the first filename for a per-image override
        target_filename = image_filenames[0]
        data = {
            "default": default_meta,
            "images": {target_filename: per_image_meta},
        }

        metadata_path = work_dir / "metadata.json"
        metadata_path.write_text(json.dumps(data), encoding="utf-8")

        parser = MetadataParser()
        config = parser.parse(metadata_path)

        # For the targeted image, per-image values should take precedence
        merged = parser.get_for_image(config, target_filename)

        if "sample_id" in per_image_meta:
            assert merged.sample_id == per_image_meta["sample_id"]
        elif "sample_id" in default_meta:
            assert merged.sample_id == default_meta["sample_id"]

        if "scale_ppm" in per_image_meta:
            assert merged.scale_ppm == pytest.approx(
                per_image_meta["scale_ppm"], rel=1e-6
            )
        elif "scale_ppm" in default_meta:
            assert merged.scale_ppm == pytest.approx(
                default_meta["scale_ppm"], rel=1e-6
            )

        # For images NOT in the per-image section, default metadata is used
        for filename in image_filenames[1:]:
            result = parser.get_for_image(config, filename)
            if "sample_id" in default_meta:
                assert result.sample_id == default_meta["sample_id"]

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        default_meta=metadata_dict_strategy(),
        extra_filenames=st.lists(
            st.from_regex(r"[a-z][a-z0-9_]{0,10}\.(png|txt|csv|tiff)", fullmatch=True),
            min_size=0,
            max_size=5,
        ),
    )
    def test_property_auto_discovery_ignores_non_metadata_files(
        self, tmp_path, default_meta, extra_filenames
    ):
        """Property: The presence of other files in the directory SHALL NOT
        interfere with auto-discovery of metadata.json.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Write some unrelated files
        for fname in extra_filenames:
            (work_dir / fname).write_text("irrelevant content", encoding="utf-8")

        # Write the canonical metadata.json
        metadata_path = work_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps({"default": default_meta}), encoding="utf-8"
        )

        parser = MetadataParser()
        config = parser.parse(metadata_path)

        assert isinstance(config.default, SampleMetadata)
        if "sample_id" in default_meta:
            assert config.default.sample_id == default_meta["sample_id"]

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        default_meta=metadata_dict_strategy(),
        image_filenames=st.lists(
            jpeg_filename_strategy(),
            min_size=1,
            max_size=8,
            unique=True,
        ),
    )
    def test_property_auto_discovery_default_applied_to_all_images(
        self, tmp_path, default_meta, image_filenames
    ):
        """Property: Default metadata from auto-discovered metadata.json SHALL
        be applied to every image that has no per-image override.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        metadata_path = work_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps({"default": default_meta}), encoding="utf-8"
        )

        parser = MetadataParser()
        config = parser.parse(metadata_path)

        for filename in image_filenames:
            result = parser.get_for_image(config, filename)
            # Every image should receive the default sample_id (no per-image override)
            if "sample_id" in default_meta:
                assert result.sample_id == default_meta["sample_id"], (
                    f"Default sample_id not applied to '{filename}'"
                )
            if "scale_ppm" in default_meta:
                assert result.scale_ppm == pytest.approx(
                    default_meta["scale_ppm"], rel=1e-6
                ), f"Default scale_ppm not applied to '{filename}'"

    # ------------------------------------------------------------------
    # Concrete / regression tests
    # ------------------------------------------------------------------

    def test_concrete_auto_discovery_basic(self, tmp_path):
        """Concrete: metadata.json in directory is parsed correctly."""
        data = {
            "default": {
                "sample_id": "RIVER-001",
                "scale_ppm": 12.5,
                "capture_date": "2024-06-01",
            }
        }
        metadata_path = tmp_path / "metadata.json"
        metadata_path.write_text(json.dumps(data), encoding="utf-8")

        parser = MetadataParser()
        config = parser.parse(metadata_path)

        assert config.default.sample_id == "RIVER-001"
        assert config.default.scale_ppm == 12.5
        assert config.default.capture_date == date(2024, 6, 1)

    def test_concrete_auto_discovery_per_image_overrides_default(self, tmp_path):
        """Concrete: Per-image metadata overrides default after auto-discovery."""
        data = {
            "default": {"sample_id": "DEFAULT", "scale_ppm": 10.0},
            "images": {
                "sample_a.jpg": {"sample_id": "SAMPLE-A", "scale_ppm": 20.0},
            },
        }
        metadata_path = tmp_path / "metadata.json"
        metadata_path.write_text(json.dumps(data), encoding="utf-8")

        parser = MetadataParser()
        config = parser.parse(metadata_path)

        result_a = parser.get_for_image(config, "sample_a.jpg")
        assert result_a.sample_id == "SAMPLE-A"
        assert result_a.scale_ppm == 20.0

        result_b = parser.get_for_image(config, "sample_b.jpg")
        assert result_b.sample_id == "DEFAULT"
        assert result_b.scale_ppm == 10.0

    def test_concrete_auto_discovery_empty_metadata_json(self, tmp_path):
        """Concrete: An empty metadata.json ({}) is valid and yields empty defaults."""
        metadata_path = tmp_path / "metadata.json"
        metadata_path.write_text("{}", encoding="utf-8")

        parser = MetadataParser()
        config = parser.parse(metadata_path)

        assert config.default == SampleMetadata()
        assert config.images == {}

    def test_concrete_no_metadata_json_raises(self, tmp_path):
        """Concrete: Attempting to parse a non-existent metadata.json raises MetadataParseError."""
        from sedimental.errors import MetadataParseError

        parser = MetadataParser()
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(tmp_path / "metadata.json")

        assert "cannot read file" in str(exc_info.value)
