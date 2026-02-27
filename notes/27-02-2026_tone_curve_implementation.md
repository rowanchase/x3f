# Log-Like Tone Curve Implementation

**Date:** 2026-02-27

## Summary

Successfully replaced the problematic 2.5x boost + gamma LUT pipeline with a log-like tone curve that:
- Lifts shadows and mid-tones to usable brightness levels
- Preserves highlight detail with soft compression
- Eliminates the triple-compression issue that was destroying Phase 2b reconstructed highlights

## Implementation Details

### Files Modified

1. **src/x3f_matrix.c**
   - Added `x3f_log_tone_curve_LUT()` function (pre-computed LUT generator)
   - Added `x3f_apply_tone_curve()` function (applies curve to RGB values)

2. **src/x3f_matrix.h**
   - Added declarations for new tone curve functions

3. **src/x3f_process.c**
   - Modified `convert_data()` to apply tone curve (when enabled)
   - Modified `x3f_get_preview()` to apply tone curve to preview
   - Disabled the 2.5x boost (commented out)
   - Replaced direct 16-bit quantization with tone curve processing

4. **src/x3f_process.h**
   - Added `use_tone_curve` parameter to `x3f_get_image()` and `x3f_get_preview()`

5. **src/x3f_output_tiff.c**
   - Updated to accept and pass `use_tone_curve` parameter

6. **src/x3f_output_tiff.h**
   - Updated function signature

7. **src/x3f_output_ppm.c, src/x3f_output_dng.c, src/x3f_histogram.c**
   - Updated to pass default tone curve values (1 for PPM/preview, 0 for DNG/histogram)

8. **src/x3f_extract.c**
   - Added `-no-tone-curve` command-line option
   - Added help text for the new option
   - Pass `use_tone_curve` flag through the processing pipeline

### Tone Curve Formula

```c
/* Log curve for shadows/mid-tones */
y = log(1 + x*(e^k - 1)) / k

/* Soft highlight compression for x > highlight_knee */
if (x > highlight_knee) {
    t = (x - highlight_knee) / (1 - highlight_knee)
    compressed = highlight_knee + (1 - highlight_knee) * (t / (t + 0.5))
    blend = t * t  /* Quadratic blend factor */
    y = y * (1-blend) + compressed * blend
}
```

**Current Parameters:**
- `shadow_boost = 4.0` (aggressive shadow/mid-tone lift)
- `highlight_knee = 0.90` (compression starts at 90%)

### Results

**Histogram Distribution (8-bit equivalent):**

| Variant | Mean | Shadows (0-49) | Midtones (50-199) | Soft HL (200-229) | Hard HL (230-255) |
|---------|------|----------------|-------------------|-------------------|-------------------|
| SPP Reference | 0.4656 | 3.2% | 91.0% | 3.5% | 2.4% |
| **Tone Curve (k=4.0)** | **0.3931** | **3.1%** | **96.1%** | **0.7%** | **0.1%** |
| No Tone Curve | 0.0846 | 92-96% | 3.6-7.6% | 0.0-0.1% | 0.2% |

**Key Observations:**
- Mean brightness is ~84% of SPP (0.3931 vs 0.4656)
- Shadow/mid-tone distribution closely matches SPP
- Highlights are more compressed than SPP (less soft/hard highlights)
- But highlights are preserved and look natural, not clipped

## Usage

### Default (Tone Curve Enabled)
```bash
./bin/linux-x86_64/x3f_extract -tiff -o output input.X3F
```

### Disable Tone Curve (Raw Output)
```bash
./bin/linux-x86_64/x3f_extract -tiff -no-tone-curve -o output input.X3F
```

## Future Improvements

1. **Tune highlight compression:** Currently we're compressing highlights more aggressively than SPP. We could reduce the highlight compression to allow more values in the 200-255 range.

2. **Make shadow_boost configurable:** Add a command-line option to adjust the curve strength (e.g., `-tone-curve-strength <1.0-5.0>`).

3. **Per-channel tone curves:** Consider applying slightly different curves to each channel to better match SPP's color handling.

## Testing Notes

The user reported that the tone curve output with k=4.0 produces "very impressive looking images, superior in fact to the SPP file" when viewed with highlight information preserved.

The `-no-tone-curve` option allows raw output for external editing in tools like Darktable where users can apply their own tone curves.
