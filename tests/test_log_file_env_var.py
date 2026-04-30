"""
Tests for SEDIMENTAL_LOG_FILE environment variable handling.

This module contains two types of tests:

Property 1: Bug Condition - Log File Not Created When Env Var Set
- CRITICAL: These tests MUST FAIL on unfixed code - failure confirms the bug exists
- DO NOT attempt to fix the test or the code when it fails
- These tests encode the expected behavior - they will validate the fix when they pass
- Requirements tested: 1.1, 1.2, 1.3

Property 2: Preservation - Behavior Without Env Var Unchanged
- These tests verify that existing behavior is preserved when SEDIMENTAL_LOG_FILE is NOT set
- EXPECTED: Tests PASS on both unfixed and fixed code (confirms no regressions)
- Requirements tested: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import logging
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, strategies as st


class TestBugConditionExploration:
    """
    Bug condition exploration tests.
    
    These tests demonstrate the bug where SEDIMENTAL_LOG_FILE environment
    variable is set but the application does not create a log file.
    
    EXPECTED OUTCOME: Tests FAIL on unfixed code (this proves the bug exists)
    """
    
    def setup_method(self):
        """Reset logging configuration before each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
    
    def teardown_method(self):
        """Clean up logging handlers after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
            root.removeHandler(handler)
    
    def test_cli_creates_log_file_when_env_var_set(self, tmp_path, monkeypatch):
        """
        Bug Condition Test: CLI should create log file when SEDIMENTAL_LOG_FILE is set.
        
        This test verifies requirement 1.1:
        WHEN SEDIMENTAL_LOG_FILE environment variable is set
        AND the CLI process command is executed
        THEN the system SHALL create a log file at the specified path
        
        EXPECTED: Test FAILS on unfixed code (bug condition confirmed)
        Counterexample: Log file is not created when SEDIMENTAL_LOG_FILE is set
        """
        # Arrange: Set up environment variable pointing to a log file in tmp_path
        log_file_path = tmp_path / "sedimental.log"
        monkeypatch.setenv("SEDIMENTAL_LOG_FILE", str(log_file_path))
        monkeypatch.setenv("SEDIMENTAL_INSIDE_CONTAINER", "1")
        
        # Create a minimal valid input file
        input_file = tmp_path / "input.jpg"
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (10, 8), color=(100, 150, 200))
        img.save(buf, format="JPEG")
        input_file.write_bytes(buf.getvalue())
        
        output_file = tmp_path / "results.csv"
        
        # Act: Import and call run_process_internal
        # We mock the orchestrator to avoid slow image processing
        from sedimental.cli import run_process_internal
        from sedimental.models import BatchResult
        import argparse
        
        args = argparse.Namespace(
            input=str(input_file),
            output=str(output_file),
            metadata=None,
            save_masks=False,
            verbose=False,
        )
        
        # Mock the orchestrator to return quickly
        mock_batch_result = BatchResult(
            total_images=1,
            successful=1,
            failed=0,
            results=[],
            errors={},
        )
        
        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_instance.process_batch.return_value = mock_batch_result
            
            # Run the CLI process
            run_process_internal(args)
        
        # Assert: Log file should exist (this will FAIL on unfixed code)
        assert log_file_path.exists(), (
            f"Bug confirmed: Log file was NOT created at {log_file_path} "
            f"even though SEDIMENTAL_LOG_FILE was set. "
            f"The CLI does not read the SEDIMENTAL_LOG_FILE environment variable."
        )
    
    def test_cli_log_file_contains_entries_when_env_var_set(self, tmp_path, monkeypatch):
        """
        Bug Condition Test: CLI should write logs to file when SEDIMENTAL_LOG_FILE is set.
        
        This test verifies that logs are actually written to the file, not just that
        the file is created.
        
        EXPECTED: Test FAILS on unfixed code (bug condition confirmed)
        """
        # Arrange
        log_file_path = tmp_path / "sedimental.log"
        monkeypatch.setenv("SEDIMENTAL_LOG_FILE", str(log_file_path))
        monkeypatch.setenv("SEDIMENTAL_INSIDE_CONTAINER", "1")
        
        # Create a minimal valid input file
        input_file = tmp_path / "input.jpg"
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (10, 8), color=(100, 150, 200))
        img.save(buf, format="JPEG")
        input_file.write_bytes(buf.getvalue())
        
        output_file = tmp_path / "results.csv"
        
        # Act
        from sedimental.cli import run_process_internal
        from sedimental.models import BatchResult
        import argparse
        
        args = argparse.Namespace(
            input=str(input_file),
            output=str(output_file),
            metadata=None,
            save_masks=False,
            verbose=False,
        )
        
        # Mock the orchestrator to return quickly but emit a log message
        mock_batch_result = BatchResult(
            total_images=1,
            successful=1,
            failed=0,
            results=[],
            errors={},
        )
        
        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_instance.process_batch.return_value = mock_batch_result
            
            run_process_internal(args)
            
            # Emit a log message to verify file logging works
            test_logger = logging.getLogger("sedimental.test")
            test_logger.info("Test log entry to verify file logging")
        
        # Flush all handlers
        for handler in logging.getLogger().handlers:
            handler.flush()
        
        # Assert: Log file should exist and contain log entries
        assert log_file_path.exists(), (
            f"Bug confirmed: Log file was NOT created at {log_file_path}"
        )
        
        content = log_file_path.read_text()
        assert len(content) > 0, (
            f"Bug confirmed: Log file exists but is empty at {log_file_path}"
        )
        assert "Test log entry" in content, (
            f"Bug confirmed: Log file exists but test log entry not found. Content: {content}"
        )
    
    def test_web_server_configures_logging_with_env_var(self, tmp_path, monkeypatch):
        """
        Bug Condition Test: Web server should call configure_logging with log file.
        
        This test verifies requirements 1.2 and 1.3:
        WHEN SEDIMENTAL_LOG_FILE environment variable is set
        AND the web server is started
        THEN the system SHALL call configure_logging() with the log file path
        
        EXPECTED: Test FAILS on unfixed code (bug condition confirmed)
        Counterexample: configure_logging() is not called with log_file parameter
        """
        # Arrange
        log_file_path = tmp_path / "sedimental.log"
        monkeypatch.setenv("SEDIMENTAL_LOG_FILE", str(log_file_path))
        
        # Track calls to configure_logging
        configure_logging_calls = []
        
        from sedimental import logging as sedimental_logging
        from sedimental import web
        original_configure_logging = sedimental_logging.configure_logging
        
        def mock_configure_logging(*args, **kwargs):
            configure_logging_calls.append({'args': args, 'kwargs': kwargs})
            # Call the original to actually configure logging
            return original_configure_logging(*args, **kwargs)
        
        # Act: Patch configure_logging on the web module where it's imported
        with patch.object(web, 'configure_logging', mock_configure_logging):
            with patch('uvicorn.run') as mock_uvicorn:
                with patch('sys.argv', ['web', '--port', '8080']):
                    web.main()
        
        # Assert: configure_logging should have been called with log_file parameter
        assert len(configure_logging_calls) > 0, (
            "Bug confirmed: configure_logging() was never called by web server main(). "
            "The web server does not configure logging at all (Requirement 1.3)."
        )
        
        # Check if any call included the log_file parameter
        log_file_configured = any(
            call['kwargs'].get('log_file') is not None 
            for call in configure_logging_calls
        )
        
        assert log_file_configured, (
            f"Bug confirmed: configure_logging() was called but without log_file parameter. "
            f"Calls received: {configure_logging_calls}. "
            f"The web server does not read SEDIMENTAL_LOG_FILE environment variable (Requirement 1.2)."
        )
    
    def test_web_server_creates_log_file_when_env_var_set(self, tmp_path, monkeypatch):
        """
        Bug Condition Test: Web server should create log file when SEDIMENTAL_LOG_FILE is set.
        
        This test verifies requirement 1.2:
        WHEN SEDIMENTAL_LOG_FILE environment variable is set
        AND the web server is started
        THEN the system SHALL create a log file at the specified path
        
        EXPECTED: Test FAILS on unfixed code (bug condition confirmed)
        """
        # Arrange
        log_file_path = tmp_path / "sedimental.log"
        monkeypatch.setenv("SEDIMENTAL_LOG_FILE", str(log_file_path))
        
        # Act: Call main() with mocked uvicorn to prevent actual server start
        from sedimental import web
        
        with patch('uvicorn.run') as mock_uvicorn:
            with patch('sys.argv', ['web', '--port', '8080']):
                web.main()
        
        # Assert: Log file should exist
        assert log_file_path.exists(), (
            f"Bug confirmed: Log file was NOT created at {log_file_path} "
            f"even though SEDIMENTAL_LOG_FILE was set. "
            f"The web server does not read the SEDIMENTAL_LOG_FILE environment variable."
        )


class TestPreservationWithoutEnvVar:
    """
    Preservation property tests.
    
    These tests verify that existing behavior is preserved when SEDIMENTAL_LOG_FILE
    is NOT set. They should PASS on both unfixed and fixed code.
    
    Property 2: Preservation - Behavior Without Env Var Unchanged
    
    EXPECTED OUTCOME: Tests PASS on unfixed code (confirms baseline behavior to preserve)
    
    Requirements tested: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
    """
    
    def setup_method(self):
        """Reset logging configuration before each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
    
    def teardown_method(self):
        """Clean up logging handlers after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
            root.removeHandler(handler)
    
    def test_cli_logs_to_stdout_without_env_var(self, tmp_path, monkeypatch, capsys):
        """
        Preservation Test: CLI should log to stdout when SEDIMENTAL_LOG_FILE is NOT set.
        
        This test verifies requirement 3.1:
        WHEN SEDIMENTAL_LOG_FILE is not set
        AND the CLI is executed
        THEN the system SHALL CONTINUE TO log only to stdout without errors
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        # Arrange: Ensure SEDIMENTAL_LOG_FILE is NOT set
        monkeypatch.delenv("SEDIMENTAL_LOG_FILE", raising=False)
        monkeypatch.setenv("SEDIMENTAL_INSIDE_CONTAINER", "1")
        
        # Create a minimal valid input file
        input_file = tmp_path / "input.jpg"
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (10, 8), color=(100, 150, 200))
        img.save(buf, format="JPEG")
        input_file.write_bytes(buf.getvalue())
        
        output_file = tmp_path / "results.csv"
        
        # Act
        from sedimental.cli import run_process_internal
        from sedimental.models import BatchResult
        import argparse
        
        args = argparse.Namespace(
            input=str(input_file),
            output=str(output_file),
            metadata=None,
            save_masks=False,
            verbose=False,
        )
        
        mock_batch_result = BatchResult(
            total_images=1,
            successful=1,
            failed=0,
            results=[],
            errors={},
        )
        
        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_instance.process_batch.return_value = mock_batch_result
            
            exit_code = run_process_internal(args)
        
        # Assert: CLI should complete without errors and log to stdout
        captured = capsys.readouterr()
        assert exit_code == 0, "CLI should return exit code 0 for successful processing"
        assert "Processing complete" in captured.out, "CLI should print success message to stdout"
        
        # Verify no file handlers were added (only stdout logging)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0, "No file handlers should be added when env var is not set"
    
    def test_cli_returns_exit_code_0_on_success_without_env_var(self, tmp_path, monkeypatch):
        """
        Preservation Test: CLI should return exit code 0 on success.
        
        This test verifies requirement 3.4:
        WHEN the CLI processes images successfully
        THEN the system SHALL CONTINUE TO return exit code 0
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        # Arrange
        monkeypatch.delenv("SEDIMENTAL_LOG_FILE", raising=False)
        monkeypatch.setenv("SEDIMENTAL_INSIDE_CONTAINER", "1")
        
        input_file = tmp_path / "input.jpg"
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (10, 8), color=(100, 150, 200))
        img.save(buf, format="JPEG")
        input_file.write_bytes(buf.getvalue())
        
        output_file = tmp_path / "results.csv"
        
        # Act
        from sedimental.cli import run_process_internal
        from sedimental.models import BatchResult
        import argparse
        
        args = argparse.Namespace(
            input=str(input_file),
            output=str(output_file),
            metadata=None,
            save_masks=False,
            verbose=False,
        )
        
        mock_batch_result = BatchResult(
            total_images=1,
            successful=1,
            failed=0,
            results=[],
            errors={},
        )
        
        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_instance.process_batch.return_value = mock_batch_result
            
            exit_code = run_process_internal(args)
        
        # Assert
        assert exit_code == 0, "CLI should return exit code 0 for successful processing"
    
    def test_cli_returns_exit_code_1_on_failure_without_env_var(self, tmp_path, monkeypatch, capsys):
        """
        Preservation Test: CLI should return exit code 1 on total failure.
        
        This test verifies requirement 3.4 (exit codes preserved):
        WHEN all images fail to process
        THEN the system SHALL CONTINUE TO return exit code 1
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        # Arrange
        monkeypatch.delenv("SEDIMENTAL_LOG_FILE", raising=False)
        monkeypatch.setenv("SEDIMENTAL_INSIDE_CONTAINER", "1")
        
        input_file = tmp_path / "input.jpg"
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (10, 8), color=(100, 150, 200))
        img.save(buf, format="JPEG")
        input_file.write_bytes(buf.getvalue())
        
        output_file = tmp_path / "results.csv"
        
        # Act
        from sedimental.cli import run_process_internal
        from sedimental.models import BatchResult
        import argparse
        
        args = argparse.Namespace(
            input=str(input_file),
            output=str(output_file),
            metadata=None,
            save_masks=False,
            verbose=False,
        )
        
        # Mock total failure
        mock_batch_result = BatchResult(
            total_images=1,
            successful=0,
            failed=1,
            results=[],
            errors={"input.jpg": "Processing failed"},
        )
        
        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_instance.process_batch.return_value = mock_batch_result
            
            exit_code = run_process_internal(args)
        
        # Assert
        assert exit_code == 1, "CLI should return exit code 1 for total failure"
        captured = capsys.readouterr()
        assert "Error" in captured.err, "CLI should print error message to stderr"
    
    def test_verbose_flag_sets_debug_level_without_env_var(self, tmp_path, monkeypatch):
        """
        Preservation Test: --verbose flag should set DEBUG log level.
        
        This test verifies requirement 3.3:
        WHEN the --verbose flag is passed to the CLI
        THEN the system SHALL CONTINUE TO set the log level to DEBUG
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        # Arrange
        monkeypatch.delenv("SEDIMENTAL_LOG_FILE", raising=False)
        monkeypatch.setenv("SEDIMENTAL_INSIDE_CONTAINER", "1")
        
        input_file = tmp_path / "input.jpg"
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (10, 8), color=(100, 150, 200))
        img.save(buf, format="JPEG")
        input_file.write_bytes(buf.getvalue())
        
        output_file = tmp_path / "results.csv"
        
        # Act
        from sedimental.cli import run_process_internal
        from sedimental.models import BatchResult
        import argparse
        
        args = argparse.Namespace(
            input=str(input_file),
            output=str(output_file),
            metadata=None,
            save_masks=False,
            verbose=True,  # Enable verbose mode
        )
        
        mock_batch_result = BatchResult(
            total_images=1,
            successful=1,
            failed=0,
            results=[],
            errors={},
        )
        
        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_instance.process_batch.return_value = mock_batch_result
            
            run_process_internal(args)
        
        # Assert: Root logger should be at DEBUG level
        root = logging.getLogger()
        assert root.level == logging.DEBUG, "Verbose flag should set root logger to DEBUG level"
    
    def test_configure_logging_works_without_log_file(self):
        """
        Preservation Test: configure_logging() should work without log_file argument.
        
        This test verifies requirement 3.6:
        WHEN configure_logging() is called with only the verbose parameter
        THEN the system SHALL CONTINUE TO work without requiring a log_file argument
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        from sedimental.logging import configure_logging
        
        # Act: Call configure_logging with only verbose parameter (no log_file)
        # This should not raise any exceptions
        configure_logging(verbose=False)
        
        # Assert: Logging should be configured correctly
        root = logging.getLogger()
        assert root.level == logging.INFO, "Default log level should be INFO"
        
        # Verify we have a stream handler
        stream_handlers = [h for h in root.handlers if type(h) == logging.StreamHandler]
        assert len(stream_handlers) >= 1, "Should have at least one stream handler"
        
        # Verify no file handlers
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0, "Should have no file handlers when log_file not specified"
    
    def test_configure_logging_verbose_true_without_log_file(self):
        """
        Preservation Test: configure_logging(verbose=True) should work without log_file.
        
        This test verifies requirement 3.6:
        WHEN configure_logging() is called with verbose=True and no log_file
        THEN the system SHALL CONTINUE TO work correctly
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        from sedimental.logging import configure_logging
        
        # Act
        configure_logging(verbose=True)
        
        # Assert
        root = logging.getLogger()
        assert root.level == logging.DEBUG, "Verbose mode should set DEBUG level"
        
        # Verify no file handlers
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0, "Should have no file handlers when log_file not specified"
    
    def test_web_server_health_endpoint_responds_without_env_var(self, monkeypatch):
        """
        Preservation Test: Web server health endpoints should respond correctly.
        
        This test verifies requirement 3.5:
        WHEN the web server receives health check requests
        THEN the system SHALL CONTINUE TO respond correctly
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        # Arrange
        monkeypatch.delenv("SEDIMENTAL_LOG_FILE", raising=False)
        
        from sedimental.web import create_app
        from fastapi.testclient import TestClient
        
        app = create_app()
        client = TestClient(app)
        
        # Act & Assert: Test health endpoints
        response = client.get("/health")
        assert response.status_code == 200, "Health endpoint should return 200"
        assert response.json()["status"] == "ok", "Health status should be 'ok'"
        
        response = client.get("/health/live")
        assert response.status_code == 200, "Liveness endpoint should return 200"
        assert response.json()["status"] == "alive", "Liveness status should be 'alive'"
    
    def test_web_server_logs_to_stdout_without_env_var(self, monkeypatch, capsys):
        """
        Preservation Test: Web server should log to stdout when SEDIMENTAL_LOG_FILE is NOT set.
        
        This test verifies requirement 3.2:
        WHEN SEDIMENTAL_LOG_FILE is not set
        AND the web server is started
        THEN the system SHALL CONTINUE TO log only to stdout without errors
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        # Arrange
        monkeypatch.delenv("SEDIMENTAL_LOG_FILE", raising=False)
        
        from sedimental import web
        
        # Act: Call main() with mocked uvicorn
        with patch('uvicorn.run') as mock_uvicorn:
            with patch('sys.argv', ['web', '--port', '8080']):
                exit_code = web.main()
        
        # Assert: Should complete without errors
        assert exit_code == 0 or exit_code is None, "Web server main() should not return error"
        
        # Verify uvicorn.run was called (server would start)
        mock_uvicorn.assert_called_once()
        
        # Verify no file handlers were added
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0, "No file handlers should be added when env var is not set"


class TestPreservationPropertyBased:
    """
    Property-based preservation tests using Hypothesis.
    
    These tests use property-based testing to verify that behavior is preserved
    across a wide range of inputs when SEDIMENTAL_LOG_FILE is NOT set.
    
    EXPECTED OUTCOME: Tests PASS on unfixed code (confirms baseline behavior to preserve)
    """
    
    def setup_method(self):
        """Reset logging configuration before each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
    
    def teardown_method(self):
        """Clean up logging handlers after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
            root.removeHandler(handler)
    
    @given(verbose=st.booleans())
    @settings(max_examples=10)
    def test_configure_logging_preserves_behavior_for_any_verbose_setting(self, verbose):
        """
        Property-based Preservation Test: configure_logging() behavior preserved for any verbose setting.
        
        FOR ALL verbose in {True, False}:
        WHEN configure_logging(verbose=verbose) is called without log_file
        THEN the system SHALL configure logging correctly without errors
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        from sedimental.logging import configure_logging
        
        # Reset logging before each example
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
        
        # Act
        configure_logging(verbose=verbose)
        
        # Assert
        root = logging.getLogger()
        expected_level = logging.DEBUG if verbose else logging.INFO
        assert root.level == expected_level, f"Log level should be {'DEBUG' if verbose else 'INFO'}"
        
        # Verify we have a stream handler
        stream_handlers = [h for h in root.handlers if type(h) == logging.StreamHandler]
        assert len(stream_handlers) >= 1, "Should have at least one stream handler"
        
        # Verify no file handlers
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0, "Should have no file handlers when log_file not specified"
    
    @given(
        total_images=st.integers(min_value=0, max_value=10),
        successful=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=20)
    def test_cli_exit_codes_preserved_for_various_batch_results(self, total_images, successful):
        """
        Property-based Preservation Test: CLI exit codes preserved for various batch results.
        
        FOR ALL (total_images, successful) combinations:
        WHEN CLI processes a batch with given results
        THEN exit code SHALL be 0 if successful > 0, else 1
        
        EXPECTED: Test PASSES on unfixed code (baseline behavior preserved)
        """
        import tempfile
        
        # Ensure successful <= total_images
        if total_images == 0:
            successful = 0
        else:
            successful = min(successful, total_images)
        
        failed = total_images - successful
        
        # Use tempfile context manager instead of tmp_path fixture
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Arrange - set environment variables
            original_log_file = os.environ.get("SEDIMENTAL_LOG_FILE")
            original_inside_container = os.environ.get("SEDIMENTAL_INSIDE_CONTAINER")
            
            if "SEDIMENTAL_LOG_FILE" in os.environ:
                del os.environ["SEDIMENTAL_LOG_FILE"]
            os.environ["SEDIMENTAL_INSIDE_CONTAINER"] = "1"
            
            try:
                # Reset logging
                root = logging.getLogger()
                for handler in root.handlers[:]:
                    root.removeHandler(handler)
                root.setLevel(logging.WARNING)
                
                input_file = tmp_path / "input.jpg"
                from PIL import Image
                import io
                buf = io.BytesIO()
                img = Image.new("RGB", (10, 8), color=(100, 150, 200))
                img.save(buf, format="JPEG")
                input_file.write_bytes(buf.getvalue())
                
                output_file = tmp_path / "results.csv"
                
                from sedimental.cli import run_process_internal
                from sedimental.models import BatchResult
                import argparse
                
                args = argparse.Namespace(
                    input=str(input_file),
                    output=str(output_file),
                    metadata=None,
                    save_masks=False,
                    verbose=False,
                )
                
                mock_batch_result = BatchResult(
                    total_images=total_images,
                    successful=successful,
                    failed=failed,
                    results=[],
                    errors={f"image_{i}.jpg": "error" for i in range(failed)},
                )
                
                with patch('sedimental.cli.ProcessingOrchestrator') as MockOrchestrator:
                    mock_instance = MockOrchestrator.return_value
                    mock_instance.process_batch.return_value = mock_batch_result
                    
                    exit_code = run_process_internal(args)
                
                # Assert: Exit code should follow the documented behavior
                # - successful > 0 → exit 0
                # - successful == 0 → exit 1
                expected_exit_code = 0 if successful > 0 else 1
                assert exit_code == expected_exit_code, (
                    f"Exit code should be {expected_exit_code} for "
                    f"total={total_images}, successful={successful}, failed={failed}"
                )
            finally:
                # Restore environment variables
                if original_log_file is not None:
                    os.environ["SEDIMENTAL_LOG_FILE"] = original_log_file
                elif "SEDIMENTAL_LOG_FILE" in os.environ:
                    del os.environ["SEDIMENTAL_LOG_FILE"]
                
                if original_inside_container is not None:
                    os.environ["SEDIMENTAL_INSIDE_CONTAINER"] = original_inside_container
                elif "SEDIMENTAL_INSIDE_CONTAINER" in os.environ:
                    del os.environ["SEDIMENTAL_INSIDE_CONTAINER"]
