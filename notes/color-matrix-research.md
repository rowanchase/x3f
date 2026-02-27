# Color Matrix Research - 27 February 2026

## Executive Summary

This document details the research into the green tint issue in x3f_extract output for Sigma Merrill cameras, the current state of the color matrix implementation, and recommendations for fixing it properly.

---

## 1. The Green Tint Issue

### Symptoms
- Green tint visible in output images, especially around edges (vignetting pattern)
- Green channel consistently too bright (~10 units in 8-bit space)
- Large a-channel errors in Lab color space (mean ~70, max >900)

### Root Causes Identified

#### Issue #117 - Black Level Calculation (FIXED)
- The RIGHT "shielded" area on DP1M, DP2M, DP3M is NOT truly optically shielded
- Contains light-sensitive data with linear exposure gradient
- Using it for black level calculation caused underestimation → green tint in shadows
- **Status:** FIXED in this codebase (PR #120 applied at x3f_process.c:118-130)

#### Issue #6 - Green Shift/Bias Correction (Kalpanika/x3f)
- Original issue filed about green shift
- Limited details available

#### Issue #114 - Spatial Gain Over-correction
- Spatial gain appears to OVER-correct for Merrill cameras
- User in darktable had to apply weighting factors: R=1.8, G=2.3, B=1.7
- Suggests interaction with white balance processing

---

## 2. Current Color Matrix Implementation

### Pipeline Position

```
Raw Data → Black Level → Raw→XYZ Matrix → XYZ→sRGB → [Tunable Matrix] → Gamma → Output
```

### Code Location
- **File:** `src/x3f_process.c`
- **Function:** `x3f_get_bmt_to_xyz()` (lines 254-285)
- **Matrix Selection:** Lines 258-266

### The Problem: Incorrect Matrix Usage

The code uses TWO approaches for color matrix computation:

#### Approach A (MERRILL - CURRENTLY USED)
```c
// Lines 258-266
if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceColorCorrections", wb,
              3, 3, cc_matrix) || ...) {
    double srgb_to_xyz[9];
    x3f_sRGB_to_XYZ(srgb_to_xyz);
    x3f_3x3_3x3_mul(srgb_to_xyz, cc_matrix, bmt_to_xyz);
}
```

This approach:
1. Reads `WhiteBalanceColorCorrections` (e.g., AutoCCMatrix) from CAMF
2. Treats it as a raw→XYZ conversion matrix
3. **THIS IS WRONG** - AutoCCMatrix is a COLOR CORRECTION matrix, not a conversion matrix

#### Example AutoCCMatrix (from _P2M1004.X3F):
```
[[ 1.906, -1.773,  0.867],
 [-1.664,  3.523, -0.859],
 [ 1.164, -5.016,  4.852]]
```

Note: Values >1 and <0 indicate this is a correction matrix (shifts colors), not a conversion matrix.

#### Approach B (NOT USED FOR MERRILL)
```c
// Lines 267-277
else if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceIlluminants", wb, ...) &&
         x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceCorrections", wb, ...)) {
    // Proper raw→XYZ computation
}
```

This is the CORRECT approach but Merrill files don't have `WhiteBalanceIlluminants` data.

---

## 3. Why This Causes Green Tint

The incorrect matrix (Approach A) produces wrong color transformations because:

1. **Wrong mathematical operation:** Color correction matrices need different handling than conversion matrices
2. **Green channel amplification:** The AutoCCMatrix has a large G coefficient (3.52), amplifying green
3. **No proper neutralization:** Unlike Approach B which applies `raw_neutral_mat` to normalize

Result: Green channel ends up too bright, causing the green tint in output.

---

## 4. Current Workaround: Tunable Matrix

### Implementation (x3f_process.c:1021-1040)

```c
static const double color_corr[9] = {
    1.00, 0.00, 0.00,   /* R row */
    0.00, 0.78, 0.00,   /* G row - reduced from 1.0 */
    0.00, 0.00, 1.05    /* B row - slight boost */
};
```

### Current Results (_P2M1004)

| Metric | Before (identity) | After (tuned) |
|--------|-------------------|---------------|
| RMSE | 27.94 | 27.49 |
| Mean DeltaE | 100.97 | 97.27 |
| R MeanErr | +0.62 | +0.62 |
| G MeanErr | +9.99 | +0.13 |
| B MeanErr | -2.28 | -0.55 |

**Channel balance is now balanced** but overall DeltaE remains high due to underlying matrix.

---

## 5. Why the Tunable Matrix Can't Fix Everything

The tunable matrix is applied at the WRONG stage:

```
Current: Raw → [Wrong Matrix] → XYZ → sRGB → [Tunable] → Gamma
```

The tunable matrix corrects sRGB output, but:
- The underlying raw→XYZ→sRGB transformation is still wrong
- Color errors in Lab space (a-channel) originate from wrong matrix
- Tunable matrix can only scale channels, not re-route color relationships

---

## 6. Solutions for Proper Fix

### Option A: Derive Correct Matrix from Spectral Data

Use published Merrill spectral sensitivity data (JOSA 2015 paper) to compute optimal compromise matrix mathematically.

**Source:** Kasson blog research using JOSA data from Iliah Borg
- SMI (Sensitivity Metamerism Index): ~82 for Merrill
- Compare: Good Bayer cameras score 88-95+

**Reference:** 
- https://blog.kasson.com/the-last-word/foveon-merrill-color-accuracy/
- https://blog.kasson.com/the-last-word/foveon-merrler-color-accuracy-continued/

### Option B: Optimize Against SPP References (RECOMMENDED)

Since we have 25 reference file pairs (X3F→SPP TIFF), use mathematical optimization to find the raw→XYZ matrix that minimizes RMSE/DeltaE.

**Process:**
1. Extract raw pixel values from X3F files
2. Apply candidate matrix: raw → XYZ → sRGB
3. Compare with SPP reference TIFF
4. Optimize matrix coefficients to minimize error

**This is the most pragmatic approach** because:
- SPP is our ground truth
- Accounts for all SPP processing quirks
- Can be solved with standard optimization (gradient descent, simplex)

### Option C: Find Existing Implementation

Check other open-source implementations for their Merrill matrices:
- RawTherapee/Art fork (gravures/Art)
- dcraw/libraw
- darktable (uses rawspeed)

---

## 7. Kasson Research Findings

From the Kasson blog:

### Optimal Matrix (from spectral data)
Kasson computed optimal compromise matrices for Merrill using genetic algorithm:
- SMI ~82.2 (theoretical best possible with Merrill sensor)
- Much lower than Bayer cameras (88-95+)

### Key Insight
> "Foveon Merrill color accuracy is fundamentally limited by the sensor's spectral characteristics. Even with perfect processing, the best possible SMI is ~82."

This means some color inaccuracy is INHERENT to the Merrill sensor, but we should still aim to match SPP as closely as possible.

---

## 8. Recommendations

### Immediate (Current Work)
1. Continue visual tuning of tunable matrix for best subjective appearance
2. Validate across multiple reference files (not just 1004)

### Short-term
1. Implement Option B: Optimize raw→XYZ matrix against SPP references
2. This should reduce DeltaE significantly

### Long-term
1. Document the color matrix issue in code comments
2. Consider adding CLI parameter for matrix selection
3. Investigate spatial gain over-correction (Issue #114)

---

## 9. Files Modified

- `src/x3f_process.c`: Added tunable color correction matrix (lines ~1021-1040)

---

## 10. References

1. Kalpanika/x3f Issue #6: https://github.com/Kalpanika/x3f/issues/6
2. Kalpanika/x3f Issue #117: https://github.com/Kalpanika/x3f/issues/117
3. Kalpanika/x3f PR #120: https://github.com/Kalpanika/x3f/pull/120
4. Kalpanika/x3f Issue #114: https://github.com/Kalpanika/x3f/issues/114
5. Kasson Blog - Merrill Color: https://blog.kasson.com/the-last-word/foveon-merrill-color-accuracy/
6. JOSA 2015 Paper: Darrodi et al., "Reference data set for camera spectral sensitivity estimation"
