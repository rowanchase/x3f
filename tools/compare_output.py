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


def compute_iq_metrics(arr):
    """Compute image quality metrics beyond RMSE - noise, dynamic range, etc.
    
    This analyzes the intrinsic quality of a single image.
    """
    metrics = {}
    
    # Handle RGBA (take first 3 channels)
    if len(arr.shape) == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    
    num_channels = arr.shape[2] if len(arr.shape) == 3 else 1
    channel_names = ['R', 'G', 'B'][:num_channels]
    
    # Calculate luminance
    if num_channels == 3:
        lum = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
    else:
        lum = arr[:,:,0] if num_channels == 1 else arr.flatten()
    
    # ==== 1. Highlight Headroom Analysis ====
    metrics['highlights'] = {}
    
    # Full-scale clipping (all channels at max)
    max_vals = np.max(arr, axis=2) if num_channels == 3 else arr
    fully_clipped = np.sum(max_vals >= 255.0)
    fully_clipped_pct = 100.0 * fully_clipped / max_vals.size
    
    # Per-channel clipping
    channel_clipped = {}
    for i, name in enumerate(channel_names):
        ch = arr[:,:,i] if num_channels > 1 else arr
        clipped = np.sum(ch >= 255.0)
        channel_clipped[name] = {
            'clipped_pixels': int(clipped),
            'clipped_pct': 100.0 * clipped / ch.size
        }
    
    # Recoverable highlights (some channels clipped, others not)
    # For Foveon: if one channel is clipped but others aren't, can reconstruct
    if num_channels == 3:
        # Find pixels where at least one channel is at max but not all
        any_clipped = np.any(arr >= 255.0, axis=2)
        all_clipped = np.all(arr >= 255.0, axis=2)
        recoverable = np.sum(any_clipped) - np.sum(all_clipped)
        recoverable_pct = 100.0 * recoverable / arr.shape[0] / arr.shape[1]
    else:
        recoverable = 0
        recoverable_pct = 0.0
    
    metrics['highlights'] = {
        'fully_clipped_pixels': int(fully_clipped),
        'fully_clipped_pct': fully_clipped_pct,
        'recoverable_pixels': int(recoverable),
        'recoverable_pct': recoverable_pct,
        'channel_clipped': channel_clipped,
    }
    
    # ==== 2. Shadow Quality Analysis ====
    metrics['shadows'] = {}
    
    # Define shadow regions by luminance
    shadow_bins = [
        ('deep_shadows', (0, 25)),
        ('dark_shadows', (25, 50)),
        ('light_shadows', (50, 85)),
    ]
    
    shadow_stats = {}
    for name, (lo, hi) in shadow_bins:
        mask = (lum >= lo) & (lum < hi)
        if np.sum(mask) > 100:  # Need enough pixels
            shadow_pixels = arr[mask]
            shadow_stats[name] = {
                'pixel_count': int(np.sum(mask)),
                'mean': float(np.mean(shadow_pixels)),
                'std': float(np.std(shadow_pixels)),
            }
    
    metrics['shadows'] = shadow_stats
    
    # ==== 3. Noise Analysis by Luminance Level ====
    metrics['noise'] = {}
    
    # Divide into luminance bins and compute statistics per bin
    lum_bins = [
        ('0-25', 0, 25),
        ('25-50', 25, 50),
        ('50-85', 50, 85),
        ('85-128', 85, 128),
        ('128-170', 128, 170),
        ('170-200', 170, 200),
        ('200-230', 200, 230),
        ('230-255', 230, 255),
    ]
    
    noise_by_lum = {}
    for name, lo, hi in lum_bins:
        mask = (lum >= lo) & (lum < hi)
        if np.sum(mask) > 100:
            bin_pixels = arr[mask]
            
            # Per-channel stats
            ch_stats = {}
            for i, ch_name in enumerate(channel_names):
                ch_pixels = bin_pixels[:, i] if num_channels > 1 else bin_pixels
                ch_stats[ch_name] = {
                    'mean': float(np.mean(ch_pixels)),
                    'std': float(np.std(ch_pixels)),
                }
            
            noise_by_lum[name] = {
                'pixel_count': int(np.sum(mask)),
                'mean_lum': float(np.mean(lum[mask])),
                'channels': ch_stats,
            }
    
    metrics['noise'] = noise_by_lum
    
    # ==== 4. Dynamic Range ====
    metrics['dynamic_range'] = {
        'min_value': float(np.min(arr)),
        'max_value': float(np.max(arr)),
        'mean_value': float(np.mean(arr)),
        'std_value': float(np.std(arr)),
    }
    
    # ==== 5. Channel Statistics ====
    metrics['channels'] = {}
    for i, name in enumerate(channel_names):
        ch = arr[:,:,i] if num_channels > 1 else arr.flatten()
        metrics['channels'][name] = {
            'min': float(np.min(ch)),
            'max': float(np.max(ch)),
            'mean': float(np.mean(ch)),
            'std': float(np.std(ch)),
        }
    
    return metrics


def compare_iq_metrics(output_metrics, ref_metrics):
    """Compare image quality metrics between output and reference."""
    comparison = {}
    
    # Highlight comparison
    comp = {}
    for key in ['fully_clipped_pixels', 'fully_clipped_pct', 'recoverable_pixels', 'recoverable_pct']:
        out_val = output_metrics['highlights'].get(key, 0)
        ref_val = ref_metrics['highlights'].get(key, 0)
        comp[key] = {
            'output': out_val,
            'reference': ref_val,
            'diff': out_val - ref_val,
        }
    comparison['highlights'] = comp
    
    # Shadow noise comparison
    comp = {}
    for shadow_name in output_metrics.get('shadows', {}):
        if shadow_name in ref_metrics.get('shadows', {}):
            out_std = output_metrics['shadows'][shadow_name].get('std', 0)
            ref_std = ref_metrics['shadows'][shadow_name].get('std', 0)
            comp[shadow_name] = {
                'output_std': out_std,
                'reference_std': ref_std,
                'diff': out_std - ref_std,
            }
    comparison['shadows'] = comp
    
    # Dynamic range comparison
    comp = {}
    for key in ['min_value', 'max_value', 'mean_value', 'std_value']:
        out_val = output_metrics['dynamic_range'].get(key, 0)
        ref_val = ref_metrics['dynamic_range'].get(key, 0)
        comp[key] = {
            'output': out_val,
            'reference': ref_val,
            'diff': out_val - ref_val,
        }
    comparison['dynamic_range'] = comp
    
    return comparison


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
    parser.add_argument('--iq-metrics', action='store_true', help='Compute image quality metrics (noise, dynamic range, etc.)')
    parser.add_argument('--iq-json', help='Output IQ metrics to JSON file')
    
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
        
        # Compute IQ metrics if requested
        if args.iq_metrics:
            print("\n" + "="*60)
            print("IMAGE QUALITY METRICS")
            print("="*60)
            
            # Compute IQ metrics for both output and reference
            output_iq = compute_iq_metrics(output_arr)
            ref_iq = compute_iq_metrics(reference_arr)
            
            # Compare them
            iq_comparison = compare_iq_metrics(output_iq, ref_iq)
            
            # Print highlight analysis
            print("\nHighlight Analysis:")
            print(f"  Fully clipped (all channels):")
            for key in ['fully_clipped_pixels', 'fully_clipped_pct']:
                out_val = output_iq['highlights'].get(key, 0)
                ref_val = ref_iq['highlights'].get(key, 0)
                diff = out_val - ref_val
                suffix = '%' if 'pct' in key else 'px'
                print(f"    {key}: output={out_val:.1f}{suffix}, ref={ref_val:.1f}{suffix}, diff={diff:+.1f}{suffix}")
            
            print(f"\n  Recoverable (some channels clipped):")
            out_val = output_iq['highlights'].get('recoverable_pixels', 0)
            ref_val = ref_iq['highlights'].get('recoverable_pixels', 0)
            print(f"    output={out_val}px ({output_iq['highlights'].get('recoverable_pct', 0):.2f}%), ref={ref_val}px ({ref_iq['highlights'].get('recoverable_pct', 0):.2f}%)")
            
            # Per-channel clipping
            print(f"\n  Per-channel clipping:")
            for ch in ['R', 'G', 'B']:
                out_pct = output_iq['highlights']['channel_clipped'].get(ch, {}).get('clipped_pct', 0)
                ref_pct = ref_iq['highlights']['channel_clipped'].get(ch, {}).get('clipped_pct', 0)
                print(f"    {ch}: output={out_pct:.3f}%, ref={ref_pct:.3f}%, diff={out_pct-ref_pct:+.3f}%")
            
            # Shadow noise analysis
            print("\nShadow Noise Analysis:")
            for shadow_name in output_iq.get('shadows', {}):
                if shadow_name in ref_iq.get('shadows', {}):
                    out_std = output_iq['shadows'][shadow_name].get('std', 0)
                    ref_std = ref_iq['shadows'][shadow_name].get('std', 0)
                    out_mean = output_iq['shadows'][shadow_name].get('mean', 0)
                    ref_mean = ref_iq['shadows'][shadow_name].get('mean', 0)
                    # SNR (signal-to-noise ratio approximation)
                    out_snr = out_mean / out_std if out_std > 0 else float('inf')
                    ref_snr = ref_mean / ref_std if ref_std > 0 else float('inf')
                    print(f"  {shadow_name}:")
                    print(f"    output: mean={out_mean:.2f}, std={out_std:.2f}, SNR={out_snr:.1f}")
                    print(f"    reference: mean={ref_mean:.2f}, std={ref_std:.2f}, SNR={ref_snr:.1f}")
                    print(f"    diff: std={out_std-ref_std:+.2f}, SNR={out_snr-ref_snr:+.1f}")
            
            # Dynamic range
            print("\nDynamic Range:")
            for key in ['min_value', 'max_value', 'mean_value', 'std_value']:
                out_val = output_iq['dynamic_range'].get(key, 0)
                ref_val = ref_iq['dynamic_range'].get(key, 0)
                print(f"  {key}: output={out_val:.2f}, ref={ref_val:.2f}, diff={out_val-ref_val:+.2f}")
            
            # Save IQ metrics to JSON if requested
            if args.iq_json:
                iq_data = {
                    'output': output_iq,
                    'reference': ref_iq,
                    'comparison': iq_comparison
                }
                with open(args.iq_json, 'w') as f:
                    json.dump(iq_data, f, indent=2)
                print(f"\nIQ metrics saved to: {args.iq_json}")
        
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
