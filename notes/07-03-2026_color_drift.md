# Journal: 07-03-2026 - Color Drift Investigation (Final)

## Summary
Investigated color drift correction using ColorShadingFactor from X3F metadata.

## What Was Implemented

### 1. ColorShadingFactor Reading (x3f_meta.c)
Added function `x3f_get_color_shading_factor()` to read the 2x2 ColorShadingFactor matrix from CAMF metadata.

### 2. Color Correction Function (x3f_spatial_gain.c)
Added `x3f_calc_color_shading_correction()` to apply the 2x2 matrix as gradient interpolation.

### 3. Validation Script (tools/validate_color_drift.py)
Created comprehensive validation script that measures:
- Per-channel mean and standard deviation
- 3x3 regional analysis
- Corner vs center delta
- RMSE/MAE against SPP reference

## Key Findings

### Baseline Results (without ColorShadingFactor)
```
Our Output:       R=127, G=121, B=145 (mean=131)
SPP Reference:   R=147, G=147, B=146 (mean=147)

RMSE: 19.57
Max Corner Delta: 13.14 (OURS) vs 20.84 (SPP) - WE'RE BETTER!
```

### Critical Discovery
**Our uniformity is actually BETTER than SPP's!**
- Our max corner delta: 13.14
- SPP max corner delta: 20.84

The issue is NOT spatial uniformity - it's **overall brightness/color balance**:
- R is 20 levels too dark
- G is 26 levels too dark  
- B is correct (145 vs 146)

This is a color matrix issue, not a spatial uniformity issue.

### ColorShadingFactor Tests (Today's Experiments)

Tested applying ColorShadingFactor with different interpretations:

1. **Bilinear interpolation (corner values)**: 
   - Treated [[a,b],[c,d]] as 4 corner offset values
   - Result: Catastrophic - RMSE went from 19.57 to 135 (image almost black)
   - Interpretation WRONG

2. **Gradient interpolation (linear)**:
   - Original approach: R correction = 1.0 + a*col + b*row
   - Result: RMSE increased from 19.57 to 21.78
   - Still makes things worse

### Spatial Gain vs No Spatial Gain

| Metric | With SGain | Without SGain | SPP Reference |
|--------|------------|---------------|----------------|
| Max Corner Delta | 13.14 | 27.74 | 20.84 |
| Mean R | 127 | 125 | 147 |
| Mean G | 121 | 121 | 147 |
| Mean B | 145 | 140 | 146 |

**Key insight**: Spatial gain is WORKING - it reduces corner delta from 27.74 to 13.14.
We are MORE uniform than SPP (13.14 vs 20.84).

### Per-Channel Boost Experiment

Tried adding per-channel boost (R*1.48, G*1.65, B*1.02) before tone curve:
- White paper RMSE: 19.57 → 6.23 (nearly perfect color balance!)
- But: Other images (e.g., _P2M0927) had DeltaE explode from ~70 to ~169

**Conclusion**: A fixed per-channel boost works for white paper but breaks natural scenes.

### Root Cause Confirmed

The "color drift" the user sees is NOT about spatial uniformity - it's about:
1. **Overall G channel too dark** (121 vs 147 = -18%)
2. **Overall R channel too dark** (127 vs 147 = -14%)
3. B channel is nearly correct (145 vs 146)

The solution requires fixing the **ROOT CAUSE** - the color matrix computation in x3f_process.c uses WhiteBalanceColorCorrections incorrectly for Merrill cameras.

## What Was Tried

1. ❌ ColorShadingFactor bilinear interpretation - makes things worse
2. ❌ ColorShadingFactor gradient interpretation - makes things worse  
3. ❌ Per-channel boost before tone curve - breaks other images
4. ✅ Existing spatial gain - already working correctly

## Conclusion

1. ColorShadingFactor from metadata does NOT help (makes RMSE worse)
2. Existing spatial gain is working correctly (we're more uniform than SPP)
3. The issue is global color balance - G channel needs ~21% boost
4. But a fixed boost breaks other images - need ROOT CAUSE fix (color matrix)

## Root Cause (from earlier analysis)

The color matrix computation uses `WhiteBalanceColorCorrections` incorrectly:
- These are color CORRECTION matrices, not conversion matrices
- Merrill files don't have `WhiteBalanceIlluminants` needed for proper conversion
- The result is wrong raw→XYZ→sRGB conversion causing color imbalance

## Next Steps

1. Research proper Merrill-specific color matrix (not available in metadata)
2. Try computing a fixed color matrix that works across all images
3. Consider per-scene white balance adaptation (complex)
