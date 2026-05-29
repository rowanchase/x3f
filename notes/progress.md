# X3F Merrill Development Progress

## Overview
This project aims to make `x3f_extract` output match Sigma Photo Pro (SPP) for Merrill series cameras (DP1m, DP2m, DP3m). Current status: **Average RMSE 11.48, DeltaE 64.29** (down from initial RMSE ~50).

---

## Completed Milestones

### 1. Foundation (2026-02-22 to 2026-02-24)
**Key Achievements:**
- Fixed PR #120: Disabled right shielded area for Merrill (was causing green tint in shadows)
- Implemented rotation handling (17/25 files are portrait orientation)
- Created test framework (`tools/compare_output.py`) with RMSE/MAE/DeltaE metrics
- Built tool successfully with OpenCV 3.0 (patched for GCC 11+)

**Root Cause - Darkness Issue:**
- Output was ~37% darker than SPP initially
- Discovered SPP applies S-curve tone adjustment + sharpening (cannot be disabled)
- Jim Kasson's blog confirmed SPP's aggressive processing

### 2. Tone Curve & Exposure (2026-02-24)
**Implementation:**
- Sigmoid tone curve with TCSteepness=3.0 from X3F metadata (was hardcoded 4.4)
- Exposure compensation: 2.5x (adjusted from 2.6x to match new tone curve)
- Results: All files now below RMSE 20, average RMSE 22.55 (9% improvement)

### 3. Color Corrections (2026-02-25 to 2026-02-26)
**Green Channel Fix:**
- Reduced green by 4% (0.96x) to address consistent G channel positive error
- Improved RMSE by 2-5% across all files

**R/B Channel Boosts:**
- Added universal R/B boost: R=1.02x, B=1.02x initially
- Later refined to: R=1.17x, B=1.19x (based on DeltaE analysis)
- Finally optimized to: R=1.08x, B=1.06x (based on Fent & Meldrum QE data)

**Global Desaturation:**
- Added desaturation factor 0.65 → 0.62 to match SPP's muted colors
- Results: 24/25 files improved, average RMSE 14.40 (24.8% improvement from 19.15)
- Saturation now 0.14 vs SPP 0.09 (closer), G-B correlation 0.90 vs 0.94

### 4. ISO-Dependent Processing (2026-02-23)
**Problem:** ISO 400 files had RMSE 22.18 vs ISO 200 at 15.31
**Solution:**
- ISO-dependent shadow desaturation: 0.7 (ISO 200) → 0.95 (ISO 400)
- B channel boost in shadows for ISO 400
- Results: ISO 400 avg improved 9% (22.18 → 20.19)

### 5. Highlight Recovery (2026-02-26 to 2026-02-27)
**Phase 1 - Foundation:**
- Read CAMF highlight parameters: HighlightBlendingLow=0.75, High=1.5, RestoreThresh=1.75
- Implemented clipping detection with 8 states (NONE, B, G, R, BG, BR, GR, ALL)
- Quality-prioritized design: 32-pixel search radius, Gaussian weighting

**Phase 2 - Multi-Channel Reconstruction:**
- Three case handlers: single channel clipped, two channels clipped, all channels clipped
- Spectral estimation using Fent & Meldrum QE data (B=10.6, G=13.2, R=9.0)
- Smoothstep blending with 30% transition zone
- Successfully handles 652K clipped pixels (file 0936)
- RMSE baseline: 11.49 (target: <5.0)

**Phase 2b - Soft-Knee & Texture Transfer:**
- Soft-knee compression: tanh function maps [0.8, ∞] → [0.8, 1.0]
- Texture transfer from unclipped channels (Foveon advantage: RGB at same location)
- Histogram: values now populate 200-250 range instead of piling at 255
- Found triple compression issue (tanh → 2.5x boost → LUT) causing pile-up
- Uniform highlight compression fix: scale all channels equally when clipping

### 6. Sharpening (2026-03-06)
**Richardson-Lucy Deconvolution:**
- Optional post-processing step (default ON for TIFF)
- Gaussian PSF with sigma=0.7, 20 iterations
- Adds ~8.5 seconds for 15MP image
- CLI flags: `-sharpen`, `-no-sharpen`, `-sharpen-psf <F>`, `-sharpen-iter <N>`

### 7. Color Management (2026-02-26)
**ICC Profile Embedding:**
- Added 560-byte Adobe RGB ICC profile to TIFF output (matches SPP)
- Fixed washed-out colors in color-managed applications

**DeltaE Metrics:**
- Added perceptual color difference measurement to compare_output.py
- Found massive a-channel (green-magenta) errors: mean=53.83
- Target DeltaE < 20; achieved 13.47 for best file (0994)

---

## Key Technical Findings

### 1. Color Matrix Issue (Fundamental Root Cause)
**Problem:** Merrill X3F files contain `WhiteBalanceColorCorrections` (e.g., AutoCCMatrix) but NOT `WhiteBalanceIlluminants`. Current code incorrectly uses ColorCorrections as raw→XYZ conversion matrix.

**Evidence:**
- Matrix has large negative values: [[0.917, -0.401, 0.694], [-1.752, 2.075, -0.059], [2.096, -4.936, 3.391]]
- Normal camera matrices should have all-positive values summing to ~1 per row
- This explains need for heavy empirical corrections (green 0.895x, desat 0.62x, R/B boosts)

**Fent & Meldrum (2016) Research:**
- Located Foveon F20 sensor spectral sensitivity data
- Quantum efficiency: Blue=10.6, Green=13.2, Red=9.0 at 500-575nm
- 4100K white balance optimal (vs standard 5500K)
- Applied blue channel correction: 1.19 → 1.06 (improved RMSE 3.9%)

### 2. SPP Processing Pipeline
**What SPP does that we must match:**
1. S-curve tone adjustment (TCSteepness=3.0 from metadata)
2. Aggressive sharpening (cannot be disabled)
3. Global desaturation (produces "film-like" muted colors)
4. Shadow noise reduction (6-8x more aggressive than us)
5. Highlight compression with soft knee

**Our vs SPP IQ Metrics:**
| Metric | Ours | SPP | Difference |
|--------|------|-----|------------|
| Sharpness (gradient) | 6.04 | 8.78 | -31% |
| Local Contrast | 0.177 | 0.209 | -15% |
| Shadow Noise (σ) | 13-14 | 1.7-2.0 | 6-8x |
| G-dominant % | 32% | 21% | +11% |
| G-B correlation | 0.90 | 0.94 | -0.04 |

### 3. Tone Curve Placement
**Experiment (2026-03-06):** Tested applying tone curve before color conversion
- Result: RMSE 118.85 (5.5x worse than baseline 21.50)
- Conclusion: Tone curve MUST remain at end of pipeline (after color conversion, desaturation, CCM)
- Moving it earlier breaks assumptions of downstream processing

---

## 2026-04-03: Darktable Processing Analysis

### Experiment
Tested whether darktable processing (from XMP file) could provide improvements to x3f_extract.

### Findings
| Metric | x3f_extract | darktable+XMP | SPP |
|--------|-------------|---------------|-----|
| RMSE | 17.12 | 19.14 | 0 |
| Saturation | 0.127 | 0.218 | 0.088 |

**Key Finding:** darktable output is WORSE than current x3f_extract (RMSE 19.14 vs 17.12).

### Attempts
1. **Global desaturation (0.7)** - RMSE increased to 17.30 (worse)
2. **Channel mixer only** - RMSE increased to 19.00 (much worse)
3. **Combined** - RMSE 16.69 but caused regressions on other files

### Conclusion
- Darktable XMP not a good reference for improving x3f_extract
- Per-scene optimizations don't generalize
- Channel mixer needs per-camera/per-ISO matrices
- Code saved in disabled block for future use

---

## Current Metrics (As of 2026-04-03)

### Best Performing Files (DeltaE < 25)
| File | RMSE | DeltaE | Notes |
|------|------|--------|-------|
| 0994 | 12.21 | 13.47 | Excellent match |
| 0990 | 12.39 | 22.43 | Good |
| 0992 | 11.89 | 22.34 | Good |
| 1000 | 12.37 | 23.32 | Good |
| 1001 | 12.46 | 23.69 | Good |

### Files Needing Improvement (DeltaE > 50)
| File | RMSE | DeltaE | Issue |
|------|------|--------|-------|
| 0927 | 11.88 | 64.29 | High DeltaE despite good RMSE |
| 0929 | 13.92 | ~67 | Scene-dependent color |
| 0930 | 14.04 | ~60 | Clipped highlights |

### Summary Statistics
- **Overall Average RMSE:** 14.40 (down from initial 51.2)
- **Overall Average DeltaE:** ~35 (varies by file)
- **ISO 200 Average RMSE:** 13.80
- **ISO 400 Average RMSE:** 17.57

---

### 8. Naive Pipeline - Spatial Color Correction (2026-05-29)
**CSF Variants 1-5 implemented:**
- Cameras store CAMF `ColorShadingFactor`: 2x2 matrix [R_col, R_row; B_col, B_row]
- Tested 5 application strategies via `#define COLOR_SHADING_VARIANT`:
  - 1-2: Applied in raw sensor space (before CCM) → CCM off-diagonals cause artifacts
  - 3: Divide in output RGB space → reduced RMSE but wrong direction
  - 4: Multiply in output space, full column+row gradient → U-shaped artifacts
  - 5: Multiply in output space, row-only gradient → **BEST performer**

**Variant 5 results (row-only output multiply):**
- Bottom green cast: reduced 64% (G-R from +7.5 to +2.7)
- Middle region: color-neutral (G-R from +1.0 to -0.1)
- RMSE: 75.15 → 74.26 (full-pipeline RMSE comparison)
- Residual: bottom-right corner G-R=+4.1 (likely vignetting, needs non-linear correction)

**Key finding:** CSF must be applied AFTER CCM in clean RGB space. Applying before CCM causes off-diagonal terms (-1.68 for G_out/R_in) to invert & amplify small corrections, creating spatial color artifacts.

**Remaining naive pipeline issues:**
- Global ~70-point brightness offset (all channels ~27% darker than reference)
- Residual bottom-right green cast (+4.1 G-R)

---

## Remaining Work

### 1. Color Matrix Correction (Priority: High)
- Research proper Merrill raw→XYZ conversion matrix
- Options: Published spectral data, per-scene calibration, scene-adaptive corrections
- Fent & Meldrum data provides foundation but needs full matrix derivation

### 2. Spatial Gain Optimization (Priority: Medium)
- Issue #114: Over-correction in some cases
- Paper emphasizes Merrill sensitivity to spectral balance
- May help with remaining color inconsistencies

### 3. White Balance Analysis (Priority: Medium)
- Test if 4100K Fluorescent provides better match than Auto
- Verify white balance implementation matches paper's optimization

### 4. ISO 400 Specific Improvements (Priority: Medium)
- ISO 400 files still underperform (RMSE 17.57 vs 13.80)
- B channel non-linear response (R² = 0.75)
- May need additional color matrix adjustment

### 5. Highlight Recovery Phase 3 (Priority: Low)
- Poisson gradient domain smoothing if needed
- Texture Transfer + Soft-Knee may reduce necessity

---

## Project Files

### Source Code
- `src/x3f_extract.c` - Main CLI tool
- `src/x3f_process.c` - Core processing pipeline
- `src/x3f_output_tiff.c` - TIFF writer with ICC embedding
- `src/x3f_matrix.c` - Color matrices, sigmoid LUT
- `src/x3f_spatial_gain.c` - Spatial gain compensation
- `src/x3f_highlight_recovery.c` - Multi-channel highlight reconstruction
- `src/x3f_sharpen.cpp` - RL deconvolution sharpening

### Tools
- `tools/compare_output.py` - Comparison with SPP references (RMSE/MAE/DeltaE/IQ metrics)

### Documentation
- `notes/highlight-recovery-plan.md` - Comprehensive highlight recovery plan
- `doc/PHASE_2B_PLAN.md` - Phase 2b implementation plan
- Daily journals: `notes/DD-MM-YYYY.md`

---

## Quick Reference: CLI Usage

```bash
# Build
make -C src

# Basic conversion
./bin/linux-x86_64/x3f_extract -color AdobeRGB input.x3f

# With sharpening control
./bin/linux-x86_64/x3f_extract -color AdobeRGB -sharpen-psf 0.7 -sharpen-iter 20 input.x3f

# Comparison
python3 tools/compare_output.py input.x3f reference.tiff --iq-metrics --delta-e
```
