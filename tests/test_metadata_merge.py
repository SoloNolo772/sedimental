"""Property-based tests for metadata merge precedence.

Feature: sedimental-analysis-tool
Property: 14 - Metadata Merge Precedence
Validates: Requirements 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10
"""

from datetime import date
from hypothesis import given, strategies as st
import pytest

from sedimental.models import SampleMetadata


# Hypothesis strategies for generating test data
@st.composite
def sample_metadata_strategy(draw):
    """Generate arbitrary SampleMetadata instances."""
    return SampleMetadata(
        sample_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        location_lat=draw(st.one_of(st.none(), st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False))),
        location_lon=draw(st.one_of(st.none(), st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False))),
        location_description=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        capture_date=draw(st.one_of(st.none(), st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))),
        scale_ppm=draw(st.one_of(st.none(), st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))),
        submitted_by=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        custom_fields=draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(), st.integers(), st.floats(allow_nan=False, allow_infinity=False)),
            max_size=5
        ))
    )


class TestMetadataMergePrecedence:
    """Test suite for Property 14: Metadata Merge Precedence."""

    @given(default=sample_metadata_strategy(), override=sample_metadata_strategy())
    def test_override_fields_take_precedence(self, default, override):
        """
        Property: Fields present in override SHALL override corresponding fields in default.
        
        For any field that is non-None in override, the merged result should have
        that field value from override, not from default.
        """
        merged = default.merge(override)
        
        # Check each field - if override has a value, merged should use it
        if override.sample_id is not None:
            assert merged.sample_id == override.sample_id
        
        if override.location_lat is not None:
            assert merged.location_lat == override.location_lat
        
        if override.location_lon is not None:
            assert merged.location_lon == override.location_lon
        
        if override.location_description is not None:
            assert merged.location_description == override.location_description
        
        if override.capture_date is not None:
            assert merged.capture_date == override.capture_date
        
        if override.scale_ppm is not None:
            assert merged.scale_ppm == override.scale_ppm
        
        if override.submitted_by is not None:
            assert merged.submitted_by == override.submitted_by

    @given(default=sample_metadata_strategy(), override=sample_metadata_strategy())
    def test_default_fields_preserved_when_override_is_none(self, default, override):
        """
        Property: Fields present only in default SHALL be preserved.
        
        For any field that is None in override but non-None in default,
        the merged result should have the default value.
        """
        merged = default.merge(override)
        
        # Check each field - if override is None, merged should use default
        if override.sample_id is None and default.sample_id is not None:
            assert merged.sample_id == default.sample_id
        
        if override.location_lat is None and default.location_lat is not None:
            assert merged.location_lat == default.location_lat
        
        if override.location_lon is None and default.location_lon is not None:
            assert merged.location_lon == default.location_lon
        
        if override.location_description is None and default.location_description is not None:
            assert merged.location_description == default.location_description
        
        if override.capture_date is None and default.capture_date is not None:
            assert merged.capture_date == default.capture_date
        
        if override.scale_ppm is None and default.scale_ppm is not None:
            assert merged.scale_ppm == default.scale_ppm
        
        if override.submitted_by is None and default.submitted_by is not None:
            assert merged.submitted_by == default.submitted_by

    @given(default=sample_metadata_strategy(), override=sample_metadata_strategy())
    def test_custom_fields_merged_correctly(self, default, override):
        """
        Property: Custom fields from both default and override SHALL be included,
        with override values taking precedence for duplicate keys.
        """
        merged = default.merge(override)
        
        # All keys from default should be present unless overridden
        for key, value in default.custom_fields.items():
            assert key in merged.custom_fields
            if key in override.custom_fields:
                # Override value should win
                assert merged.custom_fields[key] == override.custom_fields[key]
            else:
                # Default value should be preserved
                assert merged.custom_fields[key] == value
        
        # All keys from override should be present
        for key, value in override.custom_fields.items():
            assert key in merged.custom_fields
            assert merged.custom_fields[key] == value

    @given(default=sample_metadata_strategy(), override=sample_metadata_strategy())
    def test_merge_idempotence(self, default, override):
        """
        Property: The merge operation SHALL be idempotent.
        
        merge(D, merge(D, I)) == merge(D, I)
        
        Merging the same override twice should produce the same result as merging once.
        """
        merged_once = default.merge(override)
        merged_twice = default.merge(merged_once)
        
        # Both results should be identical
        assert merged_once.sample_id == merged_twice.sample_id
        assert merged_once.location_lat == merged_twice.location_lat
        assert merged_once.location_lon == merged_twice.location_lon
        assert merged_once.location_description == merged_twice.location_description
        assert merged_once.capture_date == merged_twice.capture_date
        assert merged_once.scale_ppm == merged_twice.scale_ppm
        assert merged_once.submitted_by == merged_twice.submitted_by
        assert merged_once.custom_fields == merged_twice.custom_fields

    @given(metadata=sample_metadata_strategy())
    def test_merge_with_empty_override_returns_default(self, metadata):
        """
        Property: Merging with an empty override (all None) should return the default values.
        """
        empty_override = SampleMetadata()
        merged = metadata.merge(empty_override)
        
        assert merged.sample_id == metadata.sample_id
        assert merged.location_lat == metadata.location_lat
        assert merged.location_lon == metadata.location_lon
        assert merged.location_description == metadata.location_description
        assert merged.capture_date == metadata.capture_date
        assert merged.scale_ppm == metadata.scale_ppm
        assert merged.submitted_by == metadata.submitted_by
        # Custom fields from default should be preserved
        for key, value in metadata.custom_fields.items():
            assert merged.custom_fields[key] == value

    @given(metadata=sample_metadata_strategy())
    def test_empty_default_with_override_returns_override(self, metadata):
        """
        Property: Merging an empty default with an override should return the override values.
        """
        empty_default = SampleMetadata()
        merged = empty_default.merge(metadata)
        
        assert merged.sample_id == metadata.sample_id
        assert merged.location_lat == metadata.location_lat
        assert merged.location_lon == metadata.location_lon
        assert merged.location_description == metadata.location_description
        assert merged.capture_date == metadata.capture_date
        assert merged.scale_ppm == metadata.scale_ppm
        assert merged.submitted_by == metadata.submitted_by
        assert merged.custom_fields == metadata.custom_fields

    def test_concrete_example_override_precedence(self):
        """Concrete example: Override values should take precedence over defaults."""
        default = SampleMetadata(
            sample_id="default_sample",
            location_lat=40.0,
            location_lon=-105.0,
            scale_ppm=10.0,
            custom_fields={"site": "A", "depth": 5}
        )
        
        override = SampleMetadata(
            sample_id="override_sample",
            location_lat=41.0,
            custom_fields={"site": "B", "temperature": 20}
        )
        
        merged = default.merge(override)
        
        # Override values should win
        assert merged.sample_id == "override_sample"
        assert merged.location_lat == 41.0
        
        # Default values preserved where override is None
        assert merged.location_lon == -105.0
        assert merged.scale_ppm == 10.0
        
        # Custom fields merged with override precedence
        assert merged.custom_fields["site"] == "B"  # Override wins
        assert merged.custom_fields["depth"] == 5  # Default preserved
        assert merged.custom_fields["temperature"] == 20  # Override added

    def test_concrete_example_partial_override(self):
        """Concrete example: Partial override should preserve unspecified defaults."""
        default = SampleMetadata(
            sample_id="SAMPLE001",
            location_lat=39.5,
            location_lon=-106.5,
            location_description="Colorado River",
            capture_date=date(2024, 1, 15),
            scale_ppm=12.5,
            submitted_by="researcher@example.com"
        )
        
        # Override only location
        override = SampleMetadata(
            location_lat=39.6,
            location_lon=-106.6
        )
        
        merged = default.merge(override)
        
        # Overridden fields
        assert merged.location_lat == 39.6
        assert merged.location_lon == -106.6
        
        # Preserved fields
        assert merged.sample_id == "SAMPLE001"
        assert merged.location_description == "Colorado River"
        assert merged.capture_date == date(2024, 1, 15)
        assert merged.scale_ppm == 12.5
        assert merged.submitted_by == "researcher@example.com"
