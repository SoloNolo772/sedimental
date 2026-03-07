---
inclusion: auto
---

# External Dependencies Verification

When implementing code that uses external libraries (ImageGrains, PyImageJ, Napari, scikit-image, etc.), you MUST verify the actual API by inspecting the source repositories before writing integration code.

## Required Verification Steps

Before using any function, class, or module from an external dependency:

1. **Locate the source**: Find the relevant file in the dependency's GitHub repository
2. **Verify the API**: Check function signatures, parameter names, return types, and any required imports
3. **Check version compatibility**: Note any version-specific APIs or deprecations
4. **Document the reference**: Include a comment with the source file path when using non-obvious APIs

## Key Dependencies to Verify

### ImageGrains
- Repository: https://github.com/dmair1989/imagegrains
- Key modules to inspect:
  - Segmentation algorithms and their parameters
  - Input/output formats expected
  - Any Napari-specific vs standalone usage patterns

### PyImageJ
- Repository: https://github.com/imagej/pyimagej
- Documentation: https://py.imagej.net/en/latest/api.html
- Key modules to inspect:
  - `imagej` module initialization (`imagej.init()`)
  - Particle analysis functions
  - Image conversion between numpy and ImageJ formats

### Napari (headless mode)
- Repository: https://github.com/napari/napari
- Verify headless operation requirements
- Check if ImageGrains can run without full Napari GUI

### scikit-image
- Used for image I/O and basic operations
- Verify `skimage.io` functions for JPEG/TIFF handling

## Verification Checklist

When writing code that calls external APIs:

- [ ] Inspected the actual source file in the repository
- [ ] Verified function/class exists and signature matches
- [ ] Checked for any required initialization or context managers
- [ ] Noted any version requirements or deprecation warnings
- [ ] Added source reference comment for non-obvious APIs

## Example Reference Comment

```python
# Source: imagegrains/segmentation/watershed.py
# Verified against commit abc123 (v0.2.0)
from imagegrains.segmentation import watershed_segment
```

## When in Doubt

If the API is unclear or documentation is sparse:
1. Search for usage examples in the repository's tests
2. Check the repository's example notebooks or scripts
3. Look for type hints in the source code
4. Ask the user to clarify expected behavior before proceeding
