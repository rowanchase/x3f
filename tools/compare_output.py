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
import random
from PIL import Image
import numpy as np


D65_ILLUMINANT = np.array([0.95047, 1.0, 1.08883])


def srgb_to_linear(arr):
    mask = arr <= 0.04045
    linear = np.where(mask, arr / 12.92, np.power((arr + 0.055) / 1.055, 2.4))
    return linear


def linear_to_xyz(arr):
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    return np.stack([x, y, z], axis=-1)


def xyz_to_lab(xyz):
    x_r = xyz[:,:,0] / D65_ILLUMINANT[0]
    y_r = xyz[:,:,1] / D65_ILLUMINANT[1]
    z_r = xyz[:,:,2] / D65_ILLUMINANT[2]
    
    def f(t):
        delta = 6.0 / 29.0
        return np.where(t > delta, np.power(t, 1.0/3.0), (29.0**2 * t + 4.0/29.0) / 116.0)
    
    f_x = f(x_r)
    f_y = f(y_r)
    f_z = f(z_r)
    
    L = 116.0 * f_y - 16.0
    a = 500.0 * (f_x - f_y)
    b = 200.0 * (f_y - f_z)
    return np.stack([L, a, b], axis=-1)


def rgb_to_lab(arr):
    normalized = arr / 255.0
    linear = srgb_to_linear(normalized)
    xyz = linear_to_xyz(linear)
    lab = xyz_to_lab(xyz)
    return lab


def compute_delta_e1976(lab1, lab2):
    dL = lab1[:,:,0] - lab2[:,:,0]
    da = lab1[:,:,1] - lab2[:,:,1]
    db = lab1[:,:,2] - lab2[:,:,2]
    return np.sqrt(dL**2 + da**2 + db**2)


def compute_delta_e_by_luminance(output_arr, reference_arr, num_samples=5000):
    """Compute DeltaE statistics broken down by luminance region."""
    lab1 = rgb_to_lab(output_arr)
    lab2 = rgb_to_lab(reference_arr)
    dE = compute_delta_e1976(lab1, lab2)
    
    ref_lum = 0.299 * reference_arr[:,:,0] + 0.587 * reference_arr[:,:,1] + 0.114 * reference_arr[:,:,2]
    
    shadows = ref_lum < 85
    midtones = (ref_lum >= 85) & (ref_lum < 170)
    highlights = ref_lum >= 170
    
    results = {}
    for name, mask in [('shadows', shadows), ('midtones', midtones), ('highlights', highlights)]:
        if np.sum(mask) > 0:
            dE_masked = dE[mask]
            results[name] = {
                'pixel_count': int(np.sum(mask)),
                'mean': float(np.mean(dE_masked)),
                'std': float(np.std(dE_masked)),
                'median': float(np.median(dE_masked)),
                'p95': float(np.percentile(dE_masked, 95)),
                'p99': float(np.percentile(dE_masked, 99)),
            }
    return results


def compute_per_pixel_delta_e(output_arr, reference_arr, num_samples=20):
    """Sample random pixels and compute per-pixel DeltaE."""
    lab1 = rgb_to_lab(output_arr)
    lab2 = rgb_to_lab(reference_arr)
    
    h, w = output_arr.shape[:2]
    total_pixels = h * w
    
    if num_samples >= total_pixels:
        indices = list(range(total_pixels))
    else:
        indices = random.sample(range(total_pixels), num_samples)
    
    samples = []
    for idx in indices:
        row = idx // w
        col = idx % w
        
        out_rgb = output_arr[row, col]
        ref_rgb = reference_arr[row, col]
        out_lab = lab1[row, col]
        ref_lab = lab2[row, col]
        
        dE = np.sqrt(np.sum((out_lab - ref_lab)**2))
        
        samples.append({
            'row': int(row),
            'col': int(col),
            'output_rgb': [float(v) for v in out_rgb],
            'reference_rgb': [float(v) for v in ref_rgb],
            'output_lab': [float(v) for v in out_lab],
            'reference_lab': [float(v) for v in ref_lab],
            'delta_e': float(dE),
        })
    
    return samples


def compute_delta_e_metrics(output_arr, reference_arr):
    """Compute comprehensive DeltaE-based perceptual color metrics."""
    lab1 = rgb_to_lab(output_arr)
    lab2 = rgb_to_lab(reference_arr)
    
    dE1976 = compute_delta_e1976(lab1, lab2)
    
    L_errors = np.abs(lab1[:,:,0] - lab2[:,:,0])
    a_errors = np.abs(lab1[:,:,1] - lab2[:,:,1])
    b_errors = np.abs(lab1[:,:,2] - lab2[:,:,2])
    
    metrics = {
        'DeltaE1976': {
            'mean': float(np.mean(dE1976)),
            'std': float(np.std(dE1976)),
            'max': float(np.max(dE1976)),
            'median': float(np.median(dE1976)),
            'p95': float(np.percentile(dE1976, 95)),
            'p99': float(np.percentile(dE1976, 99)),
        },
        'per_channel': {
            'L': {
                'mean': float(np.mean(L_errors)),
                'std': float(np.std(L_errors)),
                'max': float(np.max(L_errors)),
                'p95': float(np.percentile(L_errors, 95)),
            },
            'a': {
                'mean': float(np.mean(a_errors)),
                'std': float(np.std(a_errors)),
                'max': float(np.max(a_errors)),
                'p95': float(np.percentile(a_errors, 95)),
            },
            'b': {
                'mean': float(np.mean(b_errors)),
                'std': float(np.std(b_errors)),
                'max': float(np.max(b_errors)),
                'p95': float(np.percentile(b_errors, 95)),
            },
        },
        'by_luminance': compute_delta_e_by_luminance(output_arr, reference_arr),
    }
    
    return metrics


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


def check_icc_profile(path):
    """Check if TIFF has an ICC profile and return info."""
    img = Image.open(path)
    icc = img.info.get('icc_profile')
    if icc:
        # Try to detect color space from ICC profile
        # Adobe RGB profiles start with specific bytes
        is_adobe = icc[:4] == b'ADBE' or b'Adobe RGB' in icc[:100]
        is_srgb = b'sRGB' in icc[:40] or b'sRGB IEC61966' in icc[:60]
        return {
            'has_icc': True,
            'size': len(icc),
            'is_adobe_rgb': is_adobe,
            'is_srgb': is_srgb,
        }
    return {'has_icc': False, 'size': 0, 'is_adobe_rgb': False, 'is_srgb': False}


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
    
    # ==== 6. Sharpness / Edge Response Analysis ====
    metrics['sharpness'] = {}
    if num_channels == 3:
        # Convert to grayscale for sharpness analysis
        gray = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
        gray = gray.astype(np.float64)
        
        # Simplified gradient-based sharpness (using numpy roll for efficiency)
        # Horizontal gradient
        grad_x = np.abs(np.roll(gray, -1, axis=1) - gray)
        grad_x[:, -1] = 0  # zero the edge
        # Vertical gradient
        grad_y = np.abs(np.roll(gray, -1, axis=0) - gray)
        grad_y[-1, :] = 0  # zero the edge
        
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        metrics['sharpness'] = {
            'mean_gradient': float(np.mean(gradient_magnitude)),
            'max_gradient': float(np.max(gradient_magnitude)),
            'std_gradient': float(np.std(gradient_magnitude)),
            'pct_high_gradient': float(100.0 * np.sum(gradient_magnitude > 20) / gradient_magnitude.size),
        }
    
    # ==== 7. Local Contrast Analysis (simplified - block-based) ====
    metrics['local_contrast'] = {}
    if num_channels == 3:
        # Use larger blocks for efficiency (64x64 blocks)
        block_size = 64
        
        # Compute statistics on blocks
        h_blocks = lum.shape[0] // block_size
        w_blocks = lum.shape[1] // block_size
        
        block_means = []
        block_stds = []
        block_lums = []
        
        for i in range(h_blocks):
            for j in range(w_blocks):
                block = lum[i*block_size:(i+1)*block_size, j*block_size:(j+1)*block_size]
                block_means.append(np.mean(block))
                block_stds.append(np.std(block))
                block_lums.append(np.mean(block))
        
        block_means = np.array(block_means)
        block_stds = np.array(block_stds)
        block_lums = np.array(block_lums)
        
        # Local contrast = std / mean
        with np.errstate(divide='ignore', invalid='ignore'):
            local_contrast = block_stds / (block_means + 1e-6)
            local_contrast = np.nan_to_num(local_contrast)
        
        # Find which blocks are in shadow/midtone/highlight
        shadow_mask = block_lums < 50
        midtone_mask = (block_lums >= 50) & (block_lums < 200)
        highlight_mask = block_lums >= 200
        
        metrics['local_contrast'] = {
            'mean_local_contrast': float(np.mean(local_contrast)),
            'std_local_contrast': float(np.std(local_contrast)),
            'shadow_contrast': float(np.mean(local_contrast[shadow_mask])) if np.any(shadow_mask) else 0.0,
            'midtone_contrast': float(np.mean(local_contrast[midtone_mask])) if np.any(midtone_mask) else 0.0,
            'highlight_contrast': float(np.mean(local_contrast[highlight_mask])) if np.any(highlight_mask) else 0.0,
        }
    
    # ==== 8. Color Analysis (saturation, hue) ====
    metrics['color'] = {}
    if num_channels == 3:
        # Saturation: max - min normalized (HSL saturation)
        rgb_min = np.min(arr, axis=2)
        rgb_max = np.max(arr, axis=2)
        saturation = (rgb_max - rgb_min) / (rgb_max + 1e-6)
        
        # Chroma: absolute difference (not normalized by brightness)
        # This is more perceptually relevant than normalized saturation
        chroma = rgb_max - rgb_min
        
        # Colorfulness: RMS of channel differences
        # Another perceptually-relevant metric
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        colorfulness = np.sqrt((r-g)**2 + (r-b)**2 + (g-b)**2)
        
        # Perceptual chroma: distance from neutral gray
        gray = (r + g + b) / 3.0
        perceptual_chroma = np.sqrt((r-gray)**2 + (g-gray)**2 + (b-gray)**2)
        
        # Simple hue estimation using channel ratios
        # R-dominant, G-dominant, B-dominant regions
        r_dominant = (arr[:,:,0] > arr[:,:,1]) & (arr[:,:,0] > arr[:,:,2])
        g_dominant = (arr[:,:,1] > arr[:,:,0]) & (arr[:,:,1] > arr[:,:,2])
        b_dominant = (arr[:,:,2] > arr[:,:,0]) & (arr[:,:,2] > arr[:,:,1])
        
        metrics['color'] = {
            'mean_saturation': float(np.mean(saturation)),
            'std_saturation': float(np.std(saturation)),
            'mean_chroma': float(np.mean(chroma)),
            'mean_colorfulness': float(np.mean(colorfulness)),
            'mean_perceptual_chroma': float(np.mean(perceptual_chroma)),
            'r_dominant_pct': float(100.0 * np.sum(r_dominant) / r_dominant.size),
            'g_dominant_pct': float(100.0 * np.sum(g_dominant) / g_dominant.size),
            'b_dominant_pct': float(100.0 * np.sum(b_dominant) / b_dominant.size),
        }
        
        # Channel correlation (R-G, G-B, R-B)
        r, g, b = arr[:,:,0].flatten(), arr[:,:,1].flatten(), arr[:,:,2].flatten()
        metrics['color']['rg_correlation'] = float(np.corrcoef(r, g)[0,1])
        metrics['color']['gb_correlation'] = float(np.corrcoef(g, b)[0,1])
        metrics['color']['rb_correlation'] = float(np.corrcoef(r, b)[0,1])
    
    # ==== 9. Histogram Analysis ====
    metrics['histogram'] = {}
    if num_channels == 3:
        for i, name in enumerate(channel_names):
            ch = arr[:,:,i]
            h, _ = np.histogram(ch, bins=256, range=(0, 256))
            metrics['histogram'][name] = h.tolist()
    else:
        h, _ = np.histogram(arr, bins=256, range=(0, 256))
        metrics['histogram']['gray'] = h.tolist()
    
    return metrics


def compute_highlight_histogram_metrics(arr, channel_name='unknown'):
    """Compute detailed histogram metrics focused on highlight region (200-255).
    
    Args:
        arr: 2D array of channel values (0-255)
        channel_name: Name of the channel for reporting
        
    Returns:
        Dictionary with highlight-focused histogram statistics
    """
    metrics = {
        'channel': channel_name,
        'total_pixels': arr.size,
    }
    
    # Compute full histogram
    hist, bin_edges = np.histogram(arr, bins=256, range=(0, 256))
    metrics['histogram'] = hist.tolist()
    
    # Define highlight regions
    highlight_regions = {
        'soft_highlights': (200, 230),    # Starting to clip
        'hard_highlights': (230, 254),    # Nearly clipped
        'fully_clipped': (254, 256),       # At max value
    }
    
    # Per-region analysis
    region_metrics = {}
    for region_name, (low, high) in highlight_regions.items():
        mask = (arr >= low) & (arr < high)
        pixel_count = np.sum(mask)
        pixel_pct = 100.0 * pixel_count / arr.size
        
        if pixel_count > 0:
            values_in_region = arr[mask]
            region_metrics[region_name] = {
                'pixel_count': int(pixel_count),
                'pixel_pct': float(pixel_pct),
                'mean': float(np.mean(values_in_region)),
                'std': float(np.std(values_in_region)),
                'min': float(np.min(values_in_region)),
                'max': float(np.max(values_in_region)),
            }
        else:
            region_metrics[region_name] = {
                'pixel_count': 0,
                'pixel_pct': 0.0,
                'mean': 0.0,
                'std': 0.0,
                'min': 0.0,
                'max': 0.0,
            }
    
    metrics['highlight_regions'] = region_metrics
    
    # Compute percentile-based statistics
    percentiles = [90, 95, 98, 99, 99.5, 99.9, 100]
    perc_values = np.percentile(arr, percentiles)
    metrics['percentiles'] = {f'p{p}': float(v) for p, v in zip(percentiles, perc_values)}
    
    # Detect potential clipping issues
    # Look for "flat" histogram at the top (many pixels at max value)
    top_10_bins = hist[246:256]  # 246-255
    top_5_bins = hist[251:256]   # 251-255
    
    # Suspicious patterns:
    # 1. Large spike at max value (254-255)
    max_value_pixels = np.sum(hist[254:256])
    metrics['suspicious_patterns'] = {
        'max_value_pixels': int(max_value_pixels),
        'max_value_pct': float(100.0 * max_value_pixels / arr.size),
        'top_10_sum': int(np.sum(top_10_bins)),
        'top_5_sum': int(np.sum(top_5_bins)),
    }
    
    # Detect "compression" - gradual falloff vs sharp cutoff
    # A natural image should have gradual falloff in highlights
    # Clipped images often have sharp cutoffs
    if np.sum(hist[200:240]) > 0:
        # Compare density in 200-220 vs 220-240
        low_high_density = np.mean(hist[200:220])
        mid_high_density = np.mean(hist[220:240])
        
        if low_high_density > 0:
            compression_ratio = mid_high_density / low_high_density
            metrics['suspicious_patterns']['compression_ratio'] = float(compression_ratio)
            
            # If ratio is very low, it suggests compression/clipping
            if compression_ratio < 0.3:
                metrics['suspicious_patterns']['possible_compression'] = True
                metrics['suspicious_patterns']['compression_severity'] = 'high' if compression_ratio < 0.1 else 'moderate'
            else:
                metrics['suspicious_patterns']['possible_compression'] = False
                metrics['suspicious_patterns']['compression_severity'] = 'none'
    
    return metrics


def compare_histograms(out_hist_metrics, ref_hist_metrics):
    """Compare histograms between output and reference.
    
    Returns dictionary of differences and suspicious patterns.
    """
    comparison = {
        'channel': out_hist_metrics['channel'],
        'total_pixels': out_hist_metrics['total_pixels'],
    }
    
    # Compare highlight region statistics
    region_comparison = {}
    for region_name in out_hist_metrics.get('highlight_regions', {}):
        if region_name in ref_hist_metrics.get('highlight_regions', {}):
            out_reg = out_hist_metrics['highlight_regions'][region_name]
            ref_reg = ref_hist_metrics['highlight_regions'][region_name]
            
            region_comparison[region_name] = {
                'output_count': out_reg['pixel_count'],
                'reference_count': ref_reg['pixel_count'],
                'count_diff': out_reg['pixel_count'] - ref_reg['pixel_count'],
                'output_pct': out_reg['pixel_pct'],
                'reference_pct': ref_reg['pixel_pct'],
                'pct_diff': out_reg['pixel_pct'] - ref_reg['pixel_pct'],
            }
    
    comparison['highlight_regions'] = region_comparison
    
    # Compare percentiles
    perc_comparison = {}
    for perc_name in out_hist_metrics.get('percentiles', {}):
        if perc_name in ref_hist_metrics.get('percentiles', {}):
            out_val = out_hist_metrics['percentiles'][perc_name]
            ref_val = ref_hist_metrics['percentiles'][perc_name]
            diff = out_val - ref_val
            
            perc_comparison[perc_name] = {
                'output': out_val,
                'reference': ref_val,
                'diff': diff,
            }
    
    comparison['percentiles'] = perc_comparison
    
    # Detect suspicious differences
    suspicious = []
    
    # 1. Large difference in 99th percentile (suggests different highlight handling)
    p99_diff = perc_comparison.get('p99.0', {}).get('diff', 0)
    if abs(p99_diff) > 5:
        suspicious.append(f"Large p99 difference: {p99_diff:+.1f} (output={perc_comparison['p99.0']['output']:.1f}, ref={perc_comparison['p99.0']['reference']:.1f})")
    
    # 2. Different clipping behavior at max value
    out_max = out_hist_metrics['suspicious_patterns'].get('max_value_pct', 0)
    ref_max = ref_hist_metrics['suspicious_patterns'].get('max_value_pct', 0)
    max_diff = out_max - ref_max
    
    if abs(max_diff) > 0.5:  # More than 0.5% difference
        suspicious.append(f"Max value clipping differs: {max_diff:+.2f}% (output={out_max:.2f}%, ref={ref_max:.2f}%)")
    
    # 3. Different "soft highlight" region population
    if 'soft_highlights' in region_comparison:
        soft_diff = region_comparison['soft_highlights']['count_diff']
        soft_pct_diff = region_comparison['soft_highlights']['pct_diff']
        
        if abs(soft_pct_diff) > 1.0:  # More than 1% difference in 200-230 range
            suspicious.append(f"Soft highlight region differs: {soft_pct_diff:+.2f}% ({soft_diff:+d} pixels)")
    
    # 4. Compression pattern differences
    out_compression = out_hist_metrics['suspicious_patterns'].get('possible_compression', False)
    ref_compression = ref_hist_metrics['suspicious_patterns'].get('possible_compression', False)
    
    if out_compression != ref_compression:
        out_sev = out_hist_metrics['suspicious_patterns'].get('compression_severity', 'none')
        ref_sev = ref_hist_metrics['suspicious_patterns'].get('compression_severity', 'none')
        suspicious.append(f"Compression mismatch: output={out_sev}, reference={ref_sev}")
    
    comparison['suspicious_differences'] = suspicious
    comparison['has_suspicious_patterns'] = len(suspicious) > 0
    
    return comparison


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
    
    # Sharpness comparison
    if 'sharpness' in output_metrics and 'sharpness' in ref_metrics:
        comp = {}
        for key in ['mean_gradient', 'max_gradient', 'std_gradient', 'pct_high_gradient']:
            out_val = output_metrics['sharpness'].get(key, 0)
            ref_val = ref_metrics['sharpness'].get(key, 0)
            comp[key] = {
                'output': out_val,
                'reference': ref_val,
                'diff': out_val - ref_val,
            }
        comparison['sharpness'] = comp
    
    # Local contrast comparison
    if 'local_contrast' in output_metrics and 'local_contrast' in ref_metrics:
        comp = {}
        for key in ['mean_local_contrast', 'std_local_contrast', 'shadow_contrast', 'midtone_contrast', 'highlight_contrast']:
            out_val = output_metrics['local_contrast'].get(key, 0)
            ref_val = ref_metrics['local_contrast'].get(key, 0)
            comp[key] = {
                'output': out_val,
                'reference': ref_val,
                'diff': out_val - ref_val,
            }
        comparison['local_contrast'] = comp
    
    # Color comparison
    if 'color' in output_metrics and 'color' in ref_metrics:
        comp = {}
        for key in ['mean_saturation', 'std_saturation', 'mean_chroma', 'mean_colorfulness', 'mean_perceptual_chroma', 'rg_correlation', 'gb_correlation', 'rb_correlation']:
            out_val = output_metrics['color'].get(key, 0)
            ref_val = ref_metrics['color'].get(key, 0)
            comp[key] = {
                'output': out_val,
                'reference': ref_val,
                'diff': out_val - ref_val,
            }
        comparison['color'] = comp
    
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
    parser.add_argument('--histogram-json', help='Output highlight histogram metrics to JSON file')
    parser.add_argument('--no-delta-e', action='store_true', help='Disable DeltaE perceptual color metrics (enabled by default)')
    parser.add_argument('--num-samples', type=int, default=20, help='Number of random pixel samples for DeltaE (default: 20)')
    parser.add_argument('--delta-e-json', help='Output DeltaE metrics to JSON file')
    
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
        
        # Check ICC profiles
        print("\n--- ICC Profile Analysis ---")
        output_icc = check_icc_profile(output_tiff)
        ref_icc = check_icc_profile(args.reference_tiff)
        
        print(f"Output TIFF ICC: {'YES' if output_icc['has_icc'] else 'NO'}")
        if output_icc['has_icc']:
            if output_icc['is_srgb']:
                print(f"  -> Detected: sRGB")
            elif output_icc['is_adobe_rgb']:
                print(f"  -> Detected: Adobe RGB")
            else:
                print(f"  -> Unknown profile ({output_icc['size']} bytes)")
        
        print(f"Reference TIFF ICC: {'YES' if ref_icc['has_icc'] else 'NO'}")
        if ref_icc['has_icc']:
            if ref_icc['is_srgb']:
                print(f"  -> Detected: sRGB")
            elif ref_icc['is_adobe_rgb']:
                print(f"  -> Detected: Adobe RGB")
            else:
                print(f"  -> Unknown profile ({ref_icc['size']} bytes)")
        
        if output_icc['has_icc'] != ref_icc['has_icc']:
            print("\n*** WARNING: ICC profile mismatch! ***")
            print("This can cause significant color differences when viewed.")
        elif output_icc['has_icc'] and ref_icc['has_icc']:
            if output_icc['is_adobe_rgb'] != ref_icc['is_adobe_rgb']:
                print("\n*** WARNING: Different color spaces! ***")
        print("--- End ICC Analysis ---\n")
        
        # Compute metrics
        metrics = compute_metrics(output_arr, reference_arr)
        
        # Compute DeltaE metrics if requested
        delta_e_metrics = None
        if not args.no_delta_e:
            print("\n" + "="*60)
            print("PERCEPTUAL COLOR METRICS (DeltaE)")
            print("="*60)
            
            delta_e_metrics = compute_delta_e_metrics(output_arr, reference_arr)
            
            print("\nOverall DeltaE1976 (CIE76):")
            de = delta_e_metrics['DeltaE1976']
            print(f"  Mean:   {de['mean']:.2f}")
            print(f"  Std:    {de['std']:.2f}")
            print(f"  Median: {de['median']:.2f}")
            print(f"  95th percentile: {de['p95']:.2f}")
            print(f"  Max:    {de['max']:.2f}")
            
            print("\nPer-Channel Lab Errors:")
            for ch in ['L', 'a', 'b']:
                ch_err = delta_e_metrics['per_channel'][ch]
                print(f"  {ch}: mean={ch_err['mean']:.2f}, max={ch_err['max']:.2f}, p95={ch_err['p95']:.2f}")
            
            print("\nDeltaE by Luminance Region:")
            for region, stats in delta_e_metrics['by_luminance'].items():
                print(f"  {region}: mean={stats['mean']:.2f}, p95={stats['p95']:.2f} ({stats['pixel_count']} pixels)")
            
            print("\nPer-Pixel DeltaE Samples:")
            pixel_samples = compute_per_pixel_delta_e(output_arr, reference_arr, args.num_samples)
            for i, sample in enumerate(pixel_samples[:10]):
                print(f"  [{sample['row']:4d}, {sample['col']:4d}] DeltaE={sample['delta_e']:6.2f} | "
                      f"RGB out=[{sample['output_rgb'][0]:5.1f},{sample['output_rgb'][1]:5.1f},{sample['output_rgb'][2]:5.1f}] "
                      f"ref=[{sample['reference_rgb'][0]:5.1f},{sample['reference_rgb'][1]:5.1f},{sample['reference_rgb'][2]:5.1f}]")
            
            if args.num_samples > 10 and len(pixel_samples) > 10:
                print(f"  ... and {len(pixel_samples) - 10} more samples")
            
            if args.delta_e_json:
                delta_e_output = {
                    'metrics': delta_e_metrics,
                    'sampled_pixels': pixel_samples,
                }
                with open(args.delta_e_json, 'w') as f:
                    json.dump(delta_e_output, f, indent=2)
                print(f"\nDeltaE metrics saved to: {args.delta_e_json}")
            
            metrics['delta_e'] = delta_e_metrics
        
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
            
            # Sharpness analysis
            if 'sharpness' in output_iq and 'sharpness' in ref_iq:
                print("\nSharpness / Edge Response:")
                for key in ['mean_gradient', 'max_gradient', 'std_gradient', 'pct_high_gradient']:
                    out_val = output_iq['sharpness'].get(key, 0)
                    ref_val = ref_iq['sharpness'].get(key, 0)
                    suffix = '%' if 'pct' in key else ''
                    print(f"  {key}: output={out_val:.2f}{suffix}, ref={ref_val:.2f}{suffix}, diff={out_val-ref_val:+.2f}{suffix}")
            
            # Local contrast analysis
            if 'local_contrast' in output_iq and 'local_contrast' in ref_iq:
                print("\nLocal Contrast:")
                for key in ['mean_local_contrast', 'shadow_contrast', 'midtone_contrast', 'highlight_contrast']:
                    out_val = output_iq['local_contrast'].get(key, 0)
                    ref_val = ref_iq['local_contrast'].get(key, 0)
                    print(f"  {key}: output={out_val:.4f}, ref={ref_val:.4f}, diff={out_val-ref_val:+.4f}")
            
            # Color analysis (DeltaE is now the primary metric)
            if 'color' in output_iq and 'color' in ref_iq:
                print("\nColor Analysis (DeltaE is primary metric - see above):")
                for key in ['mean_colorfulness', 'mean_perceptual_chroma']:
                    out_val = output_iq['color'].get(key, 0)
                    ref_val = ref_iq['color'].get(key, 0)
                    suffix = ' (absolute)'
                    print(f"  {key}{suffix}: output={out_val:.4f}, ref={ref_val:.4f}, diff={out_val-ref_val:+.4f}")
            
            # Highlight Histogram Analysis
            print("\n" + "="*60)
            print("HIGHLIGHT HISTOGRAM ANALYSIS (200-255 range)")
            print("="*60)
            
            # Compute histogram metrics for each channel
            hist_comparisons = []
            all_suspicious = []
            
            for i, ch_name in enumerate(['R', 'G', 'B']):
                out_ch = output_arr[:,:,i]
                ref_ch = reference_arr[:,:,i]
                
                out_hist = compute_highlight_histogram_metrics(out_ch, ch_name)
                ref_hist = compute_highlight_histogram_metrics(ref_ch, ch_name)
                
                comparison = compare_histograms(out_hist, ref_hist)
                hist_comparisons.append(comparison)
                
                # Print per-channel summary
                print(f"\n{ch_name} Channel:")
                print(f"  Percentiles (output vs reference):")
                for perc in ['p90', 'p95', 'p99', 'p99.9']:
                    if perc in comparison['percentiles']:
                        p = comparison['percentiles'][perc]
                        print(f"    {perc}: {p['output']:6.1f} vs {p['reference']:6.1f} (diff: {p['diff']:+6.1f})")
                
                # Print highlight region breakdown
                print(f"\n  Highlight Region Distribution:")
                for region in ['soft_highlights', 'hard_highlights', 'fully_clipped']:
                    if region in comparison['highlight_regions']:
                        reg = comparison['highlight_regions'][region]
                        print(f"    {region:20s}: output={reg['output_count']:7d} ({reg['output_pct']:5.2f}%) "
                              f"ref={reg['reference_count']:7d} ({reg['reference_pct']:5.2f}%) "
                              f"diff={reg['count_diff']:+7d} ({reg['pct_diff']:+.2f}%)")
                
                # Print suspicious patterns
                if comparison['has_suspicious_patterns']:
                    print(f"\n  *** SUSPICIOUS PATTERNS DETECTED ***")
                    for susp in comparison['suspicious_differences']:
                        print(f"    - {susp}")
                        all_suspicious.append(f"{ch_name}: {susp}")
                else:
                    print(f"\n  No suspicious patterns detected")
            
            # Overall summary
            print("\n" + "="*60)
            print("HIGHLIGHT HISTOGRAM SUMMARY")
            print("="*60)
            
            if all_suspicious:
                print(f"\n*** {len(all_suspicious)} SUSPICIOUS DIFFERENCES FOUND ***")
                for s in all_suspicious:
                    print(f"  - {s}")
                print("\nRecommendation: Investigate highlight processing pipeline")
            else:
                print("\nNo significant highlight histogram differences detected.")
            
            # Save histogram metrics to JSON if requested
            if args.histogram_json:
                histogram_data = {
                    'per_channel_comparisons': hist_comparisons,
                    'suspicious_patterns': all_suspicious,
                    'summary': {
                        'total_suspicious': len(all_suspicious),
                        'channels_analyzed': ['R', 'G', 'B'],
                        'focus_region': '200-255 (highlights)',
                    }
                }
                with open(args.histogram_json, 'w') as f:
                    json.dump(histogram_data, f, indent=2)
                print(f"\nHistogram metrics saved to: {args.histogram_json}")
            
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
