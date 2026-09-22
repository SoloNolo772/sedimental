"""Core data models for Sedimental Analysis Tool."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np


class MeasurementUnit(Enum):
    """Units for measurements."""
    PIXELS = "pixels"
    MILLIMETERS = "mm"


@dataclass
class SampleMetadata:
    """Metadata associated with a sediment sample."""
    sample_id: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    location_description: Optional[str] = None  # e.g., "Colorado River, Mile 42"
    capture_date: Optional[date] = None
    scale_ppm: Optional[float] = None  # pixels per millimeter
    submitted_by: Optional[str] = None  # user who submitted the job (self-reported)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def merge(self, override: 'SampleMetadata') -> 'SampleMetadata':
        """Merge with another metadata, override takes precedence."""
        return SampleMetadata(
            sample_id=override.sample_id if override.sample_id is not None else self.sample_id,
            location_lat=override.location_lat if override.location_lat is not None else self.location_lat,
            location_lon=override.location_lon if override.location_lon is not None else self.location_lon,
            location_description=override.location_description if override.location_description is not None else self.location_description,
            capture_date=override.capture_date if override.capture_date is not None else self.capture_date,
            scale_ppm=override.scale_ppm if override.scale_ppm is not None else self.scale_ppm,
            submitted_by=override.submitted_by if override.submitted_by is not None else self.submitted_by,
            custom_fields={**self.custom_fields, **override.custom_fields}
        )


@dataclass
class MetadataConfig:
    """Parsed metadata configuration from JSON."""
    default: SampleMetadata
    images: Dict[str, SampleMetadata]  # filename -> metadata


@dataclass
class GrainMeasurement:
    """Measurements for a single grain."""
    grain_id: int
    area: float
    perimeter: float
    circularity: float  # 4π×area/perimeter²
    roundness: float    # 4×area/(π×major_axis²)
    feret_diameter: float
    major_axis: float
    minor_axis: float
    unit: MeasurementUnit
    scale_factor: Optional[float]  # pixels per mm, if converted


@dataclass
class SegmentationResult:
    """Result of grain segmentation."""
    mask: np.ndarray  # (H, W) integer labels, 0 = background
    grain_count: int
    warnings: List[str] = field(default_factory=list)


@dataclass
class ImageResult:
    """Complete results for a single image."""
    source_file: str
    metadata: SampleMetadata
    measurements: List[GrainMeasurement]
    segmentation_mask_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)
    # Overlap-filter fields (populated only when the filter runs).
    overlap_filter_applied: bool = False
    original_grain_count: Optional[int] = None
    removed_overlap_ids: List[int] = field(default_factory=list)
    filtered_mask_path: Optional[Path] = None
    overlap_analysis_path: Optional[Path] = None


@dataclass
class ProcessingResult:
    """Result of processing a single image."""
    success: bool
    image_result: Optional[ImageResult] = None
    error: Optional[str] = None


@dataclass
class BatchResult:
    """Result of batch processing."""
    total_images: int
    successful: int
    failed: int
    results: List[ImageResult]
    errors: Dict[str, str]  # filename -> error message
