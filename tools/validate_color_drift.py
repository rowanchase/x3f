#!/usr/bin/env python3
"""
Validate color drift correction on white paper images.

This script analyzes the uniformity of a white paper photograph to detect
color drift across the sensor. After correction, the output should be
uniform gray/white without colored gradients.

Usage:
    python validate_color_drift.py <x3f_file> [--spp-reference <tiff>] [--output-tiff]

Example:
    python validate_color_drift.py reference_files/X3Fs/_P2M1182.X3F --spp-reference reference_files/TIFFs/_P2M1182.tif
"""

import argparse
import subprocess
import sys
import os
import tempfile
import numpy as np
from PIL import Image


def analyze_uniformity(img_array, name="Image"):
    """Analyze color uniformity of an image.
    
    Returns dict with:
    - std_dev per channel
    - mean per channel
    - max_deviation from center
    - regional means (3x3 grid)
    """
    h, w = img_array.shape[:2]
    
    results = {}
    
    results['std_dev'] = {
        'R': float(np.std(img_array[:,:,0])),
        'G': float(np.std(img_array[:,:,1])),
        'B': float(np.std(img_array[:,:,2]))
    }
    
    results['mean'] = {
        'R': float(np.mean(img_array[:,:,0])),
        'G': float(np.mean(img_array[:,:,1])),
        'B': float(np.mean(img_array[:,:,2]))
    }
    
    region_h = h // 3
    region_w = w // 3
    
    regional_means = np.zeros((3, 3, 3))
    for ri in range(3):
        for ci in range(3):
            rh = ri * region_h
            rw = ci * region_w
            region = img_array[rh:rh+region_h, rw:rw+region_w]
            regional_means[ri, ci] = np.mean(region, axis=(0,1))
    
    results['regional_means'] = regional_means
    
    center_region = img_array[h//4:3*h//4, w//4:3*w//4]
    center_mean = np.mean(center_region, axis=(0,1))
    
    corner_deltas = []
    corners = [
        (0, 0),
        (0, w-region_w),
        (h-region_h, 0),
        (h-region_h, w-region_w)
    ]
    
    for cr, cc in corners:
        corner_region = img_array[cr:cr+region_h, cc:cc+region_w]
        corner_mean = np.mean(corner_region, axis=(0,1))
        delta = np.sqrt(np.sum((corner_mean - center_mean)**2))
        corner_deltas.append(delta)
    
    results['max_corner_delta'] = max(corner_deltas)
    results['center_mean'] = center_mean
    
    overall_mean = np.mean(img_array, axis=(0,1))
    results['overall_mean'] = overall_mean
    
    return results


def print_uniformity_report(our_results, ref_results=None, title="Color Drift Validation"):
    """Print a formatted uniformity report."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    
    print(f"\n--- Per-Channel Statistics ---")
    print(f"{'Channel':<10} {'Mean':>10} {'Std Dev':>12}")
    print(f"{'-'*32}")
    for ch in ['R', 'G', 'B']:
        mean_val = our_results['mean'][ch]
        std_val = our_results['std_dev'][ch]
        print(f"{ch:<10} {mean_val:>10.2f} {std_val:>12.2f}")
    
    print(f"\n--- Regional Analysis (3x3 Grid) ---")
    print("Region means (RGB):")
    for ri in range(3):
        row_str = f"  Row {ri}: "
        for ci in range(3):
            r, g, b = our_results['regional_means'][ri, ci]
            row_str += f"[{r:6.1f} {g:6.1f} {b:6.1f}]  "
        print(row_str)
    
    print(f"\n--- Corner vs Center Analysis ---")
    print(f"Center RGB: {our_results['center_mean'][0]:.1f}, {our_results['center_mean'][1]:.1f}, {our_results['center_mean'][2]:.1f}")
    print(f"Max corner delta from center: {our_results['max_corner_delta']:.2f}")
    
    if ref_results:
        print(f"\n--- Comparison with SPP Reference ---")
        print(f"{'Metric':<30} {'Ours':>12} {'SPP Ref':>12} {'Diff':>12}")
        print(f"{'-'*66}")
        
        for ch in ['R', 'G', 'B']:
            our_mean = our_results['mean'][ch]
            ref_mean = ref_results['mean'][ch]
            diff = our_mean - ref_mean
            print(f"{ch} Mean{'':<24} {our_mean:>12.2f} {ref_mean:>12.2f} {diff:>+12.2f}")
        
        our_std_r = our_results['std_dev']['R']
        ref_std_r = ref_results['std_dev']['R']
        print(f"\n{'Std Dev (R)':<30} {our_std_r:>12.2f} {ref_std_r:>12.2f} {our_std_r-ref_std_r:>+12.2f}")
        
        our_max_delta = our_results['max_corner_delta']
        ref_max_delta = ref_results['max_corner_delta']
        print(f"{'Max Corner Delta':<30} {our_max_delta:>12.2f} {ref_max_delta:>12.2f} {our_max_delta-ref_max_delta:>+12.2f}")
        
        diff = our_results['overall_mean'] - ref_results['overall_mean']
        print(f"\n{'Overall Mean RGB Diff':<30} R:{diff[0]:+.2f} G:{diff[1]:+.2f} B:{diff[2]:+.2f}")
    
    print(f"\n{'='*60}")


def compute_rmse(img1, img2):
    """Compute RMSE between two images."""
    return np.sqrt(np.mean((img1.astype(float) - img2.astype(float))**2))


def compute_mae(img1, img2):
    """Compute MAE between two images."""
    return np.mean(np.abs(img1.astype(float) - img2.astype(float)))


def main():
    parser = argparse.ArgumentParser(
        description='Validate color drift correction on white paper images'
    )
    parser.add_argument('x3f_file', help='Input X3F file')
    parser.add_argument('--spp-reference', '-r', 
                       help='SPP reference TIFF file for comparison')
    parser.add_argument('--output-tiff', '-o', 
                       help='Output TIFF file path')
    parser.add_argument('--x3f-extract', default='./bin/linux-x86_64/x3f_extract',
                       help='Path to x3f_extract binary')
    
    args = parser.parse_args()
    
    x3f_file = args.x3f_file
    
    if not os.path.exists(x3f_file):
        print(f"Error: X3F file not found: {x3f_file}", file=sys.stderr)
        sys.exit(1)
    
    if args.output_tiff:
        output_tiff = args.output_tiff
    else:
        fd, output_tiff = tempfile.mkstemp(suffix='.tiff')
        os.close(fd)
    
    print(f"Processing {x3f_file}...")
    
    x3f_dir = os.path.dirname(os.path.abspath(x3f_file))
    x3f_basename = os.path.basename(x3f_file)
    generated_tiff = os.path.join(x3f_dir, x3f_basename + '.tif')
    
    cmd = [args.x3f_extract, '-tiff', '-color', 'AdobeRGB', x3f_file]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error running x3f_extract:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    
    actual_output = generated_tiff
    print(f"Output: {actual_output}")
    
    our_img = Image.open(actual_output)
    our_array = np.array(our_img)
    
    our_results = analyze_uniformity(our_array, "Our Output")
    
    if args.spp_reference:
        if not os.path.exists(args.spp_reference):
            print(f"Error: Reference TIFF not found: {args.spp_reference}", file=sys.stderr)
            sys.exit(1)
        
        ref_img = Image.open(args.spp_reference)
        ref_array = np.array(ref_img)
        
        if ref_array.shape != our_array.shape:
            print(f"Warning: Image sizes differ - ours: {our_array.shape}, ref: {ref_array.shape}")
            min_h = min(our_array.shape[0], ref_array.shape[0])
            min_w = min(our_array.shape[1], ref_array.shape[1])
            our_array = our_array[:min_h, :min_w]
            ref_array = ref_array[:min_h, :min_w]
            print(f"Using intersection: {our_array.shape}")
        
        ref_results = analyze_uniformity(ref_array, "SPP Reference")
        
        rmse = compute_rmse(our_array, ref_array)
        mae = compute_mae(our_array, ref_array)
        
        print_uniformity_report(our_results, ref_results)
        
        print(f"\n--- RMSE/MAE vs SPP Reference ---")
        print(f"RMSE: {rmse:.2f}")
        print(f"MAE:  {mae:.2f}")
        
        if rmse < 5.0:
            print(f"\n✓ PASS: RMSE < 5.0")
            exit_code = 0
        else:
            print(f"\n✗ RMSE target not met (target: < 5.0)")
            exit_code = 1
    else:
        print_uniformity_report(our_results, title="Color Drift Analysis")
        exit_code = 0
    
    pass
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
