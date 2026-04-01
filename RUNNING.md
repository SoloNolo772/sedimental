# Running Sedimental

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- WSL2 backend enabled in Docker Desktop (Settings → General → "Use the WSL 2 based engine")
- NVIDIA GPU driver 525+ installed (for GPU acceleration)

---

## First-time setup

Build the Docker image once before first use, or after any changes to `Dockerfile` or `requirements.txt`:

```powershell
docker compose build
```

This takes several minutes on first run (downloads CUDA base image and PyTorch).

---

## Web Interface

### Start the server

```powershell
docker compose up
```

### Open in browser

```
http://localhost:8080
```

### Stop the server

Press `Ctrl+C` in the terminal, or from a separate terminal:

```powershell
docker compose down
```

---

## CLI (batch processing)

Place your JPEG images in the `data/input/` folder, then run:

```powershell
# Process a single image
docker compose run --rm sedimental process /data/input/sample.jpg -o /data/output/results.csv

# Process all JPEGs in the input directory
docker compose run --rm sedimental process /data/input -o /data/output/results.csv

# With segmentation masks saved as TIFF files
docker compose run --rm sedimental process /data/input -o /data/output/results.csv --save-masks

# With scale calibration (pixels per millimeter)
docker compose run --rm sedimental process /data/input -o /data/output/results.csv --scale 4.5

# With verbose logging
docker compose run --rm sedimental process /data/input -o /data/output/results.csv -v
```

### Output locations

| File | Location |
|------|----------|
| CSV results | `data/output/results.csv` |
| TIFF masks | `data/output/masks/` |
| Log file | `data/output/sedimental.log` |

---

## Optional metadata file

Drop a `metadata.json` in `data/input/` to attach sample information:

```json
{
  "default": {
    "sample_id": "my-sample",
    "location": { "lat": 36.1, "lon": -112.1 },
    "capture_date": "2026-04-01",
    "scale_ppm": 4.5
  },
  "images": {
    "sample_A.jpg": { "sample_id": "sample-A-override" }
  }
}
```

---

## GPU configuration

GPU acceleration is enabled by default via the `SEDIMENTAL_USE_GPU=true` environment variable in `docker-compose.yml`.

To disable GPU and fall back to CPU, change that line to:

```yaml
- SEDIMENTAL_USE_GPU=false
```

To verify your GPU is being used:

```powershell
docker compose run --rm --entrypoint python sedimental -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"
```

---

## Rebuilding

Only rebuild when `Dockerfile` or `requirements.txt` change:

```powershell
docker compose build
```

Source code changes in `sedimental/` are picked up automatically via volume mounts — no rebuild needed.
