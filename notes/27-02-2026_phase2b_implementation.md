# Phase 2b Implementation - Soft-Knee Compression & Texture Transfer

**Date:** 2026-02-27  
**File:** `doc/PHASE_2B_PLAN.md`  
**Status:** COMPLETE

## Overview

Implemented Phase 2b of the Foveon X3F highlight recovery according to the detailed plan. This phase bridges the gap between "hard value recovery" (Phase 2) and "natural texture recovery" (SPP Match).

## Problem Being Solved

The current Phase 2 implementation produces accurate flat colors but lacks texture and has a harsh clipping transition, resulting in a histogram pile-up at 255 (fully clipped). The goal is to:
1. Populate the 200-250 histogram range (soft highlights)
2. Restore texture and detail in reconstructed highlights using unclipped layers

## Implementation Details

### 1. Configuration Parameters (lines 19-22)

Added three key parameters at the top of `x3f_highlight_recovery.c`:
```c
#define SOFT_KNEE_THRESHOLD 0.80f  /* Start compression at ~204/255 */
#define TEXTURE_STRENGTH 1.0f       /* Full texture transfer */
#define NEAR_CLIP_THRESHOLD 0.80f   /* Process near-clipped pixels for smooth transition */
```

### 2. New Helper Functions (lines 327-394)

#### `compress_highlight()` - Soft-Knee Compression

Uses a tanh-like function to compress highlight values smoothly into a shoulder region instead of hard clipping:

```c
static float compress_highlight(float value, float threshold)
{
  if (value <= threshold) {
    return value;
  }
  
  float spread = 1.0f - threshold;
  float excess = (value - threshold) / spread;
  return threshold + spread * tanhf(excess);
}
```

**Effect**: Maps values > 0.8 into a compressed shoulder [0.8, 1.0] using hyperbolic tangent, creating smooth rolloff instead of harsh clipping.

#### `get_local_average()` - 3x3 Neighborhood Average

Computes local average of a channel in a 3x3 window for texture ratio calculation:
```c
static float get_local_average(x3f_clip_map_t *map, int x, int y, int channel)
```

#### `get_texture_ratio()` - Detail Extraction

Calculates the ratio between a pixel's value and its local average, representing local detail (texture):
```c
static float get_texture_ratio(x3f_clip_map_t *map, int x, int y, int channel)
{
  float local_avg = get_local_average(map, x, y, channel);
  int idx = y * map->width + x;
  float pixel_val = map->pixels[idx].raw_values[channel];
  
  if (local_avg < 0.001f) {
    return 1.0f;
  }
  
  return pixel_val / local_avg;
}
```

**Purpose**: Captures high-frequency detail from unclipped channels to transfer to clipped channels.

#### `find_texture_source()` - Channel Selection

Finds the best unclipped channel for texture transfer:
```c
static int find_texture_source(x3f_pixel_clip_info_t *info)
{
  /* Prefer Red (2), then Green (1), then Blue (0) for texture source
   * Red typically has best signal in highlights
   */
  if (!(info->state & CLIP_STATE_RED)) return 2;
  if (!(info->state & CLIP_STATE_GREEN)) return 1;
  if (!(info->state & CLIP_STATE_BLUE)) return 0;
  
  return -1; /* All channels clipped */
}
```

**Priority**: Red > Green > Blue (Red has best signal-to-noise in highlights)

### 3. Updated `reconstruct_single_channel()` (lines 425-508)

**Changes**:
1. Added `clip_map`, `x`, `y` parameters to access neighboring pixels
2. Finds texture source channel (unclipped neighbor)
3. Calculates texture ratio with clamping [0.5, 1.5] to prevent extremes
4. Multiplies reconstructed estimate by texture ratio
5. Applies `compress_highlight()` to result
6. Clamps reconstructed values to prevent runaway amplification

**Example for Blue clipped**:
```c
/* Weighted average with texture transfer */
reconstructed[0] = (0.6f * estimate_bg + 0.4f * estimate_br) * texture_ratio;
/* Clamp to prevent extreme values from texture amplification */
if (reconstructed[0] > 2.0f) reconstructed[0] = 2.0f;
```

### 4. Updated `reconstruct_two_channels()` (lines 615-664)

**Changes**:
1. Added `clip_map`, `x`, `y` parameters
2. Uses single valid channel as texture source
3. Applies texture ratio to both reconstructed channels
4. Applies soft-knee compression to outputs

### 5. Updated `reconstruct_all_channels()` (lines 667-711)

**Changes**:
1. Applies soft-knee compression to all reconstructed values
2. Maintains desaturation logic but compresses final output

### 6. Updated Main Loop `x3f_reconstruct_highlights()` (lines 720-780)

**Critical Change**: Now processes **near-clipped pixels** (values > 0.8 but not yet clipped) to create smooth transition:

```c
if (info->state == CLIP_STATE_NONE) {
  /* Phase 2b: Check for near-clipped pixels (smooth transition zone) */
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
  } else {
    /* Unclipped pixel - copy directly */
    for (c = 0; c < 3; c++) {
      reconstructed[c] = info->raw_values[c];
    }
  }
}
```

**Effect**: Pixels approaching clipping now get smoothly compressed into the shoulder region, preventing the histogram from piling up at 255.

## Technical Theory

### Soft-Knee Compression
The hyperbolic tangent compression creates a smooth "S-curve" shoulder:
- Linear region: 0.0 → 0.8 (unchanged)
- Compression region: 0.8 → infinity maps to 0.8 → 1.0
- Formula: `f(x) = T + (1-T) * tanh((x-T)/(1-T))`

This is similar to how film and professional digital cameras handle highlights.

### Texture Transfer (Foveon Advantage)
Foveon sensors capture RGB at the same spatial location. When Blue is clipped but Red is valid:
- Red's texture (high-frequency detail) is a perfect predictor for Blue's missing texture
- Reconstruct Blue as: `B_rec = B_flat_estimate * (R_pixel / R_local_avg)`
- The ratio `(R_pixel / R_local_avg)` captures local detail independent of overall intensity

## Build Verification

**Command**:
```bash
make clean && make
```

**Result**: Clean build with no errors (only unrelated OpenCV warnings)

## Test Results

**Command**:
```bash
./bin/linux-x86_64/x3f_extract -tiff -o /tmp/test_output reference_files/X3Fs/_P2M0927.X3F
```

**Result**: Successfully processes image with highlight recovery enabled.

**Comparison**:
```bash
python3 tools/compare_output.py reference_files/X3Fs/_P2M0927.X3F reference_files/TIFFs/_P2M0927.tif --x3f-extract ./bin/linux-x86_64/x3f_extract
```

**Metrics for _P2M0927.X3F**:
- RMSE: 11.49 (baseline for Phase 2b)
- MAE: 8.71
- Per-channel MAE: R=7.43, G=7.20, B=11.50

Note: The RMSE remains similar to Phase 2 because this is still just one piece of the puzzle. Phase 2b specifically targets highlight quality and histogram distribution, not overall accuracy.

## Expected Improvements

With Phase 2b implementation:
1. **Histogram**: Values should now populate the 200-250 range instead of piling at 255
2. **Texture**: Clipped regions should show detail from unclipped channels
3. **Visual**: Highlights should look textured and natural, not flat white patches
4. **Transition**: Smooth gradation from near-clipped to fully clipped areas

## Files Modified

- `src/x3f_highlight_recovery.c` - Complete Phase 2b implementation
  - Added configuration parameters
  - Added 4 helper functions
  - Modified 3 reconstruction functions
  - Updated main reconstruction loop

## Future Work (Phase 3)

Poisson smoothing is still planned for final polish, but Texture Transfer + Soft-Knee may reduce its necessity if boundaries blend well.

## Commit Ready

The implementation is complete and ready to commit.
