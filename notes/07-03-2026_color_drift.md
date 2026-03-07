# Journal: 07-03-2026 - Color Drift Investigation

## Summary
Investigated color drift correction using ColorShadingFactor from X3F metadata.

## What Was Implemented

### 1. ColorShadingFactor Reading (x3f_meta.c)
Added function `x3f_get_color_shading_factor()` to read the 2x2 ColorShadingFactor matrix from CAMF metadata.

### 2. Color Correction Function (x3f_spatial_gain.c)
Added `x3f_calc_color_shading_correction()` to apply bilinear interpolation of the 2x2 matrix for per-pixel color correction.

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

### ColorShadingFactor Tests
Tested applying ColorShadingFactor - it made things WORSE:
- RMSE increased from 19.57 to ~22
- The 2x2 matrix interpretation appears wrong

## Conclusion

The "color drift" the user sees is likely due to:
1. Overall brightness being wrong (G channel too dark)
2. The G channel needs ~21% boost relative to current processing

The ColorShadingFactor from metadata is not the solution for this particular camera's issue.

## Next Steps

1. Investigate color matrix/brightness issue separately
2. Consider whether ColorShadingFactor might work for OTHER cameras
3. The validation script is useful for future work
