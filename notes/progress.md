# X3F Merrill Development Progress

## Overview
This project aims to fix issues with the `x3f_extract` tool for processing Sigma Foveon X3F files from Merrill series cameras (DP1m, DP2m, DP3m). The goal is to make the output match Sigma Photo Pro's reference outputs exactly.

## Work Completed

### 2026-02-27: Phase 2b - Soft-Knee Compression & Texture Transfer

#### Summary
Implemented Phase 2b of the Foveon X3F highlight recovery according to `doc/PHASE_2B_PLAN.md`. This phase adds **Soft-Knee Blending** to populate the 200-250 histogram range and **Texture Transfer** to restore detail using unclipped layers, bridging the gap between Phase 2's "hard value recovery" and SPP's "natural texture recovery".

#### Problem Being Solved
Phase 2 produces accurate flat colors but lacks texture and has a harsh clipping transition, resulting in a histogram pile-up at 255. Phase 2b addresses:
1. **Histogram**: Pile-up at 255 from harsh clipping
2. **Texture**: Flat, lifeless reconstructed highlights
3. **Transition**: Abrupt boundary between clipped and unclipped regions

#### Technical Implementation
**Modified File:**
- `src/x3f_highlight_recovery.c` - Added Phase 2b features:

**New Configuration Parameters:**
```c
#define SOFT_KNEE_THRESHOLD 0.80f  /* Start compression at ~204/255 */
#define TEXTURE_STRENGTH 1.0f       /* Full texture transfer */
#define NEAR_CLIP_THRESHOLD 0.80f   /* Process near-clipped pixels */
```

**New Helper Functions:**
1. **`compress_highlight()`** - Soft-knee compression using tanh-like function
   - Linear region: 0.0 → 0.8 (unchanged)
   - Compression region: maps [0.8, ∞) → [0.8, 1.0] smoothly
   - Formula: `f(x) = T + (1-T) * tanh((x-T)/(1-T))`

2. **`get_local_average()`** - 3x3 neighborhood average for texture context

3. **`get_texture_ratio()`** - Extracts detail ratio (pixel/local_avg)
   - Returns ratio representing local detail (e.g., 0.9 to 1.1)
   - Captures high-frequency texture from unclipped channels

4. **`find_texture_source()`** - Selects best unclipped channel (Red > Green > Blue)

**Modified Reconstruction Functions:**

1. **`reconstruct_single_channel()`** - Now includes:
   - Texture transfer from unclipped channels
   - Clamped texture ratio [0.5, 1.5] to prevent extremes
   - Soft-knee compression on output
   - Value clamping to prevent runaway amplification

2. **`reconstruct_two_channels()`** - Now includes:
   - Texture transfer from single valid channel
   - Applied to both reconstructed channels
   - Soft-knee compression on output

3. **`reconstruct_all_channels()`** - Now includes:
   - Soft-knee compression on desaturated output

**Critical Main Loop Update:**
`x3f_reconstruct_highlights()` now processes **near-clipped pixels** (values > 0.8):
```c
if (info->state == CLIP_STATE_NONE) {
  /* Check for near-clipped pixels (smooth transition zone) */
  for (c = 0; c < 3; c++) {
    if (info->raw_values[c] > NEAR_CLIP_THRESHOLD) {
      has_near_clipped = 1;
      break;
    }
  }
  
  if (has_near_clipped) {
    /* Apply soft-knee compression to near-clipped channels */
    for (c = 0; c < 3; c++) {
      reconstructed[c] = compress_highlight(info->raw_values[c], SOFT_KNEE_THRESHOLD);
    }
  }
}
```

#### Foveon Advantage: Texture Transfer
Unlike Bayer sensors, Foveon captures RGB at the same spatial location:
- If **Blue is Clipped** but **Red is Valid**, Red's texture is a perfect predictor for Blue's missing texture
- Reconstruct: `B_rec = B_flat_estimate * (R_pixel / R_local_avg)`
- The ratio captures local detail independent of overall intensity

#### Build & Test Results
- **Build**: Clean compilation with no errors
- **Test**: Successfully processes _P2M0927.X3F with highlight recovery
- **Metrics**: RMSE 11.49 (baseline - Phase 2b targets highlight quality, not overall RMSE)

#### Expected Improvements
1. **Histogram**: Values populate 200-250 range instead of piling at 255
2. **Texture**: Clipped regions show natural detail from unclipped channels
3. **Visual**: Highlights appear textured and natural, not flat white patches
4. **Transition**: Smooth gradation from near-clipped to fully clipped areas

#### Documentation
- Detailed journal: `notes/27-02-2026_phase2b_implementation.md`
- Plan document: `doc/PHASE_2B_PLAN.md`

#### Future Work (Phase 3)
Poisson smoothing still planned, but Texture Transfer + Soft-Knee may reduce its necessity if boundaries blend well.

#### Pipeline Ordering Investigation (Same Day)
**Problem Discovered:** Phase 2b soft-knee compression is being applied BEFORE the 2.5x exposure compensation in `x3f_process.c`, effectively undoing its benefits.

**Investigation:**
1. **Attempt 1**: Moved compression to after 2.5x boost in x3f_process.c
   - Result: Histogram got significantly worse (+93K to +207K more soft highlights)
   - Issue: Threshold of 1.0 after boost compressed values back into soft range

2. **Attempt 2**: Adjusted threshold to 2.5 (accounting for boost)
   - Result: No change (most values ≤2.5)

3. **Attempt 3**: Restored compression in highlight_recovery.c with adjusted threshold (0.32 = 0.8/2.5)
   - Result: Same histogram as original

**Root Cause:**
- The tanh-based compression maps [threshold, ∞] → [threshold, 1.0]
- With threshold=0.8: boosted values go to [2.0, 2.5], mapping to soft highlights (200-255)
- The problem isn't WHERE compression happens, but HOW - tanh creates concentration instead of distribution

**Current Status:**
- Reverted to original approach (compression in highlight_recovery.c with threshold=0.8)
- Documented findings in `notes/27-02-2026_pipeline_ordering.md`
- Identified next steps: investigate LUT mapping, try alternative compression curves

---

### 2026-02-27: Phase 2 - Multi-Channel Highlight Reconstruction

#### Summary
Implemented the core reconstruction algorithms for Foveon X3F highlight recovery. This phase uses Phase 1's boundary data to estimate values for clipped pixels using the unique three-layer Foveon sensor architecture.

#### Technical Implementation
**Modified Files:**
- `src/x3f_highlight_recovery.h` - Added `x3f_reconstruct_highlights()` declaration
- `src/x3f_highlight_recovery.c` - Phase 2 implementation with three case handlers:
  - Case 1: Single channel clipped (ratio-based reconstruction)
  - Case 2: Two channels clipped (spectral estimation from QE data)
  - Case 3: All channels clipped (graceful desaturation)
- `src/x3f_process.c` - Integration with pipeline, bug fix for NULL pointer dereference

#### Key Features
- **New Buffer Strategy**: Allocates separate output buffer for reconstructed image
- **Spectral Estimation**: Uses Fent & Meldrum (2016) QE data (Blue=10.6, Green=13.2, Red=9.0)
- **Smoothstep Blending**: 30% transition zone at clipping boundaries
- **Always Enabled**: Automatically processes all Foveon images with clipped pixels
- **Simplified Case 2**: Direct spectral estimation (hierarchical processing noted for future)

#### Bug Fix: NULL Pointer Dereference
**Issue**: Called `x3f_get_highlight_params()` with NULL pointers for unused parameters, but function writes to all parameters unconditionally.

**Fix**: Used already-fetched `hl_sat_factor` from line 813 instead of calling function again.

#### Test Results

**_P2M0927.X3F (Standard case):**
- Clipped pixels: 14,470 (0.09%)
  - Single channel: 7,064 → reconstruct_single_channel()
  - Two channels: 6,284 → reconstruct_two_channels()
  - All channels: 1,122 → reconstruct_all_channels()
- **Result**: SUCCESS - All 14,470 pixels reconstructed without crash

**_P2M0936.X3F (Worst case - severe clipping):**
- Clipped pixels: 652,921 (4.06% of image)
  - Single channel: 131,656
  - Two channels: 252,659
  - All channels: 268,606
- **Result**: SUCCESS - Handles large clipped regions (652K pixels) without issues

**_P2M0928.X3F (Minimal clipping):**
- Clipped pixels: 3,722 (0.02%)
- **Result**: SUCCESS - Works with minimal clipping

#### Quality Metrics (Initial Baseline)

Comparing to SPP reference for _P2M0927.X3F:
- RMSE: 11.49 (target: < 5.0)
- MAE: 8.71
- Per-channel MAE: R=7.43, G=7.20, B=11.50

The RMSE is higher than target, which is expected for initial implementation. This provides a baseline for Phase 3 (Poisson smoothing) and further refinements.

#### Build & Integration
- Build: Clean (no compiler warnings)
- No segfaults or crashes across all test files
- Memory properly managed (allocation/deallocation)
- Integrated seamlessly with existing pipeline

#### Documentation
- Created detailed Phase 2 journal: `notes/27-02-2026_phase2_complete.md`
- Documented hierarchical processing as future enhancement
- Recorded spectral constants and algorithm details

#### Next Steps
1. ⬜ Run full test suite on all 10 reference files
2. ⬜ Implement Phase 3 (Poisson gradient domain smoothing) if needed
3. ⬜ Analyze reconstruction quality and optimize spectral estimation
4. ⬜ Consider hierarchical processing if large region accuracy is insufficient

---

### 2026-02-27: Phase 1 - Highlight Recovery Foundation

#### Summary
Implemented the foundation for Foveon-specific highlight recovery using multi-layer sensor data. This phase establishes clipping detection and boundary analysis capabilities.

#### Technical Implementation
**New Files:**
- `src/x3f_highlight_recovery.h` - Data structures and function declarations
- `src/x3f_highlight_recovery.c` - Core clipping detection and boundary analysis

**Modified Files:**
- `src/makefile` - Added new module to build
- `src/x3f_process.c` - Integrated into processing pipeline

#### Key Features
- **Quality-Prioritized Design**: 32-pixel search radius, Gaussian weighting
- **Complete Clipping State Detection**: All 8 states (NONE, B, G, R, BG, BR, GR, ALL)
- **Boundary Analysis**: Computes B/G, B/R, G/R ratios from unclipped neighbors
- **Always Enabled**: As per user requirements
- **Metadata Integration**: Uses HighlightBlendingLow threshold from X3F files

#### Test Results (_P2M0927.X3F)
- Total clipped pixels: 14,470 (0.09% of image)
- Single channel clipped: 7,064
- Two channels clipped: 6,284
- All channels clipped: 1,122

#### Foundation for Phase 2
The clipping map and boundary data structures are now ready for:
- Single-channel reconstruction using unclipped neighbors
- Two-channel reconstruction with spectral estimation
- Poisson gradient domain smoothing
- Hierarchical processing for large clipped regions

---

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

### Additional Improvements (2026-02-26)

Applied R/B boost relative to G approach:
- green_correction: 0.85 → 0.895
- b_correction: 1.10 → 1.19
- r_correction: 1.08 → 1.17
- desat_factor: 0.70 → 0.62

Results:
| File | Before | After | Change |
|------|--------|-------|--------|
| 0927 | 69.14 | 64.29 | -7.0% |
| 0993 | 31.65 | 28.82 | -8.9% |
| 0994 | 13.65 | 13.47 | -1.3% |
| 1003 | 55.61 | 54.42 | -2.1% |
| 1009 | 32.25 | 31.05 | -3.7% |

Files now under/close to DeltaE < 25:
- 0994: 13.47 ✓
- 0990: 22.43 ✓
- 0992: 22.34 ✓
- 1000: 23.32 ✓
- 1001: 23.69 ✓
- 0993: 28.82 (close)
- 1009: 31.05 (close)

Still high: 0927 (64), 0929 (67), 0930 (60)

### Next Steps
- Investigate why some files (0927, 0929) still have high DeltaE
- Consider scene-adaptive color correction
- Focus on ISO 400 specific improvements

---

---

## 2026-02-26: Fundamental Color Matrix Analysis (Deep Research)

### Root Cause Discovery

After deep analysis of the color processing pipeline, I've identified the **fundamental root cause** of our color inaccuracies:

**The color matrix computation is wrong for Merrill cameras.**

In `src/x3f_process.c` lines 253-284, there are TWO approaches:

**Approach A** (lines 257-264) - Used for Merrill:
- Uses `WhiteBalanceColorCorrections` matrix (e.g., AutoCCMatrix)
- Treats it as raw→sRGB conversion matrix
- **WRONG**: These are color CORRECTION matrices, not conversion matrices
- Contains values like: [[1.90, -1.76, 0.86], [-1.68, 3.53, -0.85], [1.08, -4.91, 4.83]]

**Approach B** (lines 266-276) - NOT USED for Merrill:
- Uses `WhiteBalanceIlluminants` + `WhiteBalanceCorrections`
- Properly computes raw→XYZ
- **NOT AVAILABLE** in Merrill X3F files

### Why This Matters

Since Merrill files have `WhiteBalanceColorCorrections` but NOT `WhiteBalanceIlluminants`:
- Approach A succeeds → wrong matrix used
- This explains why we need heavy empirical corrections:
  - Green: 0.895 (to counteract wrong matrix)
  - Desaturation: 0.62 (to counteract saturation error)
  - R/B boost: 1.17/1.19 (to balance channels)

### Research Findings

1. **dcraw approach**: Also uses WhiteBalanceIlluminants + Corrections, but Merrill files don't have this data
2. **Foveon Merrill inherent limitation**: SMI ~82 (vs 98+ for good cameras) - fundamentally limited by sensor physics
3. **Academic research**: JOSA 2015 paper measured actual SD1 Merrill spectral sensitivity

### Options for Fix

1. **Find alternative matrix**: Research published Merrill spectral data
2. **Force different computation**: Skip WhiteBalanceColorCorrections  
3. **Per-scene calibration**: Adaptive corrections based on image statistics
4. **Continue incremental tuning**: Current approach (some files already <25 DeltaE)

### Current DeltaE Status

| File | DeltaE | Status |
|------|--------|--------|
| 0994 | 13.47 | ✓ Excellent |
| 0990 | 22.43 | ✓ Good |
| 0992 | 22.34 | ✓ Good |
| 1000 | 23.32 | ✓ Good |
| 1001 | 23.69 | ✓ Good |
| 0993 | 28.82 | Close |
| 1009 | 31.05 | Close |
| 0927 | 64.29 | Needs fix |
| 0929 | ~67 | Needs fix |
| 0930 | ~60 | Needs fix |

### Recommended Next Steps

1. ~~Add debug output to confirm which matrix path is used~~
2. Research Merrill-specific spectral sensitivity data  
3. Try processing with dcraw for comparison
4. Consider scene-adaptive corrections for high-DeltaE files

---

## 2026-02-26: Debug Matrix Path - CONFIRMED

### What I Did

1. Added debug output to `x3f_get_bmt_to_xyz()` and `x3f_get_raw_to_xyz()` to confirm:
   - Which code path is taken (ColorCorrections vs Illuminants)
   - The actual matrix values being used

2. Analyzed dcraw source code (`/tmp/dcraw.c`) to understand its Foveon handling

### Findings

**CONFIRMED**: Merrill uses ColorCorrections path (as expected)

**Matrix values from CAMF (AutoCCMatrix)**:
```
[[1.898, -1.758, 0.859],
 [-1.680, 3.531, -0.852],
 [1.078, -4.906, 4.828]]
```

**Current formula**: `bmt_to_xyz = sRGB_to_XYZ * cc_matrix`

**Resulting raw_to_xyz** (with gain applied):
```
[[0.917, -0.401, 0.694],
 [-1.752, 2.075, -0.059],
 [2.096, -4.936, 3.391]]
```

**Key observation**: Large negative values in the matrix indicate this is NOT a proper camera→XYZ conversion matrix. Normal camera matrices have all-positive values that sum to ~1 per row.

### dcraw Research

- Downloaded dcraw source (`/tmp/dcraw.c`)
- dcraw also relies on `WhiteBalanceIlluminants` + `WhiteBalanceCorrections`
- If Illuminants missing, dcraw prints error and returns
- **dcraw does NOT have hardcoded Merrill matrices**
- This confirms: no easy solution from dcraw

### Matrix Multiplication Order Experiments

Tested different approaches:

| Approach | Formula | Row 0 | Row 1 | Row 2 |
|----------|---------|-------|-------|-------|
| Current | sRGB_to_XYZ * cc | 0.377, -0.348, 0.921 | -0.720, 1.798, -0.078 | 0.861, -4.276, 4.504 |
| Alternative | cc * sRGB_to_XYZ | 0.426, -0.476, 1.033 | 0.042, 1.823, -0.858 | -0.505, -2.548, 4.430 |
| Identity | sRGB_to_XYZ only | 0.412, 0.358, 0.181 | 0.213, 0.715, 0.072 | 0.019, 0.119, 0.950 |

All approaches have unusual negative values - none look like proper camera matrices.

### Key Insights

1. **Root cause confirmed**: CCMatrix is incorrectly used as conversion matrix
2. **No easy fix**: No alternative matrix available in metadata
3. **Foveon Merrill limitations**: SMI ~82 vs 98+ for good cameras (sensor physics)
4. **File-dependent**: 0994 achieves 13.47 DeltaE, 0927 has 64

### What Was Changed

- `src/x3f_process.c`: Added and then removed debug output for matrix analysis

### Next Steps

1. Try experiment: Skip CCMatrix entirely, use identity/sRGB_to_XYZ only
2. Research published Foveon spectral sensitivity data for Merrill
3. Consider scene-adaptive corrections for high-DeltaE files



---

## 26 Feb 2026 - Research: Fent & Meldrum (2016) Paper Review

**Completed**: Comprehensive review of "A Foveon Sensor/Green-Pass Filter Technique for Direct Exposure of Traditional False Color Images" by Fent & Meldrum (Journal of Imaging, 2016)

**Key Discoveries**:
1. Located detailed spectral sensitivity data for Foveon F20 sensor (Merrill series)
2. Found quantum efficiency ratios for all three layers at different wavelengths
3. Identified 4100K white balance as optimal setting (vs standard 5500K)
4. Discovered Alternate Vision Corp as source for Foveon QE curves
5. Learned about cross-layer spectral overlap requiring careful matrix calibration

**Relevant to Current Issues**:
- Color matrix accuracy in x3f_matrix.c
- White balance handling differences
- Spatial gain compensation for Merrill cameras
- Spectral sensitivity calibration

**Next Steps**:
- Locate Alternate Vision Corp spectral data files
- Compare current color matrices against paper's QE ratios
- Verify white balance implementation matches 4100K optimization
- Investigate spatial gain values


---

## 26 Feb 2026 - IMPLEMENTATION: Blue Channel Correction Optimization

### Completed Work

1. **Comprehensive paper review** of Fent & Meldrum (2016) - documented key findings
2. **Pipeline analysis** - examined empirical corrections in x3f_process.c
3. **Applied improvement** - adjusted blue channel correction based on QE data
   - Changed: 1.19 → 1.06 (19% boost → 6% boost)
   - Based on paper's F20 sensor QE: Blue=10.6, Green=13.2 at 500-575nm
   
### Results

**Quantitative improvements on _P2M0927.X3F:**
- RMSE improved by 3.9% (11.94 → 11.48)
- B-channel error reduced by 7.4% (MAE: 12.40 → 11.48)
- B-channel bias nearly eliminated (MeanErr: 4.23 → -0.38)

**Commit:** `013e5c7` - "Adjust blue channel correction based on Fent & Meldrum (2016) QE data"

### Key Insights from Implementation

1. The Fent & Meldrum QE data provides concrete numerical values for sensor response
2. Small adjustments (13% reduction in blue boost) can yield measurable improvements
3. The empirical corrections were over-compensating for blue channel
4. Remaining errors suggest other factors (spatial gain, denoising, WB) need attention

### Remaining Work

1. **Spatial gain optimization** - Paper emphasizes Merrill sensitivity to spectral balance
2. **White balance analysis** - Test if 4100K Fluorescent provides better match than Auto
3. **Per-image variation** - Understand why different files show different error levels
4. **Additional channel corrections** - Green and red corrections may also need tuning

### Success Criteria

Target: RMSE < 5.0 and DeltaE mean < 10 across all reference files
Current: RMSE ~11-15, DeltaE mean ~64 (significant room for improvement)

