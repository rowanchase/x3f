# Foveon X3F Highlight Recovery Implementation Plan

## Document Information
- **Status**: Phase 1 Complete, Phases 2+ Planned
- **Last Updated**: 27-02-2026
- **Target**: Sigma Foveon Merrill Cameras (DP1m, DP2m, DP3m)
- **Priority**: Quality over Speed

---

## Executive Summary

This document outlines the complete implementation plan for Foveon-specific highlight recovery in x3f_extract. Unlike traditional Bayer sensors, Foveon's 3-layer architecture provides unique opportunities for highlight reconstruction - when upper layers clip, lower layers may still contain valid data that can be used to estimate the true color.

### Current Status: Phase 1 Complete
✅ Clipping detection system implemented
✅ Boundary analysis with 32-pixel search radius
✅ Quality-prioritized Gaussian weighting
✅ Integration into processing pipeline

### Next: Phase 2 - Multi-Channel Reconstruction

---

## Phase 2: Multi-Channel Reconstruction

### 2.1 Overview
Implement the actual reconstruction algorithms for clipped highlight regions using the boundary data and clipping maps from Phase 1. This phase handles three cases:
- **Case 1**: Single channel clipped (most common)
- **Case 2**: Two channels clipped (challenging)
- **Case 3**: All channels clipped (graceful degradation)

### 2.2 Case 1: Single Channel Clipped (Blue, Green, or Red)

#### Algorithm Strategy
Use the two unclipped channels to estimate the clipped channel via color ratios learned from boundary pixels.

#### Implementation Details
```c
static void reconstruct_single_channel(
    x3f_pixel_clip_info_t *clip_info,
    x3f_boundary_data_t *boundary,
    int pixel_idx,
    double *output)
{
    x3f_clip_state_t state = clip_info->state;
    float *ratios;
    
    switch(state) {
        case CLIP_STATE_BLUE:
            // Blue clipped, use Green and Red
            // Estimate Blue = Green * (B/G ratio from boundary)
            // Cross-validate with Red * (B/R ratio)
            ratios = boundary->boundary_ratios_bg;
            output[0] = clip_info->raw_values[1] * ratios[pixel_idx];
            
            // Secondary estimate from B/R ratio
            float ratio_br = boundary->boundary_ratios_br[pixel_idx];
            float estimate2 = clip_info->raw_values[2] * ratio_br;
            
            // Weighted average (prefer B/G as it's more stable)
            output[0] = 0.6 * output[0] + 0.4 * estimate2;
            output[1] = clip_info->raw_values[1];  // Green unclipped
            output[2] = clip_info->raw_values[2];  // Red unclipped
            break;
            
        case CLIP_STATE_GREEN:
            // Green clipped, use Blue and Red
            // Estimate Green = Blue / (B/G ratio)
            // Cross-validate with Red * (G/R ratio)
            float ratio_bg = boundary->boundary_ratios_bg[pixel_idx];
            float estimate1 = clip_info->raw_values[0] / ratio_bg;
            
            float ratio_gr = boundary->boundary_ratios_gr[pixel_idx];
            float estimate2 = clip_info->raw_values[2] * ratio_gr;
            
            // Average the two estimates
            output[1] = (estimate1 + estimate2) / 2.0;
            output[0] = clip_info->raw_values[0];  // Blue unclipped
            output[2] = clip_info->raw_values[2];  // Red unclipped
            break;
            
        case CLIP_STATE_RED:
            // Red clipped, use Blue and Green
            // Estimate Red = Blue / (B/R ratio)
            // Cross-validate with Green / (G/R ratio)
            float ratio_br = boundary->boundary_ratios_br[pixel_idx];
            float estimate1 = clip_info->raw_values[0] / ratio_br;
            
            float ratio_gr = boundary->boundary_ratios_gr[pixel_idx];
            float estimate2 = clip_info->raw_values[1] / ratio_gr;
            
            output[2] = (estimate1 + estimate2) / 2.0;
            output[0] = clip_info->raw_values[0];  // Blue unclipped
            output[1] = clip_info->raw_values[1];  // Green unclipped
            break;
    }
    
    // Apply blending based on distance to boundary
    float blend = smoothstep(0.0, 0.3, clip_info->distance_to_boundary);
    for (int c = 0; c < 3; c++) {
        output[c] = lerp(clip_info->raw_values[c], output[c], blend);
    }
}
```

#### Quality Considerations
- **Spectral Consistency**: Use Fent & Meldrum QE data to validate ratios
- **Blending Zones**: Smooth transition at clipping boundaries (0-30% of search radius)
- **Validation**: Cross-check estimates from multiple unclipped channels

### 2.3 Case 2: Two Channels Clipped

#### Algorithm Strategy: Hierarchical Processing
For large clipped regions (>1000 pixels), use a hierarchical approach:

1. **Level 1**: Process boundary pixels (1 layer away from unclipped)
2. **Level 2**: Process pixels 2-5 layers deep using Level 1 results
3. **Level 3**: Process interior pixels using propagated estimates

#### Implementation
```c
static void reconstruct_two_channels_hierarchical(
    x3f_clip_map_t *clip_map,
    x3f_boundary_data_t *boundary,
    double *output_image,  // Flat array [row][col][3]
    int width, int height)
{
    // Identify large clipped regions
    int *region_ids = calloc(width * height, sizeof(int));
    int num_regions = identify_clipped_regions(clip_map, region_ids);
    
    for (int r = 0; r < num_regions; r++) {
        region_t region = get_region_bounds(region_ids, r, width, height);
        
        if (region.pixel_count > 1000) {
            // Hierarchical processing for large regions
            process_region_hierarchical(clip_map, boundary, &region, 
                                       output_image, width, height);
        } else {
            // Standard processing for small regions
            process_region_standard(clip_map, boundary, &region,
                                   output_image, width, height);
        }
    }
    
    free(region_ids);
}

static void process_region_hierarchical(
    x3f_clip_map_t *clip_map,
    x3f_boundary_data_t *boundary,
    region_t *region,
    double *output_image,
    int width, int height)
{
    int levels = 4;  // Number of processing levels
    
    for (int level = 0; level < levels; level++) {
        float max_distance = (float)(level + 1) * region->max_distance / levels;
        float min_distance = (float)level * region->max_distance / levels;
        
        // Process pixels at this distance level
        for (int y = region->y_min; y < region->y_max; y++) {
            for (int x = region->x_min; x < region->x_max; x++) {
                int idx = y * width + x;
                x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
                
                // Check if pixel is at this distance level
                if (info->distance_to_boundary >= min_distance &&
                    info->distance_to_boundary < max_distance &&
                    info->state == CLIP_STATE_BG || info->state == CLIP_STATE_BR ||
                    info->state == CLIP_STATE_GR) {
                    
                    reconstruct_at_level(info, boundary, level, output_image, idx);
                }
            }
        }
    }
}

static void reconstruct_at_level(
    x3f_pixel_clip_info_t *info,
    x3f_boundary_data_t *boundary,
    int level,
    double *output,
    int idx)
{
    // For level 0: use boundary ratios directly
    // For higher levels: use interpolated ratios from previous level
    
    float *unclipped_channel = NULL;
    int unclipped_idx = -1;
    
    // Find the unclipped channel
    for (int c = 0; c < 3; c++) {
        if (!(info->state & (1 << c))) {
            unclipped_channel = &info->raw_values[c];
            unclipped_idx = c;
            break;
        }
    }
    
    if (unclipped_idx == -1) return;  // All clipped, handled elsewhere
    
    // Spectral estimation using Foveon response curves
    // The F20 sensor has known spectral response characteristics
    // Blue layer: peaks at ~450nm
    // Green layer: peaks at ~550nm  
    // Red layer: peaks at ~650nm with NIR response
    
    switch(info->state) {
        case CLIP_STATE_BG:
            // Blue+Green clipped, Red valid
            // Estimate Blue from Red using spectral model
            // B/R ratio ~ 0.8-1.2 depending on color temperature
            output[2] = *unclipped_channel;  // Red is valid
            output[0] = estimate_from_red(*unclipped_channel, CHANNEL_BLUE);
            output[1] = estimate_from_red(*unclipped_channel, CHANNEL_GREEN);
            break;
            
        case CLIP_STATE_BR:
            // Blue+Red clipped, Green valid
            output[1] = *unclipped_channel;  // Green is valid
            output[0] = estimate_from_green(*unclipped_channel, CHANNEL_BLUE);
            output[2] = estimate_from_green(*unclipped_channel, CHANNEL_RED);
            break;
            
        case CLIP_STATE_GR:
            // Green+Red clipped, Blue valid
            output[0] = *unclipped_channel;  // Blue is valid
            output[1] = estimate_from_blue(*unclipped_channel, CHANNEL_GREEN);
            output[2] = estimate_from_blue(*unclipped_channel, CHANNEL_RED);
            break;
    }
}
```

#### Spectral Estimation Functions
Based on Fent & Meldrum (2016) paper data and Foveon F20 sensor characteristics:

```c
// Spectral response coefficients from Fent & Meldrum
static const float f20_qe_blue = 10.6;   // At 500-575nm
static const float f20_qe_green = 13.2;  // At 500-575nm
static const float f20_qe_red = 9.0;     // At 500-575nm (NIR layer)

static float estimate_from_green(float green_val, int target_channel)
{
    switch(target_channel) {
        case CHANNEL_BLUE:
            // Blue estimated from Green
            // B/G ratio typically 0.65-0.85 for skin tones
            // B/G ratio ~0.4-0.6 for foliage
            // Use conservative 0.75 to avoid over-saturation
            return green_val * (f20_qe_blue / f20_qe_green) * 0.95;
            
        case CHANNEL_RED:
            // Red estimated from Green
            // R/G ratio typically 0.8-1.2 for most colors
            return green_val * (f20_qe_red / f20_qe_green) * 1.05;
    }
    return green_val;
}

static float estimate_from_blue(float blue_val, int target_channel)
{
    switch(target_channel) {
        case CHANNEL_GREEN:
            return blue_val * (f20_qe_green / f20_qe_blue) * 1.05;
            
        case CHANNEL_RED:
            // Blue to Red has larger uncertainty due to spectral distance
            // Be conservative to avoid color casts
            return blue_val * (f20_qe_red / f20_qe_blue) * 0.85;
    }
    return blue_val;
}

static float estimate_from_red(float red_val, int target_channel)
{
    switch(target_channel) {
        case CHANNEL_BLUE:
            // Large uncertainty, conservative estimate
            return red_val * (f20_qe_blue / f20_qe_red) * 0.75;
            
        case CHANNEL_GREEN:
            return red_val * (f20_qe_green / f20_qe_red) * 0.95;
    }
    return red_val;
}
```

### 2.4 Case 3: All Channels Clipped

#### Strategy: Graceful Desaturation
When all three layers are clipped, we cannot recover the original color. Instead, we:
1. Map to maximum valid luminance
2. Desaturate towards white based on HighlightSatFactor
3. Preserve local luminance variations if possible

```c
static void reconstruct_all_channels_clipped(
    x3f_pixel_clip_info_t *info,
    double hl_sat_factor,
    double *output)
{
    // All channels are at or near clipping threshold
    // We cannot determine true color, so desaturate gracefully
    
    // Estimate luminance from the "least clipped" channel
    float max_luminance = 0.0;
    for (int c = 0; c < 3; c++) {
        if (info->raw_values[c] > max_luminance) {
            max_luminance = info->raw_values[c];
        }
    }
    
    // Cap at white point
    if (max_luminance > 1.0) max_luminance = 1.0;
    
    // Apply desaturation factor from metadata
    // hl_sat_factor = 1.0 means no desaturation
    // hl_sat_factor < 1.0 means desaturate towards white
    float desat = hl_sat_factor;
    
    // For fully clipped, desaturate more aggressively
    if (desat > 0.8) desat = 0.8;
    
    // Generate desaturated color (towards white)
    for (int c = 0; c < 3; c++) {
        output[c] = max_luminance * (0.5 + 0.5 * desat);
    }
    
    // Add slight variation if we have any gradient info
    if (info->has_unclipped_neighbor) {
        // Subtle variation to avoid flat white patches
        float variation = (max_luminance - 0.98) * 10.0;  // 0-0.2 range
        for (int c = 0; c < 3; c++) {
            output[c] -= variation * 0.05;
        }
    }
}
```

### 2.5 Reconstruction Pipeline

```c
int x3f_reconstruct_highlights(
    x3f_area16_t *image,
    x3f_clip_map_t *clip_map,
    x3f_boundary_data_t *boundary,
    double hl_blending_low,
    double hl_blending_high,
    double hl_sat_factor,
    x3f_area16_t *output)
{
    int width = image->columns;
    int height = image->rows;
    
    // Allocate output buffer
    output->data = malloc(width * height * 3 * sizeof(uint16_t));
    output->rows = height;
    output->columns = width;
    output->channels = 3;
    output->row_stride = width * 3;
    
    // Copy unclipped pixels directly
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int idx = y * width + x;
            x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
            
            if (info->state == CLIP_STATE_NONE) {
                // Unclipped - copy directly
                for (int c = 0; c < 3; c++) {
                    output->data[idx * 3 + c] = 
                        image->data[y * image->row_stride + x * 3 + c];
                }
            }
        }
    }
    
    // Process by severity
    // 1. Single channel clipped (most reliable)
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int idx = y * width + x;
            x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
            
            if (x3f_count_clipped_channels(info->state) == 1) {
                double reconstructed[3];
                reconstruct_single_channel(info, boundary, idx, reconstructed);
                
                // Convert back to 16-bit
                for (int c = 0; c < 3; c++) {
                    output->data[idx * 3 + c] = 
                        (uint16_t)(reconstructed[c] * 65535.0);
                }
            }
        }
    }
    
    // 2. Two channels clipped (hierarchical processing)
    reconstruct_two_channels_hierarchical(clip_map, boundary, 
                                          (double*)output->data, width, height);
    
    // 3. All channels clipped (desaturate)
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int idx = y * width + x;
            x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
            
            if (info->state == CLIP_STATE_ALL) {
                double reconstructed[3];
                reconstruct_all_channels_clipped(info, hl_sat_factor, reconstructed);
                
                for (int c = 0; c < 3; c++) {
                    output->data[idx * 3 + c] = 
                        (uint16_t)(reconstructed[c] * 65535.0);
                }
            }
        }
    }
    
    return 1;
}
```

### 2.6 Integration Timeline

**Week 1**: Case 1 (Single Channel) Implementation
- Day 1-2: Implement reconstruct_single_channel()
- Day 3-4: Test on reference images with single-channel clipping
- Day 5: Refine blending and validation

**Week 2**: Case 2 (Two Channels) with Hierarchical Processing
- Day 1-2: Implement region identification and hierarchical framework
- Day 3-4: Implement spectral estimation functions
- Day 5: Test on large clipped regions (>1000 pixels)

**Week 3**: Case 3 (All Channels) and Pipeline Integration
- Day 1-2: Implement graceful desaturation
- Day 3-4: Integrate full pipeline into x3f_process.c
- Day 5: Initial testing and debugging

---

## Phase 3: Poisson Gradient Domain Smoothing

### 3.1 Overview
After reconstruction, apply Poisson smoothing to eliminate artifacts at clipping boundaries. This ensures smooth transitions between reconstructed and original pixels.

### 3.2 Algorithm: Gradient Domain Reconstruction

Based on Rouf et al. (2012) "Gradient Domain Color Restoration of Clipped Highlights":

1. Compute gradient field of reconstructed region
2. Replace gradients in clipped areas with boundary gradients
3. Solve Poisson equation to reconstruct smooth image

### 3.3 Implementation

```c
// Poisson solver using Successive Over-Relaxation (SOR)
// Faster than direct solvers for this application

static void poisson_smooth_reconstructed(
    x3f_area16_t *image,
    x3f_clip_map_t *clip_map,
    x3f_boundary_data_t *boundary,
    int iterations,
    float omega)  // SOR relaxation factor (1.5-1.9)
{
    int width = image->columns;
    int height = image->rows;
    
    // Temporary buffers for each channel
    float *temp[3];
    for (int c = 0; c < 3; c++) {
        temp[c] = calloc(width * height, sizeof(float));
    }
    
    // Initialize with current values
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int idx = y * width + x;
            for (int c = 0; c < 3; c++) {
                temp[c][idx] = image->data[y * image->row_stride + x * 3 + c] / 65535.0f;
            }
        }
    }
    
    // SOR iterations
    for (int iter = 0; iter < iterations; iter++) {
        for (int y = 1; y < height - 1; y++) {
            for (int x = 1; x < width - 1; x++) {
                int idx = y * width + x;
                x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
                
                // Only smooth pixels that were clipped
                if (info->state == CLIP_STATE_NONE) continue;
                
                for (int c = 0; c < 3; c++) {
                    // Laplacian operator (4-connected)
                    float laplacian = 
                        temp[c][(y-1) * width + x] +
                        temp[c][(y+1) * width + x] +
                        temp[c][y * width + (x-1)] +
                        temp[c][y * width + (x+1)] -
                        4.0f * temp[c][idx];
                    
                    // Gradient guidance from boundary
                    float gradient_bias = 0.0f;
                    if (info->has_unclipped_neighbor) {
                        // Use boundary gradient magnitude to weight update
                        float grad_weight = boundary->gradient_magnitude[idx];
                        gradient_bias = grad_weight * 0.01f;  // Small influence
                    }
                    
                    // SOR update
                    float update = (laplacian + gradient_bias) / 4.0f;
                    temp[c][idx] += omega * update;
                    
                    // Clamp to valid range
                    if (temp[c][idx] < 0.0f) temp[c][idx] = 0.0f;
                    if (temp[c][idx] > 1.0f) temp[c][idx] = 1.0f;
                }
            }
        }
    }
    
    // Copy back to image
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int idx = y * width + x;
            x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
            
            if (info->state != CLIP_STATE_NONE) {
                for (int c = 0; c < 3; c++) {
                    image->data[y * image->row_stride + x * 3 + c] = 
                        (uint16_t)(temp[c][idx] * 65535.0f);
                }
            }
        }
    }
    
    for (int c = 0; c < 3; c++) {
        free(temp[c]);
    }
}
```

### 3.4 Integration Point

Called after reconstruction, before color conversion:

```c
// In x3f_process.c convert_data()

// 1. Detect clipping (Phase 1 - done)
// 2. Analyze boundaries (Phase 1 - done)
// 3. Reconstruct highlights (Phase 2)
if (clip_map->total_clipped_pixels > 0 && boundary_data) {
    x3f_area16_t reconstructed;
    x3f_reconstruct_highlights(image, clip_map, boundary_data,
                               hl_blending_low, hl_blending_high,
                               hl_sat_factor, &reconstructed);
    
    // 4. Poisson smoothing (Phase 3)
    poisson_smooth_reconstructed(&reconstructed, clip_map, boundary_data,
                                  100, 1.7);  // 100 iterations, omega=1.7
    
    // Use reconstructed image for further processing
    *image = reconstructed;
}

// 5. Color conversion (existing)
```

### 3.5 Timeline

**Week 4**: Poisson Smoothing
- Day 1-2: Implement SOR-based Poisson solver
- Day 3-4: Tune parameters (iterations, omega) on test images
- Day 5: Validate smoothness metrics

---

## Phase 4: Testing and Validation

### 4.1 Test Cases

#### Test 1: Single Channel Clipping (Reference: _P2M0927.X3F)
- **Scenario**: Mild overexposure, mostly blue channel clipping
- **Metric**: RMSE in highlight regions < 5.0
- **Visual**: No color shifts in reconstructed highlights
- **Method**: Compare against SPP output

#### Test 2: Two Channel Clipping (Reference: _P2M0936.X3F - worst case)
- **Scenario**: Severe clipping in 2 channels
- **Metric**: DeltaE in clipped regions < 15
- **Visual**: Smooth transitions, no banding
- **Method**: L*a*b* comparison in overexposed regions

#### Test 3: Large Clipped Regions
- **Scenario**: Large sky area or bright surface
- **Metric**: No visible artifacts at 100% zoom
- **Visual**: Consistent texture in reconstructed areas
- **Method**: Hierarchical processing validation

#### Test 4: Specular Highlights
- **Scenario**: Small bright specular reflections
- **Metric**: Natural roll-off, not flat white
- **Visual**: Preserved detail in reflections
- **Method**: Edge profile analysis

#### Test 5: Colored Light Sources
- **Scenario**: Bright colored lights (neon, LED)
- **Metric**: Hue accuracy in reconstructed regions
- **Visual**: Correct color, not washed out
- **Method**: Spectral accuracy comparison

### 4.2 Validation Metrics

```python
# Python comparison script (tools/compare_highlights.py)

def analyze_highlight_recovery(x3f_output, spp_reference, clipping_mask):
    """
    Analyze highlight recovery quality
    """
    # 1. RMSE in clipped regions only
    clipped_rmse = compute_rmse_masked(x3f_output, spp_reference, clipping_mask)
    
    # 2. Color accuracy (DeltaE)
    delta_e = compute_deltaE_masked(x3f_output, spp_reference, clipping_mask)
    
    # 3. Gradient consistency at boundaries
    boundary_mask = dilate(clipping_mask) - clipping_mask
    boundary_gradient_error = compute_gradient_error(
        x3f_output, spp_reference, boundary_mask)
    
    # 4. Smoothness metric (Laplacian variance)
    smoothness = compute_laplacian_variance(x3f_output, clipping_mask)
    
    return {
        'clipped_rmse': clipped_rmse,
        'delta_e_mean': np.mean(delta_e),
        'delta_e_max': np.max(delta_e),
        'boundary_gradient_error': boundary_gradient_error,
        'smoothness_score': smoothness
    }
```

### 4.3 Success Criteria

| Metric | Target | Acceptable | Measurement |
|--------|--------|------------|-------------|
| RMSE (clipped regions) | < 5.0 | < 8.0 | Per-file comparison |
| DeltaE mean | < 8.0 | < 12.0 | CIEDE2000 in clipped areas |
| DeltaE max | < 20.0 | < 30.0 | Worst-case pixel |
| Boundary artifacts | 0 | < 5% | Visual inspection |
| Smoothness | > 0.9 | > 0.7 | Laplacian variance ratio |
| Performance | < 2x | < 3x | Time vs baseline |

### 4.4 Regression Testing

Ensure highlight recovery doesn't damage non-clipped images:
- Run all 25 reference files through pipeline
- Verify RMSE doesn't increase for files without clipping
- Check that processing time remains reasonable

### 4.5 Timeline

**Week 5**: Comprehensive Testing
- Day 1-2: Test Case 1 & 2 (single/two channel)
- Day 3: Test Case 3 (large regions)
- Day 4: Test Case 4 & 5 (specular/colored lights)
- Day 5: Regression testing and optimization

---

## Performance Considerations

### Memory Usage
- Clip map: ~50MB for 15MP image
- Boundary data: ~100MB for 15MP image
- Poisson solver: ~60MB temporary buffers
- **Total overhead: ~210MB** (acceptable)

### Processing Time Estimates
- Phase 1 (Clipping detection): ~200ms
- Phase 1 (Boundary analysis): ~500ms (32-pixel radius)
- Phase 2 (Reconstruction): ~300ms
- Phase 3 (Poisson smoothing): ~800ms (100 iterations)
- **Total: ~1.8 seconds** for 15MP image

### Optimization Opportunities (Post-Quality Validation)
1. SIMD vectorization for Poisson solver
2. Tiled processing for cache efficiency
3. Multi-threading (already available via OpenMP)
4. Adaptive iteration count for Poisson (convergence detection)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Color accuracy loss in 2-channel | Conservative spectral estimates, heavy blending |
| Performance degradation | Profile-guided optimization after quality validation |
| Memory pressure | Stream processing for very large images (future) |
| Artifacts in complex scenes | Extensive test suite with challenging cases |
| Integration complexity | Modular design, clear separation of concerns |

---

## Dependencies and Prerequisites

### Completed (Phase 1)
- ✅ Clipping detection infrastructure
- ✅ Boundary analysis with color ratios
- ✅ Integration into processing pipeline
- ✅ Metadata parameter reading (HighlightBlendingLow/High, etc.)

### Required for Phase 2
- Spectral response data (Fent & Meldrum QE values - available)
- Region identification algorithm (new implementation)
- Hierarchical processing framework (new implementation)

### Required for Phase 3
- Poisson solver implementation (SOR-based)
- Parameter tuning framework
- Smoothness metrics

---

## Documentation and Deliverables

### Code Documentation
- Doxygen comments for all public functions
- Inline comments for complex algorithms
- Algorithm references (papers, spectral data sources)

### Testing Documentation
- Test case descriptions with expected outcomes
- Performance benchmark results
- Visual comparison galleries

### User Documentation
- No user-facing changes (always enabled)
- Technical blog post about Foveon highlight recovery (optional)

---

## Summary Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 2** | Weeks 1-3 | Multi-channel reconstruction with hierarchical processing |
| **Phase 3** | Week 4 | Poisson gradient domain smoothing |
| **Phase 4** | Week 5 | Comprehensive testing and validation |
| **Integration** | Week 6 | Final integration, optimization, documentation |

**Total Estimated Duration: 6 weeks**

---

## References

1. Rouf, M., Lau, C., & Heidrich, W. (2012). "Gradient Domain Color Restoration of Clipped Highlights" 
   - EPFL Technical Report

2. Fent, I., & Meldrum, T. (2016). "Color Science and the Foveon Sensor" 
   - Journal of Imaging, 2(1), 14

3. Elboher, E., & Werman, M. (2010). "Recovering Color and Details of Clipped Image Regions"
   - Color Lines model for RGB reconstruction

4. Foveon X3 Sensor Technical Documentation
   - Spectral response curves for F20 sensor

5. Boris van Schooten Analysis
   - "Why do Foveon highlights look better?" - 13thmonkey.org

---

## Notes

- **Quality Priority**: All decisions favor quality over speed
- **Always Enabled**: No user parameter for highlight recovery
- **Aggressive Reconstruction**: Maximize detail recovery within quality constraints
- **Hierarchical Processing**: Essential for large clipped regions (>1000 pixels)
- **Poisson Smoothing**: Required for artifact-free boundaries

**Document Status**: Phase 1 Complete, Phase 2 Ready to Begin
