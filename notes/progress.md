# X3F Merrill Development Progress

## Overview
This project aims to fix issues with the `x3f_extract` tool for processing Sigma Foveon X3F files from Merrill series cameras (DP1m, DP2m, DP3m). The goal is to make the output match Sigma Photo Pro's reference outputs exactly.

## Work Completed

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
- Files have varying ISO: ISO 200 (most) and ISO 400 (1003, 1008)
- Attempted ISO-relative exposure compensation but made things worse
- Original 2.6x compensation works best across all ISO values

#### Current Metrics (25 files)
| File | RMSE | MAE | Mean Error |
|------|------|-----|------------|
| 0927 | 16.78 | 12.51 | +1.9 |
| 0928 | 22.63 | 18.03 | +8.9 |
| 0929 | 18.58 | 14.28 | +4.1 |
| 0930 | 23.23 | 15.34 | +3.8 |
| 0932 | 26.20 | 21.55 | +9.8 |
| 0933 | 29.12 | 22.75 | +11.2 |
| 0934 | 29.57 | 20.89 | +8.8 |
| 0935 | 29.14 | 20.45 | +8.4 |
| 0936 | 34.19 | 20.36 | +5.9 |
| 0937 | 31.67 | 21.01 | +8.0 |
| 0990 | 23.26 | 19.29 | +7.4 |
| 0991 | 18.75 | 14.04 | +4.4 |
| 0992 | 24.30 | 20.56 | +10.4 |
| **0993** | **15.39** | 10.17 | +0.8 |
| 0994 | 23.30 | 18.86 | +8.3 |
| 0995 | 21.82 | 17.65 | +8.2 |
| 0996 | 22.02 | 17.85 | +8.5 |
| 0997 | 22.94 | 18.76 | +8.0 |
| 0998 | 21.27 | 16.91 | +6.7 |
| 1000 | 23.07 | 18.87 | +10.3 |
| 1001 | 24.17 | 20.31 | +11.1 |
| 1003 | 30.05 | 23.60 | +5.6 |
| 1004 | 28.30 | 20.13 | +3.4 |
| 1008 | 29.55 | 23.33 | +4.1 |
| 1009 | 31.41 | 25.69 | +6.9 |

**Best match:** 0993 (RMSE 15.39, mean error 0.76)
**Average RMSE:** ~24.8

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

### With Exposure Compensation (2.6x)

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
4. ✅ Investigate darkness issue
   - Root cause: SPP applies ~2.6x additional exposure
   - Implemented exposure compensation
5. ✅ Test on all 10 reference files

## Remaining Work

1. **Implement rotation handling** (HIGH PRIORITY)
   - Read ROTATION metadata from CAMF
   - Apply 90°/270° rotation as needed
   
2. **Investigate remaining exposure variance**
   - Files 28, 32, 37 are over-exposed
   - May need scene-dependent adjustments

3. **Test S-curve tone curve**
   - Non-linear ratio suggests S-curve would help
   - Shadows need more lift, highlights less

4. **Investigate spatial gain weighting** (Issue #114)

### Source Code
- `src/x3f_extract.c` - Main CLI tool entry point
- `src/x3f_process.c` - Core image processing (black level, color conversion, denoising)
- `src/x3f_output_tiff.c` - TIFF output writer
- `src/x3f_matrix.c` - Color space conversion matrices
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
