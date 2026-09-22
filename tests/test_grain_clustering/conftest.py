"""
Shared pytest fixtures for the grain_clustering test suite.

Fixtures
--------
minimal_df          - A minimal valid DataFrame with ≥10 rows and all seven dimensions.
make_grain_df       - Factory fixture that builds DataFrames of arbitrary size.
output_dir          - A fresh temporary directory for output files (via tmp_path).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pytest

# The seven morphological dimension column names required by the spec.
DIMENSIONS = [
    "area",
    "perimeter",
    "circularity",
    "roundness",
    "feret_diameter",
    "major_axis",
    "minor_axis",
]


# ---------------------------------------------------------------------------
# Minimal valid DataFrame
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_df() -> pd.DataFrame:
    """Return a minimal valid DataFrame with exactly 12 rows and all seven dimensions.

    Values are plausible but synthetic sediment-grain measurements.
    No NaN values, no non-finite values, no zero-variance columns.
    """
    rng = np.random.default_rng(seed=0)
    n = 12

    data = {
        "area": rng.uniform(0.5, 50.0, n),
        "perimeter": rng.uniform(2.0, 40.0, n),
        "circularity": rng.uniform(0.3, 1.0, n),
        "roundness": rng.uniform(0.3, 1.0, n),
        "feret_diameter": rng.uniform(1.0, 15.0, n),
        "major_axis": rng.uniform(1.0, 12.0, n),
        "minor_axis": rng.uniform(0.5, 8.0, n),
    }
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# DataFrame factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_grain_df() -> Callable[..., pd.DataFrame]:
    """Return a factory that builds a DataFrame of grain measurements.

    Usage::

        df = make_grain_df(n_rows=20, seed=42)
        df_with_extra_col = make_grain_df(n_rows=15, extra_cols={"label": "A"})

    Parameters
    ----------
    n_rows : int
        Number of rows to generate (default 12).
    seed : int
        NumPy random seed for reproducibility (default 0).
    nan_rows : int
        Number of rows to inject NaN values into (default 0).
        NaN values are placed in a random dimension column per affected row.
    extra_cols : dict, optional
        Additional columns to append to the DataFrame (scalar values are
        broadcast to all rows).
    dimensions : list[str], optional
        Subset of the seven dimension names to include (default: all seven).
    """

    def _factory(
        n_rows: int = 12,
        seed: int = 0,
        nan_rows: int = 0,
        extra_cols: dict | None = None,
        dimensions: list[str] | None = None,
    ) -> pd.DataFrame:
        if dimensions is None:
            dimensions = list(DIMENSIONS)

        rng = np.random.default_rng(seed=seed)

        # Generate plausible values for each requested dimension.
        _ranges: dict[str, tuple[float, float]] = {
            "area": (0.5, 50.0),
            "perimeter": (2.0, 40.0),
            "circularity": (0.3, 1.0),
            "roundness": (0.3, 1.0),
            "feret_diameter": (1.0, 15.0),
            "major_axis": (1.0, 12.0),
            "minor_axis": (0.5, 8.0),
        }

        data: dict[str, object] = {}
        for dim in dimensions:
            lo, hi = _ranges[dim]
            data[dim] = rng.uniform(lo, hi, n_rows)

        df = pd.DataFrame(data)

        # Inject NaN rows if requested.
        if nan_rows > 0 and n_rows > 0:
            nan_indices = rng.choice(n_rows, size=min(nan_rows, n_rows), replace=False)
            for idx in nan_indices:
                col = rng.choice(dimensions)
                df.at[idx, col] = np.nan

        # Append any extra columns.
        if extra_cols:
            for col_name, value in extra_cols.items():
                df[col_name] = value

        return df

    return _factory


# ---------------------------------------------------------------------------
# Temporary output directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Return a fresh temporary directory for output files.

    Uses pytest's built-in ``tmp_path`` fixture so it is automatically
    cleaned up after each test.
    """
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out
