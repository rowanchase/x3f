# Test: Disabling 2.5x Boost and LUT Stage

**Date:** 2026-02-27
**Goal:** Test what Phase 2b output looks like without the 2.5x exposure boost and without the LUT gamma compression

## Changes Made

Modified `src/x3f_process.c`:
1. Commented out the 2.5x exposure compensation block (lines 960-970)
2. Replaced LUT lookup with direct linear conversion:
   - Before: `*valp[color] = x3f_LUT_lookup(lut, LUTSIZE, output[color]);`
   - After: Direct clamped 16-bit conversion

## Results

### Without 2.5x boost, without LUT:
- **Float mean:** 0.0846
- **Shadows (0-49):** 92-96%
- **Midtones (50-199):** 3.6-7.6%
- **Soft highlights (200-229):** 0.0-0.1%
- **Hard highlights (230-255):** 0.2%

The output is extremely dark - most values concentrated in shadows with histogram peak around 11-15 (8-bit equivalent).

### With 2.5x boost, without LUT:
- **Float mean:** 0.2118
- **Ratio to SPP:** 2.20x (SPP is still 2.2x brighter)
- **Shadows (0-49):** 63.8%
- **Midtones (50-199):** 33.6%
- **Soft highlights (200-229):** 0.6%
- **Hard highlights (230-255):** 1.9%

With the 2.5x boost, values are ~2.5x higher as expected, but SPP is still significantly brighter.

### Reference SPP:
- **Float mean:** 0.4656
- **Shadows (0-49):** 3.2%
- **Midtones (50-199):** 91.0%
- **Soft highlights (200-229):** 3.5%
- **Hard highlights (230-255):** 2.4%
- **Histogram peak:** Around 104-114 (8-bit)

## Key Findings

1. **Without processing pipeline:** The raw Phase 2b output is ~5.5x darker than SPP
2. **With 2.5x boost only:** Still ~2.2x darker than SPP
3. **Missing brightness:** SPP applies additional brightness beyond the 2.5x boost we identified
4. **16-bit values confirmed:** The output is properly writing 16-bit values (max 65535) with linear mapping

## Implications

The triple-compression issue (Phase 2b tanh + 2.5x boost + LUT rolloff) is real, but simply disabling these stages creates an unusably dark image. SPP must be applying:
- Different/more aggressive exposure compensation
- A different tone curve that lifts shadows/midtones more
- Possibly different ISO or base exposure scaling

## Next Steps

We need to understand what SPP is doing differently. The 2.5x boost helps but is insufficient. The LUT's gamma curve (when enabled) would compress values further, not expand them. SPP appears to have additional brightness amplification that we haven't identified yet.

## Files Modified

- `src/x3f_process.c`: Lines 960-970 (2.5x boost commented out), lines 1059-1069 (LUT disabled)

## Test Command Used

```bash
./bin/linux-x86_64/x3f_extract -tiff -o /tmp/test reference_files/X3Fs/_P2M0927.X3F
```
