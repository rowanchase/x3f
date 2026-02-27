# Option 4 Results: Post-Matrix Corrections Disabled

## Changes Made
Wrapped the following post-matrix corrections in `#if 0` / `#endif` in `src/x3f_process.c`:
- Green reduction (0.895 factor)
- Blue boost (1.06 factor) 
- Red boost (1.17 factor)
- Global desaturation (0.62 factor)

Shadow and highlight desaturation remain enabled (noise reduction features).

## Test Results - _P2M0994.X3F

### Color Metrics (DeltaE)
- **Mean DeltaE:** 15.52 (lower is better)
- **Median DeltaE:** 3.89
- **95th percentile:** 81.33

### Per-Channel MAE
- **Red:** 24.72 (too dark)
- **Green:** 19.16 (too dark)
- **Blue:** 14.07 (closest to reference)

### Key Observations
1. **Blue cast reduced:** Blue channel MAE is now lowest (14.07 vs 24.72 for red)
2. **All channels too dark:** Negative mean errors indicate overall underexposure
3. **Midtones worst affected:** Mean DeltaE in midtones = 97.55 (very high)
4. **Shadows reasonable:** Mean DeltaE in shadows = 6.13 (acceptable)

### Sample Pixel Comparison
```
[200, 3068]  Output: [34, 42, 50]  Reference: [84, 85, 70]  DeltaE=73
[1358, 1908] Output: [75, 96, 108] Reference: [186, 166, 165] DeltaE=63
```

**Problem:** Output is significantly darker and more blue-tinted than SPP reference.

## Analysis

### What's Working
- Removing corrections eliminated extreme color distortions
- No more purple/black artifacts in highlights (yellows/oranges safe)
- Shadow areas are reasonably close (DeltaE ~6)

### What's Not Working
- Balanced test matrix produces overall blue cast
- Significant underexposure in midtones and highlights
- Colors are not matching SPP reference at all

## Conclusion

**Option 4 (removing corrections) + balanced matrix is NOT sufficient.**

The balanced test matrix is designed to avoid artifacts, not to match SPP colors. While we've eliminated the extreme artifacts, the resulting colors are completely wrong.

## Next Steps

We need to move to **Option 2: Derive matrix from SPP reference**. Options:

1. **Mathematical derivation:** Use the 10 X3F/TIFF pairs to solve for optimal matrix coefficients that minimize DeltaE
2. **Manual tuning:** Adjust balanced matrix coefficients iteratively based on visual feedback
3. **Hybrid approach:** Start from balanced matrix, then use reference data to fine-tune

Recommendation: **Option 2.1 - Mathematical derivation** using least-squares optimization on reference data.
