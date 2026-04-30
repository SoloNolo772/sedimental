# Implementation Plan

## Overview

This task list implements the fix for the `SEDIMENTAL_LOG_FILE` environment variable bug. The fix ensures that when the environment variable is set, logs are written to the specified file path in addition to stdout.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Log File Not Created When Env Var Set
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases where `SEDIMENTAL_LOG_FILE` is set
  - Create test file `tests/test_log_file_env_var.py`
  - Test that when `SEDIMENTAL_LOG_FILE` is set and CLI `run_process_internal()` is called, a log file is created at the specified path
  - Test that when `SEDIMENTAL_LOG_FILE` is set and web server `main()` is called, logging is configured with the file path
  - Use `monkeypatch` to set the environment variable and `tmp_path` for the log file location
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found: "Log file is not created when SEDIMENTAL_LOG_FILE is set"
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Behavior Without Env Var Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for cases where `SEDIMENTAL_LOG_FILE` is NOT set
  - Add preservation tests to `tests/test_log_file_env_var.py`
  - Test that CLI logs to stdout and returns correct exit codes when `SEDIMENTAL_LOG_FILE` is not set
  - Test that `--verbose` flag continues to set DEBUG log level
  - Test that `configure_logging(verbose=True)` without `log_file` continues to work
  - Test that web server health endpoints continue to respond correctly
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Fix for SEDIMENTAL_LOG_FILE environment variable not being read

  - [x] 3.1 Update CLI to read SEDIMENTAL_LOG_FILE environment variable
    - In `sedimental/cli.py`, modify `run_process_internal()` function
    - Add `log_file_env = os.environ.get("SEDIMENTAL_LOG_FILE")` before calling `configure_logging()`
    - Convert to Path if set: `log_file = Path(log_file_env) if log_file_env else None`
    - Update the call to `configure_logging(verbose=getattr(args, "verbose", False), log_file=log_file)`
    - _Bug_Condition: isBugCondition(input) where SEDIMENTAL_LOG_FILE is set and mode is cli_process_
    - _Expected_Behavior: Log file created at specified path, logs written to both stdout and file_
    - _Preservation: CLI without env var continues to log only to stdout_
    - _Requirements: 2.1, 2.4_

  - [x] 3.2 Update web server to call configure_logging() with SEDIMENTAL_LOG_FILE
    - In `sedimental/web.py`, add import: `from .logging import configure_logging`
    - In `main()` function, before starting uvicorn, add:
      - `log_file_env = os.environ.get("SEDIMENTAL_LOG_FILE")`
      - `log_file = Path(log_file_env) if log_file_env else None`
      - `configure_logging(log_file=log_file)`
    - _Bug_Condition: isBugCondition(input) where SEDIMENTAL_LOG_FILE is set and mode is web_server_
    - _Expected_Behavior: configure_logging() called, log file created at specified path_
    - _Preservation: Web server without env var continues to log only to stdout_
    - _Requirements: 2.2, 2.3, 2.4_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Log File Created When Env Var Set
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Behavior Without Env Var Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to ensure no regressions: `docker compose run --rm sedimental test tests/test_log_file_env_var.py -v`
  - Run existing logging tests to verify no regressions: `docker compose run --rm sedimental test tests/test_logging.py -v`
  - Ensure all tests pass, ask the user if questions arise
