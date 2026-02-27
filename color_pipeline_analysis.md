# X3F Merrill Color Processing Pipeline Analysis

## Executive Summary

This analysis examines the complete color processing pipeline in x3f_extract to identify why DeltaE values remain at 60-80 (target: <20). The investigation covers all major stages from raw sensor data to final TIFF output.

---

## 1. Complete Color Processing Chain

### 1.1 Pipeline Overview (x3f_process.c)

The color processing pipeline in `convert_data()` follows this sequence:

```
Raw X3F Data
    ↓
[1] Preprocessing (preprocess_data)
    - Black level subtraction (from masked pixels)
    - Scaling to 14-bit intermediate range
    - Bad pixel interpolation
    ↓
[2] Spatial Gain Application (x3f_calc_spatial_gain)
    - Per-pixel gain correction based on position
    - Separate tables for R, G, B channels
    ↓
[3] Color Space Conversion (conv_matrix)
    - Raw → XYZ → Target RGB (sRGB/AdobeRGB/ProPhotoRGB)
    - White balance applied via gain matrix
    ↓
[4] Post-Processing Corrections
    - SPP-like exposure compensation (2.5x)
    - Green channel correction (0.895x)
    - Blue boost (1.19x)
    - Red boost (1.17x)
    - Global desaturation (0.62x)
    - Shadow desaturation (ISO-dependent)
    - Highlight desaturation
    ↓
[5] Tone Curve Application (LUT)
    - Sigmoid-enhanced sRGB tone curve
    - TCSteepness from metadata (default 4.4, actual 3.0)
    - Highlight threshold 0.95
    ↓
[6] TIFF Output (x3f_output_tiff.c)
    - Adobe RGB ICC profile embedded
    - 16-bit per channel
```

### 1.2 Color Conversion Matrix Derivation

The critical `raw_to_rgb` matrix is computed in `get_conv()`:

```c
// 1. Get raw→XYZ matrix (from CAMF metadata)
x3f_get_raw_to_xyz(x3f, wb, raw_to_xyz)

// 2. Get XYZ→RGB matrix (standard color spaces)
x3f_XYZ_to_sRGB(xyz_to_rgb);  // or AdobeRGB, ProPhotoRGB

// 3. Combine: raw→RGB = XYZ→RGB × raw→XYZ
x3f_3x3_3x3_mul(xyz_to_rgb, raw_to_xyz, raw_to_rgb);

// 4. Apply ISO scaling
x3f_scalar_3x3_mul(iso_scaling, raw_to_rgb, conv_matrix);
```

---

## 2. Color Space Conversion Matrices (x3f_matrix.c)

### 2.1 Standard Matrices Used

**sRGB from XYZ (D65 white point):**
```
[ 3.2406  -1.5372  -0.4986 ]
[-0.9689   1.8758   0.0415 ]
[ 0.0557  -0.2040   1.0570 ]
```

**Adobe RGB from XYZ:**
```
[ 2.04159  -0.56501  -0.34473 ]
[-0.96924   1.87597   0.04156 ]
[ 0.01344  -0.11836   1.01517 ]
```

**Bradford D65→D50 adaptation:**
```
[ 1.0478   0.0229  -0.0501 ]
[ 0.0295   0.9905  -0.0170 ]
[-0.0092   0.0150   0.7521 ]
```

### 2.2 Matrix Assessment

These are **standard, well-established matrices** from color.org and ICC specifications. They are mathematically correct.

**Verdict:** The matrices themselves are NOT the source of color errors.

---

## 3. Raw→XYZ Matrix Sources (x3f_process.c)

### 3.1 Two Different Approaches

**Approach A: WhiteBalanceColorCorrections (lines 257-264)**
```c
if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceColorCorrections", wb, 3, 3, cc_matrix)) {
    double srgb_to_xyz[9];
    x3f_sRGB_to_XYZ(srgb_to_xyz);  // Inverse of XYZ→sRGB
    x3f_3x3_3x3_mul(srgb_to_xyz, cc_matrix, bmt_to_xyz);
}
```

**Approach B: WhiteBalanceIlluminants + WhiteBalanceCorrections (lines 266-276)**
```c
else if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceIlluminants", wb, 3, 3, cam_to_xyz) &&
         x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceCorrections", wb, 3, 3, wb_correction)) {
    x3f_3x3_3x3_mul(wb_correction, cam_to_xyz, raw_to_xyz);
    get_raw_neutral(raw_to_xyz, raw_neutral);
    x3f_3x3_diag(raw_neutral, raw_neutral_mat);
    x3f_3x3_3x3_mul(raw_to_xyz, raw_neutral_mat, bmt_to_xyz);
}
```

### 3.2 Critical Finding: Approach A Uses WRONG Matrix!

**In Approach A:**
- `cc_matrix` is multiplied by `srgb_to_xyz`
- This produces a matrix that goes sRGB→XYZ, NOT raw→XYZ
- **This is fundamentally wrong for Merrill cameras!**

**In Approach B:**
- Properly computes raw→XYZ from illuminant matrices
- Applies neutral white balance
- **This is the correct approach**

### 3.3 The Problem

The code tries Approach A first. If `WhiteBalanceColorCorrections` exists in the CAMF block, it uses the WRONG matrix transformation. Merrill cameras may have this metadata entry, causing incorrect color rendering.

**Root Cause Candidate #1:** Approach A produces incorrect raw→XYZ transformation.

---

## 4. White Balance and Gains (x3f_process.c)

### 4.1 Gain Extraction (lines 219-251)

```c
if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceGains", wb, 3, 0, gain) ||
    x3f_get_camf_matrix_for_wb(x3f, "DP1_WhiteBalanceGains", wb, 3, 0, gain));
else if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceIlluminants", wb, 3, 3, cam_to_xyz) &&
         x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceCorrections", wb, 3, 3, wb_correction)) {
    // Compute gains from matrices
}
```

Additional gain factors applied:
- `SensorAdjustmentGainFact` (vector multiply)
- `TempGainFact` (vector multiply)
- `FNumberGainFact` (vector multiply)

### 4.2 Assessment

The gain extraction logic is correct. The gains are applied as a diagonal matrix after the color matrix.

**Verdict:** White balance gains are correctly extracted and applied.

---

## 5. Spatial Gain Compensation (x3f_spatial_gain.c)

### 5.1 How It Works

For Merrill cameras, spatial gain uses `GainsTable` entries from CAMF:

```c
get_merrill_type_gains_table(x3f, name, "R", &mgain, &rows, &cols, &mingain, &delta)
get_merrill_type_gains_table(x3f, name, "G", &mgain, &rows, &cols, &mingain, &delta)
get_merrill_type_gains_table(x3f, name, "B", &mgain, &rows, &cols, &mingain, &delta)
```

### 5.2 Interpolation

The code does bilinear interpolation over:
- 1/aperture (x-axis)
- Lens position (y-axis, computed from focal length and object distance)

### 5.3 Application

Spatial gain is applied in `convert_data()` BEFORE color matrix conversion:

```c
input[color] = x3f_calc_spatial_gain(sgain, sgain_num, row, col, color, rows, cols) *
               (*valp[color] - ilevels->black[color]) / (ilevels->white[color] - ilevels->black[color]);
```

### 5.4 Assessment

Spatial gain corrects for lens vignetting and color cast variations across the frame. The implementation appears correct.

**Verdict:** Spatial gain implementation is correct for Merrill cameras.

---

## 6. Post-Processing Corrections (Empirical Hacks)

### 6.1 Current Corrections in convert_data()

The code contains several empirical corrections added to match SPP:

| Correction | Value | Purpose |
|------------|-------|---------|
| `spp_exposure_comp` | 2.5 | Brightness match |
| `green_correction` | 0.895 | Reduce green cast |
| `b_correction` | 1.19 | Boost blue |
| `r_correction` | 1.17 | Boost red |
| `desat_factor` | 0.62 | Global desaturation |
| `shadow_strength` | 0.7-0.95 | Shadow desaturation (ISO-dependent) |

### 6.2 Critical Analysis

These corrections are **compensating for an underlying problem** upstream. They should not be needed if the color matrix pipeline were correct.

**The need for massive green reduction (0.895) + red/blue boost (1.17-1.19) + heavy desaturation (0.62) indicates:**

1. The raw→XYZ matrix is producing incorrect color balance
2. The resulting colors are too green and too saturated
3. The corrections are "fixing" a fundamental color transform error

**Root Cause Candidate #2:** The empirical corrections mask but don't fix the underlying matrix problem.

---

## 7. Tone Curve and Gamma (x3f_matrix.c)

### 7.1 Sigmoid LUT Implementation

```c
void x3f_sRGB_sigmoid_LUT(double *lut, int size, uint16_t max, double steepness, double highlight_threshold)
{
    // Apply sRGB gamma first
    if (lin <= thres)
        srgb = 12.92 * lin;
    else
        srgb = (1 + a) * pow(lin, 1/2.4) - a;
    
    // Then apply sigmoid
    sig = 1.0 / (1.0 + exp(-steepness * (srgb - 0.5)));
    norm_sig = (sig - sig_min) / (sig_max - sig_min);
}
```

### 7.2 Assessment

- TCSteepness is read from CAMF metadata (3.0 for Merrill files)
- The sigmoid curve is applied on top of sRGB gamma
- This matches SPP's "film-like" tone curve

**Verdict:** Tone curve implementation is correct.

---

## 8. ICC Profile Handling (x3f_output_tiff.c)

### 8.1 Adobe RGB Profile

The code embeds a 560-byte Adobe RGB (1998) ICC profile extracted from SPP reference TIFFs:

```c
static const unsigned char adobe_rgb_profile[] = { 560 bytes };

if (encoding == ARGB) {
    TIFFSetField(f_out, TIFFTAG_ICCPROFILE, sizeof(adobe_rgb_profile), adobe_rgb_profile);
}
```

### 8.2 Assessment

The ICC profile is correctly embedded and matches SPP's output.

**Verdict:** ICC profile handling is correct.

---

## 9. Critical Findings and Root Causes

### 9.1 Primary Issue: Incorrect raw→XYZ Matrix (Approach A)

**Location:** `x3f_get_bmt_to_xyz()` in x3f_process.c, lines 257-264

**Problem:**
```c
if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceColorCorrections", wb, 3, 3, cc_matrix)) {
    double srgb_to_xyz[9];
    x3f_sRGB_to_XYZ(srgb_to_xyz);
    x3f_3x3_3x3_mul(srgb_to_xyz, cc_matrix, bmt_to_xyz);  // WRONG!
}
```

**Why it's wrong:**
- `WhiteBalanceColorCorrections` is likely a **color correction matrix (CCM)**, not a complete color space transform
- Multiplying by sRGB→XYZ assumes the input is already in sRGB space, but we're in raw sensor space
- This produces a matrix that doesn't properly represent the raw→XYZ transformation

**Evidence:**
- The massive empirical corrections (green 0.895, desat 0.62) are compensating for this
- Approach B (using Illuminants+Corrections) would produce correct results
- Some files may have `WhiteBalanceColorCorrections` entries, triggering the wrong path

### 9.2 Secondary Issue: Missing Color Calibration Data

X3F files contain additional color metadata that may not be fully utilized:

**Potentially unused CAMF entries:**
- `WhiteBalanceColorCorrections` - Misinterpreted (treated as complete matrix instead of correction)
- `SensorAdjustmentGainFact` - Applied, but may need different interpretation
- `TempGainFact` - Applied, but may need different interpretation
- `FNumberGainFact` - Applied, but may need different interpretation

### 9.3 Missing Pieces

1. **No sensor-specific color calibration:** The code doesn't apply any camera-specific color calibration beyond the white balance matrices.

2. **No LUT-based color correction:** SPP likely uses 3D LUTs or per-channel LUTs for color correction that we're not using.

3. **Incorrect interpretation of `WhiteBalanceColorCorrections`:** This entry appears to be a correction matrix applied to an existing color space, not a complete raw→sRGB transform.

---

## 10. Recommendations

### 10.1 Immediate Fix: Disable Approach A for Merrill Cameras

Modify `x3f_get_bmt_to_xyz()` to skip Approach A for Merrill cameras:

```c
/* extern */ int x3f_get_bmt_to_xyz(x3f_t *x3f, char *wb, double *bmt_to_xyz)
{
    double cc_matrix[9], cam_to_xyz[9], wb_correction[9];
    
    // DISABLE Approach A for Merrill cameras - it produces wrong colors
    // Only use Approach B (Illuminants + Corrections)
    
    if (x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceIlluminants", wb, 3, 3, cam_to_xyz) &&
        x3f_get_camf_matrix_for_wb(x3f, "WhiteBalanceCorrections", wb, 3, 3, wb_correction)) {
        double raw_to_xyz[9], raw_neutral[3], raw_neutral_mat[9];
        
        x3f_3x3_3x3_mul(wb_correction, cam_to_xyz, raw_to_xyz);
        get_raw_neutral(raw_to_xyz, raw_neutral);
        x3f_3x3_diag(raw_neutral, raw_neutral_mat);
        x3f_3x3_3x3_mul(raw_to_xyz, raw_neutral_mat, bmt_to_xyz);
        
        x3f_printf(DEBUG, "bmt_to_xyz (from Illuminants+Corrections)\n");
        x3f_3x3_print(DEBUG, bmt_to_xyz);
        return 1;
    }
    
    return 0;
}
```

### 10.2 Investigate WhiteBalanceColorCorrections Meaning

Research what `WhiteBalanceColorCorrections` actually contains:
- It may be a **correction** applied after raw→XYZ, not a complete transform
- It may need to be applied differently (e.g., after XYZ conversion, not before)
- Check if SPP uses this entry differently

### 10.3 Verify Color Matrix Chain

Print out the complete color matrix chain for debugging:
1. Raw→XYZ matrix (from CAMF)
2. XYZ→sRGB matrix (standard)
3. Combined raw→sRGB matrix
4. Compare with known-good values from other Foveon processors

### 10.4 Check for Missing Color LUTs

Search X3F CAMF blocks for:
- 3D color LUTs
- Per-channel LUTs
- Color transformation tables

---

## 11. Summary

| Component | Status | Issue |
|-----------|--------|-------|
| Black level | OK | Correctly computed from masked areas |
| Scaling | OK | Correct 14-bit intermediate |
| Spatial gain | OK | Correctly applied for Merrill |
| **Raw→XYZ matrix** | **PROBLEM** | Approach A is wrong for Merrill |
| **Approach B** | **OK** | Correctly uses Illuminants+Corrections |
| XYZ→RGB matrices | OK | Standard ICC matrices |
| White balance | OK | Gains correctly applied |
| Tone curve | OK | Sigmoid LUT matches SPP |
| Post-processing | COMPENSATION | Empirical fixes for matrix error |
| ICC profile | OK | Adobe RGB correctly embedded |

**Primary root cause:** The `WhiteBalanceColorCorrections` path (Approach A) in `x3f_get_bmt_to_xyz()` produces an incorrect raw→XYZ transformation for Merrill cameras. This causes a green color cast and excessive saturation, which is only partially corrected by empirical adjustments.

**Recommended fix:** Disable Approach A and always use Approach B (Illuminants+Corrections) for Merrill cameras.
