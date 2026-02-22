#!/usr/bin/env python3
"""
Compare x3f_extract output against Sigma Photo Pro reference TIFFs.

Usage:
    python compare_output.py <x3f_file> <reference_tiff> [--x3f-extract <path>]
    
Example:
    python compare_output.py reference_files/X3Fs/_P2M0927.X3F reference_files/TIFFs/_P2M0927.tif
"""

import argparse
import subprocess
import sys
import os
import tempfile
import json
from PIL import Image
import numpy as np


def run_x3f_extract(x3f_path, output_path, x3f_extract_path='x3f_extract', 
                    color_space='sRGB', crop=True, denoise=False):
    """Run x3f_extract to convert X3F to TIFF.
    
    Returns the actual output file path (which may differ from output_path).
    """
    # x3f_extract -o expects a directory, not a file path
    output_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else '.'
    
    args = [x3f_extract_path, '-tiff', '-o', output_dir]
    
    if not denoise:
        args.append('-no-denoise')
    
    if color_space:
        args.extend(['-color', color_space])
    
    if not crop:
        args.append('-no-crop')
    
    args.append(x3f_path)
    
    print(f"Running: {' '.join(args)}")
    result = subprocess.run(args, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"x3f_extract failed with code {result.returncode}")
    
    # x3f_extract outputs to the same filename with .tif extension in output dir
    # For input _P2M0927.X3F, output is _P2M0927.X3F.tif
    actual_output = os.path.join(output_dir, os.path.basename(x3f_path) + '.tif')
    
    if not os.path.exists(actual_output):
        # Try alternative naming
        base_name = os.path.splitext(os.path.basename(x3f_path))[0]
        actual_output = os.path.join(output_dir, base_name + '.tif')
    
    if not os.path.exists(actual_output):
        raise RuntimeError(f"Could not find output file. Expected: {actual_output}")
    
    # Rename to the expected output path if needed
    if actual_output != output_path:
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(actual_output, output_path)
    
    return output_path


def load_tiff(path):
    """Load TIFF file as numpy array."""
    img = Image.open(path)
    arr = np.array(img, dtype=np.float64)
    return arr


def compute_metrics(output_arr, reference_arr):
    """Compute comparison metrics between output and reference."""
    # Handle transposed images (some SPP outputs are rotated)
    if output_arr.shape != reference_arr.shape:
        # Check if transposed
        if (output_arr.shape[0] == reference_arr.shape[1] and 
            output_arr.shape[1] == reference_arr.shape[0] and
            output_arr.shape[2] == reference_arr.shape[2]):
            # Transpose reference to match output
            reference_arr = np.transpose(reference_arr, (1, 0, 2))
    
    assert output_arr.shape == reference_arr.shape, \
        f"Shape mismatch: output {output_arr.shape} vs reference {reference_arr.shape}"
    
    diff = output_arr - reference_arr
    abs_diff = np.abs(diff)
    
    metrics = {}
    
    # Overall metrics
    metrics['rmse'] = float(np.sqrt(np.mean(diff ** 2)))
    metrics['mae'] = float(np.mean(abs_diff))
    metrics['max_error'] = float(np.max(abs_diff))
    metrics['psnr'] = float(10 * np.log10((255.0 ** 2) / np.mean(diff ** 2))) if np.mean(diff ** 2) > 0 else float('inf')
    
    # Per-channel metrics (assuming RGB or RGBA)
    num_channels = min(output_arr.shape[2], 3) if len(output_arr.shape) == 3 else 1
    channel_names = ['R', 'G', 'B'][:num_channels]
    
    metrics['channels'] = {}
    for i, name in enumerate(channel_names):
        channel_diff = diff[:, :, i] if num_channels > 1 else diff
        channel_abs_diff = abs_diff[:, :, i] if num_channels > 1 else abs_diff
        
        metrics['channels'][name] = {
            'mean_error': float(np.mean(channel_diff)),
            'mae': float(np.mean(channel_abs_diff)),
            'rmse': float(np.sqrt(np.mean(channel_diff ** 2))),
            'max_error': float(np.max(channel_abs_diff)),
            'mean_abs_error': float(np.mean(channel_abs_diff)),
        }
    
    # Luminance-based analysis (for RGB images)
    ref_lum = None
    if num_channels == 3:
        # Simple luminance approximation
        ref_lum = 0.299 * reference_arr[:,:,0] + 0.587 * reference_arr[:,:,1] + 0.114 * reference_arr[:,:,2]
        out_lum = 0.299 * output_arr[:,:,0] + 0.587 * output_arr[:,:,1] + 0.114 * output_arr[:,:,2]
        lum_diff = out_lum - ref_lum
        
        metrics['luminance'] = {
            'mean_error': float(np.mean(lum_diff)),
            'mae': float(np.mean(np.abs(lum_diff))),
            'rmse': float(np.sqrt(np.mean(lum_diff ** 2))),
        }
    
    # Regional analysis by luminance level (shadows, midtones, highlights)
    if num_channels == 3 and ref_lum is not None:
        regions = {
            'shadows': (ref_lum < 85),
            'midtones': (ref_lum >= 85) & (ref_lum < 170),
            'highlights': (ref_lum >= 170),
        }
        
        metrics['regions'] = {}
        for region_name, mask in regions.items():
            if np.sum(mask) > 0:
                region_diff = diff[mask]
                metrics['regions'][region_name] = {
                    'pixel_count': int(np.sum(mask)),
                    'mae': float(np.mean(np.abs(region_diff))),
                    'mean_error': float(np.mean(region_diff)),
                }
    
    return metrics


def print_report(metrics, verbose=False):
    """Print a human-readable report."""
    print("\n" + "="*60)
    print("COMPARISON REPORT")
    print("="*60)
    
    print(f"\nOverall Metrics:")
    print(f"  RMSE:        {metrics['rmse']:.4f}")
    print(f"  MAE:         {metrics['mae']:.4f}")
    print(f"  Max Error:   {metrics['max_error']:.1f}")
    print(f"  PSNR:        {metrics['psnr']:.2f} dB")
    
    print(f"\nPer-Channel Metrics:")
    for ch, ch_metrics in metrics.get('channels', {}).items():
        print(f"  {ch}: MAE={ch_metrics['mae']:.4f}, MeanErr={ch_metrics['mean_error']:.4f}, Max={ch_metrics['max_error']:.1f}")
    
    if 'luminance' in metrics:
        print(f"\nLuminance:")
        print(f"  MAE: {metrics['luminance']['mae']:.4f}")
        print(f"  Mean Error: {metrics['luminance']['mean_error']:.4f}")
    
    if 'regions' in metrics:
        print(f"\nRegional Analysis (by luminance):")
        for region, reg_metrics in metrics['regions'].items():
            print(f"  {region}: {reg_metrics['pixel_count']} pixels, MAE={reg_metrics['mae']:.4f}")
    
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description='Compare x3f_extract output to reference TIFF')
    parser.add_argument('x3f_file', help='Input X3F file')
    parser.add_argument('reference_tiff', help='Reference TIFF from Sigma Photo Pro')
    parser.add_argument('--x3f-extract', default='./x3f_extract', help='Path to x3f_extract binary')
    parser.add_argument('--output-tiff', help='Path for output TIFF (default: temp file)')
    parser.add_argument('--color-space', default='sRGB', choices=['sRGB', 'AdobeRGB', 'ProPhotoRGB', 'none'],
                        help='Color space for conversion')
    parser.add_argument('--no-crop', action='store_true', help='Disable cropping')
    parser.add_argument('--denoise', action='store_true', help='Enable denoising')
    parser.add_argument('--json', help='Output metrics to JSON file')
    parser.add_argument('--keep-output', action='store_true', help='Keep the generated TIFF file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if not os.path.isfile(args.x3f_file):
        print(f"Error: X3F file not found: {args.x3f_file}")
        sys.exit(1)
    
    if not os.path.isfile(args.reference_tiff):
        print(f"Error: Reference TIFF not found: {args.reference_tiff}")
        sys.exit(1)
    
    if not os.path.isfile(args.x3f_extract):
        print(f"Error: x3f_extract binary not found: {args.x3f_extract}")
        sys.exit(1)
    
    # Create output path
    if args.output_tiff:
        output_tiff = args.output_tiff
        cleanup = False
    else:
        fd, output_tiff = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        cleanup = not args.keep_output
    
    try:
        # Run conversion
        print(f"Converting {args.x3f_file}...")
        run_x3f_extract(
            args.x3f_file, 
            output_tiff,
            x3f_extract_path=args.x3f_extract,
            color_space=args.color_space,
            crop=not args.no_crop,
            denoise=args.denoise
        )
        
        # Load images
        print(f"Loading output: {output_tiff}")
        output_arr = load_tiff(output_tiff)
        print(f"Output shape: {output_arr.shape}, dtype: {output_arr.dtype}")
        
        print(f"Loading reference: {args.reference_tiff}")
        reference_arr = load_tiff(args.reference_tiff)
        print(f"Reference shape: {reference_arr.shape}, dtype: {reference_arr.dtype}")
        
        # Compute metrics
        metrics = compute_metrics(output_arr, reference_arr)
        
        # Print report
        print_report(metrics, args.verbose)
        
        # Save JSON if requested
        if args.json:
            with open(args.json, 'w') as f:
                json.dump(metrics, f, indent=2)
            print(f"\nMetrics saved to: {args.json}")
        
        # Exit with code based on match quality
        if metrics['max_error'] == 0 and metrics['rmse'] == 0:
            print("\nPERFECT MATCH!")
            return 0
        else:
            print(f"\nDifferences found (RMSE={metrics['rmse']:.4f})")
            return 1
        
    finally:
        if cleanup and os.path.exists(output_tiff):
            os.remove(output_tiff)


if __name__ == '__main__':
    sys.exit(main())
