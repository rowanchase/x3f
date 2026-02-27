# 27 Feb 2026 - Histogram Comparison Tool Enhancement

## Task
Added comprehensive highlight histogram comparison to `tools/compare_output.py` to help diagnose clipping detection issues.

## Problem
User reported that x3f_extract only detects 45 clipped pixels in a file with large sky region that should have extensive clipping. The clipping threshold was reduced from 0.75 to 0.50 but didn't significantly increase detection.

## Solution
Added detailed histogram analysis focused on the highlight region (200-255):

### New Functions Added
1. `compute_highlight_histogram_metrics()` - Per-channel histogram statistics with focus on highlights
   - Highlight region breakdown: soft_highlights (200-230), hard_highlights (230-254), fully_clipped (254-256)
   - Percentile analysis (p90, p95, p99, p99.9)
   - Suspicious pattern detection:
     - Large spike at max value
     - Compression detection (ratio of 220-240 density vs 200-220)
     - Gradual vs sharp cutoff analysis

2. `compare_histograms()` - Compare output vs reference histograms
   - Per-region pixel count comparison
   - Percentile value comparison
   - Detection of suspicious differences:
     - Large p99 difference (>5)
     - Max value clipping differences (>0.5%)
     - Soft highlight region differences (>1%)
     - Compression pattern mismatches

3. Integration into `--iq-metrics` output:
   - Per-channel histogram summary (R, G, B)
   - Percentile comparison table
   - Highlight region distribution breakdown
   - Suspicious pattern detection with recommendations
   - Overall summary with actionable insights

### Command Line Options
- `--iq-metrics`: Enable histogram analysis (existing)
- `--histogram-json <file>`: Save histogram comparison to JSON

## Technical Details

### Highlight Regions
- **Soft highlights (200-230)**: Starting to clip, recoverable
- **Hard highlights (230-254)**: Nearly clipped, critical region
- **Fully clipped (254-256)**: At max value, definitely clipped

### Suspicious Pattern Detection
1. Large p99 difference (>5): Indicates different highlight handling
2. Max value clipping difference (>0.5%): Different clipping behavior
3. Soft highlight region difference (>1%): Significant population difference in 200-230 range
4. Compression mismatch: One has gradual falloff, other has sharp cutoff

## Files Modified
- `tools/compare_output.py`: Added histogram comparison functions and integration

## Next Steps
1. Run the enhanced comparison tool on the problematic file (_P2M1109.X3F)
2. Analyze histogram differences to understand why clipping isn't being detected
3. Compare our output histogram vs SPP reference in the 200-255 range
4. Use insights to adjust clipping detection algorithm
