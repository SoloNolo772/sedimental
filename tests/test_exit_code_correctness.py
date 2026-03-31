"""Property-based tests for CLI exit code correctness.

Feature: sedimental-analysis-tool
Property: 17 - Exit Code Correctness
Validates: Requirements 6.8, 6.9
"""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.models import BatchResult, ImageResult, SampleMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(input_path: str, output: str = "results.csv") -> argparse.Namespace:
    return argparse.Namespace(
        input=input_path,
        output=output,
        metadata=None,
        save_masks=False,
        scale=None,
        verbose=False,
    )


def _make_batch_result(
    total: int,
    successful: int,
    failed: int,
    errors: dict | None = None,
) -> BatchResult:
    return BatchResult(
        total_images=total,
        successful=successful,
        failed=failed,
        results=[],
        errors=errors or {},
    )


def _run_with_batch(batch: BatchResult, tmp_path: Path) -> int:
    """Call run_process_internal with a mocked orchestrator returning *batch*."""
    from sedimental.cli import run_process_internal

    args = _make_args(str(tmp_path / "input"), str(tmp_path / "out.csv"))
    with patch("sedimental.cli.ProcessingOrchestrator") as MockOrch:
        MockOrch.return_value.process_batch.return_value = batch
        return run_process_internal(args)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def all_success_scenario(draw):
    """BatchResult where every image succeeds (successful == total, failed == 0)."""
    total = draw(st.integers(min_value=1, max_value=20))
    return _make_batch_result(total=total, successful=total, failed=0)


@st.composite
def all_failure_scenario(draw):
    """BatchResult where every image fails (successful == 0, failed == total > 0)."""
    total = draw(st.integers(min_value=1, max_value=20))
    errors = {f"img{i}.jpg": "error" for i in range(total)}
    return _make_batch_result(total=total, successful=0, failed=total, errors=errors)


@st.composite
def partial_failure_scenario(draw):
    """BatchResult where some images succeed and some fail (0 < failed < total)."""
    total = draw(st.integers(min_value=2, max_value=20))
    failed = draw(st.integers(min_value=1, max_value=total - 1))
    successful = total - failed
    errors = {f"bad{i}.jpg": "error" for i in range(failed)}
    return _make_batch_result(
        total=total, successful=successful, failed=failed, errors=errors
    )


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestExitCodeCorrectness:
    """
    Property 17: Exit Code Correctness

    For any CLI invocation:
    - If all images process successfully, exit code SHALL be 0
    - If any image fails to process AND no images succeed, exit code SHALL be non-zero
    - If some images fail but at least one succeeds (partial failure),
      exit code SHALL be 0 with warnings logged

    Validates: Requirements 6.8, 6.9
    """

    # ------------------------------------------------------------------
    # Property 17a: All success → exit 0
    # ------------------------------------------------------------------

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(batch=all_success_scenario())
    def test_property_all_success_exits_zero(self, tmp_path, batch):
        """
        Property 17a: When all images succeed, exit code SHALL be 0.

        Validates: Requirement 6.8
        """
        result = _run_with_batch(batch, tmp_path)
        assert result == 0, (
            f"Expected exit 0 for all-success batch "
            f"(total={batch.total_images}, successful={batch.successful}), "
            f"got {result}"
        )

    # ------------------------------------------------------------------
    # Property 17b: All failure → non-zero exit
    # ------------------------------------------------------------------

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(batch=all_failure_scenario())
    def test_property_all_failure_exits_nonzero(self, tmp_path, batch):
        """
        Property 17b: When no images succeed, exit code SHALL be non-zero.

        Validates: Requirement 6.9
        """
        result = _run_with_batch(batch, tmp_path)
        assert result != 0, (
            f"Expected non-zero exit for all-failure batch "
            f"(total={batch.total_images}, failed={batch.failed}), "
            f"got {result}"
        )

    # ------------------------------------------------------------------
    # Property 17c: Partial failure → exit 0
    # ------------------------------------------------------------------

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(batch=partial_failure_scenario())
    def test_property_partial_failure_exits_zero(self, tmp_path, batch):
        """
        Property 17c: When some images fail but at least one succeeds,
        exit code SHALL be 0.

        Validates: Requirement 6.8 (partial failure is not a fatal error)
        """
        result = _run_with_batch(batch, tmp_path)
        assert result == 0, (
            f"Expected exit 0 for partial-failure batch "
            f"(total={batch.total_images}, successful={batch.successful}, "
            f"failed={batch.failed}), got {result}"
        )

    # ------------------------------------------------------------------
    # Property 17d: No images found → non-zero exit
    # ------------------------------------------------------------------

    def test_property_no_images_found_exits_nonzero(self, tmp_path):
        """
        Property 17d: When no JPEG images are found (total == 0),
        exit code SHALL be non-zero.

        Validates: Requirement 6.9
        """
        batch = _make_batch_result(total=0, successful=0, failed=0)
        result = _run_with_batch(batch, tmp_path)
        assert result != 0, (
            f"Expected non-zero exit when no images found, got {result}"
        )

    # ------------------------------------------------------------------
    # Property 17e: Partial failure logs a warning (not an error)
    # ------------------------------------------------------------------

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(batch=partial_failure_scenario())
    def test_property_partial_failure_emits_warning(self, tmp_path, batch, capsys):
        """
        Property 17e: Partial failure SHALL log a warning message to stderr.
        """
        _run_with_batch(batch, tmp_path)
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower() or "Warning" in captured.err, (
            f"Expected a warning in stderr for partial failure "
            f"(successful={batch.successful}, failed={batch.failed}), "
            f"got stderr: {captured.err!r}"
        )

    # ------------------------------------------------------------------
    # Property 17f: All failure emits an error message
    # ------------------------------------------------------------------

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(batch=all_failure_scenario())
    def test_property_all_failure_emits_error_message(self, tmp_path, batch, capsys):
        """
        Property 17f: When all images fail, an error message SHALL be
        written to stderr.

        Validates: Requirement 6.9
        """
        _run_with_batch(batch, tmp_path)
        captured = capsys.readouterr()
        assert "error" in captured.err.lower() or "Error" in captured.err, (
            f"Expected an error message in stderr for all-failure batch, "
            f"got stderr: {captured.err!r}"
        )

    # ------------------------------------------------------------------
    # Property 17g: Orchestrator exception → non-zero exit
    # ------------------------------------------------------------------

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(msg=st.text(min_size=1, max_size=80))
    def test_property_orchestrator_exception_exits_nonzero(self, tmp_path, msg):
        """
        Property 17g: When the orchestrator raises an unexpected exception,
        exit code SHALL be non-zero.

        Validates: Requirement 6.9
        """
        from sedimental.cli import run_process_internal

        args = _make_args(str(tmp_path / "input"), str(tmp_path / "out.csv"))
        with patch("sedimental.cli.ProcessingOrchestrator") as MockOrch:
            MockOrch.return_value.process_batch.side_effect = RuntimeError(msg)
            result = run_process_internal(args)

        assert result != 0, (
            f"Expected non-zero exit when orchestrator raises RuntimeError({msg!r}), "
            f"got {result}"
        )

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_single_success_exits_zero(self, tmp_path):
        """Concrete: 1 image, 1 success → exit 0."""
        batch = _make_batch_result(total=1, successful=1, failed=0)
        assert _run_with_batch(batch, tmp_path) == 0

    def test_concrete_single_failure_exits_nonzero(self, tmp_path):
        """Concrete: 1 image, 1 failure → non-zero exit."""
        batch = _make_batch_result(
            total=1, successful=0, failed=1, errors={"bad.jpg": "load error"}
        )
        assert _run_with_batch(batch, tmp_path) != 0

    def test_concrete_two_success_one_failure_exits_zero(self, tmp_path):
        """Concrete: 3 images, 2 succeed, 1 fails → exit 0 (partial failure)."""
        batch = _make_batch_result(
            total=3, successful=2, failed=1, errors={"bad.jpg": "segmentation error"}
        )
        assert _run_with_batch(batch, tmp_path) == 0

    def test_concrete_all_fail_exits_one(self, tmp_path):
        """Concrete: 3 images, all fail → exit code is exactly 1."""
        batch = _make_batch_result(
            total=3, successful=0, failed=3,
            errors={"a.jpg": "err", "b.jpg": "err", "c.jpg": "err"},
        )
        assert _run_with_batch(batch, tmp_path) == 1
