# Requirements Document

## Introduction

A standalone Python script that performs k-means clustering analysis on sediment grain measurement data exported from the Sedimental application. The script is intended for use in river confluence sediment studies, where researchers compare grain populations from transects taken before and after a confluence point. It accepts a single CSV file of per-grain morphological measurements, runs k-means for k = 2, 3, 4, and 5, evaluates cluster naturalness via silhouette coefficient analysis, and produces labelled output CSVs and SVG visualisations. The script has no dependency on or coupling to the main Sedimental application codebase.

---

## Glossary

- **Script**: The standalone Python script `grain_clustering.py` that is the subject of these requirements.
- **Input_CSV**: A comma-separated values file supplied by the user, containing one row per grain with morphological measurement columns.
- **Grain**: A single sediment particle described by the seven morphological dimensions.
- **Feature_Matrix**: The numerical array derived from Input_CSV used as input to k-means, comprising the selected grain dimensions.
- **Dimension**: One of the seven per-grain measurements: `area`, `perimeter`, `circularity`, `roundness`, `feret_diameter`, `major_axis`, `minor_axis`. All length-based dimensions are in millimetres; shape ratios (`circularity`, `roundness`) are dimensionless.
- **K**: The number of clusters in a single k-means run; one of the values {2, 3, 4, 5}.
- **Cluster_Label**: An integer in the range [0, K−1] assigned to each grain by the k-means algorithm.
- **Labelled_CSV**: A copy of the Input_CSV with one additional column, `cluster_k{K}`, containing Cluster_Labels for a given K run.
- **Silhouette_Score**: The mean silhouette coefficient across all grains for a given K, as defined by Rousseeuw (1987), ranging from −1 to +1.
- **Silhouette_Report**: A CSV file containing one row per K value with its corresponding Silhouette_Score and the recommended K.
- **SVG_Plot**: A scalable vector graphics file produced for a given K run, visualising the cluster assignments.
- **Output_Directory**: The directory into which all output files are written, defaulting to the same directory as the Input_CSV.
- **Scaler**: A standard-score (z-score) normalisation applied to the Feature_Matrix before clustering.

---

## Requirements

### Requirement 1: Script Invocation

**User Story:** As a researcher, I want to invoke the script from the command line with a single CSV file path argument, so that I can run the analysis without modifying any code.

#### Acceptance Criteria

1. THE Script SHALL accept a positional command-line argument specifying the path to the Input_CSV.
2. THE Script SHALL accept an optional `--output-dir` argument specifying the Output_Directory; WHEN the argument is omitted, THE Script SHALL write all outputs to the directory containing the Input_CSV; IF the Input_CSV path contains no directory component (bare filename), THEN THE Script SHALL resolve the output directory as the current working directory.
3. THE Script SHALL accept an optional `--dimensions` argument accepting a space-separated subset of the seven Dimension names (`area`, `perimeter`, `circularity`, `roundness`, `feret_diameter`, `major_axis`, `minor_axis`); WHEN the argument is omitted, THE Script SHALL use all seven Dimensions.
4. IF the Input_CSV path does not refer to an existing file, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.
5. IF the Input_CSV path refers to an existing file that cannot be read due to permissions, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.
6. IF `--output-dir` is supplied with a path that does not exist or is not writable, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.
7. IF `--dimensions` is supplied with a name that is not one of the seven valid Dimension names, THEN THE Script SHALL print a descriptive error message listing all seven valid names and exit with a non-zero exit code.
8. IF `--dimensions` is supplied with fewer than two Dimension names, THEN THE Script SHALL print a descriptive error message stating that at least two dimensions are required and exit with a non-zero exit code.

---

### Requirement 2: Input Validation

**User Story:** As a researcher, I want the script to validate the input CSV before analysis begins, so that I receive clear feedback rather than a cryptic runtime error.

#### Acceptance Criteria

1. WHEN the Input_CSV is loaded, THE Script SHALL perform validation checks in the following order: column presence, minimum row count, NaN row removal, then numeric value check.
2. WHEN the Input_CSV is loaded, THE Script SHALL verify that every selected Dimension column is present; IF one or more selected Dimension columns are absent, THEN THE Script SHALL print the names of the missing columns to stderr and exit with a non-zero exit code.
3. WHEN the Input_CSV is loaded, THE Script SHALL verify that the file contains at least 10 rows of grain data; IF fewer than 10 rows are present, THEN THE Script SHALL print an error message to stderr stating the observed row count and the minimum threshold of 10, and exit with a non-zero exit code.
4. WHEN the Input_CSV is loaded, THE Script SHALL drop rows where any selected Dimension value is missing (NaN), using the total row count before NaN removal as the baseline; IF more than 20% of rows are dropped, THEN THE Script SHALL print a warning to stderr stating the number and percentage of rows dropped.
5. WHEN the Input_CSV is loaded, THE Script SHALL verify that all remaining selected Dimension values are finite numeric values (i.e., castable to a finite float); IF non-numeric or infinite values are detected, THEN THE Script SHALL print the column names and 1-based row indices (CSV line numbers) containing invalid values and exit with a non-zero exit code.

---

### Requirement 3: Feature Normalisation

**User Story:** As a researcher, I want the grain measurements normalised before clustering, so that dimensions with larger numeric ranges do not dominate the distance calculations.

#### Acceptance Criteria

1. WHEN the Feature_Matrix is assembled, THE Script SHALL apply the Scaler to each Dimension column independently, producing a Scaled_Feature_Matrix with zero-mean and unit-variance per column.
2. WHEN the Scaler is fitted, THE Script SHALL fit it once on the full Feature_Matrix and apply the same fitted Scaler to all K runs; the Scaled_Feature_Matrix SHALL remain identical across all K runs.
3. IF any selected Dimension column in the Feature_Matrix has zero variance (all values identical), THEN THE Script SHALL print a descriptive error message to stderr naming the constant column and exit with a non-zero exit code.

---

### Requirement 4: K-Means Clustering

**User Story:** As a researcher, I want the script to run k-means for k = 2, 3, 4, and 5, so that I can compare cluster structures across multiple granularities.

#### Acceptance Criteria

1. THE Script SHALL run k-means clustering for each K in {2, 3, 4, 5}.
2. WHEN running k-means for a given K, THE Script SHALL use exactly 10 distinct random initialisations (`n_init=10`) to reduce sensitivity to initialisation.
3. WHEN running k-means for a given K, THE Script SHALL use a fixed random seed of 42, so that results are reproducible given the same input.
4. WHEN k-means completes for a given K, THE Script SHALL assign a Cluster_Label in [0, K−1] to every grain that has complete (non-missing) feature values.
5. IF a grain has one or more missing Dimension values, THEN THE Script SHALL exclude that grain from k-means clustering and assign it a Cluster_Label of `-1` in the Labelled_CSV.
6. IF K is greater than or equal to the number of valid grains available for clustering, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.

---

### Requirement 5: Silhouette Analysis

**User Story:** As a researcher, I want a silhouette coefficient computed for each k value, so that I can identify the k that best reflects natural groupings in the data.

#### Acceptance Criteria

1. WHEN k-means completes for a given K, THE Script SHALL compute the Silhouette_Score using the Scaled_Feature_Matrix and the Cluster_Labels assigned by that run.
2. THE Script SHALL identify the K with the highest Silhouette_Score as the recommended K; WHEN two or more K values share the highest Silhouette_Score to four decimal places, THE Script SHALL select the smallest such K as the recommended K.
3. WHEN silhouette scoring is complete, THE Script SHALL print a summary table to stdout listing each K, its Silhouette_Score rounded to four decimal places, and a `*` marker in a separate column indicating the recommended K.
4. IF K equals 1 (mathematically undefined silhouette), THEN THE Script SHALL not compute a Silhouette_Score for that K and SHALL display "N/A" wherever the score would appear.

---

### Requirement 6: Labelled CSV Output

**User Story:** As a researcher, I want a copy of the original CSV with cluster labels appended for each k run, so that I can cross-reference grain properties with cluster membership in downstream analysis.

#### Acceptance Criteria

1. WHEN k-means completes for a given K, THE Script SHALL write a Labelled_CSV to the Output_Directory.
2. THE Labelled_CSV SHALL contain all columns from the Input_CSV in their original order, followed by one additional column named `cluster_k{K}` (e.g., `cluster_k3`) with integer dtype.
3. THE Labelled_CSV SHALL preserve all original rows from the Input_CSV in their original order.
4. WHEN a row was excluded from clustering due to missing values, THE Script SHALL assign the integer value `-1` to its `cluster_k{K}` cell.
5. THE Labelled_CSV file SHALL be named `{input_stem}_clusters_k{K}.csv` where `{input_stem}` is the base filename of the Input_CSV without its extension; IF a file with that name already exists in the Output_Directory, THE Script SHALL overwrite it.
6. IF writing the Labelled_CSV fails, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.

---

### Requirement 7: Silhouette Report Output

**User Story:** As a researcher, I want a single CSV file summarising silhouette scores for all k values, so that I can record and share the cluster selection rationale.

#### Acceptance Criteria

1. WHEN silhouette scoring is complete for all K values, THE Script SHALL write the Silhouette_Report to the Output_Directory.
2. THE Silhouette_Report SHALL contain a header row with the column names `k`, `silhouette_score`, `recommended`, followed by exactly four data rows, one per K value in ascending order of K.
3. THE `silhouette_score` column SHALL contain the Silhouette_Score rounded to four decimal places.
4. THE `recommended` column SHALL contain the value `true` for the recommended K row and `false` for all other rows; WHEN multiple K values tie for the highest score to four decimal places, THE Script SHALL mark the smallest such K as `true`.
5. THE Silhouette_Report file SHALL be named `{input_stem}_silhouette.csv` where `{input_stem}` is the base filename of the Input_CSV without its extension; IF a file with that name already exists, THE Script SHALL overwrite it.
6. IF writing the Silhouette_Report fails, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.

---

### Requirement 8: SVG Visualisation Output

**User Story:** As a researcher, I want an SVG plot for each k run showing cluster assignments, so that I can visually inspect cluster separation and include figures in publications.

#### Acceptance Criteria

1. WHEN a K run completes, THE Script SHALL write one SVG_Plot to the Output_Directory; IF a file with that name already exists, THE Script SHALL overwrite it.
2. THE SVG_Plot SHALL display grains as points in a two-dimensional projection of the Scaled_Feature_Matrix using the first two principal components (PCA), where the PCA is fitted once on the full Scaled_Feature_Matrix and reused for all K runs.
3. THE SVG_Plot SHALL colour-code points by their Cluster_Label using a qualitatively distinct colour palette where each colour differs from every other colour by at least 30 degrees of hue angle in HSL space.
4. THE SVG_Plot SHALL include a legend mapping each colour to its Cluster_Label integer.
5. THE SVG_Plot SHALL include a title stating the K value and the Silhouette_Score rounded to four decimal places (e.g., "k=3 | Silhouette: 0.4821").
6. THE SVG_Plot SHALL label the x-axis "PC1" and the y-axis "PC2".
7. THE SVG_Plot file SHALL be named `{input_stem}_clusters_k{K}.svg`.
8. IF writing the SVG_Plot fails, THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code.

---

### Requirement 9: Silhouette Summary SVG

**User Story:** As a researcher, I want a single SVG plot showing silhouette scores across all k values, so that I can visually identify the optimal k at a glance.

#### Acceptance Criteria

1. WHEN silhouette scoring is complete for all K values, THE Script SHALL write one SVG_Plot to the Output_Directory showing a bar chart with K on the x-axis (labelled "k") and Silhouette_Score on the y-axis (labelled "Silhouette Score") with a fixed y-axis range of [−1, 1], for K ∈ {2, 3, 4, 5}.
2. IF the recommended K bar fill colour differs from the non-recommended bar fill colour, THEN THE Script SHALL annotate each bar with its numeric Silhouette_Score rounded to four decimal places.
3. THE chart SHALL include a title "Silhouette Scores by k".
4. THE summary SVG file SHALL be named `{input_stem}_silhouette.svg`; IF a file with that name already exists, THE Script SHALL overwrite it.
5. IF silhouette scores are unavailable (e.g., due to a prior clustering error), THEN THE Script SHALL print a descriptive error message to stderr and exit with a non-zero exit code rather than writing an empty or partial chart.

---

### Requirement 10: Console Progress Output

**User Story:** As a researcher, I want the script to print progress messages as it runs, so that I know the analysis is proceeding and can estimate completion time.

#### Acceptance Criteria

1. WHEN Input_CSV loading and validation are complete, THE Script SHALL print a message to stdout stating the number of valid grains loaded, the number of invalid or skipped grains, and the Dimensions selected.
2. WHEN k-means clustering completes for a given K, THE Script SHALL print a message to stdout stating K and the resulting Silhouette_Score rounded to four decimal places.
3. WHEN all output files have been written, THE Script SHALL print a completion message to stdout listing each output file path, one path per line.
4. IF clustering fails for a given K (e.g., convergence error or insufficient data), THEN THE Script SHALL print a descriptive error message to stderr naming the K value and the reason, and exit with a non-zero exit code.

---

### Requirement 11: Independence from Main Application

**User Story:** As a researcher, I want the clustering script to be entirely self-contained, so that I can copy it to any machine with a Python environment and run it without installing the Sedimental application.

#### Acceptance Criteria

1. THE Script SHALL import only from the Python standard library and from the packages `numpy`, `pandas`, `scikit-learn`, and `matplotlib`.
2. THE Script SHALL NOT import from any module within the `sedimental` package or any other project-internal module.
3. THE Script SHALL be a single `.py` file located either at the repository root or in a dedicated `analysis/` subdirectory.
4. THE Script SHALL include a `if __name__ == "__main__":` entry-point guard so that it is executable as a standalone script without side effects when imported.
