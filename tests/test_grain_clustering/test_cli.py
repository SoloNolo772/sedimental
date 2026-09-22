"""
Unit tests for parse_args() CLI argument parsing.

Covers requirements 1.1, 1.2, 1.3, 1.7, 1.8.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Import the function under test.
from analysis.grain_clustering import VALID_DIMENSIONS, parse_args


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_parse_args(argv: list[str]):
    """Run parse_args() with the given sys.argv (excluding program name)."""
    with patch.object(sys, "argv", ["grain_clustering.py"] + argv):
        return parse_args()


def run_parse_args_exit(argv: list[str]) -> tuple[int, str]:
    """Run parse_args() expecting SystemExit; return (exit_code, stderr_output)."""
    import io

    with patch.object(sys, "argv", ["grain_clustering.py"] + argv):
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                parse_args()
            return exc_info.value.code, mock_stderr.getvalue()


# ---------------------------------------------------------------------------
# 1.1 – positional csv_path
# ---------------------------------------------------------------------------


def test_csv_path_is_accepted():
    """parse_args() stores the positional csv_path on the namespace."""
    args = run_parse_args(["/some/path/grains.csv"])
    assert args.csv_path == "/some/path/grains.csv"


# ---------------------------------------------------------------------------
# 1.2 – output directory resolution
# ---------------------------------------------------------------------------


def test_output_dir_explicit(tmp_path: Path):
    """When --output-dir is supplied (and exists), it is used as-is (as a Path)."""
    args = run_parse_args(["/data/grains.csv", "--output-dir", str(tmp_path)])
    assert args.output_dir == tmp_path


def test_output_dir_defaults_to_csv_parent():
    """When --output-dir is omitted and csv_path has a directory, default is that parent."""
    args = run_parse_args(["/data/subdir/grains.csv"])
    assert args.output_dir == Path("/data/subdir")


def test_output_dir_bare_filename_defaults_to_cwd():
    """When csv_path is a bare filename (no directory), default is cwd."""
    args = run_parse_args(["grains.csv"])
    assert args.output_dir == Path.cwd()


# ---------------------------------------------------------------------------
# 1.3 – default dimensions are all seven
# ---------------------------------------------------------------------------


def test_all_seven_dimensions_default():
    """Omitting --dimensions produces all seven dimension names."""
    args = run_parse_args(["/data/grains.csv"])
    assert args.dimensions == list(VALID_DIMENSIONS)


def test_subset_of_dimensions_accepted():
    """A valid subset of two or more dimensions is accepted."""
    args = run_parse_args(["/data/grains.csv", "--dimensions", "area", "perimeter"])
    assert args.dimensions == ["area", "perimeter"]


# ---------------------------------------------------------------------------
# 1.7 – invalid dimension name → exit 2, lists all seven
# ---------------------------------------------------------------------------


def test_invalid_dimension_exits_with_code_2():
    """An unknown dimension name causes exit with code 2."""
    code, _ = run_parse_args_exit(["/data/grains.csv", "--dimensions", "not_a_dim"])
    assert code == 2


def test_invalid_dimension_message_lists_all_seven():
    """Error message for an invalid dimension must list all seven valid names."""
    _, stderr = run_parse_args_exit(["/data/grains.csv", "--dimensions", "not_a_dim"])
    for name in VALID_DIMENSIONS:
        assert name in stderr, f"Expected '{name}' in stderr; got:\n{stderr}"


def test_invalid_dimension_mixed_valid_and_invalid():
    """Even when some names are valid, an invalid name still triggers exit 2."""
    code, stderr = run_parse_args_exit(
        ["/data/grains.csv", "--dimensions", "area", "bad_dim"]
    )
    assert code == 2
    for name in VALID_DIMENSIONS:
        assert name in stderr


# ---------------------------------------------------------------------------
# 1.8 – fewer than two dimensions → exit 2
# ---------------------------------------------------------------------------


def test_single_dimension_exits_with_code_2():
    """Supplying only one dimension name must cause exit with code 2."""
    code, _ = run_parse_args_exit(["/data/grains.csv", "--dimensions", "area"])
    assert code == 2


def test_single_dimension_message_mentions_two():
    """Error message for fewer than two dimensions must mention the requirement."""
    _, stderr = run_parse_args_exit(["/data/grains.csv", "--dimensions", "area"])
    assert "two" in stderr.lower() or "2" in stderr, (
        f"Expected 'two' or '2' in stderr; got:\n{stderr}"
    )


# ---------------------------------------------------------------------------
# All seven individual dimension names are valid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dim", VALID_DIMENSIONS)
def test_each_valid_dimension_accepted_in_pair(dim: str):
    """Each valid dimension name is accepted when paired with another valid name."""
    other = [d for d in VALID_DIMENSIONS if d != dim][0]
    args = run_parse_args(["/data/grains.csv", "--dimensions", dim, other])
    assert dim in args.dimensions


# ---------------------------------------------------------------------------
# Property 2: Invalid dimension names are always rejected
# Feature: grain-clustering-analysis, Property 2: Invalid dimension names are always rejected
# ---------------------------------------------------------------------------


@given(
    invalid_dim=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=1,
    ).filter(lambda s: s not in VALID_DIMENSIONS)
)
@settings(max_examples=100)
def test_invalid_dimension_always_rejected(invalid_dim: str) -> None:
    """Property 2: Invalid dimension names are always rejected
    **Validates: Requirements 1.7**

    For any string that is not one of the seven valid dimension names, passing
    it as a --dimensions argument must cause parse_args() to exit with a
    non-zero code and the error message must list all seven valid names.
    """
    import io

    # Null bytes and strings starting with '-' confuse argparse at the OS level.
    assume("\x00" not in invalid_dim)
    assume(not invalid_dim.startswith("-"))

    argv = ["grain_clustering.py", "/data/grains.csv", "--dimensions", invalid_dim]

    with patch.object(sys, "argv", argv):
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                parse_args()
            exit_code = exc_info.value.code
            stderr_output = mock_stderr.getvalue()

    # Exit code must be non-zero.
    assert exit_code != 0, (
        f"Expected non-zero exit for invalid dimension {invalid_dim!r}, "
        f"got exit code {exit_code}"
    )

    # All seven valid dimension names must appear in stderr.
    for name in VALID_DIMENSIONS:
        assert name in stderr_output, (
            f"Expected '{name}' in stderr for invalid dimension {invalid_dim!r}; "
            f"got:\n{stderr_output}"
        )


# ---------------------------------------------------------------------------
# Property 1: Output directory resolution rule
# Feature: grain-clustering-analysis, Property 1: Output directory resolution rule
# ---------------------------------------------------------------------------


@given(
    csv_path=st.text(min_size=1),
    output_dir_supplied=st.booleans(),
    output_dir_arg=st.text(min_size=1),
)
@settings(max_examples=100)
def test_output_dir_resolution_rule(
    csv_path: str,
    output_dir_supplied: bool,
    output_dir_arg: str,
) -> None:
    """Property 1: Output directory resolution rule
    **Validates: Requirements 1.2**

    For any combination of csv_path (with or without a directory component)
    and the presence/absence of --output-dir, the resolved output_dir must
    equal:
      - Path(output_dir_arg)           if --output-dir is supplied
      - Path(csv_path).parent          if csv_path has a directory component
      - Path.cwd()                     if csv_path is a bare filename
    """
    # Filter out strings that would confuse argparse or the OS path machinery.
    # Null bytes cause argparse to raise an error at the OS level.
    assume("\x00" not in csv_path)
    assume("\x00" not in output_dir_arg)
    # Avoid strings that look like option flags and would confuse argparse.
    assume(not csv_path.startswith("-"))
    assume(not output_dir_arg.startswith("-"))

    argv = ["grain_clustering.py", csv_path]
    if output_dir_supplied:
        argv += ["--output-dir", output_dir_arg]

    try:
        with patch.object(sys, "argv", argv):
            args = parse_args()
    except SystemExit:
        # argparse rejected this combination (e.g. dimension validation, etc.)
        # or output-dir validation failed (path does not exist / not writable)
        # — skip it; we only care about cases where parsing succeeds.
        assume(False)
        return

    # --- Determine expected output directory per the spec rule ---
    if output_dir_supplied:
        expected = Path(output_dir_arg)
    else:
        parent = Path(csv_path).parent
        if parent == Path("."):
            expected = Path.cwd()
        else:
            expected = parent

    assert args.output_dir == expected, (
        f"csv_path={csv_path!r}, output_dir_supplied={output_dir_supplied}, "
        f"output_dir_arg={output_dir_arg!r}: "
        f"expected {expected!r}, got {args.output_dir!r}"
    )


# ---------------------------------------------------------------------------
# 1.6 – --output-dir missing or not writable → exit non-zero
# ---------------------------------------------------------------------------


def test_output_dir_not_exists_exits_nonzero(tmp_path: Path):
    """Supplying a non-existent directory as --output-dir causes non-zero exit."""
    nonexistent = tmp_path / "does_not_exist"
    code, _ = run_parse_args_exit(
        ["/data/grains.csv", "--output-dir", str(nonexistent)]
    )
    assert code != 0


def test_output_dir_not_exists_stderr_message(tmp_path: Path):
    """Error message for non-existent --output-dir must mention the supplied path."""
    nonexistent = tmp_path / "does_not_exist"
    _, stderr = run_parse_args_exit(
        ["/data/grains.csv", "--output-dir", str(nonexistent)]
    )
    assert str(nonexistent) in stderr, (
        f"Expected path {nonexistent!r} in stderr; got:\n{stderr}"
    )


def test_output_dir_not_writable_exits_nonzero(tmp_path: Path):
    """Supplying an unwritable --output-dir causes non-zero exit."""
    unwritable = tmp_path / "unwritable"
    unwritable.mkdir()
    with patch("os.access", return_value=False):
        code, _ = run_parse_args_exit(
            ["/data/grains.csv", "--output-dir", str(unwritable)]
        )
    assert code != 0


def test_output_dir_not_writable_stderr_message(tmp_path: Path):
    """Error message for unwritable --output-dir must mention the supplied path."""
    unwritable = tmp_path / "unwritable"
    unwritable.mkdir()
    with patch("os.access", return_value=False):
        _, stderr = run_parse_args_exit(
            ["/data/grains.csv", "--output-dir", str(unwritable)]
        )
    assert str(unwritable) in stderr, (
        f"Expected path {unwritable!r} in stderr; got:\n{stderr}"
    )


def test_output_dir_valid_existing_writable_accepted(tmp_path: Path):
    """A real existing writable directory is accepted without error."""
    args = run_parse_args(["/data/grains.csv", "--output-dir", str(tmp_path)])
    assert args.output_dir == tmp_path
