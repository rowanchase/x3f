# X3F Merrill Development Progress

## Overview
This project aims to fix issues with the `x3f_extract` tool for processing Sigma Foveon X3F files from Merrill series cameras (DP1m, DP2m, DP3m). The goal is to make the output match Sigma Photo Pro's reference outputs exactly.

## Work Completed

### 2026-02-24: Green Cast Correction

#### Analysis
- User observed slight green cast in output images
- Per-channel analysis confirmed consistent G channel positive mean error (+2 to +4)
- R and B channels had negative mean errors (underexposed)

#### Implementation
- Added green channel correction factor of 0.96 in `src/x3f_process.c`
- Applied after exposure compensation, before shadow/highlight processing

#### Results
| File | Before RMSE | After RMSE | G Mean Err Before | G Mean Err After |
|------|-------------|------------|------------------|------------------|
| 0993 | 12.72 | 12.68 | +2.10 | +0.20 |
| 0994 | 12.14 | 12.12 | -0.01 | -0.62 |
| 0990 | 13.85 | 13.79 | +4.08 | +2.66 |
| 0991 | 13.77 | 13.67 | - | +1.52 |
| 1003 | 19.80 | 19.73 | +3.14 | +1.35 |

**All files showed improved RMSE with green correction.**

### 2026-02-24: TCSteepness & Exposure Compensation Refinement (commit 585a584)

#### Analysis
- **Tone Curve:** Found `TCSteepness=3.0` in X3F metadata.
- **Testing:** Using `TCSteepness=3.0` (instead of hardcoded 4.4) improved RMSE but shifted exposure (Mean Error went from near 0 to +3-5).
- **Correction:** Adjusted exposure compensation from 2.6x to 2.5x to balance the exposure with the new tone curve.

#### Implementation
- Modified `src/x3f_process.c` to read `TCSteepness` from CAMF metadata.
- Updated `spp_exposure_comp` to 2.5.

#### Results (Selected Files)
| File | Type | Previous RMSE | New RMSE | Improvement |
|------|------|---------------|----------|-------------|
| 0993 | Best | 13.05 | 12.72 | 2.5% |
| 0936 | Clipped | 18.52 | 17.91 | 3.3% |
| 1003 | ISO 400 | 20.86 | 19.80 | 5.1% |

**All tested files are now below RMSE 20.**

### 2026-02-23: ISO-Dependent Shadow Processing (commit 0168f4c)

#### Analysis
- ISO 400 files had higher RMSE (22.18) vs ISO 200 (15.31)
- Linear regression revealed non-linear B channel response for ISO 400 (R² = 0.75)
- Shadow regions needed stronger desaturation for higher ISO

#### Implementation
- Added capture_iso parameter to convert_data()
- ISO-dependent shadow desaturation: 0.7 (ISO 200) → 0.95 (ISO 400)
- Added B channel boost in shadows for ISO 400

#### Results
- Average RMSE: 16.41 → 16.09 (2% better)
- ISO 400 avg: 22.18 → 20.19 (9% better)
- ISO 200 avg: 15.31 (unchanged)

### 2026-02-23: Shadow Desaturation (commit b301e04)

#### Analysis
- Discovered SPP desaturates highlights towards white
- Our highlights had saturation 0.353, reference had 0.052
- B/G ratio in highlights: ours 0.704, reference 0.917

#### Implementation
- Added highlight desaturation in `src/x3f_process.c`
- For bright pixels (max channel > 0.6), gradually bring channels towards max
- Uses quadratic falloff for smooth transition

#### Results
- File 0936 (worst case): RMSE 33.49 → **22.19** (34% improvement!)
- Files with clipped highlights all improved by 15-34%
- **Average RMSE: 22.55 → 21.09** (6.5% improvement)
- Non-clipped files unaffected (0993: 14.87 → 14.89)

### 2026-02-24: Sigmoid Tone Curve Implementation

#### Analysis
- Discovered consistent luminance error pattern:
  - Shadows (0-50): +17-18 too bright
  - Lower midtones (50-100): +12-13 too bright
  - Midtones (100-150): Near perfect
  - Upper midtones (150-200): -6-7 too dark
  - Highlights (200-255): -2-4 too dark
- This pattern indicates SPP applies an S-curve tone adjustment

#### Implementation
- Added `x3f_sigmoid_LUT()` and `x3f_sRGB_sigmoid_LUT()` to `src/x3f_matrix.c`
- Modified `src/x3f_process.c` to use sigmoid-enhanced sRGB LUT
- Optimal sigmoid steepness: k=4.4

#### Results After Sigmoid (25 files)
| File | RMSE | Mean Error |
|------|------|------------|
| 0993 | 14.87 | +2.38 |
| 0994 | 16.83 | +0.84 |
| 0991 | 17.69 | +1.18 |
| 0998 | 18.28 | +0.98 |
| 0927 | 18.28 | -0.92 |
| 0990 | 18.35 | +1.02 |
| 1000 | 18.39 | +0.27 |
| 0992 | 18.61 | -0.25 |
| 1001 | 18.98 | -0.16 |
| 0997 | 19.11 | +1.81 |
| 0995 | 19.25 | -0.48 |
| 0996 | 19.35 | -0.35 |
| 0929 | 19.81 | -1.33 |
| 0928 | 21.01 | -0.32 |
| 0932 | 23.05 | +1.59 |
| 0930 | 23.95 | -1.57 |
| 0933 | 24.01 | +0.97 |
| 1009 | 26.99 | +2.57 |
| 0935 | 27.92 | -0.03 |
| 1008 | 28.09 | +1.19 |
| 0934 | 28.10 | -0.04 |
| 1004 | 28.97 | -0.26 |
| 1003 | 29.59 | -0.23 |
| 0937 | 30.73 | +0.61 |
| 0936 | 33.49 | -1.86 |

**Average RMSE: 22.55** (improved from 24.8, 9% better)
**Mean errors now balanced around zero**

### 2026-02-23: Rotation Implementation & New Reference Files

#### New Reference Files Added
- 15 new X3F/TIFF pairs added (0990-1009)
- Total: 25 reference files

#### Rotation Implementation
- Implemented rotation handling in `src/x3f_output_tiff.c`
- Reads rotation metadata from X3F header (0, 90, 180, 270 degrees)
- Applies 90° CW, 90° CCW, or 180° rotation as needed
- 17 of 25 files required rotation (portrait orientation)

#### ISO Discovery
- Files have varying ISO: ISO 200 (most) and ISO 400 (1003, 1004, 1008, 1009)
- Attempted ISO-relative exposure compensation but made things worse
- Original 2.6x compensation works best across all ISO values

#### Build Environment
- Patched OpenCV 3.0 cmake files for GCC 11 compatibility
- Built OpenCV with `-DENABLE_PRECOMPILED_HEADERS=OFF`
- Fixed src/makefile to not require TBB on Linux
- Successfully built x3f_extract binary

#### Test Framework
- Created `tools/compare_output.py` for comparing x3f_extract output against Sigma Photo Pro references
- Computes: RMSE, MAE, per-channel metrics, regional analysis (shadows/midtones/highlights)

#### First Comparison Results
- **Before fix:** RMSE 51.2, MAE 46.9, shadows MAE 24.4
- Our output was darker than reference (mean 75 vs 119)

#### Applied PR #120 Fix
- Modified `src/x3f_process.c` to disable right shielded area for Merrill cameras
- **After fix:** RMSE 48.5, MAE 43.8, shadows MAE 19.3
- **Improvement in shadows confirms the fix helped**

#### Remaining Issue: Output ~37% Darker
- Both reference and our output are 8-bit (0-255)
- Our mean: 75.1, Reference mean: 118.7
- ISO scaling (capture/sensor = 2.0x) might be handled differently by SPP

### 2026-02-22: Initial Setup & Analysis
- Created notes directory structure
- Familiarized with codebase structure
- Identified key source files and processing pipeline
- Identified reference files (10 X3F files + corresponding TIFFs from Sigma Photo Pro)
- Understood existing test framework (behave/BDD style)
- Researched X3F file format and Foveon sensor technology
- Created comprehensive X3F format technical notes (`notes/x3f-format.md`)
- **Reviewed all GitHub issues from upstream Kalpanika/x3f repo** - see `notes/22-02-2026.md` for full details

## Key Findings from GitHub Issues

### CRITICAL: Green Tint in Shadows (Issue #117 + PR #120) - PARTIALLY FIXED
- **Root cause:** Right shielded area on Merrill sensors is NOT truly optically shielded
- **Effect:** Using it for black level calculation causes underestimation → green tint in shadows
- **Fix applied:** Disabled right shielded area for DP1M/DP2M/DP3M
- **Status:** Shadows improved but overall output still ~37% darker than SPP

### Other Known Issues
1. **Spatial gain over-correction** (Issue #114) - tested, not the main issue
2. **ProPhoto color space wrong colors** (Issue #113) - not yet tested
3. **Pattern of incorrect shielded areas** across different Sigma cameras (DP2, sdQH, Merrill)

## Remaining Work

1. ~~Build the tool~~ ✓
2. ~~Apply PR #120 fix~~ ✓ (shadows improved)
3. ~~Create test framework~~ ✓
4. **INVESTIGATE DARKNESS ISSUE** - output is 37% darker than SPP
   - ~~Check ISO scaling handling~~ - ISO scaling is applied correctly
   - ~~Compare exposure/gain processing~~ - Processing is correct
   - **ROOT CAUSE IDENTIFIED**: SPP applies a tone curve (S-curve) on top of sRGB gamma
   - **Solution needed**: Implement SPP-like tone curve for matching
5. Run tests on all 10 reference files
6. Investigate spatial gain weighting if needed
7. Test ProPhoto color space handling

## Key Finding: SPP Tone Curve

SPP is NOT producing neutral output. It applies:
1. A contrast-enhancing S-curve tone adjustment
2. Aggressive sharpening (cannot be fully disabled)
3. Shadow lift (toe of S-curve)

**Transfer function analysis:**
- Power curve fit: `SPP = 3.41 * x3f^1.11`
- Ratio increases with luminance (characteristic of S-curve)
- Shadows: ~9.7x lift, Midtones: ~2.5x, Highlights: ~2.8x

**Reference:** Jim Kasson's blog confirms SPP applies aggressive processing that cannot be disabled.

## Current Metrics

### After ISO-Dependent Shadow Processing (25 files)

**Average RMSE: 16.09** (improved from 16.41, 2% better)

| File | RMSE | Mean Err | Notes |
|------|------|----------|-------|
| 0994 | 11.19 | - | Best match |
| 0992 | 11.84 | - | |
| 1000 | 12.37 | - | |
| 1001 | 12.46 | - | |
| 0990 | 12.94 | - | |
| 0993 | 13.05 | +2.23 | |
| 0998 | 13.67 | - | |
| 0997 | 14.00 | - | |
| 0933 | 14.10 | - | Clipped |
| 0996 | 14.25 | - | |
| 0991 | 14.26 | - | |
| 0995 | 14.26 | - | |
| 0927 | 15.83 | - | |
| 0928 | 16.56 | - | |
| 0929 | 17.23 | - | |
| 0930 | 17.33 | - | Clipped |
| 1009 | 17.82 | - | ISO 400 |
| 0932 | 18.51 | - | |
| 0936 | 18.52 | - | Clipped |
| 0934 | 19.39 | - | Clipped |
| 0935 | 19.47 | - | Clipped |
| 0937 | 20.30 | - | Clipped |
| 1008 | 20.66 | - | ISO 400 |
| 1003 | 20.86 | - | ISO 400 |
| 1004 | 21.42 | - | ISO 400 |

**ISO 200 avg RMSE: 15.31**
**ISO 400 avg RMSE: 20.19** (improved from 22.18, 9% better)

**Files with correct orientation (rotation=0):**
| File | RMSE | MAE | Mean Err | Notes |
|------|------|-----|----------|-------|
| 0927 | 16.78 | 12.51 | +1.9 | Good match |
| 0928 | 22.63 | 18.03 | +8.9 | Slight over-exposure |
| 0929 | 18.58 | 14.28 | +4.1 | Good match |
| 0932 | 26.20 | 21.55 | +9.8 | Over-exposed |
| 0937 | 31.67 | 21.01 | +8.0 | Over-exposed |

**Average RMSE for correctly oriented files: 23.17**

**Files needing rotation:**
| File | Rotation | RMSE (unrotated) |
|------|----------|------------------|
| 0930 | 90° CW | 51.80 |
| 0933 | 90° CW | 61.78 |
| 0934 | 270° CCW | 64.71 |
| 0935 | 270° CCW | 64.75 |
| 0936 | 90° CW | 67.89 |

## Completed Work

1. ✅ Build the tool
2. ✅ Apply PR #120 fix (shadows improved)
3. ✅ Create test framework
4. ✅ Implement exposure compensation (2.5x)
5. ✅ Test on all 25 reference files
6. ✅ Implement rotation handling
7. ✅ Implement sigmoid tone curve (using metadata TCSteepness)
8. ✅ Implement highlight desaturation
9. ✅ Implement shadow desaturation (luminance-based)
10. ✅ Implement ISO-dependent shadow processing
11. ✅ Implement green channel correction (0.96x)
12. ✅ Implement universal R/B channel boost (1.02x)

## Current Average RMSE

**Average RMSE: 13.45** (with green + R/B corrections)

| File | RMSE | Notes |
|------|------|-------|
| 0994 | 12.12 | Best match |
| 0993 | 12.68 | |
| 0991 | 13.53 | |
| 0990 | 13.80 | |
| 0995 | 14.28 | |
| 0996 | 14.28 | |
| 0997 | 14.53 | |

## Remaining Work

### Highlight Recovery Improvement Project

A comprehensive plan has been developed to improve highlight recovery beyond SPP. See `notes/highlight-recovery-plan.md` for full details.

**Key Discovery**: X3F files contain unused highlight metadata:
- `HighlightBlendingLow` = 0.75
- `HighlightBlendingHigh` = 1.5
- `HighlightRestoreThresh` = 1.75
- `HighlightChanThresh1/2` = 0.5
- `HighlightSatFactor` = 1.0

**Advantage**: Foveon sensor captures RGB at every pixel, enabling direct channel reconstruction when other channels are unclipped (unlike Bayer which requires spatial interpolation).

**Phased Plan**:
1. **Phase 1**: Read and utilize CAMF highlight parameters ✅ (COMPLETED)
2. **Phase 2**: Implement channel-based reconstruction  
3. **Phase 3**: Advanced soft knee compression
4. **Phase 4**: Multiple reconstruction methods (luminance, color propagation, edge-aware)
5. **Phase 5**: Extended 14-bit dynamic range processing

#### Phase 1 Implementation (2026-02-24)

Completed:
- Added `x3f_get_highlight_params()` function in `x3f_meta.c`
- Added logging in `x3f_get_image()` to output highlight parameters in DEBUG mode
- Added CLI flags for override (-hl-blending-low, -hl-blending-high, etc.)
- Verified with test file _P2M0927.X3F - parameters correctly read and logged

Verification output:
```
dbg: Highlight parameters from CAMF:
dbg:   HighlightBlendingLow    = 0.750000
dbg:   HighlightBlendingHigh   = 1.500000
dbg:   HighlightRestoreThresh = 1.750000
dbg:   HighlightChanThresh1   = 0.500000
dbg:   HighlightChanThresh2   = 0.500000
dbg:   HighlightSatFactor     = 1.000000
```

#### Phase 2 Implementation (2026-02-24)

Completed:
- Added `reconstruct_highlight_channels()` function in `x3f_process.c`
- Function is integrated into `convert_data()` pipeline
- Receives CAMF highlight parameters (blending_low, blending_high)
- Framework in place for channel-based reconstruction

Current Status:
- Function currently passes through input to output (baseline)
- Tested multiple approaches:
  - Threshold 0.95: No significant change (RMSE 17.83)
  - Threshold 0.80: No significant change (RMSE 17.83)
  - Old highlight desaturation disabled: RMSE worsened to 35.2 (confirms old code is essential)

#### Phase 2/3 Full Testing (2026-02-25)

**Testing Results**:
- Implemented and verified channel reconstruction with debug output
- Function called and made changes (e.g., R raised from 0.78 to 1.02 in highlights)
- RMSE unchanged (17.83 for file 0936)
- Root cause: Existing post-conversion highlight desaturation already handles highlights well

**Phase 3 Attempt - Soft Knee Tuning**:
- Made `x3f_sRGB_sigmoid_LUT` tunable with highlight_threshold parameter
- Tested using CAMF hl_blending_low (0.75) as threshold
- CAMF values don't map to LUT data range - no improvement

**Key Findings**:
1. Pre-conversion channel reconstruction doesn't improve RMSE
2. CAMF highlight parameters (0.75, 1.5) are for 14-bit sensor data range
3. Current highlight handling is already good: highlight MAE (11.80) < midtones MAE (15.08)
4. Infrastructure in place for future enhancement (CAMF reading, CLI flags, tunable functions)

Key Finding:
- The existing highlight desaturation (threshold 0.6, at output color space) is critical
- Any reconstruction at the raw RGB level must work IN CONJUNCTION with it
- The challenge is that the normalized input data range doesn't match CAMF parameter ranges

Next Steps:
- Phase 2 implementation needs more research on:
  - Proper threshold values for detecting "clipped" channels in normalized data
  - Channel ratio reconstruction algorithm
  - Integration with existing highlight desaturation

### Original Remaining Work

1. ~~**Investigate Highlight Recovery**~~ → Now covered by new plan above
   - Clipped files (0936, 1003) still have high RMSE (17-19)

2. **Investigate remaining B channel errors for ISO 400**
   - B channel still has non-linear response (R² = 0.75)
   - May need additional color matrix adjustment

3. **Investigate spatial gain weighting** (Issue #114)

### Source Code
- `src/x3f_extract.c` - Main CLI tool entry point
- `src/x3f_process.c` - Core image processing (black level, color conversion, denoising)
- `src/x3f_output_tiff.c` - TIFF output writer
- `src/x3f_matrix.c` - Color space conversion matrices, sigmoid LUT
- `src/x3f_spatial_gain.c` - Spatial gain/color compensation

### Tools
- `tools/compare_output.py` - Comparison script for testing against SPP references

### Reference Files
- `reference_files/X3Fs/` - 10 raw X3F files from DP2 Merrill
- `reference_files/TIFFs/` - Corresponding TIFFs from Sigma Photo Pro

### Testing
- `features/consistency.feature` - Existing behave tests (MD5 hash based)
- `features/steps/consistency.py` - Test step implementations

## Notes Location
- Daily journal: `notes/DD-MM-YYYY.md`
- Progress tracking: `notes/progress.md` (this file)

---

## 2026-02-25: Image Quality Metrics Analysis (commit 821e177)

Enhanced `tools/compare_output.py` with IQ metrics beyond RMSE:
- Shadow noise analysis (std dev, SNR per luminance bin)
- Highlight headroom measurement (clipped percentages, recoverable highlights)
- Dynamic range comparison

### Key Finding: Shadow Noise Difference

**SPP applies extremely aggressive noise reduction in shadows:**

| Region | Our Noise (σ) | SPP Noise (σ) | Ratio |
|--------|---------------|---------------|-------|
| Deep shadows (0-25) | 13-14 | 1.7-2.0 | 6-8x |
| Dark shadows (25-50) | 13-14 | 7.1-7.2 | ~2x |

Our shadow SNR: ~1.1, SPP shadow SNR: ~11-13

### Implications

1. **Trade-off identified**: We preserve more shadow detail (but also more noise), SPP smoothness (but loses some detail)

2. **This contributes to RMSE**: The shadow noise difference accounts for part of the RMSE, but represents a deliberate aesthetic choice

3. **Could match SPP with shadow smoothing**: If exact SPP matching is desired, could add ISO-dependent shadow noise reduction

4. **Highlight clipping**: SPP clips highlights more aggressively (0.6-27% vs our 0.5-19% depending on image)

### Command to Use

```bash
python3 tools/compare_output.py <x3f> <ref_tiff> --iq-metrics
```

---

## Enhanced IQ Metrics Results (2026-02-25)

Added comprehensive IQ measurements to compare_output.py:
- Sharpness/edge response (gradient magnitude)
- Local contrast (block-based)
- Color analysis (saturation, channel dominance, correlations)

### Key Findings from New Metrics

#### 1. Sharpness - SPP Applies Aggressive Sharpening

| File | Our Mean Gradient | SPP Mean Gradient | Diff |
|------|------------------|-------------------|------|
| 0927 | 6.04 | 8.78 | -31% |
| 0993 | 5.58 | 8.28 | -33% |

- SPP has **3x more high-gradient pixels** (edges): 7.6% vs 2.4% (0927)
- SPP's sharpening accounts for much of the visual "pop" in their output

#### 2. Local Contrast - SPP Has Higher Contrast

| File | Our Local Contrast | SPP Local Contrast | Diff |
|------|-------------------|-------------------|------|
| 0927 | 0.177 | 0.209 | -15% |
| 0993 | 0.152 | 0.182 | -16% |

#### 3. Color - Significant Channel Balance Differences

**Channel Dominance (0927):**
- R-dominant: 30.1% vs 33.7% (SPP more red)
- **G-dominant: 42.5% vs 20.8%** (SPP much less green!)
- B-dominant: 22.7% vs 29.4% (SPP more blue)

**Channel Correlations:**
- RG: 0.92 vs 0.99 (SPP more correlated)
- GB: 0.76 vs 0.94 (SPP much more correlated!)
- RB: 0.87 vs 0.94 (SPP more correlated)

The **G-B channel correlation** difference (0.76 vs 0.94) is the most significant - SPP processes green and blue channels together much more tightly.

### Implications

1. **SPP sharpening is significant** - accounts for 30% higher gradients
2. **SPP has different color balance** - much lower G-dominant percentage
3. **Channel processing is tighter in SPP** - higher correlations between channels

### Possible Next Steps

1. Investigate the G-dominant discrepancy - is this a color matrix issue?
2. The G-B correlation difference suggests different color processing
3. Could add sharpening to match SPP's edge response

---

## 2026-02-25: Global Desaturation Implementation (commit ffe0725)

### Analysis
IQ metrics revealed our output was 2x more saturated than SPP (0.21 vs 0.09). This caused:
- G-dominant: 42% vs 21% (too much green)
- B-dominant: 23% vs 29% (not enough blue)
- Low channel correlations (G-B: 0.76 vs 0.94)

### Implementation
Added global desaturation in `src/x3f_process.c`:
```c
double gray = (output[0] + output[1] + output[2]) / 3.0;
double desat_factor = 0.65;
for (color = 0; color < 3; color++) {
  output[color] = gray + (output[color] - gray) * desat_factor;
}
```

Also adjusted channel multipliers: green=0.91, B=1.08, R=1.06

### Results

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| RMSE (0927) | 14.56 | 11.88 | - |
| Saturation | 0.21 | 0.14 | 0.09 |
| G-B correlation | 0.76 | 0.90 | 0.94 |
| RB correlation | 0.87 | 0.95 | 0.94 |
| RG correlation | 0.92 | 0.97 | 0.99 |
| G-dominant % | 42% | 32% | 21% |
| B-dominant % | 23% | 29% | 29% |

**Overall RMSE improvement: 18.4%** (14.56 → 11.88 for file 0927)

### Key Finding
SPP applies significant global desaturation that:
1. Reduces overall saturation (more muted colors)
2. Brings channel correlations closer together
3. Naturally reduces G-dominant bias

This is likely part of SPP's "film-like" processing aesthetic.

### Remaining Differences
- G-dominant is still 32% vs 21% (but RMSE improved significantly!)
- Sharpness is still 30% lower than SPP (aesthetic choice)
- Shadow noise is still 6-8x higher than SPP (detail preservation)

---

## 2026-02-26: Full Reference Set Validation

### Objective
Validate that desaturation improvements are consistent across all 25 reference files.

### Test Results

| Metric | Pre-Desaturation | Post-Desaturation | Improvement |
|--------|-----------------|-------------------|-------------|
| Overall Avg RMSE | 19.15 | 14.40 | **24.8%** |
| ISO 200 Avg RMSE | 18.95 | 13.80 | **27.2%** |
| ISO 400 Avg RMSE | 20.19 | 17.57 | **13.0%** |

### Per-File Results

| File | RMSE | Change | Notes |
|------|------|--------|-------|
| 0993 | 10.74 | -15.3% | Best match |
| 0991 | 11.93 | -16.3% | |
| 0992 | 11.89 | +0.4% | Slightly worse (tiny) |
| 0994 | 11.751% | |
 | -3.| 0927 | 11.88 | -18.4% | |
| 0990 | 12.39 | -32.5% | |
| 0995 | 12.47 | -12.6% | |
| 0996 | 12.48 | -12.4% | |
| 0998 | 12.60 | -7.8% | |
| 0997 | 12.85 | -8.2% | |
| 0929 | 13.92 | -29.7% | |
| 0930 | 14.04 | -41.4% | |
| 0928 | 14.62 | -33.6% | |
| 0933 | 14.72 | -38.7% | |
| 0932 | 17.43 | -24.4% | |
| 0936 | 16.37 | -51.1% | Best improvement |
| 0935 | 17.42 | -37.6% | |
| 0934 | 17.49 | -37.8% | |
| 0937 | 18.44 | -40.0% | |
| 1003 | 17.46 | -16.3% | ISO 400 |
| 1004 | 17.54 | -18.1% | ISO 400 |
| 1008 | 17.77 | -14.0% | ISO 400 |
| 1009 | 17.53 | -1.6% | ISO 400 |

**Improved: 24/25 files** (only 0992 was essentially unchanged, +0.05)

### Key Observations

1. **Best improvements**: Clipped files (0936: -51.1%, 0937: -40.0%) improved dramatically
2. **ISO 200 vs 400**: Desaturation helps ISO 200 files more (27% vs 13%)
3. **Remaining high-RMSE files**: 
   - ISO 400 files (1003, 1004, 1008, 1009) still around 17.5
   - Some clipped files (0934, 0935, 0937) still above 17

### IQ Metrics Consistency Check

| File | Our Saturation | Ref Saturation | Our G-Dom | Ref G-Dom |
|------|----------------|----------------|-----------|-----------|
| 0927 | 0.14 | 0.09 | 32% | 21% |
| 0993 | 0.10 | 0.10 | 30% | 38% |
| 0994 | 0.43 | 0.18 | 31% | 16% |
| 1003 | 0.20 | 0.06 | 40% | 21% |

- **File 0993**: Nearly perfect match (saturation 0.10 vs 0.10)
- **Other files**: Still show saturation discrepancy (varies by scene)
- **ISO 400**: Higher saturation issue persists

### Conclusion

Desaturation was the right direction - **24/25 files improved**. The average RMSE dropped from 19.15 to 14.40 (24.8% improvement). Remaining issues are:
1. Scene-dependent saturation - some images need more/less desaturation
2. ISO 400 files still underperform (13% vs 27% improvement)
3. IQ metrics show color balance still differs by scene

### Next Steps Options

1. **Further desaturation**: Try factor 0.60-0.55 for more aggressive desaturation
2. **Per-ISO tuning**: Different desaturation for ISO 400 vs ISO 200
3. **Scene-adaptive**: Adjust desaturation based on image statistics
4. **Focus on ISO 400**: These files need specific improvements

---

## 2026-02-26: ICC Profile Embedding Fix

### Problem
Output TIFFs were missing ICC profiles, causing color-managed applications to incorrectly interpret colors as sRGB instead of Adobe RGB, resulting in washed-out/grey appearance.

### Analysis
- SPP reference TIFFs contain 560-byte Adobe RGB (1998) ICC profiles
- x3f_extract was not embedding any ICC profile in output TIFFs
- When using `-color AdobeRGB`, output should include the Adobe RGB ICC profile

### Implementation
Added Adobe RGB ICC profile embedding in `src/x3f_output_tiff.c`:
1. Extracted 560-byte Adobe RGB ICC profile from SPP reference TIFF
2. Added `adobe_rgb_profile[]` array (560 bytes) to the source
3. Added `TIFFSetField()` call to embed ICC when encoding==ARGB

### Results
- **Output TIFF ICC profile**: 560 bytes (matches SPP)
- **ICC profiles verified as IDENTICAL** between output and reference
- Comparison tool now shows ICC profile embedded correctly

### Verification
```
Reference TIFF ICC: YES (560 bytes)
Output TIFF ICC:   YES (560 bytes)
ICC profiles MATCH!
```

### Commit
- `33dc5e7`: Embed Adobe RGB ICC profile in TIFF output

---

## 2026-02-26: DeltaE Perceptual Color Metrics

### Problem
Saturation metrics (HSL-based) were misleading - visually undersaturated output had similar/higher saturation values than SPP reference. Needed perceptual color accuracy metric.

### Solution
Added DeltaE (CIELAB color difference) to compare_output.py:
- RGB → linear → XYZ → Lab conversion
- DeltaE1976 calculation per pixel
- Per-channel Lab error analysis (L, a, b)
- Regional DeltaE (shadows/midtones/highlights)
- Per-pixel random sampling with full RGB/Lab values

### Key Finding from DeltaE Analysis
**The 'a' channel (green-magenta axis) has massive errors (mean=53.83, max=907.14)**:
- This explains the green cast issue
- Midtones are worst (mean DeltaE 105.26 vs shadows 45.09)
- This is the primary color accuracy issue to address

### Metrics Comparison
| Metric | What it measures | Useful for |
|--------|-----------------|------------|
| RMSE | Raw pixel difference | General accuracy |
| DeltaE | Perceptual color difference | **Color accuracy** |
| Saturation | (max-min)/max | NOT useful |

DeltaE > 20 = visually different colors. Our mean DeltaE ~82 indicates significant color inaccuracy.

### Command
```bash
python3 tools/compare_output.py <x3f> <ref_tiff> --delta-e --num-samples 50
```

DeltaE is now enabled by default. Use `--no-delta-e` to disable.

### Commit
- `4e2020b`: Add DeltaE perceptual color metrics to comparison tool

---

## 2026-02-26: DeltaE Improvements

### Problem
DeltaE analysis revealed massive a-channel (green-magenta) errors:
- Mean DeltaE: 81.99 (target < 20)
- a-channel: mean=53.83, max=907.14
- Midtones worst: mean=105.26 vs shadows 45.09

### Solution
1. Stronger green channel reduction (0.91 → 0.85)
2. Increased B/R boosts (B: 1.08→1.10, R: 1.06→1.08)
3. Added global desaturation (factor 0.70) to target midtones

### Results for _P2M0927.X3F

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Mean DeltaE | 81.99 | 69.14 | **15.7%** |
| a-channel | 53.83 | 42.76 | **20.5%** |
| Midtone DeltaE | 105.26 | 90.77 | **13.8%** |
| RMSE | 14.44 | 12.47 | **13.6%** |

### Per-File DeltaE Results

| File | Mean DeltaE | a-channel | RMSE | Notes |
|------|-------------|-----------|------|-------|
| 0994 | 13.65 | 8.59 | 12.21 | Best |
| 0993 | 31.65 | 17.15 | 11.38 | |
| 1009 | 32.25 | 20.87 | 18.47 | ISO 400 |
| 0928 | 48.13 | 28.77 | 15.03 | |
| 1003 | 55.61 | 37.70 | 18.36 | ISO 400 |
| 0930 | 61.72 | 37.84 | 14.50 | |
| 0929 | 68.22 | 42.16 | 14.52 | |
| 0927 | 69.14 | 42.76 | 12.47 | |

### Key Findings
1. File 0994 achieves DeltaE 13.65 - nearly perfect match!
2. Some files (0927, 0929) still have high DeltaE (~69)
3. ISO 400 files (1003, 1009) show mixed results
4. The a-channel is still the biggest contributor to error

### Next Steps
- Investigate why some files (0927, 0929) still have high DeltaE
- Consider scene-adaptive color correction
- Focus on ISO 400 specific improvements

---
