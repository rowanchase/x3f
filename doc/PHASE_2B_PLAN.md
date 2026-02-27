# Foveon X3F Highlight Recovery - Phase 2b Detailed Implementation Plan

## Overview

**Goal:** Bridge the gap between "hard value recovery" (Phase 2) and "natural texture recovery" (SPP Match). 
**Problem:** Current implementation produces accurate *flat* colors but lacks texture and has a harsh clipping transition, resulting in a histogram pile-up at 255.
**Solution:** Implement **Soft-Knee Blending** to populate the 200-250 histogram range and **Texture Transfer** to restore detail using unclipped layers.

---

## 1. Core Concepts

### 1.1 Soft-Knee Compression
Instead of clamping values $> 1.0$ to $1.0$, we compress them into a high-dynamic-range shoulder.
*   **Linear Region**: $0.0 \to T$ (Threshold, e.g., 0.8)
*   **Compression Region**: $T \to \infty$ maps to $T \to 1.0$ using a hyperbolic tangent or similar function.

**Formula:**
$$ f(x) = T + (1-T) \cdot \tanh\left(\frac{x - T}{1 - T}\right) \quad \text{for } x > T $$

### 1.2 Texture Transfer (Foveon Advantage)
Foveon sensors capture Red, Green, and Blue at the *same spatial location*.
*   If **Blue is Clipped** but **Red is Valid**, the *texture* (high-frequency detail) of Red is a perfect predictor for Blue's missing texture.
*   We can reconstruct Blue as:
    $$ B_{rec} = B_{flat\_estimate} \times \frac{R_{pixel}}{R_{local\_avg}} $$

---

## 2. Implementation Details

### 2.1 New Helper Functions (`src/x3f_highlight_recovery.c`)

#### `float compress_highlight(float value, float threshold)`
*   **Input**: Linear float value (can be $> 1.0$), threshold (e.g., 0.8).
*   **Output**: Compressed float value in $[0.0, 1.0]$.
*   **Logic**:
    ```c
    if (value <= threshold) return value;
    float spread = 1.0f - threshold;
    // Tanh-like compression mapping [threshold, infinity] -> [threshold, 1.0]
    return threshold + spread * tanh((value - threshold) / spread);
    ```

#### `float get_texture_ratio(x3f_clip_map_t *map, int x, int y, int channel)`
*   **Input**: Coordinates, channel index of the *unclipped* source (Red or Green).
*   **Output**: Ratio representing local detail (e.g., 0.9 to 1.1).
*   **Logic**:
    1.  Compute local 3x3 average of `channel` centered at `(x,y)`.
    2.  Avoid division by zero (epsilon check).
    3.  Return `pixel_value / local_average`.

### 2.2 Modified Reconstruction Logic

#### Update `reconstruct_single_channel`
*   **Current**: Calculates flat spectral estimate.
*   **New**:
    1.  Identify best unclipped source channel (e.g., Red if Blue is clipped).
    2.  Calculate `ratio = get_texture_ratio(..., source_channel)`.
    3.  Multiply flat estimate by `ratio`.
    4.  Apply `compress_highlight` to the result.

#### Update `reconstruct_two_channels`
*   **Current**: Calculates flat spectral estimate.
*   **New**:
    1.  Use the *single* valid channel as the texture source.
    2.  Apply texture ratio to both reconstructed channels.
    3.  Apply `compress_highlight` to the results.

### 2.3 Main Loop Updates (`x3f_reconstruct_highlights`)

The critical change to fix the histogram is processing **Near-Clipped Pixels**.

*   **Current Loop**: Only processes pixels with `state != CLIP_STATE_NONE`.
*   **New Loop**:
    1.  Check `state`.
    2.  **If Clipped**: Perform reconstruction (with texture & compression).
    3.  **If NOT Clipped**: Check if any channel value $> 0.8$ (Soft Threshold).
        *   If yes, apply `compress_highlight` to that channel.
        *   This ensures smooth transition into the reconstructed area and populates the 200-230 histogram buckets.

---

## 3. Configuration Parameters

*   **`SOFT_KNEE_THRESHOLD`**: `0.80` (Starts compressing at ~204/255)
*   **`TEXTURE_STRENGTH`**: `1.0` (Full texture transfer)

---

## 4. Verification Steps

1.  **Rebuild**: `make clean && make`
2.  **Run Histogram Analysis**:
    ```bash
    python3 tools/compare_output.py ref/_P2M0927.X3F ref/_P2M0927.tif --iq-metrics
    ```
3.  **Check Metrics**:
    *   **Soft Highlights (200-230)**: Count should increase significantly (closer to SPP).
    *   **Fully Clipped (254-256)**: Count should decrease.
    *   **Visual**: Highlights should look textured, not flat white/grey patches.

---

## 5. Future Optimization (Phase 3)
*   **Poisson Smoothing**: Still planned for final polish, but Texture Transfer might make it less critical if boundaries blend well via Soft-Knee.
