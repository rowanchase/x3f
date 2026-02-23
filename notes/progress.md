# X3F Merrill Development Progress

## Overview
This project aims to fix issues with the `x3f_extract` tool for processing Sigma Foveon X3F files from Merrill series cameras (DP1m, DP2m, DP3m). The goal is to make the output match Sigma Photo Pro's reference outputs exactly.

## Work Completed

### 2026-02-23: Highlight Desaturation Implementation

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
4. ✅ Implement exposure compensation (2.6x)
5. ✅ Test on all 25 reference files
6. ✅ Implement rotation handling
7. ✅ Implement sigmoid tone curve (k=4.4)
8. ✅ Implement highlight desaturation
9. ✅ Implement shadow desaturation (luminance-based)
10. ✅ Implement ISO-dependent shadow processing

## Remaining Work

1. **Consider reading TC parameters from X3F**
   - Currently hardcoding steepness=4.4
   - X3F metadata has TCGamma, TCStart, TCEnd, TCSteepness

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
