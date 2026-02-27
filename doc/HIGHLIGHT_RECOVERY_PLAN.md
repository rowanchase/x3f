# Foveon X3F Highlight Recovery Implementation Plan

## Document Information
- **Status**: Phase 2 Core Implemented, Phase 2b (Optimization) In Progress
- **Last Updated**: 27-02-2026
- **Target**: Sigma Foveon Merrill Cameras (DP1m, DP2m, DP3m)
- **Goal**: Match Sigma Photo Pro (SPP) highlight recovery quality and histogram distribution

---

## Executive Summary

We are developing a specialized highlight recovery pipeline for Foveon sensors. Unlike Bayer sensors, Foveon's vertical 3-layer architecture (Blue-Green-Red) allows for unique recovery strategies: when the top (Blue) layer clips, the deeper (Green/Red) layers often retain valid data with perfect spatial alignment.

### Current Status
*   ✅ **Phase 1 (Complete):** Clipping detection, boundary analysis, metadata integration.
*   ✅ **Phase 2 (Core Implemented):** Multi-channel reconstruction using spectral ratios (Fent & Meldrum QE data) and smoothstep blending.
*   ⚠️ **Findings (27-02-2026):** Histogram analysis shows we are "hard clipping" (piling pixels at 255) while SPP exhibits "soft clipping" (smooth roll-off in 200-255 range). Our reconstruction is mathematically correct but aesthetically harsh.

### Immediate Focus: Phase 2b (Soft-Knee & Texture Transfer)
We must bridge the gap between "recovering value" and "recovering texture" to match SPP's natural look.

---

## Phase 2: Multi-Channel Reconstruction (Implemented)

### 2.1 Core Implementation (Completed)
We have implemented the three primary reconstruction cases in `src/x3f_highlight_recovery.c`:
- **Case 1 (Single Channel)**: Uses weighted ratios from unclipped neighbors (e.g., Blue reconstructed from Green/Red).
- **Case 2 (Two Channels)**: Uses spectral estimation based on Foveon F20 sensor Quantum Efficiency (QE) data (Blue=10.6, Green=13.2, Red=9.0).
- **Case 3 (All Channels)**: Graceful desaturation towards white.

### 2.2 Current Limitations
Histogram analysis of `_P2M0927` vs SPP reference:
- **SPP**: Large population of pixels in "Soft Highlight" range (200-230).
- **Us**: Lower population in Soft Highlights, higher population in Fully Clipped (254-256).
- **Conclusion**: Our transition to clipping is too abrupt. We are recovering *values* but clamping them hard, losing the natural roll-off.

---

## Phase 2b: Optimization - Histogram & Texture Matching (NEW)

**Objective**: Move from "Hard Reconstruction" to "Soft Reconstruction" to match SPP's histogram shape.

### 2.3 Soft-Knee Blending
Instead of a hard threshold where reconstruction kicks in, implement a "Confidence-Based Blending" model.

**Strategy:**
1.  Define a **Transition Zone** (e.g., raw value 0.7 to 1.0).
2.  Calculate a **Reconstruction Weight** $w$ that ramps from 0.0 to 1.0 in this zone.
3.  Final Value = $(1-w) \cdot Raw + w \cdot Reconstructed$.
4.  **Crucial Step**: Apply a **Compression Curve** to the result. If the reconstructed value > 1.0 (which is physically possible), map it smoothly into the 0.95-1.0 range instead of hard clamping.

### 2.4 Texture Transfer (The Foveon Advantage)
Since Foveon layers are vertically aligned, the *gradient* (texture) of the unclipped deep layer is a perfect predictor for the clipped top layer's texture.

**Algorithm:**
1.  Identify the most reliable unclipped channel (e.g., Red).
2.  Compute the local gradient/texture of Red.
3.  Impose this texture onto the reconstructed Blue channel.
    *   $Blue_{rec} = Blue_{flat\_est} \times \frac{Red_{local}}{Red_{lowfreq}}$
4.  This ensures that even if the *color* is estimated, the *detail* matches the unclipped layers, preventing the "flat highlight" look.

---

## Phase 3: Poisson Gradient Domain Smoothing (Planned)

**Objective**: Eliminate artifacts at reconstruction boundaries.

### 3.1 Algorithm
Based on Rouf et al. (2012). We will solve the Poisson equation to reconstruct the image guided by:
1.  **Boundary Conditions**: Pixels just outside the clipped region.
2.  **Guidance Field**: The gradients of the reconstructed/unclipped channels.

### 3.2 Refinement for Phase 2b Results
If Phase 2b successfully transfers texture, the Poisson step becomes less about *generating* detail and more about *seamless integration* of the reconstructed patches.

---

## Phase 4: Validation & Tuning

### 4.1 Metrics
We will use the newly developed `tools/compare_output.py` with histogram analysis:
- **Target**: Match SPP's "Soft Highlight" (200-230) pixel count within 10%.
- **Target**: Reduce "Fully Clipped" count to match SPP.
- **Metric**: RMSE < 5.0 in clipped regions.

### 4.2 Test Suite
- **_P2M0927**: Standard single-channel clipping (Blue sky).
- **_P2M0936**: Severe multi-channel clipping (Sun/Clouds).
- **_P2M0930**: Mixed clipping scenarios.

---

## Technical Appendix: Foveon Spectral Data

Used for Case 2 reconstruction (Source: Fent & Meldrum, 2016):
- **Blue QE**: ~10.6 (Peak ~450nm)
- **Green QE**: ~13.2 (Peak ~540nm)
- **Red QE**: ~9.0 (Peak ~620nm + NIR)

**Reconstruction Logic (Simplified):**
- $B_{est} \approx G \times (10.6/13.2) \times 0.95$
- $G_{est} \approx R \times (13.2/9.0) \times 1.05$
- *Note: Red -> Blue estimation is least reliable due to spectral distance.*

---

## Timeline Updates

1.  **Phase 2b (Immediate)**: Implement Soft-Knee Blending and Texture Transfer logic. Adjust thresholds to populate 200-230 histogram range.
2.  **Phase 3**: Implement Poisson solver (SOR method) for final polish.
3.  **Phase 4**: Full regression testing against all 25 reference files.
