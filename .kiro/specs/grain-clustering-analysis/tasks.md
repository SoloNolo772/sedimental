# Implementation Plan: Grain Clustering Analysis

## Overview

Implement `grain_clustering.py` as a standalone, single-file Python script in `analysis/` and a
companion test suite under `tests/test_grain_clustering/`. The pipeline flows linearly: CLI
parsing → input validation → feature matrix assembly → scaling → PCA → k-means loop →
silhouette analysis → all output files → console summary. Tests use `pytest` with `hypothesis`
for property-based coverage and `unittest.mock` for file-I/O error simulation.

---

## Tasks

- [x] 1. Scaffold the project layout and shared test fixtures
  - Create `analysis/grain_clustering.py` as an empty module with the `if __name__ == "__main__":` guard and all function stubs (return `None` / placeholder values).
  - Create `tests/test_grain_clustering/__init__.py` (empty).
  - Create `tests/test_grain_clustering/conftest.py` with shared `pytest` fixtures: a minimal valid DataFrame (≥10 rows, all seven dimensions), a factory that builds DataFrames of arbitrary size, and a temp-directory fixture for output files.
  - _Requirements: 11.3, 11.4_

- [x] 2. Implement CLI argument parsing (`parse_args`)
  - [x] 2.1 Implement `parse_args()` with `argparse`
    - Accept positional `csv_path`, optional `--output-dir`, optional `--dimensions nargs='+'`.
    - Validate dimension names against the seven valid names; exit with code 2 and list all seven on any invalid name.
    - Validate that `--dimensions` receives at least two names; exit with code 2 with the "at least two dimensions required" message.
    - Resolve default output directory: parent of `csv_path`; bare filename → current working directory.
    - _Requirements: 1.1, 1.2, 1.3, 1.7, 1.8_

  - [x] 2.2 Write property test for output directory resolution rule
    - **Property 1: Output directory resolution rule**
    - **Validates: Requirements 1.2**
    - Use `hypothesis` `st.text()` for path strings (with and without directory components) and `st.booleans()` for whether `--output-dir` is supplied; assert the resolved directory equals the spec rule in all cases.

  - [x] 2.3 Write property test for invalid dimension name rejection
    - **Property 2: Invalid dimension names are always rejected**
    - **Validates: Requirements 1.7**
    - Generate arbitrary strings that are not in the valid-dimension set and assert exit code is non-zero and stderr lists all seven valid names.

  - [x] 2.4 Write unit tests for CLI edge cases (`test_cli.py`)
    - `test_all_seven_dimensions_default`: omitting `--dimensions` produces all seven.
    - Edge cases: fewer than two dimensions supplied, unknown dimension name, `--output-dir` missing/not-writable.
    - _Requirements: 1.3, 1.6, 1.7, 1.8_

- [x] 3. Implement input validation and CSV loading (`validate_and_load`)
  - [x] 3.1 Implement `validate_and_load(csv_path, dimensions)`
    - Enforce validation order: column presence → minimum 10 rows (raw) → NaN row removal with >20% warning → post-NaN minimum row count check → non-finite/non-numeric check.
    - Print missing column names to stderr and exit(1) when columns absent.
    - Print observed row count + threshold to stderr and exit(1) when fewer than 10 rows.
    - Drop NaN rows; print warning to stderr with count and percentage when >20% dropped.
    - Print column names and 1-based row indices of non-finite/non-numeric values to stderr and exit(1).
    - Handle `FileNotFoundError` and `PermissionError` with descriptive stderr messages and exit(1).
    - Return cleaned DataFrame with original index preserved.
    - _Requirements: 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Write property test for missing column detection
    - **Property 3: Missing columns are detected and named**
    - **Validates: Requirements 2.2**
    - Generate arbitrary subsets of the seven dimensions as absent columns; assert exit is non-zero and error message names exactly the missing columns.

  - [x] 3.3 Write property test for minimum row count rejection
    - **Property 4: Row count below minimum is rejected with observed count**
    - **Validates: Requirements 2.3**
    - Generate DataFrames with 0–9 rows; assert exit is non-zero and error message contains both the observed count and the threshold 10.

  - [x] 3.4 Write property test for NaN fraction warning boundary
    - **Property 5: NaN fraction warning fires exactly at the >20% boundary**
    - **Validates: Requirements 2.4**
    - Generate DataFrames parameterised by total rows and NaN-row count; assert warning appears if and only if NaN fraction strictly exceeds 20%.

  - [x] 3.5 Write property test for non-finite/non-numeric value reporting
    - **Property 6: Non-finite/non-numeric values are reported with exact location**
    - **Validates: Requirements 2.5**
    - Inject `inf`, `nan`, or non-numeric strings at random positions; assert exit is non-zero and the column name and 1-based row index appear in stderr.

  - [x] 3.6 Write unit tests for validation edge cases (`test_validation.py`)
    - File not found, unreadable (mocked `PermissionError`).
    - `test_validation_order`: craft a CSV violating multiple constraints; assert first error fires.
    - Exactly 10 rows passes; 9 rows fails.
    - NaN rows at exactly 20% produce no warning; 20.001% produces warning.
    - _Requirements: 1.4, 1.5, 2.1, 2.3, 2.4_

- [x] 4. Implement feature matrix assembly and normalisation (`build_feature_matrix`, `fit_scaler`)
  - [x] 4.1 Implement `build_feature_matrix(df, dimensions)`
    - Extract selected dimension columns from cleaned DataFrame.
    - Return `float64` NumPy array of shape `(n_valid_grains, n_dimensions)`.
    - _Requirements: 3.1_

  - [x] 4.2 Implement `fit_scaler(X)`
    - Fit `StandardScaler` on `X`.
    - Detect zero-variance columns before returning; print column name to stderr and exit(1).
    - Return `(fitted_scaler, X_scaled)`.
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 4.3 Write property test for zero-mean unit-variance scaling
    - **Property 7: Scaling produces zero-mean, unit-variance per column**
    - **Validates: Requirements 3.1**
    - Generate feature matrices with at least two distinct values per column; assert each column of `X_scaled` has mean ≈ 0 and std ≈ 1 within floating-point tolerance.

  - [x] 4.4 Write unit tests for normalisation edge cases (`test_normalisation.py`)
    - Zero-variance column triggers exit(1) and names the column.
    - _Requirements: 3.3_

- [x] 5. Implement PCA fitting and k-means clustering (`fit_pca`, `run_kmeans`)
  - [x] 5.1 Implement `fit_pca(X_scaled)`
    - Fit `PCA(n_components=2)` on `X_scaled`.
    - Return `(fitted_pca, X_pca)`.
    - _Requirements: 8.2_

  - [x] 5.2 Implement `run_kmeans(X_scaled, k)`
    - Run `KMeans(n_clusters=k, n_init=10, random_state=42)`.
    - Detect K ≥ number of valid grains; print descriptive message to stderr and exit(1).
    - Catch convergence failures; print K value and reason to stderr and exit(1).
    - Return `(labels, silhouette_score)`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 5.1, 10.4_

  - [x] 5.3 Write property test for scaler and PCA shared across k runs
    - **Property 8: Scaler and PCA are fitted once and shared across all k runs**
    - **Validates: Requirements 3.2, 8.2**
    - Verify element-wise equality of `X_scaled` and `X_pca` across all four k values for any valid dataset.

  - [x] 5.4 Write property test for clustering reproducibility
    - **Property 9: Clustering is reproducible**
    - **Validates: Requirements 4.3**
    - Run `run_kmeans` twice on the same input; assert identical label arrays for each k value.

  - [x] 5.5 Write unit tests for k-means edge cases (`test_clustering.py`)
    - `test_kmeans_n_init_is_10`: mock `KMeans`, verify `n_init=10` and `random_state=42`.
    - K ≥ valid grain count triggers exit(1).
    - `test_four_k_runs_produce_four_outputs`: verify four labelled CSVs and four SVGs exist after a full run.
    - _Requirements: 4.2, 4.3, 4.6_

- [x] 6. Implement silhouette analysis and recommended-k selection (`select_recommended_k`)
  - [x] 6.1 Implement `select_recommended_k(scores)`
    - Pure function: return k with highest silhouette score.
    - Ties broken by smallest k (comparison to four decimal places).
    - _Requirements: 5.2, 7.4_

  - [x] 6.2 Write property test for recommended-k selection
    - **Property 11: Recommended k is the highest-silhouette k, ties broken by smallest k**
    - **Validates: Requirements 5.2, 7.4**
    - Generate arbitrary score mappings over {2, 3, 4, 5}; assert return value is always the correct k.

  - [x] 6.3 Write unit tests for silhouette output to stdout (`test_silhouette.py`)
    - Verify the stdout summary table lists each K, Silhouette_Score to 4 dp, and `*` marker on recommended K.
    - _Requirements: 5.3_

- [x] 7. Checkpoint — validate the core pipeline
  - Ensure all tests pass up to this point. Run:
    `docker compose run --rm sedimental test tests/test_grain_clustering/ -v`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement labelled CSV output (`write_labelled_csv`)
  - [x] 8.1 Implement `write_labelled_csv(df_original, valid_mask, labels, k, output_dir, input_stem)`
    - Preserve all original columns in original order.
    - Append `cluster_k{K}` column (int64).
    - Assign `-1` to rows excluded by `valid_mask`.
    - Name file `{input_stem}_clusters_k{K}.csv`; overwrite if exists.
    - Catch `OSError`; print descriptive message to stderr and exit(1).
    - Return output path.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 8.2 Write property test for labelled CSV structure invariant
    - **Property 10: Labelled_CSV structure invariant**
    - **Validates: Requirements 6.2, 6.3, 6.4, 4.4, 4.5**
    - Generate DataFrames with random NaN positions; read back the written CSV and assert all five sub-invariants simultaneously for each K.

  - [x] 8.3 Write unit tests for labelled CSV edge cases (`test_outputs.py`)
    - Write failure via mocked `open`/`OSError` triggers exit(1) and descriptive stderr.
    - Existing file is overwritten.
    - _Requirements: 6.5, 6.6_

- [x] 9. Implement silhouette report CSV output (`write_silhouette_csv`)
  - [x] 9.1 Implement `write_silhouette_csv(scores, recommended_k, output_dir, input_stem)`
    - Write header `k,silhouette_score,recommended` + four data rows in ascending k order.
    - Round scores to 4 decimal places; `recommended` column is `"true"` / `"false"`.
    - Name file `{input_stem}_silhouette.csv`; overwrite if exists.
    - Catch `OSError`; print descriptive message to stderr and exit(1).
    - Return output path.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 9.2 Write property test for silhouette report structure and values
    - **Property 12: Silhouette report has correct structure and values**
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - Generate score dicts; read back the written CSV and assert four rows in ascending order, rounded scores, exactly one `"true"` row matching the recommended k.

  - [x] 9.3 Write unit tests for silhouette CSV edge cases (extend `test_outputs.py`)
    - Write failure triggers exit(1).
    - Tie-breaking rule produces `"true"` on smallest k.
    - _Requirements: 7.4, 7.6_

- [x] 10. Implement per-k scatter SVG visualisation (`write_scatter_svg`)
  - [x] 10.1 Implement `write_scatter_svg(X_pca, labels, k, silhouette, output_dir, input_stem)`
    - Plot PCA scatter with `tab10` colour palette.
    - Add legend with exactly K entries (labels 0 … K−1).
    - Set title to `f"k={k} | Silhouette: {silhouette:.4f}"`.
    - Label axes "PC1" and "PC2".
    - Save as SVG; name `{input_stem}_clusters_k{K}.svg`; overwrite if exists.
    - Catch `OSError`; print descriptive message to stderr and exit(1).
    - Return output path.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x] 10.2 Write property test for scatter SVG legend entry count
    - **Property 13: Scatter SVG legend has exactly K entries**
    - **Validates: Requirements 8.4**
    - For each k ∈ {2, 3, 4, 5}, assert the matplotlib figure legend has exactly k handles.

  - [x] 10.3 Write property test for scatter SVG title format
    - **Property 14: Scatter SVG title matches format string**
    - **Validates: Requirements 8.5**
    - Generate arbitrary k and silhouette float values; assert title equals `f"k={k} | Silhouette: {score:.4f}"`.

  - [x] 10.4 Write unit tests for scatter SVG axis labels (`test_visualisation.py`)
    - `test_scatter_svg_axis_labels`: assert x-label is "PC1" and y-label is "PC2".
    - SVG write failure via mocked `savefig` triggers exit(1).
    - _Requirements: 8.6, 8.8_

- [x] 11. Implement silhouette summary bar chart SVG (`write_silhouette_svg`)
  - [x] 11.1 Implement `write_silhouette_svg(scores, recommended_k, output_dir, input_stem)`
    - Render bar chart for K ∈ {2, 3, 4, 5}.
    - Fixed y-axis range [−1, 1]; label axes "k" and "Silhouette Score".
    - Highlight recommended-k bar with distinct colour; annotate all bars with score to 4 dp.
    - Set title "Silhouette Scores by k".
    - Name `{input_stem}_silhouette.svg`; overwrite if exists.
    - Catch `OSError`; print descriptive message to stderr and exit(1).
    - Return output path.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 11.2 Write property test for silhouette bar chart y-axis range
    - **Property 15: Silhouette bar chart y-axis is always fixed at [−1, 1]**
    - **Validates: Requirements 9.1**
    - Generate arbitrary score sets; assert `ax.get_ylim()` equals `(-1.0, 1.0)` regardless of score values.

  - [x] 11.3 Write property test for bar annotation values
    - **Property 16: Bar annotations match scores rounded to 4 decimal places**
    - **Validates: Requirements 9.2**
    - Generate arbitrary score sets; extract bar text annotations and assert each equals the score formatted to 4 dp.

  - [x] 11.4 Write unit tests for silhouette SVG (`test_visualisation.py`)
    - `test_silhouette_chart_title`: assert figure title is "Silhouette Scores by k".
    - SVG write failure via mocked `savefig` triggers exit(1).
    - _Requirements: 9.3, 9.5_

- [x] 12. Implement console progress output and wire `main()` together
  - [x] 12.1 Implement console progress printing in `main()`
    - After load/validation: print valid grain count, skipped count, and selected dimensions to stdout.
    - After each k run: print K and silhouette score rounded to 4 dp to stdout.
    - After all files written: print each output file path, one per line, to stdout.
    - Wire all functions together in the correct pipeline order: parse → validate → build matrix → scale → PCA → k-loop (kmeans + silhouette + labelled CSV + scatter SVG) → select recommended k → silhouette CSV + summary SVG → summary table + completion message.
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 12.2 Write property test for console progress output accuracy
    - **Property 17: Console progress output reflects actual pipeline results**
    - **Validates: Requirements 10.1, 10.2, 10.3**
    - Run the full pipeline on a generated valid DataFrame; capture stdout and assert (a) valid/skipped counts match, (b) each K line shows correct silhouette to 4 dp, (c) all written file paths appear in the completion listing.

  - [x] 12.3 Write unit tests for independence (`test_independence.py`)
    - `test_script_has_main_guard`: AST-parse `grain_clustering.py` and verify `if __name__ == "__main__"` node is present.
    - `test_no_project_internal_imports`: AST-parse and assert no `import sedimental` or `from sedimental` statement exists.
    - `test_only_approved_imports`: assert all top-level imports come from stdlib, `numpy`, `pandas`, `sklearn`, or `matplotlib`.
    - _Requirements: 11.1, 11.2, 11.4_

- [x] 13. Final checkpoint — full test suite
  - Run the complete test suite:
    `docker compose run --rm sedimental test tests/test_grain_clustering/ -v`
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery.
- Each task references specific requirements for traceability.
- Checkpoints (tasks 7 and 13) ensure incremental validation at logical seams.
- Property tests validate universal correctness properties using `hypothesis` (`max_examples=100`).
- Unit/edge-case tests use `pytest` with `unittest.mock.patch` for I/O error simulation.
- Tests run inside Docker: `docker compose run --rm sedimental test tests/test_grain_clustering/ -v`
- The scaler and PCA must be fitted exactly once before the k-loop and passed into each iteration — do not re-fit inside the loop.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.2", "3.3", "3.4", "3.5", "3.6", "4.2"] },
    { "id": 3, "tasks": ["4.3", "4.4", "5.1", "5.2", "6.1"] },
    { "id": 4, "tasks": ["5.3", "5.4", "5.5", "6.2", "6.3", "8.1", "9.1", "10.1", "11.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "9.2", "9.3", "10.2", "10.3", "10.4", "11.2", "11.3", "11.4", "12.1"] },
    { "id": 6, "tasks": ["12.2", "12.3"] }
  ]
}
```
