# Log File Environment Variable Bugfix Design

## Overview

This bugfix addresses the issue where the `SEDIMENTAL_LOG_FILE` environment variable is defined in `docker-compose.yml` but never read by the application. The `configure_logging()` function in `sedimental/logging.py` already supports a `log_file` parameter, but neither the CLI nor the web server reads the environment variable to pass it to the logging configuration.

The fix requires minimal changes: updating `cli.py` to read the environment variable and pass it to `configure_logging()`, and updating `web.py` to call `configure_logging()` with the environment variable value at startup.

## Glossary

- **Bug_Condition (C)**: The condition where `SEDIMENTAL_LOG_FILE` is set but the application does not create a log file
- **Property (P)**: The desired behavior where logs are written to the file specified by `SEDIMENTAL_LOG_FILE`
- **Preservation**: Existing logging behavior (stdout logging, verbose flag handling) that must remain unchanged
- **configure_logging()**: The function in `sedimental/logging.py` that sets up logging handlers, already supports `log_file` parameter
- **SEDIMENTAL_LOG_FILE**: Environment variable specifying the path where logs should be written

## Bug Details

### Bug Condition

The bug manifests when the `SEDIMENTAL_LOG_FILE` environment variable is set and either the CLI `process` command is executed or the web server is started. The application ignores the environment variable and does not create a log file.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ApplicationStartup
  OUTPUT: boolean
  
  RETURN os.environ.get("SEDIMENTAL_LOG_FILE") IS NOT None
         AND (input.mode == "cli_process" OR input.mode == "web_server")
         AND log_file_not_created(os.environ.get("SEDIMENTAL_LOG_FILE"))
END FUNCTION
```

### Examples

- **CLI with env var set**: `SEDIMENTAL_LOG_FILE=/data/output/sedimental.log` is set, user runs `sedimental process input.jpg -o results.csv` → Expected: logs written to `/data/output/sedimental.log`, Actual: no log file created
- **Web server with env var set**: `SEDIMENTAL_LOG_FILE=/data/output/sedimental.log` is set, web server starts → Expected: logs written to `/data/output/sedimental.log`, Actual: no log file created
- **Web server logging unconfigured**: Web server starts → Expected: `configure_logging()` called, Actual: logging never configured
- **CLI without env var**: `SEDIMENTAL_LOG_FILE` not set, user runs CLI → Expected: logs only to stdout (no change needed)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Logging to stdout must continue to work exactly as before
- The `--verbose` flag must continue to set log level to DEBUG
- CLI exit codes must remain unchanged (0 for success, 1 for failure)
- Web server health check endpoints must continue to respond correctly
- `configure_logging()` must continue to work when called with only the `verbose` parameter

**Scope:**
All inputs that do NOT involve the `SEDIMENTAL_LOG_FILE` environment variable should be completely unaffected by this fix. This includes:
- CLI execution without `SEDIMENTAL_LOG_FILE` set
- Web server startup without `SEDIMENTAL_LOG_FILE` set
- All existing logging behavior to stdout
- All existing CLI argument handling

## Hypothesized Root Cause

Based on the bug description, the root causes are:

1. **CLI does not read environment variable**: The `run_process_internal()` function in `cli.py` calls `configure_logging(verbose=...)` but does not read `SEDIMENTAL_LOG_FILE` from the environment and pass it as the `log_file` parameter.

2. **Web server does not call configure_logging()**: The `main()` function in `web.py` starts the uvicorn server but never calls `configure_logging()` at all, leaving logging unconfigured.

3. **No environment variable reading code exists**: Neither `cli.py` nor `web.py` contains any code to read `os.environ.get("SEDIMENTAL_LOG_FILE")`.

## Correctness Properties

Property 1: Bug Condition - Log File Created When Env Var Set

_For any_ application startup where `SEDIMENTAL_LOG_FILE` environment variable is set to a valid path, the fixed application SHALL create a log file at that path and write log messages to it in addition to stdout.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Behavior Without Env Var

_For any_ application startup where `SEDIMENTAL_LOG_FILE` environment variable is NOT set, the fixed application SHALL produce exactly the same logging behavior as the original application, logging only to stdout without errors.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

**File**: `sedimental/cli.py`

**Function**: `run_process_internal()`

**Specific Changes**:
1. **Import Path from pathlib**: Already imported, no change needed
2. **Read environment variable**: Add `log_file_env = os.environ.get("SEDIMENTAL_LOG_FILE")` before calling `configure_logging()`
3. **Convert to Path if set**: If `log_file_env` is not None, convert to `Path(log_file_env)`
4. **Pass to configure_logging()**: Update the call to `configure_logging(verbose=..., log_file=...)`

**File**: `sedimental/web.py`

**Function**: `main()`

**Specific Changes**:
1. **Import configure_logging**: Add `from .logging import configure_logging` to imports
2. **Read environment variable**: Add `log_file_env = os.environ.get("SEDIMENTAL_LOG_FILE")` in `main()`
3. **Convert to Path if set**: If `log_file_env` is not None, convert to `Path(log_file_env)`
4. **Call configure_logging()**: Add call to `configure_logging(log_file=...)` before starting uvicorn

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that set `SEDIMENTAL_LOG_FILE` environment variable and verify whether a log file is created. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **CLI Log File Test**: Set `SEDIMENTAL_LOG_FILE`, run CLI process command, check if log file exists (will fail on unfixed code)
2. **Web Server Log File Test**: Set `SEDIMENTAL_LOG_FILE`, start web server, check if log file exists (will fail on unfixed code)
3. **Web Server Logging Configured Test**: Start web server, verify `configure_logging()` was called (will fail on unfixed code)

**Expected Counterexamples**:
- Log file is not created when `SEDIMENTAL_LOG_FILE` is set
- Possible causes: environment variable not read, `log_file` parameter not passed to `configure_logging()`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := start_application_fixed(input)
  ASSERT log_file_exists(os.environ.get("SEDIMENTAL_LOG_FILE"))
  ASSERT log_file_contains_entries(os.environ.get("SEDIMENTAL_LOG_FILE"))
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT start_application_original(input).stdout_logs = start_application_fixed(input).stdout_logs
  ASSERT start_application_original(input).exit_code = start_application_fixed(input).exit_code
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for CLI execution without env var and web server without env var, then write property-based tests capturing that behavior.

**Test Cases**:
1. **CLI Without Env Var Preservation**: Verify CLI logs to stdout and returns correct exit codes when `SEDIMENTAL_LOG_FILE` is not set
2. **Verbose Flag Preservation**: Verify `--verbose` flag continues to set DEBUG log level
3. **Web Server Health Check Preservation**: Verify health endpoints continue to work correctly
4. **configure_logging() API Preservation**: Verify calling `configure_logging(verbose=True)` without `log_file` continues to work

### Unit Tests

- Test that `SEDIMENTAL_LOG_FILE` is read from environment in CLI
- Test that `SEDIMENTAL_LOG_FILE` is read from environment in web server
- Test that log file is created when env var is set
- Test that logs are written to both stdout and file when env var is set
- Test that behavior is unchanged when env var is not set

### Property-Based Tests

- Generate random valid file paths and verify log files are created at those paths
- Generate random CLI arguments and verify preservation of exit codes and stdout logging
- Test that verbose flag behavior is preserved across many configurations

### Integration Tests

- Test full CLI workflow with `SEDIMENTAL_LOG_FILE` set inside Docker container
- Test web server startup with `SEDIMENTAL_LOG_FILE` set inside Docker container
- Test that log file contains expected log entries after processing
