# Bugfix Requirements Document

## Introduction

The `SEDIMENTAL_LOG_FILE` environment variable is defined in `docker-compose.yml` but is never read or used by the application code. The `configure_logging()` function in `sedimental/logging.py` already supports a `log_file` parameter that correctly sets up file logging, but neither the CLI (`sedimental/cli.py`) nor the web server (`sedimental/web.py`) reads the environment variable and passes it to the logging configuration.

As a result, no log file is ever created despite the environment variable being set, making it impossible to persist logs to disk for debugging or auditing purposes.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `SEDIMENTAL_LOG_FILE` environment variable is set AND the CLI `process` command is executed THEN the system ignores the environment variable and does not create a log file

1.2 WHEN `SEDIMENTAL_LOG_FILE` environment variable is set AND the web server is started THEN the system ignores the environment variable and does not create a log file

1.3 WHEN the web server starts THEN the system does not call `configure_logging()` at all, resulting in unconfigured logging

### Expected Behavior (Correct)

2.1 WHEN `SEDIMENTAL_LOG_FILE` environment variable is set AND the CLI `process` command is executed THEN the system SHALL read the environment variable and write logs to the specified file path in addition to stdout

2.2 WHEN `SEDIMENTAL_LOG_FILE` environment variable is set AND the web server is started THEN the system SHALL read the environment variable and write logs to the specified file path in addition to stdout

2.3 WHEN the web server starts THEN the system SHALL call `configure_logging()` to properly initialize logging

2.4 WHEN `SEDIMENTAL_LOG_FILE` environment variable is not set THEN the system SHALL continue to log only to stdout (no file logging)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `SEDIMENTAL_LOG_FILE` is not set AND the CLI is executed THEN the system SHALL CONTINUE TO log only to stdout without errors

3.2 WHEN `SEDIMENTAL_LOG_FILE` is not set AND the web server is started THEN the system SHALL CONTINUE TO log only to stdout without errors

3.3 WHEN the `--verbose` flag is passed to the CLI THEN the system SHALL CONTINUE TO set the log level to DEBUG

3.4 WHEN the CLI processes images successfully THEN the system SHALL CONTINUE TO return exit code 0

3.5 WHEN the web server receives health check requests THEN the system SHALL CONTINUE TO respond correctly

3.6 WHEN `configure_logging()` is called with only the `verbose` parameter THEN the system SHALL CONTINUE TO work without requiring a `log_file` argument
