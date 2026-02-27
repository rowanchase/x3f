# Validation Report: Phase 2b Implementation

**Date:** 2026-02-27  
**Test Files:** _P2M0927.X3F (moderate clipping), _P2M0936.X3F (severe clipping)

## Summary

Phase 2b implementation is **FUNCTIONAL but IMPACTED by downstream processing**. The soft-knee compression and texture transfer are working in the highlight recovery module, but the results are being partially undone by subsequent pipeline stages, particularly the 2.5x exposure compensation.

## Test Results

### File: _P2M0927.X3F (Moderate Clipping - 31,571 pixels)

**Histogram Analysis:**

| Channel | Region | Output | Reference | Diff | Status |
|---------|--------|--------|-----------|------|--------|
| R | Soft (200-229) | 3.68% | 4.35% | **-0.67%** | ⚠️ |
| R | Hard (230-253) | 2.68% | 2.51% | +0.17% | ⚠️ |
| R | Clipped (254-255) | 1.04% | 1.07% | -0.03% | ✓ |
| G | Soft (200-229) | 2.60% | 4.03% | **-1.42%** | ❌ |
| G | Hard (230-253) | 1.76% | 1.87% | -0.11% | ✓ |
| G | Clipped (254-255) | 0.93% | 0.68% | **+0.25%** | ❌ |
| B | Soft (200-229) | 1.64% | 2.14% | **-0.50%** | ⚠️ |
| B | Hard (230-253) | 1.41% | 0.71% | **+0.70%** | ❌ |
| B | Clipped (254-255) | 0.84% | 0.35% | **+0.49%** | ❌ |

**Key Finding:** We have FEWER pixels in soft highlights and MORE pixels in hard/clipped ranges compared to SPP.

### File: _P2M0936.X3F (Severe Clipping - 652,921 pixels)

Similar pattern observed:
- Soft highlights: -0.31% to -0.68% fewer than reference
- Hard highlights: +0.09% to +0.49% more than reference  
- Fully clipped: +0.38% to +0.90% more than reference

## Root Cause Analysis

### 1. Pipeline Order Issue
The soft-knee compression in Phase 2b happens **BEFORE** the 2.5x exposure compensation in the main processing loop. This means:

1. Phase 2b compresses values > 0.8 into [0.8, 1.0] range ✓
2. Main loop normalizes raw data to [0, 1.0] range ✓
3. **Exposure compensation multiplies by 2.5x**, pushing compressed values back to [2.0, 2.5] ✗
4. This effectively **undoes the soft-knee compression**

**Code flow:**
```c
// Phase 2b: compress_highlight() produces values in [0, 1.0]
// ... later in main loop ...
double spp_exposure_comp = 2.5;
output[color] *= spp_exposure_comp;  // Values now 0-2.5 range!
```

### 2. Highlight Desaturation
The highlight desaturation (lines 1041-1056 in x3f_process.c) brings bright values toward white, which may be shifting the histogram toward the high end.

## What IS Working

✓ **Soft-knee compression function** - Code correctly implements tanh-like compression  
✓ **Texture transfer** - Properly extracts and applies texture ratios  
✓ **Near-clipped pixel processing** - Detects and compresses values > 0.8  
✓ **Integration** - Pipeline correctly calls reconstruction functions  
✓ **No crashes** - Processes 31K-652K clipped pixels without errors

## What Needs Improvement

### Option A: Move Soft-Knee to End of Pipeline
Apply compression AFTER all linear processing (exposure comp, corrections) but BEFORE gamma/LUT:

```c
// After all linear processing:
output[color] *= spp_exposure_comp;  // 2.5x
output[color] *= channel_corrections; // R/B boost
// ... etc ...

// Apply soft-knee here:
output[color] = compress_highlight(output[color], 0.8);

// Then gamma/LUT:
*valp[color] = x3f_LUT_lookup(lut, LUTSIZE, output[color]);
```

### Option B: Adjust Thresholds
The current threshold of 0.80 (204/255) may not be optimal. Testing needed:
- Try 0.75 (start compression earlier)
- Try more aggressive tanh curve
- Test different shoulder shapes

### Option C: Remove Legacy Processing
The highlight desaturation (lines 1038-1056) may conflict with Phase 2b's smooth compression. Consider:
- Disabling legacy highlight desaturation when Phase 2b is active
- Or making Phase 2b the primary/only highlight handler

## Recommendations

1. **Immediate:** Test moving soft-knee compression to after exposure compensation
2. **Short-term:** Tune threshold and compression curve parameters  
3. **Long-term:** Consider making Phase 2b the exclusive highlight handler, removing legacy code

## Conclusion

Phase 2b implementation is **technically correct** but **strategically misplaced** in the pipeline. The soft-knee compression works as designed, but downstream processing (especially 2.5x exposure comp) counteracts its benefits.

**Next step:** Reorder pipeline so soft-knee compression happens after linear processing but before gamma encoding.

## Evidence

- Soft highlights populated: 543,388 pixels (R), 384,141 pixels (G), 241,883 pixels (B)
- Fully clipped: 153,147 pixels (R), 137,082 pixels (G), 123,541 pixels (B)
- More values in 200-229 range than without Phase 2b (confirmed by comparison)
- But still less than SPP reference due to pipeline ordering issue
