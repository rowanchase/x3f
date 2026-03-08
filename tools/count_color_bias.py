#!/usr/bin/env python3
"""
Analyze TIFF images to count pixels with color bias vs. neutral pixels.
A pixel has color bias when one channel significantly exceeds the average,
indicating it is R, G, or B dominant rather than white, grey, or black.
"""

import argparse
import sys
import os
import numpy as np
from PIL import Image


DEFAULT_THRESHOLD_16BIT = 512
DEFAULT_THRESHOLD_8BIT = 2

CATEGORY_NEUTRAL = 0
CATEGORY_R_BIASED = 1
CATEGORY_G_BIASED = 2
CATEGORY_B_BIASED = 3


def load_tiff(filepath):
    """Load TIFF and return numpy array with bit depth info."""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    
    img = Image.open(filepath)
    
    width, height = img.size
    bands = len(img.getbands())
    
    if img.mode == 'I;16' or img.mode == 'I;16L' or img.mode == 'I;16B':
        raw_bytes = img.tobytes()
        data_uint16 = np.frombuffer(raw_bytes, dtype=np.uint16)
        if len(data_uint16) != height * width * bands:
            print(f"Warning: Size mismatch in 16-bit image", file=sys.stderr)
        data = data_uint16.reshape((height, width, bands))
        bit_depth = 16
    else:
        data = np.array(img)
        bit_depth = 8 if data.dtype == np.uint8 else 16
    
    return data, bit_depth


def auto_detect_threshold(bit_depth):
    """Return appropriate threshold based on data dtype."""
    if bit_depth == 16:
        return DEFAULT_THRESHOLD_16BIT
    else:
        return DEFAULT_THRESHOLD_8BIT


def classify_pixels(data, threshold):
    """
    Classify each pixel as neutral, R-biased, G-biased, or B-biased.
    
    Returns 2D array with values:
    0 = neutral
    1 = R-biased
    2 = G-biased  
    3 = B-biased
    
    If multiple biases apply, the channel with maximum deviation wins.
    """
    h, w, c = data.shape
    assert c == 3, "Expected 3-channel image"
    
    r = data[:, :, 0].astype(np.float64)
    g = data[:, :, 1].astype(np.float64)
    b = data[:, :, 2].astype(np.float64)
    
    mean = (r + g + b) / 3.0
    
    r_delta = r - mean
    g_delta = g - mean
    b_delta = b - mean
    
    r_bias = (r_delta > threshold) & (g_delta < 0) & (b_delta < 0)
    g_bias = (g_delta > threshold) & (r_delta < 0) & (b_delta < 0)
    b_bias = (b_delta > threshold) & (r_delta < 0) & (g_delta < 0)
    
    neutral = ~(r_bias | g_bias | b_bias)
    
    abs_r = np.abs(r_delta)
    abs_g = np.abs(g_delta)
    abs_b = np.abs(b_delta)
    
    max_delta = np.maximum.reduce([abs_r, abs_g, abs_b])
    
    classification = np.zeros((h, w), dtype=np.uint8)
    classification[neutral] = CATEGORY_NEUTRAL
    
    biased_mask = ~neutral
    
    r_wins = biased_mask & (abs_r == max_delta) & r_bias
    g_wins = biased_mask & (abs_g == max_delta) & g_bias
    b_wins = biased_mask & (abs_b == max_delta) & b_bias
    
    classification[r_wins] = CATEGORY_R_BIASED
    classification[g_wins] = CATEGORY_G_BIASED
    classification[b_wins] = CATEGORY_B_BIASED
    
    neutral_fallback = biased_mask & ~r_wins & ~g_wins & ~b_wins
    classification[neutral_fallback] = CATEGORY_NEUTRAL
    
    return classification


def analyze_region(classification, row_start, row_end, col_start, col_end):
    """Analyze a specific region and return counts."""
    region = classification[row_start:row_end, col_start:col_end]
    
    total = region.size
    neutral = np.sum(region == CATEGORY_NEUTRAL)
    r_biased = np.sum(region == CATEGORY_R_BIASED)
    g_biased = np.sum(region == CATEGORY_G_BIASED)
    b_biased = np.sum(region == CATEGORY_B_BIASED)
    
    return {
        'total': total,
        'neutral': neutral,
        'r_biased': r_biased,
        'g_biased': g_biased,
        'b_biased': b_biased
    }


def analyze_regional_breakdown(data, classification):
    """Perform 3x3 regional analysis."""
    h, w = data.shape[:2]
    
    region_h = h // 3
    region_w = w // 3
    
    regions = []
    for ri in range(3):
        for ci in range(3):
            rs = ri * region_h
            re = (ri + 1) * region_h if ri < 2 else h
            cs = ci * region_w
            ce = (ci + 1) * region_w if ci < 2 else w
            
            stats = analyze_region(classification, rs, re, cs, ce)
            regions.append({
                'row': ri,
                'col': ci,
                'stats': stats
            })
    
    return regions


def print_report(data, classification, bit_depth, threshold, regions=None):
    """Format and print the analysis report."""
    h, w = data.shape[:2]
    total_pixels = h * w
    
    neutral = np.sum(classification == CATEGORY_NEUTRAL)
    r_biased = np.sum(classification == CATEGORY_R_BIASED)
    g_biased = np.sum(classification == CATEGORY_G_BIASED)
    b_biased = np.sum(classification == CATEGORY_B_BIASED)
    
    print("=" * 60)
    print("Color Bias Analysis")
    print("=" * 60)
    print(f"Image: {w}x{h}, {bit_depth}-bit")
    print(f"Threshold: {threshold}")
    print()
    print("--- Overall ---")
    print(f"Total pixels:  {total_pixels:,}")
    print(f"Neutral:      {neutral:>10,} ({100*neutral/total_pixels:>5.1f}%)")
    print(f"R-biased:     {r_biased:>10,} ({100*r_biased/total_pixels:>5.1f}%)")
    print(f"G-biased:     {g_biased:>10,} ({100*g_biased/total_pixels:>5.1f}%)")
    print(f"B-biased:     {b_biased:>10,} ({100*b_biased/total_pixels:>5.1f}%)")
    
    if regions:
        print()
        print("--- Regional Breakdown (3x3 grid) ---")
        print(f"{'':10} | {'Neutral':>10} | {'R-biased':>10} | {'G-biased':>10} | {'B-biased':>10}")
        print("-" * 60)
        
        row_names = ['Top', 'Middle', 'Bottom']
        col_names = ['Left', 'Center', 'Right']
        
        for ri in range(3):
            for ci in range(3):
                r_idx = ri * 3 + ci
                stats = regions[r_idx]['stats']
                
                total = stats['total']
                n_pct = 100 * stats['neutral'] / total
                r_pct = 100 * stats['r_biased'] / total
                g_pct = 100 * stats['g_biased'] / total
                b_pct = 100 * stats['b_biased'] / total
                
                region_name = f"{row_names[ri]} {col_names[ci]}"
                print(f"{region_name:10} | {n_pct:>9.1f}% | {r_pct:>9.1f}% | {g_pct:>9.1f}% | {b_pct:>9.1f}%")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze TIFF images to count pixels with color bias'
    )
    parser.add_argument('tiff_file', help='Input TIFF file')
    parser.add_argument('--threshold', '-t', type=int, default=None,
                       help=f'Absolute threshold for bias detection '
                            f'(default: {DEFAULT_THRESHOLD_16BIT} for 16-bit, '
                            f'{DEFAULT_THRESHOLD_8BIT} for 8-bit)')
    parser.add_argument('--no-regional', action='store_true',
                       help='Disable regional 3x3 breakdown')
    
    args = parser.parse_args()
    
    data, bit_depth = load_tiff(args.tiff_file)
    
    if args.threshold is not None:
        threshold = args.threshold
    else:
        threshold = auto_detect_threshold(bit_depth)
    
    print(f"Loading {args.tiff_file} ({bit_depth}-bit)...")
    print(f"Using threshold: {threshold}")
    
    classification = classify_pixels(data, threshold)
    
    regions = None
    if not args.no_regional:
        regions = analyze_regional_breakdown(data, classification)
    
    print()
    print_report(data, classification, bit_depth, threshold, regions)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
