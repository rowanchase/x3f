# Phase 2b Compression Investigation - 27 Feb 2026 (Continued)

## Investigation Summary

### Root Cause Identified
The histogram concentration in soft highlights (200-229) is caused by **triple compression**:

1. **Phase 2b tanh compression**: Maps [0.8, ∞] → [0.8, 1.0]
2. **2.5x exposure boost**: [0.8, 1.0] → [2.0, 2.5]
3. **LUT compression** (x3f_matrix.c line 334-338): Maps [0.95, ∞] → compressed range
   - Formula: `0.95 + 0.05 * (t / (t + 1))` where t = (val - 0.95) / 0.05
   - For val=2.0: compressed ≈ 0.997
   - For val=2.5: compressed ≈ 0.998
   - Both map to nearly identical output values!

### Attempts Made

#### 1. Threshold Calibration (0.38 = 0.95/2.5)
**Theory**: Set threshold so after 2.5x boost, compressed values stay at 0.95 (LUT threshold)
**Result**: No improvement - histogram unchanged
**Analysis**: The tanh compression still maps everything towards 1.0 too aggressively

#### 2. Remove Old Highlight Desaturation
**Theory**: The old desaturation code (lines 1038-1056) might be conflicting
**Result**: 
- B channel improved: +66K → +16K soft highlights
- G channel worsened: +207K → +152K soft highlights
**Analysis**: The old desaturation was actually helping by spreading values

#### 3. Disable Phase 2b Compression
**Theory**: Let LUT handle all compression naturally
**Result**: Same histogram as with compression
**Analysis**: Texture transfer naturally produces values in 0.8-1.0 range, compression or not

#### 4. Square Root Compression (instead of tanh)
**Theory**: Gentler curve preserves more differentiation
**Result**: Back to original histogram
**Analysis**: The issue isn't the compression curve - it's the range of values being reconstructed

### Key Insight

The problem is **not** the compression algorithm but the **reconstructed value range**:
- Texture transfer + QE ratios produce values typically in 0.8-1.0 range
- 2.5x boost pushes these to 2.0-2.5
- LUT aggressively compresses 2.0-2.5 to nearly identical values (~0.997-0.998)
- These all map to ~254 in 8-bit, creating the soft highlight concentration

### Why This Happens

Looking at the LUT compression formula:
```c
double t = (val - 0.95) / 0.05;  // For val=2.0: t=21, for val=2.5: t=31
double compressed = 0.95 + 0.05 * (t / (t + 1));
// t/(t+1) for t=21: 21/22 = 0.954, for t=31: 31/32 = 0.969
// compressed: 0.95 + 0.05*0.954 = 0.998, 0.95 + 0.05*0.969 = 0.998
```

The function `t/(t+1)` approaches 1.0 asymptotically, so large input ranges get squashed to nearly identical outputs.

### Potential Solutions

1. **Modify LUT compression**: Use a gentler rolloff formula that preserves more range
2. **Pre-LUT scaling**: Scale values down before LUT to avoid triggering overflow path
3. **Alternative reconstruction**: Produce lower reconstructed values so 2.5x boost stays < 0.95
4. **Remove LUT overflow compression**: Skip lines 334-338 for reconstructed highlights

### Current State

- Reverted to tanh compression in Phase 2b
- Restored old highlight desaturation (helps spread values)
- Threshold at 0.38 (calibrated for LUT)
- Texture transfer enabled

### Next Steps

1. Investigate modifying the LUT compression formula in x3f_matrix.c
2. Try scaling reconstructed values to avoid LUT overflow
3. Consider the trade-off: softer highlights vs natural texture

## Files Modified

- `src/x3f_highlight_recovery.c` - Restored tanh compression, threshold 0.38
- `src/x3f_process.c` - Restored old highlight desaturation
