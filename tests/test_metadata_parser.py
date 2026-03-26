"""Tests for MetadataParser class.

Feature: sedimental-analysis-tool
Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.10, 5.11
"""

import json
import pytest
from datetime import date
from pathlib import Path

from sedimental.metadata import MetadataParser
from sedimental.models import MetadataConfig, SampleMetadata
from sedimental.errors import MetadataParseError


@pytest.fixture
def parser():
    return MetadataParser()


@pytest.fixture
def metadata_file(tmp_path):
    """Helper to write a metadata JSON file and return its path."""
    def _write(data: dict) -> Path:
        p = tmp_path / "metadata.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p
    return _write


class TestMetadataParserParse:
    """Tests for MetadataParser.parse()."""

    def test_parse_full_default_section(self, parser, metadata_file):
        path = metadata_file({
            "default": {
                "sample_id": "S001",
                "location": {"lat": 39.5, "lon": -106.5, "description": "Colorado River"},
                "capture_date": "2024-03-15",
                "scale_ppm": 12.5,
                "submitted_by": "researcher"
            }
        })
        config = parser.parse(path)
        m = config.default
        assert m.sample_id == "S001"
        assert m.location_lat == 39.5
        assert m.location_lon == -106.5
        assert m.location_description == "Colorado River"
        assert m.capture_date == date(2024, 3, 15)
        assert m.scale_ppm == 12.5
        assert m.submitted_by == "researcher"

    def test_parse_images_section(self, parser, metadata_file):
        path = metadata_file({
            "default": {"sample_id": "DEFAULT"},
            "images": {
                "img1.jpg": {"sample_id": "IMG1"},
                "img2.jpg": {"scale_ppm": 20.0}
            }
        })
        config = parser.parse(path)
        assert config.images["img1.jpg"].sample_id == "IMG1"
        assert config.images["img2.jpg"].scale_ppm == 20.0

    def test_parse_empty_object(self, parser, metadata_file):
        path = metadata_file({})
        config = parser.parse(path)
        assert config.default == SampleMetadata()
        assert config.images == {}

    def test_parse_custom_fields_captured(self, parser, metadata_file):
        path = metadata_file({
            "default": {"sample_id": "S1", "depth_m": 5, "notes": "test"}
        })
        config = parser.parse(path)
        assert config.default.custom_fields["depth_m"] == 5
        assert config.default.custom_fields["notes"] == "test"

    def test_parse_invalid_json_raises(self, parser, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(p)
        assert "invalid JSON" in str(exc_info.value)

    def test_parse_non_object_root_raises(self, parser, metadata_file):
        path = metadata_file([1, 2, 3])  # array, not object
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert "JSON object" in str(exc_info.value)

    def test_parse_missing_file_raises(self, parser, tmp_path):
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(tmp_path / "nonexistent.json")
        assert "cannot read file" in str(exc_info.value)

    def test_parse_invalid_default_type_raises(self, parser, metadata_file):
        path = metadata_file({"default": "not an object"})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert '"default"' in str(exc_info.value)

    def test_parse_invalid_images_type_raises(self, parser, metadata_file):
        path = metadata_file({"images": "not an object"})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert '"images"' in str(exc_info.value)

    def test_parse_invalid_image_entry_type_raises(self, parser, metadata_file):
        path = metadata_file({"images": {"img.jpg": "bad"}})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert "images.img.jpg" in str(exc_info.value)

    def test_parse_invalid_capture_date_raises(self, parser, metadata_file):
        path = metadata_file({"default": {"capture_date": "not-a-date"}})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert "capture_date" in str(exc_info.value)

    def test_parse_invalid_scale_ppm_zero_raises(self, parser, metadata_file):
        path = metadata_file({"default": {"scale_ppm": 0}})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert "scale_ppm" in str(exc_info.value)

    def test_parse_invalid_lat_out_of_range_raises(self, parser, metadata_file):
        path = metadata_file({"default": {"location": {"lat": 91.0}}})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert "lat" in str(exc_info.value)

    def test_parse_invalid_lon_out_of_range_raises(self, parser, metadata_file):
        path = metadata_file({"default": {"location": {"lon": 200.0}}})
        with pytest.raises(MetadataParseError) as exc_info:
            parser.parse(path)
        assert "lon" in str(exc_info.value)


class TestMetadataParserGetForImage:
    """Tests for MetadataParser.get_for_image()."""

    def test_returns_default_when_no_per_image_entry(self, parser):
        config = MetadataConfig(
            default=SampleMetadata(sample_id="DEFAULT"),
            images={}
        )
        result = parser.get_for_image(config, "img.jpg")
        assert result.sample_id == "DEFAULT"

    def test_per_image_overrides_default(self, parser):
        config = MetadataConfig(
            default=SampleMetadata(sample_id="DEFAULT", scale_ppm=10.0),
            images={"img.jpg": SampleMetadata(sample_id="OVERRIDE")}
        )
        result = parser.get_for_image(config, "img.jpg")
        assert result.sample_id == "OVERRIDE"
        assert result.scale_ppm == 10.0  # default preserved

    def test_default_preserved_for_unspecified_fields(self, parser):
        config = MetadataConfig(
            default=SampleMetadata(
                sample_id="S1",
                location_lat=39.5,
                capture_date=date(2024, 1, 1)
            ),
            images={"img.jpg": SampleMetadata(location_lat=40.0)}
        )
        result = parser.get_for_image(config, "img.jpg")
        assert result.location_lat == 40.0
        assert result.sample_id == "S1"
        assert result.capture_date == date(2024, 1, 1)

    def test_unknown_image_returns_default(self, parser):
        config = MetadataConfig(
            default=SampleMetadata(sample_id="DEFAULT"),
            images={"other.jpg": SampleMetadata(sample_id="OTHER")}
        )
        result = parser.get_for_image(config, "unknown.jpg")
        assert result.sample_id == "DEFAULT"

    def test_round_trip_parse_and_get(self, parser, tmp_path):
        """Parsing a file then getting per-image metadata should merge correctly."""
        data = {
            "default": {"sample_id": "BASE", "scale_ppm": 10.0},
            "images": {
                "sample1.jpg": {"sample_id": "S1", "scale_ppm": 20.0},
                "sample2.jpg": {"submitted_by": "alice"}
            }
        }
        p = tmp_path / "metadata.json"
        p.write_text(json.dumps(data), encoding="utf-8")

        config = parser.parse(p)

        m1 = parser.get_for_image(config, "sample1.jpg")
        assert m1.sample_id == "S1"
        assert m1.scale_ppm == 20.0

        m2 = parser.get_for_image(config, "sample2.jpg")
        assert m2.sample_id == "BASE"   # from default
        assert m2.scale_ppm == 10.0     # from default
        assert m2.submitted_by == "alice"
