We are developing and testing inside the running docker container for this project, not locally.

## Running Tests

Both `sedimental/` and `tests/` are mounted as volumes into the container, so code changes are picked up immediately without rebuilding. To run a test file, just use:

```
docker compose run --rm sedimental test tests/test_logging.py -v
```

## When to run `docker compose build`

Only run `docker compose build` when:
- `requirements.txt` has changed (new or updated Python packages)
- `Dockerfile` has changed
- The image does not exist yet on this machine

Do NOT run `docker compose build` just because source code or test files changed — the volume mounts handle that automatically.
