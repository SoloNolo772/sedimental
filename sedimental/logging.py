"""Logging configuration for Sedimental."""

import logging
from pathlib import Path
from typing import Optional


def configure_logging(verbose: bool = False, log_file: Optional[Path] = None):
    """
    Configure logging for Sedimental.
    
    Args:
        verbose: If True, set level to DEBUG; otherwise INFO
        log_file: Optional path to write logs to a file
    
    Configures per-component log levels:
    - sedimental.cli: INFO (progress, summary)
    - sedimental.loader: WARNING (skipped files)
    - sedimental.segmentation: INFO (grain counts), WARNING (no grains)
    - sedimental.measurement: DEBUG (per-grain), WARNING (failures)
    - sedimental.output: INFO (file written)
    """
    # Set root level based on verbose flag
    level = logging.DEBUG if verbose else logging.INFO
    
    # Get root logger
    root = logging.getLogger()
    root.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    # Remove only our own handlers (StreamHandler and FileHandler) to avoid duplicates
    # but preserve any pytest handlers
    handlers_to_remove = []
    for handler in root.handlers:
        # Remove StreamHandler (but not subclasses like pytest's LogCaptureHandler)
        if type(handler) == logging.StreamHandler:
            handlers_to_remove.append(handler)
        # Remove FileHandler
        elif isinstance(handler, logging.FileHandler):
            handlers_to_remove.append(handler)
    
    for handler in handlers_to_remove:
        root.removeHandler(handler)
    
    # Add stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    
    # Configure per-component log levels
    logging.getLogger('sedimental.cli').setLevel(logging.INFO)
    logging.getLogger('sedimental.loader').setLevel(logging.WARNING)
    logging.getLogger('sedimental.segmentation').setLevel(logging.INFO)
    logging.getLogger('sedimental.measurement').setLevel(logging.DEBUG if verbose else logging.WARNING)
    logging.getLogger('sedimental.output').setLevel(logging.INFO)
