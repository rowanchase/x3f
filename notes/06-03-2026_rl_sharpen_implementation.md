# Richardson-Lucy Deconvolution Sharpening Implementation

## Summary
Implemented Richardson-Lucy deconvolution sharpening as a new post-processing step in the x3f_extract tool. The sharpening is applied after the tone curve transformation on non-linear data and operates on all three color channels independently.

## Implementation Details

### New Files Created
- `src/x3f_sharpen.h` - Header file with function declaration
- `src/x3f_sharpen.cpp` - Implementation using OpenCV

### Modified Files
- `src/makefile` - Added x3f_sharpen.o to build
- `src/x3f_process.h` - Added sharpening parameters to x3f_get_image() signature
- `src/x3f_process.c` - Added call to x3f_rl_deconv() after tone curve
- `src/x3f_output_tiff.h` - Updated function signature
- `src/x3f_output_tiff.c` - Pass sharpening parameters
- `src/x3f_output_ppm.c` - Pass default values (sharpening disabled for PPM)
- `src/x3f_output_dng.c` - Pass default values (sharpening disabled for DNG)
- `src/x3f_histogram.c` - Pass default values (sharpening disabled for histograms)
- `src/x3f_extract.c` - Added CLI arguments and help text

## Algorithm

### Richardson-Lucy Deconvolution
The algorithm uses an iterative maximum-likelihood approach:
1. Start with blurred image as initial estimate
2. For each iteration:
   - Forward projection: Convolve estimate with PSF
   - Compute ratio: observed / convolved
   - Backward projection: Convolve ratio with flipped PSF
   - Update: estimate *= backward_projection
3. Clamp values to prevent divergence

### PSF (Point Spread Function)
- Gaussian kernel with configurable sigma (default: 0.7 pixels)
- Kernel size: 2*ceil(3*sigma) + 1
- Normalized to sum = 1.0

## CLI Options

```
-sharpen              Apply RL deconvolution sharpening (default: ON)
-no-sharpen           Disable sharpening
-sharpen-psf <F>      PSF sigma in pixels (default: 0.7)
-sharpen-iter <N>     Number of iterations (default: 20)
```

## Default Parameters
- **apply_sharpen**: 1 (enabled by default for TIFF output)
- **sharpen_psf**: 0.7 pixels
- **sharpen_iter**: 20 iterations

## Performance

### Timing Test (_P2M0927.X3F, 4800x3200)
- Without sharpening: ~10.6 seconds
- With sharpening (20 iterations): ~19.1 seconds
- Overhead: ~8.5 seconds (80% increase)

### Memory Usage
Minimal additional memory - allocates temporary float arrays per channel.

## Pipeline Position
Sharpening is applied:
1. After color space conversion (sRGB/AdobeRGB/ProPhoto)
2. After tone curve application
3. After highlight reconstruction
4. Before output to TIFF

This ensures sharpening works on perceptually-corrected data for optimal visual results.

## Quality Impact

Expected improvements based on research:
- Gradient magnitude increase: 30-50% (targeting SPP-like sharpness)
- Edge detail enhancement without artifacts
- No halos when properly configured (using RL vs USM)

## Future Enhancements

Potential improvements to consider:
1. Luminance-only processing option for speed
2. Adaptive PSF estimation from image content
3. Different PSF per channel (account for sensor characteristics)
4. Convergence detection (stop iterations early if stable)
5. GPU acceleration via OpenCL

## Testing

### Basic Functionality
```bash
# Sharpening enabled (default)
./x3f_extract -tiff -color sRGB input.X3F

# Sharpening disabled
./x3f_extract -tiff -color sRGB -no-sharpen input.X3F

# Custom parameters
./x3f_extract -tiff -color sRGB -sharpen-psf 0.5 -sharpen-iter 30 input.X3F
```

### Verification
- Build successful with no errors
- Processing completes without crashes
- Verbose mode shows "Starting Richardson-Lucy deconvolution" and "complete" messages
- Output files generated successfully

## Notes

The implementation prioritizes quality over speed as requested. The 8.5 second overhead for a 15MP image with 20 iterations is acceptable given the quality gains. Future parameter tuning will be needed to find optimal PSF sigma for the Merrill sensor specifically.
