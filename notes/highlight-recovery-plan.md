# Highlight Recovery Improvement Plan

## Executive Summary

This document outlines a comprehensive plan to improve the highlight recovery capabilities of the x3f_extract tool for Sigma Foveon X3 Merrill cameras. The goal is not merely to match Sigma Photo Pro (SPP) output, but to exceed it by leveraging the unique advantages of the Foveon sensor architecture.

---

## 1. Background and Context

### 1.1 The Foveon X3 Advantage for Highlight Recovery

Unlike conventional Bayer sensors that capture only one color per pixel and require demosaicing, the Foveon X3 sensor captures all three colors (R, G, B) at every pixel location through stacked photodiodes:

- **Blue layer**: ~0.2μm depth (short wavelength absorption)
- **Green layer**: ~0.6μm depth (medium wavelength absorption)  
- **Red layer**: ~2.0μm depth (long wavelength absorption)

This architecture provides a **fundamental advantage for highlight recovery**: when one channel clips, the other two channels at the same pixel location retain valid data. With Bayer sensors, a clipped pixel loses 2/3 of its color information; with Foveon, only the clipped channel(s) are lost.

### 1.2 Current State of x3f_extract

The current implementation in x3f_extract:

1. **Basic highlight handling**: Exists in `src/x3f_process.c` (lines 893-911) - simple desaturation towards white for pixels where max_channel > 0.6

2. **Soft clipping**: `highlight_rolloff()` in `src/x3f_matrix.c` (lines 284-291) provides soft knee compression at threshold 0.95, but this is not tunable

3. **HighlightPixelsInfo**: Used only for marking bad pixels, not for reconstruction (`src/x3f_process.c` lines 437-442)

4. **Intermediate bit depth**: Merrill cameras store 14-bit data internally (`LinLUTBitDepth=14`), but this headroom is not fully utilized

### 1.3 Sigma Photo Pro's Approach

SPP applies its own highlight processing, but the exact algorithms are proprietary. From analysis:

- Uses highlight blend zones (0.75-1.5 range in normalized values)
- Applies threshold-based restoration
- Desaturates towards white in highlights
- Cannot be fully disabled

### 1.4 Reference Files Analysis

The Merrill X3F files contain rich metadata including:

| Parameter | Location | Typical Value |
|-----------|----------|---------------|
| ImageDepth | CAMF | 12 (bits) |
| LinLUTBitDepth | CAMF | 14 (bits) |
| HighlightBlendingLow | CAMF | 0.75 |
| HighlightBlendingHigh | CAMF | 1.5 |
| HighlightRestoreThresh | CAMF | 1.75 |
| HighlightChanThresh1 | CAMF | 0.5 |
| HighlightChanThresh2 | CAMF | 0.5 |
| HighlightSatFactor | CAMF | 1.0 |

These parameters are currently **completely unused** by x3f_extract.

---

## 2. Key Findings

### Finding 1: Unused CAMF Metadata
The X3F files contain detailed highlight processing parameters that SPP uses internally. x3f_extract does not read or utilize any of these values.

### Finding 2: 14-bit Headroom Not Exploited
Merrill cameras capture at 14-bit precision internally, but output is 12-bit. This 2-stop headroom could be used for better highlight handling before tone mapping.

### Finding 3: Foveon's Native Advantage
Every Foveon pixel has complete RGB data. Channel-based reconstruction algorithms can directly use the unclipped channels at each pixel location, rather than requiring spatial interpolation from neighboring pixels (as with Bayer).

### Finding 4: Current Implementation is Too Simple
The existing highlight desaturation (lines 893-911 in x3f_process.c) applies a single formula globally:
- Threshold: 0.6 (fixed)
- Desaturation: quadratic falloff
- No channel-specific handling
- No use of intermediate data

### Finding 5: Darktable/RawTherapee Algorithms are Documented
Other raw processors have well-documented highlight reconstruction algorithms:
- Luminance recovery
- Color propagation  
- Inpaint opposed
- CIELab reconstruction
- Guided Laplacians

---

## 3. Detailed Implementation Plan

### Phase 1: Foundation - Read and Utilize CAMF Metadata

**Objective**: Begin using the existing highlight parameters stored in X3F files

**Tasks**:
1.1 Add functions to read highlight parameters from CAMF:
    - `HighlightBlendingLow`
    - `HighlightBlendingHigh`  
    - `HighlightRestoreThresh`
    - `HighlightChanThresh1`
    - `HighlightChanThresh2`
    - `HighlightSatFactor`

1.2 Store parameters in processing context structure

1.3 Log parameter values when verbose mode enabled

1.4 Add CLI flags to override CAMF values (for experimentation)

**Expected Outcome**: Tool reads and acknowledges the highlight metadata, establishing foundation for future phases

**Difficulty**: Easy (primarily metadata reading)

**Files Modified**: 
- `src/x3f_meta.c` / `src/x3f_meta.h` - add getter functions
- `src/x3f_process.c` - integrate parameters
- `src/x3f_extract.c` - add CLI overrides

---

### Phase 2: Implement Channel-Based Reconstruction

**Objective**: Leverage Foveon's per-pixel RGB to reconstruct clipped channels

**Theory**:
For a pixel where channel C is clipped (value = max), but channels A and B are valid:
1. Calculate the ratio A/B from the valid channels
2. Estimate what C should be based on typical scene chromaticity
3. Or: use luminance preservation to estimate C

**Tasks**:
2.1 Add clipping detection at the intermediate (14-bit) level:
    - Identify pixels where any channel approaches saturation
    - Use the CAMF threshold parameters

2.2 Implement per-pixel channel reconstruction:
    - When R clips but G,B valid: estimate R from G,B ratio
    - When G clips but R,B valid: estimate G from R,B ratio
    - When B clips but R,G valid: estimate B from R,G ratio

2.3 Implement blend between reconstructed and original:
    - Use HighlightBlendingLow/High parameters
    - Smooth transition in the 0.75-1.5 range

2.4 Handle fully-clipped pixels (all channels saturated):
    - Fall back to spatial interpolation from neighbors
    - Or use luminance-only reconstruction

**Expected Outcome**: Significantly better color preservation in highlights compared to simple desaturation

**Difficulty**: Medium (requires understanding of intermediate data flow)

**Files Modified**:
- `src/x3f_process.c` - core reconstruction logic
- New file: `src/x3f_highlight.c` (or integrate into x3f_process.c)

---

### Phase 3: Advanced Soft Knee Compression

**Objective**: Replace current highlight_rolloff with tunable soft knee

**Theory**:
Soft knee tone mapping smoothly transitions from linear to compressed response:
```
if (x < threshold):
    output = x
else:
    output = threshold + (x - threshold) * compression_factor
```

This preserves highlight rolloff while maintaining better local contrast than hard clipping.

**Tasks**:
3.1 Replace static `highlight_rolloff()` with configurable soft knee:
    - Make threshold tunable (default from CAMF or 0.95)
    - Make compression ratio tunable
    - Support different knee shapes (linear, exponential, logarithmic)

3.2 Implement multi-zone highlight processing:
    - Zone 1 (0.0 - BlendingLow): Linear processing
    - Zone 2 (BlendingLow - BlendingHigh): Smooth blend to reconstruction
    - Zone 3 (BlendingHigh - RestoreThresh): Aggressive reconstruction
    - Zone 4 (> RestoreThresh): Maximum compression

3.3 Add highlight recovery controls to CLI:
    - `--highlight-method`: off, desat, reconstruct, blend
    - `--highlight-threshold`: 0.0-1.0
    - `--highlight-strength`: 0.0-1.0

**Expected Outcome**: Highlights roll off smoothly without harsh clipping artifacts

**Difficulty**: Medium

**Files Modified**:
- `src/x3f_matrix.c` - enhanced LUT generation
- `src/x3f_process.c` - integrate soft knee
- `src/x3f_extract.c` - CLI controls

---

### Phase 4: Advanced Reconstruction Methods

**Objective**: Implement multiple reconstruction algorithms for different scenarios

**Methods to Implement**:

4.1 **Luminance Recovery**:
   - Preserve overall brightness
   - Rebuild color channels from chromaticity
   - Good for neutral/high-key highlights

4.2 **Color Propagation**:
   - Bleed color from adjacent unclipped regions
   - Good for structured highlights (e.g., specular on edges)

4.3 **CIELAB Reconstruction**:
   - Work in perceptual color space
   - Preserve hue better than RGB methods

4.4 **Edge-Aware Reconstruction**:
   - Use gradient information to guide reconstruction
   - Preserve highlight shapes and transitions

**Tasks**:
4.1 Add method selection to processing pipeline
4.2 Implement each algorithm
4.3 Add automatic method selection based on image analysis
4.4 Document tradeoffs and add CLI controls

**Expected Outcome**: Best-in-class highlight handling across diverse shooting scenarios

**Difficulty**: Hard (requires careful implementation and testing)

**Files Modified**:
- `src/x3f_highlight.c` - new file with multiple methods
- `src/x3f_process.c` - integrate selection logic
- `src/x3f_extract.c` - CLI method selection

---

### Phase 5: Extended Dynamic Range Processing

**Objective**: Leverage 14-bit internal data for better highlight handling

**Theory**:
Merrill cameras capture 14-bit internal data but output 12-bit. By processing in the full 14-bit space before final tone mapping, we preserve more highlight headroom.

**Tasks**5.1:
- Maintain 14-bit precision through processing pipeline
- Add extended range mode that outputs >8-bit TIFF
- Implement exposure-to-16-bit conversion option

5.2 Explore HDR output formats:
- OpenEXR support for highlights
- 16-bit TIFF with extended range
- Float TIFF

**Expected Outcome**: Maximum highlight preservation for post-processing flexibility

**Difficulty**: Medium-Hard

---

## 4. Implementation Order

```
Phase 1: Foundation (Week 1)
├── 1.1 Read CAMF parameters
├── 1.2 Add to processing context
└── 1.3 CLI overrides

Phase 2: Channel Reconstruction (Week 2)
├── 2.1 Clipping detection
├── 2.2 Per-pixel reconstruction
└── 2.3 Blend zones

Phase 3: Soft Knee Compression (Week 3)
├── 3.1 Configurable soft knee
├── 3.2 Multi-zone processing
└── 3.3 CLI controls

Phase 4: Advanced Methods (Week 4-5)
├── 4.1 Luminance recovery
├── 4.2 Color propagation
└── 4.3 Edge-aware methods

Phase 5: Extended Range (Week 6)
├── 5.1 14-bit pipeline
└── 5.2 HDR formats
```

---

## 5. Testing Strategy

### 5.1 Reference Files
Use existing test images with known highlights:
- Files with clipped highlights: 0936, 1003, 1004, 1008, 1009
- Compare before/after each phase

### 5.2 Metrics
- RMSE vs reference TIFFs (existing framework)
- Highlight-specific metrics:
  - Color error in highlight regions
  - Luminance preservation
  - Subjective quality assessment

### 5.3 Test Cases
1. Single-channel clipped (R only, G only, B only)
2. Two-channel clipped (RG, GB, RB)
3. All-channel clipped (white/sky highlights)
4. Gradient transitions (specular highlights)
5. Complex scenes (mixed highlight types)

---

## 6. Technical Considerations

### 6.1 Performance
- Channel reconstruction is per-pixel (fast)
- Edge-aware methods require spatial access (slower)
- Implement optimization flags

### 6.2 Memory
- Current pipeline uses intermediate buffers
- Add in-place processing where possible
- Consider streaming for large images

### 6.3 Compatibility
- Maintain backward compatibility
- Default to existing behavior
- New features opt-in via CLI

---

## 7. Success Criteria

### Minimum Success (Phase 1-2):
- [ ] Read CAMF highlight parameters
- [ ] Implement channel-based reconstruction
- [ ] Measurable improvement in highlight RMSE

### Target Success (Phase 3-4):
- [ ] Multiple reconstruction methods available
- [ ] Soft knee compression working
- [ ] CLI controls for user preference

### Stretch Goal (Phase 5):
- [ ] 14-bit processing pipeline
- [ ] HDR output formats
- [ ] Highlight recovery exceeds SPP quality

---

## 8. References

- Darktable highlight reconstruction: https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/highlight-reconstruction/
- RawTherapee highlight methods: https://rawpedia.rawtherapee.com/Highlight_Reconstruction
- Photo Ninja color recovery: https://picturecode.com/tutorials/hr.php
- Jim Kasson Foveon analysis: https://blog.kasson.com/the-last-word/more-on-foveon-image-processing/
- X3F Format: libopenraw.freedesktop.org/formats/x3f/x3f-raw-format.pdf

---

## 9. Appendix: Key Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Highlight desaturation | x3f_process.c | 893-911 |
| Highlight rolloff | x3f_matrix.c | 284-291 |
| LUT lookup | x3f_matrix.c | 325-343 |
| Sigmoid LUT | x3f_matrix.c | 293-323 |
| Max raw levels | x3f_meta.c | 397-417 |
| Black level | x3f_process.c | 604-621 |
| Intermediate bias | x3f_process.c | 315-333 |

---

*Document Version: 1.0*  
*Created: 2026-02-24*  
*Author: opencode agent*
