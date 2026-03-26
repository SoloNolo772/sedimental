"""
Sedimental - Sediment grain analysis tool.

A Docker-first sediment analysis tool that automates the conversion of JPEG
images of sediment samples into quantitative grain measurements using
ImageGrains for segmentation and PyImageJ for particle analysis.
"""

__version__ = "1.0.0"
__author__ = "Sedimental Team"

from .errors import (
    SedimentalError,
    ImageError,
    InvalidImageError,
    UnsupportedFormatError,
    SegmentationError,
    MeasurementError,
    MetadataParseError,
    OutputError,
)
from .csv_writer import CSVWriter
from .logging import configure_logging
from .metadata import MetadataParser
from .orchestrator import ProcessingOrchestrator

__all__ = [
    "CSVWriter",
    "MetadataParser",
    "ProcessingOrchestrator",
    "SedimentalError",
    "ImageError",
    "InvalidImageError",
    "UnsupportedFormatError",
    "SegmentationError",
    "MeasurementError",
    "MetadataParseError",
    "OutputError",
    "configure_logging",
]
