"""
Error hierarchy for Sedimental analysis tool.

This module defines all custom exceptions used throughout the application,
organized in a hierarchy for granular error handling.
"""

from typing import Optional


class SedimentalError(Exception):
    """Base exception for all Sedimental errors."""
    pass


class ImageError(SedimentalError):
    """Errors related to image loading and validation."""
    pass


class InvalidImageError(ImageError):
    """Raised when an image file is corrupted or invalid."""
    
    def __init__(self, filename: str, reason: str):
        self.filename = filename
        self.reason = reason
        super().__init__(f"Invalid image '{filename}': {reason}")


class UnsupportedFormatError(ImageError):
    """Raised when a file is not a supported image format."""
    
    def __init__(self, filename: str, detected_format: str):
        self.filename = filename
        self.detected_format = detected_format
        super().__init__(
            f"Unsupported format '{detected_format}' for file '{filename}'"
        )


class SegmentationError(SedimentalError):
    """Errors during grain segmentation."""
    
    def __init__(self, filename: str, reason: str):
        self.filename = filename
        self.reason = reason
        super().__init__(f"Segmentation failed for '{filename}': {reason}")


class MeasurementError(SedimentalError):
    """Errors during particle measurement."""
    
    def __init__(self, filename: str, grain_id: Optional[int], reason: str):
        self.filename = filename
        self.grain_id = grain_id
        self.reason = reason
        grain_info = f" grain {grain_id}" if grain_id is not None else ""
        super().__init__(
            f"Measurement failed for '{filename}'{grain_info}: {reason}"
        )


class MetadataParseError(SedimentalError):
    """Errors parsing metadata JSON."""
    
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to parse metadata '{path}': {reason}")


class OutputError(SedimentalError):
    """Errors writing output files."""
    pass
