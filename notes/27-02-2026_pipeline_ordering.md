# Pipeline Ordering Investigation - 27 Feb 2026

## Summary
Investigated the pipeline ordering issue for Phase 2b highlight recovery. The soft-knee compression was being applied BEFORE the 2.5x exposure compensation, which undoes its benefits.

## Attempts Made

### 1. Remove compression from highlight_recovery.c, add to x3f_process.c after 2.5x boost
**Result**: Histogram got worse - MORE soft highlights than before
- R: +93K soft highlights
- G: +207K soft highlights  
- B: +66K soft highlights

**Analysis**: The threshold of 1.0 after 2.5x boost was compressing values >1.0 back down into the soft range instead of letting them progress to hard highlights.

### 2. Adjust threshold to 2.5 in x3f_process.c
**Result**: No change in histogram
**Analysis**: Most values are ≤2.5 even after boost, so compression wasn't triggered.

### 3. Restore compression in highlight_recovery.c with adjusted threshold (0.32 = 0.8/2.5)
**Result**: Same histogram as original
**Analysis**: The threshold adjustment isn't helping because the fundamental issue is that reconstructed values naturally fall in 0.8-1.0 range, and the tanh compression maps [threshold, inf] to [threshold, 1.0], so after 2.5x boost they end up in [0.8, 2.5].

## Root Cause

The Phase 2b soft-knee compression uses:
```c
output = threshold + spread * tanh(excess)
```

This maps [threshold, infinity] to [threshold, 1.0] asymptotically.

With threshold=0.8 (or 0.32 after adjustment):
- Values > threshold get compressed towards 1.0
- After 2.5x boost: [0.8, 1.0] becomes [2.0, 2.5]
- These map to ~[204, 255] in 8-bit, creating the soft highlight concentration

## Key Insight

The problem isn't just WHERE we apply compression, but HOW:
- We want to compress values so they transition through soft → hard → clipped
- But tanh compression maps everything towards a single value (1.0)
- This creates a concentration in one range instead of a smooth distribution

## Current State

Reverted to original approach:
- Soft-knee compression in highlight_recovery.c with original threshold=0.8
- No compression in x3f_process.c
- Texture transfer is working but histogram distribution needs improvement

## Next Steps

1. **Investigate the LUT mapping**: Check how x3f_LUT_lookup handles values > 1.0
2. **Alternative compression**: Try a different compression curve that provides better distribution
3. **Adjust reconstruction values**: Modify QE ratios or reconstruction logic to produce different value ranges
4. **Remove old highlight desaturation**: The code at lines 1038-1056 in x3f_process.c may be conflicting with Phase 2b

## Files Modified

- `src/x3f_highlight_recovery.c` - Restored compress_highlight calls with original threshold
- `src/x3f_process.c` - Removed duplicate compression attempt
- `doc/PHASE_2B_PLAN.md` - Documentation of the issue
