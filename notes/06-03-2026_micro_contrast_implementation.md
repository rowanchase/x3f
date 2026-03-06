# Micro-Contrast Enhancement Implementation

## Date: March 6, 2026

## Overview
Implemented micro-contrast enhancement for the x3f_extract tool using Gaussian blur-based base/detail separation. This feature enhances fine detail and texture in images.

## Algorithm: Gaussian Blur Detail Enhancement

**How it works:**
1. Apply Gaussian blur with specified radius (default 8px) to create smooth base layer
2. Extract detail layer by subtracting base from original image
3. Enhance detail layer by multiplying by amount factor (default 1.3 = 30% boost)
4. Reconstruct output by adding enhanced detail back to base
5. Clamp values to valid range [0, 65535]

**Key characteristics:**
- **Fast:** Gaussian blur is highly optimized in OpenCV
- **Effective:** Actually separates base and detail layers (unlike guided filter)
- **Fine-scale:** Enhances micro-contrast (texture/detail) not large-scale transitions
- **Full RGB:** Processes all three channels independently

**Implementation Note:** Initially tried guided filter but it failed to separate base/detail for 16-bit data (output ≈ input). Switched to Gaussian blur which reliably creates separation.

## Implementation Details

### New Files
- `src/x3f_contrast.h` - Header with function declarations
- `src/x3f_contrast.cpp` - Implementation using OpenCV GaussianBlur

### Modified Files
- `src/x3f_process.h` - Added micro-contrast parameters to x3f_get_image()
- `src/x3f_process.c` - Added include and call to x3f_micro_contrast()
- `src/x3f_output_tiff.h/c` - Updated to pass micro-contrast parameters
- `src/x3f_output_ppm.c` - Added default disabled values
- `src/x3f_output_dng.c` - Added default disabled values  
- `src/x3f_histogram.c` - Added default disabled values
- `src/x3f_extract.c` - Added CLI arguments and help text
- `src/makefile` - Added x3f_contrast.o to build

### Pipeline Position
Applied AFTER Richardson-Lucy sharpening, before output:
```
Color Conversion -> Tone Curve -> RL Sharpening -> Micro-Contrast -> Output
```

This ordering ensures sharpening defines edges first, then micro-contrast enhances surface detail.

## CLI Arguments

```
-no-micro-contrast    Disable micro-contrast (default is ON)
-micro-contrast       Enable micro-contrast (default)
-mc-radius <R>        Filter radius in pixels (default: 8.0, range: 3-20)
-mc-amount <A>        Enhancement amount (default: 1.3, range: 1.0-3.0+)
```

**Note:** Epsilon parameter removed - not needed for Gaussian blur approach

## Default Settings

```cpp
apply_micro_contrast = 1    // ON by default
mc_radius = 8.0            // Fine micro-contrast scale
mc_amount = 1.3            // 30% boost - noticeable but natural
```

These settings should:
- Enhance texture and fine detail (fabric, foliage, skin)
- Maintain natural appearance without artifacts
- Work well with RL sharpening

## Testing

Build successful with no errors (only expected warnings about signed/unsigned comparisons).

Tested with reference file _P2M0927.X3F:
- ✅ Default (micro-contrast ON): Processed successfully
- ✅ With -no-micro-contrast: Processed successfully  
- ✅ With -mc-amount 3.5: Dramatic effect visible (detail amplified 350%)
- ✅ Output file size correct (85MB for 4800x3200 16-bit RGB TIFF)

## Technical Details

**Gaussian blur sigma calculation:**
```cpp
sigma = radius / 3.0
```
- Radius 8px → sigma ~2.7
- This creates effective base/detail separation

**Why Gaussian blur works better than guided filter:**
- Guided filter with self-guidance: output ≈ input, detail ≈ 0 (no effect)
- Gaussian blur: definitely creates smooth base layer, detail = input - base
- Even with amount=1.0, you get unsharp mask effect

## Quality Characteristics

**Strengths:**
- Actually works (unlike guided filter approach)
- Fast execution (OpenCV optimized)
- Simple and predictable
- Easy to tune

**Trade-offs:**
- May create slight halos at strong edges (amount > 2.0)
- Not edge-aware like guided filter would be (if it worked)

**Best for:**
- Enhancing fine detail in surfaces (fabric, foliage, skin texture)
- Increasing "clarity" without affecting large-scale contrast
- Complementing edge-sharpening (RL deconvolution)

## Comparison to Other Algorithms

| Algorithm | Speed | Halos | Quality | Works? |
|-----------|-------|-------|---------|---------|
| Gaussian Blur | Fast | Slight | Good | ✅ Yes |
| Guided Filter | Fast | No | Good | ❌ No (self-guidance issue) |
| Bilateral Filter | Slow | No | Good | ✅ Yes (but slower) |
| DoG | Fast | Some | Medium | ✅ Yes |
| Local Laplacian | Very Slow | No | Excellent | ✅ Yes (complex) |

**We chose Gaussian Blur** because:
- Actually creates base/detail separation
- Fast and simple
- User confirmed it works with amount=3.5

## Tuning Guidelines

**Radius:** 3-20 pixels
- Smaller (3-6): Very fine micro-contrast, subtle effect
- Default (8): Good balance
- Larger (12-20): Broader detail enhancement, more "clarity" effect

**Amount:** 1.0-3.0+
- 1.0: No effect (neutral)
- 1.3: Default (30% boost) - natural enhancement
- 2.0: Strong effect - noticeable clarity boost
- 3.0+: Very aggressive - dramatic detail enhancement, may show halos

## Integration Complete

✅ All components implemented and tested
✅ Build successful
✅ CLI interface working
✅ Algorithm verified working by user (amount=3.5 produces visible effect)
✅ Ready for use

## Version History

- **Initial implementation:** Guided filter (didn't work - no visible effect)
- **Fixed implementation:** Switched to Gaussian blur (works correctly)
