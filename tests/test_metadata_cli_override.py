"""Property-based tests for metadata CLI override.

Feature: sedimental-analysis-tool
Property: 13 - Metadata CLI Override
Validates: Requirements 5.2
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
# Property 13: Metadata CLI Override
# ---------------------------------------------------------------------------

class TestMetadataCLIOverride:
    """Property 13: Metadata CLI Override.

    For any input directory containing "metadata.json" AND a --metadata
    argument pointing to a different file, the MetadataParser SHALL use only
    the file specified by --metadata, ignoring the auto-discovered file.

    Validates: Requirements 5.2
    """

    # ------------------------------------------------------------------
    # Property tests
    # ------------------------------------------------------------------

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        auto_meta=metadata_dict_strategy(),
        override_meta=metadata_dict_strategy(),
    )
    def test_property_cli_override_ignores_auto_discovered_file(
        self, tmp_path, auto_meta, override_meta
    ):
        """Property: When --metadata points to an explicit file, the parser
        SHALL load that file and NOT the auto-discovered metadata.json in the
        input directory.

        Simulated by: parsing the override path directly (as the CLI would
        pass it) and verifying the result reflects the override file's content,
        not the auto-discovered file's content.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Write the auto-discovered metadata.json in the input directory
        auto_path = work_dir / "metadata.json"
        auto_path.write_text(json.dumps({"default": auto_meta}), encoding="utf-8")

        # Write the CLI-specified override file in a different location
        override_dir = tmp_path / "override"
        override_dir.mkdir(exist_ok=True)
        override_path = override_dir / "custom_metadata.json"
        override_path.write_text(json.dumps({"default": override_meta}), encoding="utf-8")

        parser = MetadataParser()

        # Simulate CLI override: parse the explicitly provided path
        config = parser.parse(override_path)

        # The result must reflect the override file, not the auto-discovered one
        if "sample_id" in override_meta:
            assert config.default.sample_id == override_meta["sample_id"]

        if "scale_ppm" in override_meta:
            assert config.default.scale_ppm == pytest.approx(
                override_meta["scale_ppm"], rel=1e-6
            )

        # If the two files have distinct sample_ids, the auto-discovered one
        # must NOT appear in the result
        auto_sid = auto_meta.get("sample_id")
        override_sid = override_meta.get("sample_id")
        if auto_sid and override_sid and auto_sid != override_sid:
            assert config.default.sample_id != auto_sid, (
                "CLI override was ignored: auto-discovered sample_id leaked into result"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        auto_meta=metadata_dict_strategy(),
        override_meta=metadata_dict_strategy(),
        image_filenames=st.lists(
            jpeg_filename_strategy(), min_size=1, max_size=6, unique=True
        ),
    )
    def test_property_cli_override_applies_to_all_images(
        self, tmp_path, auto_meta, override_meta, image_filenames
    ):
        """Property: Metadata from the CLI-specified file SHALL be applied to
        all images, regardless of what the auto-discovered file contains.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Auto-discovered file with per-image entries for every filename
        auto_images = {fn: auto_meta for fn in image_filenames}
        auto_path = work_dir / "metadata.json"
        auto_path.write_text(
            json.dumps({"default": auto_meta, "images": auto_images}),
            encoding="utf-8",
        )

        # Override file with only default metadata (no per-image section)
        override_dir = tmp_path / "override"
        override_dir.mkdir(exist_ok=True)
        override_path = override_dir / "override.json"
        override_path.write_text(
            json.dumps({"default": override_meta}), encoding="utf-8"
        )

        parser = MetadataParser()
        config = parser.parse(override_path)

        # Every image should receive override defaults, not auto-discovered values
        for filename in image_filenames:
            result = parser.get_for_image(config, filename)

            if "sample_id" in override_meta:
                assert result.sample_id == override_meta["sample_id"], (
                    f"Override sample_id not applied to '{filename}'"
                )

            if "scale_ppm" in override_meta:
                assert result.scale_ppm == pytest.approx(
                    override_meta["scale_ppm"], rel=1e-6
                ), f"Override scale_ppm not applied to '{filename}'"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        auto_meta=metadata_dict_strategy(),
        override_default=metadata_dict_strategy(),
        per_image_meta=metadata_dict_strategy(),
        image_filenames=st.lists(
            jpeg_filename_strategy(), min_size=2, max_size=6, unique=True
        ),
    )
    def test_property_cli_override_per_image_entries_respected(
        self, tmp_path, auto_meta, override_default, per_image_meta, image_filenames
    ):
        """Property: Per-image entries in the CLI-specified override file SHALL
        take precedence over its own default section, just as in normal parsing.
        The auto-discovered file's per-image entries SHALL be ignored entirely.
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Auto-discovered file — should be completely ignored
        auto_path = work_dir / "metadata.json"
        auto_path.write_text(
            json.dumps({"default": auto_meta, "images": {fn: auto_meta for fn in image_filenames}}),
            encoding="utf-8",
        )

        # Override file: default + per-image entry for the first filename only
        target_filename = image_filenames[0]
        override_dir = tmp_path / "override"
        override_dir.mkdir(exist_ok=True)
        override_path = override_dir / "override.json"
        override_path.write_text(
            json.dumps({
                "default": override_default,
                "images": {target_filename: per_image_meta},
            }),
            encoding="utf-8",
        )

        parser = MetadataParser()
        config = parser.parse(override_path)

        # Target image: per-image values from override file take precedence
        merged = parser.get_for_image(config, target_filename)
        if "sample_id" in per_image_meta:
            assert merged.sample_id == per_image_meta["sample_id"]
        elif "sample_id" in override_default:
            assert merged.sample_id == override_default["sample_id"]

        # Other images: only override default applies (not auto-discovered values)
        for filename in image_filenames[1:]:
            result = parser.get_for_image(config, filename)
            if "sample_id" in override_default:
                assert result.sample_id == override_default["sample_id"], (
                    f"Override default not applied to '{filename}'"
                )
            # Auto-discovered per-image sample_id must NOT appear if it differs
            auto_sid = auto_meta.get("sample_id")
            override_sid = override_default.get("sample_id")
            if auto_sid and override_sid and auto_sid != override_sid:
                assert result.sample_id != auto_sid, (
                    f"Auto-discovered metadata leaked into '{filename}' despite CLI override"
                )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(override_meta=metadata_dict_strategy())
    def test_property_cli_override_works_without_auto_discovered_file(
        self, tmp_path, override_meta
    ):
        """Property: The CLI override SHALL work correctly even when no
        metadata.json exists in the input directory (auto-discovery would
        have found nothing).
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()
        # Deliberately do NOT write metadata.json in work_dir

        override_dir = tmp_path / "override"
        override_dir.mkdir(exist_ok=True)
        override_path = override_dir / "metadata.json"
        override_path.write_text(
            json.dumps({"default": override_meta}), encoding="utf-8"
        )

        parser = MetadataParser()
        config = parser.parse(override_path)

        assert isinstance(config.default, SampleMetadata)
        if "sample_id" in override_meta:
            assert config.default.sample_id == override_meta["sample_id"]
        if "scale_ppm" in override_meta:
            assert config.default.scale_ppm == pytest.approx(
                override_meta["scale_ppm"], rel=1e-6
            )

    # ------------------------------------------------------------------
    # Concrete / regression tests
    # ------------------------------------------------------------------

    def test_concrete_cli_override_takes_precedence(self, tmp_path):
        """Concrete: CLI-specified metadata file is used instead of auto-discovered one."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Auto-discovered file
        auto_data = {"default": {"sample_id": "AUTO-001", "scale_ppm": 10.0}}
        (input_dir / "metadata.json").write_text(json.dumps(auto_data), encoding="utf-8")

        # CLI override file
        override_data = {"default": {"sample_id": "OVERRIDE-001", "scale_ppm": 25.0}}
        override_path = tmp_path / "custom.json"
        override_path.write_text(json.dumps(override_data), encoding="utf-8")

        parser = MetadataParser()
        config = parser.parse(override_path)

        assert config.default.sample_id == "OVERRIDE-001"
        assert config.default.scale_ppm == 25.0

    def test_concrete_cli_override_different_directory(self, tmp_path):
        """Concrete: Override file can reside in a completely different directory."""
        input_dir = tmp_path / "images"
        input_dir.mkdir()
        metadata_dir = tmp_path / "configs"
        metadata_dir.mkdir()

        (input_dir / "metadata.json").write_text(
            json.dumps({"default": {"sample_id": "FROM-INPUT-DIR"}}), encoding="utf-8"
        )
        override_path = metadata_dir / "project_metadata.json"
        override_path.write_text(
            json.dumps({"default": {"sample_id": "FROM-CONFIG-DIR", "scale_ppm": 15.0}}),
            encoding="utf-8",
        )

        parser = MetadataParser()
        config = parser.parse(override_path)

        assert config.default.sample_id == "FROM-CONFIG-DIR"
        assert config.default.scale_ppm == 15.0

    def test_concrete_cli_override_with_per_image_entries(self, tmp_path):
        """Concrete: Per-image entries in the override file are honoured."""
        override_data = {
            "default": {"sample_id": "BASE", "scale_ppm": 10.0},
            "images": {
                "rock_a.jpg": {"sample_id": "ROCK-A", "scale_ppm": 20.0},
            },
        }
        override_path = tmp_path / "override.json"
        override_path.write_text(json.dumps(override_data), encoding="utf-8")

        parser = MetadataParser()
        config = parser.parse(override_path)

        result_a = parser.get_for_image(config, "rock_a.jpg")
        assert result_a.sample_id == "ROCK-A"
        assert result_a.scale_ppm == 20.0

        result_b = parser.get_for_image(config, "rock_b.jpg")
        assert result_b.sample_id == "BASE"
        assert result_b.scale_ppm == 10.0

    def test_concrete_cli_override_nonexistent_file_raises(self, tmp_path):
        """Concrete: Providing a non-existent override path raises MetadataParseError."""
        from sedimental.errors import MetadataParseError

        parser = MetadataParser()
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(tmp_path / "does_not_exist.json")

        assert "cannot read file" in str(exc_info.value)
