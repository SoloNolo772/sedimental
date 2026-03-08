# Sedimental Test Suite

This directory contains the test suite for the Sedimental Analysis Tool, including both unit tests and property-based tests.

## Running Tests

### Option 1: Using the convenience script (Recommended)

**Windows:**
```bash
run-tests.bat
```

**Linux/Mac:**
```bash
./run-tests.sh
```

### Option 2: Using docker-compose directly

Build the image and run all tests:
```bash
docker-compose build
docker-compose run --rm sedimental test tests/ -v
```

Run specific test file:
```bash
docker-compose run --rm sedimental test tests/test_metadata_merge.py -v
```

Run with specific pytest options:
```bash
docker-compose run --rm sedimental test tests/ -v --tb=short -k "merge"
```

### Option 3: Interactive testing in container

Start a shell inside the container:
```bash
docker-compose run --rm sedimental shell
```

Then run tests interactively:
```bash
pytest tests/ -v
pytest tests/test_metadata_merge.py::TestMetadataMergePrecedence::test_override_fields_take_precedence -v
```

## Test Structure

### Property-Based Tests

Property-based tests use [Hypothesis](https://hypothesis.readthedocs.io/) to generate random test cases and verify universal properties of the code.

- **Minimum iterations**: 100 per property test (configurable via Hypothesis settings)
- **Strategy**: Generate arbitrary `SampleMetadata` instances with random field values
- **Coverage**: Tests verify correctness across the entire input space, not just specific examples

### Current Tests

#### `test_metadata_merge.py`
- **Property 14: Metadata Merge Precedence**
- **Validates**: Requirements 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10
- **Tests**:
  - Override fields take precedence over defaults
  - Default fields preserved when override is None
  - Custom fields merged correctly with override precedence
  - Merge operation is idempotent
  - Edge cases: empty override, empty default
  - Concrete examples for documentation

## Pytest Options

Useful pytest command-line options:

- `-v` or `--verbose`: Verbose output showing each test
- `-vv`: Extra verbose (shows full diff on failures)
- `--tb=short`: Shorter traceback format
- `--tb=long`: Full traceback format
- `-k EXPRESSION`: Run tests matching the expression (e.g., `-k "merge"`)
- `-x`: Stop on first failure
- `--maxfail=N`: Stop after N failures
- `--lf`: Run last failed tests
- `--ff`: Run failed tests first, then others
- `-s`: Don't capture output (show print statements)

## Hypothesis Options

Configure Hypothesis behavior via pytest options:

- `--hypothesis-show-statistics`: Show detailed statistics about generated examples
- `--hypothesis-seed=SEED`: Use specific random seed for reproducibility
- `--hypothesis-verbosity=LEVEL`: Set verbosity (quiet, normal, verbose, debug)

Example:
```bash
docker-compose run --rm sedimental test tests/test_metadata_merge.py --hypothesis-show-statistics
```

## Writing New Tests

### Property-Based Test Template

```python
from hypothesis import given, strategies as st
from sedimental.models import SampleMetadata

@given(metadata=sample_metadata_strategy())
def test_my_property(metadata):
    """
    Property: Describe the universal property being tested.
    
    Validates: Requirements X.Y, X.Z
    """
    # Perform operation
    result = some_operation(metadata)
    
    # Assert property holds
    assert some_invariant(result)
```

### Unit Test Template

```python
def test_specific_behavior():
    """Test a specific concrete example."""
    # Arrange
    input_data = create_test_data()
    
    # Act
    result = function_under_test(input_data)
    
    # Assert
    assert result == expected_value
```

## Continuous Integration

Tests should be run:
- Before committing code changes
- In CI/CD pipeline on every push
- Before deploying to production

## Troubleshooting

### Tests fail with import errors
Make sure the Docker image is built with the latest code:
```bash
docker-compose build --no-cache
```

### Tests are slow
Property-based tests run 100+ iterations by default. For faster feedback during development:
```bash
# Run with fewer examples (not recommended for CI)
docker-compose run --rm sedimental test tests/ --hypothesis-profile=dev
```

### Need to debug a specific test
Use the interactive shell and add breakpoints:
```bash
docker-compose run --rm sedimental shell
pytest tests/test_metadata_merge.py::test_name -s --pdb
```
