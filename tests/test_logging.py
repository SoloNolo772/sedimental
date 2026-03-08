"""Tests for logging configuration."""

import logging
import pytest
from pathlib import Path
from sedimental.logging import configure_logging


class TestConfigureLogging:
    """Unit tests for configure_logging function."""
    
    def setup_method(self):
        """Reset logging configuration before each test."""
        # Clear all handlers and reset to default state
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
    
    def test_default_configuration(self):
        """Test logging with default settings (verbose=False, no log file)."""
        configure_logging()
        
        root = logging.getLogger()
        assert root.level == logging.INFO
        # Check we have at least one StreamHandler (may have pytest handlers too)
        stream_handlers = [h for h in root.handlers if type(h) == logging.StreamHandler]
        assert len(stream_handlers) >= 1
    
    def test_verbose_mode(self):
        """Test logging with verbose=True sets DEBUG level."""
        configure_logging(verbose=True)
        
        root = logging.getLogger()
        assert root.level == logging.DEBUG
    
    def test_log_file_handler(self, tmp_path):
        """Test logging with log file creates file handler."""
        log_file = tmp_path / "test.log"
        configure_logging(log_file=log_file)
        
        root = logging.getLogger()
        # Check we have both StreamHandler and FileHandler (may have pytest handlers too)
        stream_handlers = [h for h in root.handlers if type(h) == logging.StreamHandler]
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) >= 1
        assert len(file_handlers) >= 1
    
    def test_log_file_and_verbose(self, tmp_path):
        """Test logging with both verbose and log file."""
        log_file = tmp_path / "test.log"
        configure_logging(verbose=True, log_file=log_file)
        
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        # Check we have both StreamHandler and FileHandler (may have pytest handlers too)
        stream_handlers = [h for h in root.handlers if type(h) == logging.StreamHandler]
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) >= 1
        assert len(file_handlers) >= 1
    
    def test_log_format(self):
        """Test that log format includes timestamp, level, name, and message."""
        configure_logging()
        
        root = logging.getLogger()
        # Find our StreamHandler (not pytest's handlers)
        our_handler = None
        for handler in root.handlers:
            if type(handler) == logging.StreamHandler:
                our_handler = handler
                break
        
        assert our_handler is not None
        formatter = our_handler.formatter
        
        # Check format string contains expected components
        assert formatter is not None
        format_str = formatter._fmt
        assert '%(asctime)s' in format_str
        assert '%(levelname)s' in format_str
        assert '%(name)s' in format_str
        assert '%(message)s' in format_str
    
    def test_component_log_levels_default(self):
        """Test per-component log levels with verbose=False."""
        configure_logging(verbose=False)
        
        assert logging.getLogger('sedimental.cli').level == logging.INFO
        assert logging.getLogger('sedimental.loader').level == logging.WARNING
        assert logging.getLogger('sedimental.segmentation').level == logging.INFO
        assert logging.getLogger('sedimental.measurement').level == logging.WARNING
        assert logging.getLogger('sedimental.output').level == logging.INFO
    
    def test_component_log_levels_verbose(self):
        """Test per-component log levels with verbose=True."""
        configure_logging(verbose=True)
        
        # Most components stay the same
        assert logging.getLogger('sedimental.cli').level == logging.INFO
        assert logging.getLogger('sedimental.loader').level == logging.WARNING
        assert logging.getLogger('sedimental.segmentation').level == logging.INFO
        assert logging.getLogger('sedimental.output').level == logging.INFO
        
        # Measurement component changes to DEBUG in verbose mode
        assert logging.getLogger('sedimental.measurement').level == logging.DEBUG
    
    def test_log_file_is_created(self, tmp_path):
        """Test that log file is actually created when logging occurs."""
        log_file = tmp_path / "test.log"
        configure_logging(log_file=log_file)
        
        # Write a log message
        logger = logging.getLogger('sedimental.cli')
        logger.info("Test message")
        
        # Flush handlers to ensure write
        for handler in logging.getLogger().handlers:
            handler.flush()
        
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content
        assert "[INFO]" in content
        assert "sedimental.cli" in content
    
    def test_reconfiguration_overrides_previous(self, tmp_path):
        """Test that calling configure_logging again overrides previous config."""
        # First configuration
        configure_logging(verbose=False)
        assert logging.getLogger().level == logging.INFO
        
        # Second configuration
        configure_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG
    
    def test_console_and_file_both_receive_logs(self, tmp_path, caplog):
        """Test that logs are written to both console and file when both are configured."""
        log_file = tmp_path / "test.log"
        configure_logging(log_file=log_file)
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger('sedimental.cli')
            logger.info("Test message")
        
        # Flush handlers
        for handler in logging.getLogger().handlers:
            handler.flush()
        
        # Check file
        assert log_file.exists()
        file_content = log_file.read_text()
        assert "Test message" in file_content
        
        # Check console (caplog)
        assert "Test message" in caplog.text


class TestLoggingBehavior:
    """Integration tests for logging behavior."""
    
    def setup_method(self):
        """Reset logging configuration before each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
    
    def test_cli_logger_info_messages(self, caplog):
        """Test that CLI logger outputs INFO messages."""
        configure_logging()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger('sedimental.cli')
            logger.info("Processing started")
        
        assert "Processing started" in caplog.text
    
    def test_loader_logger_filters_info(self, caplog):
        """Test that loader logger filters out INFO messages (WARNING level)."""
        configure_logging()
        
        with caplog.at_level(logging.DEBUG):
            logger = logging.getLogger('sedimental.loader')
            logger.info("This should not appear")
            logger.warning("This should appear")
        
        assert "This should not appear" not in caplog.text
        assert "This should appear" in caplog.text
    
    def test_measurement_logger_debug_in_verbose(self, caplog):
        """Test that measurement logger outputs DEBUG in verbose mode."""
        configure_logging(verbose=True)
        
        with caplog.at_level(logging.DEBUG):
            logger = logging.getLogger('sedimental.measurement')
            logger.debug("Per-grain measurement")
        
        assert "Per-grain measurement" in caplog.text
    
    def test_measurement_logger_no_debug_in_normal(self, caplog):
        """Test that measurement logger filters DEBUG in normal mode."""
        configure_logging(verbose=False)
        
        with caplog.at_level(logging.DEBUG):
            logger = logging.getLogger('sedimental.measurement')
            logger.debug("This should not appear")
            logger.warning("This should appear")
        
        assert "This should not appear" not in caplog.text
        assert "This should appear" in caplog.text
    
    def test_segmentation_logger_info_and_warning(self, caplog):
        """Test that segmentation logger outputs both INFO and WARNING."""
        configure_logging()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger('sedimental.segmentation')
            logger.info("Found 42 grains")
            logger.warning("No grains detected")
        
        assert "Found 42 grains" in caplog.text
        assert "No grains detected" in caplog.text
    
    def test_output_logger_info_messages(self, caplog):
        """Test that output logger outputs INFO messages."""
        configure_logging()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger('sedimental.output')
            logger.info("File written: results.csv")
        
        assert "File written: results.csv" in caplog.text
