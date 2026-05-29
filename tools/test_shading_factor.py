#!/usr/bin/env python3
"""
Test harness for evaluating ColorShadingFactor variants.

Computes per-channel mean values in a 7x7 grid across the image,
reports R/G and B/G ratios spatially, and computes RMSE against a
reference TIFF.

Usage:
    python3 tools/test_shading_factor.py <test_tiff> [<reference_tiff>]
"""

import sys
import os
import numpy as np
from PIL import Image


def load_tiff(path):
    img = Image.open(path)
    arr = np.array(img, dtype=np.float64)
    return arr


def compute_grid_ratios(arr, grid_size=7):
    """Compute R/G and B/G ratios in a grid_size x grid_size grid across the image.

    Returns dict with per-cell stats and overall spatial ratio maps.
    """
    h, w, c = arr.shape
    assert c >= 3, f"Expected >= 3 channels, got {c}"

    # Extract channels
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    # Compute R/G and B/G per pixel (add epsilon to avoid div by zero)
    eps = 1e-8
    rg_map = r / (g + eps)
    bg_map = b / (g + eps)

    # Divide into grid cells
    cell_h = h // grid_size
    cell_w = w // grid_size

    cells = []
    for i in range(grid_size):
        row_start = i * cell_h
        row_end = (i + 1) * cell_h if i < grid_size - 1 else h
        for j in range(grid_size):
            col_start = j * cell_w
            col_end = (j + 1) * cell_w if j < grid_size - 1 else w

            cell_rg = rg_map[row_start:row_end, col_start:col_end]
            cell_bg = bg_map[row_start:row_end, col_start:col_end]

            # Mean per-channel values in cell
            cell_r_mean = np.mean(r[row_start:row_end, col_start:col_end])
            cell_g_mean = np.mean(g[row_start:row_end, col_start:col_end])
            cell_b_mean = np.mean(b[row_start:row_end, col_start:col_end])

            cells.append({
                'row_idx': i,
                'col_idx': j,
                'row_range': (row_start, row_end),
                'col_range': (col_start, col_end),
                'r_mean': float(cell_r_mean),
                'g_mean': float(cell_g_mean),
                'b_mean': float(cell_b_mean),
                'rg_ratio': float(np.mean(cell_rg)),
                'bg_ratio': float(np.mean(cell_bg)),
            })

    # Compute edge vs center ratios
    # Left edge: columns 0, Center: column grid_size//2, Right edge: column grid_size-1
    left_cols = [c for c in cells if c['col_idx'] == 0]
    center_cols = [c for c in cells if c['col_idx'] == grid_size // 2]
    right_cols = [c for c in cells if c['col_idx'] == grid_size - 1]

    # Top row, center row, bottom row
    top_rows = [c for c in cells if c['row_idx'] == 0]
    center_rows = [c for c in cells if c['row_idx'] == grid_size // 2]
    bottom_rows = [c for c in cells if c['row_idx'] == grid_size - 1]

    spatial = {
        'left_edge': {
            'rg_mean': float(np.mean([c['rg_ratio'] for c in left_cols])),
            'bg_mean': float(np.mean([c['bg_ratio'] for c in left_cols])),
        },
        'center': {
            'rg_mean': float(np.mean([c['rg_ratio'] for c in center_cols])),
            'bg_mean': float(np.mean([c['bg_ratio'] for c in center_cols])),
        },
        'right_edge': {
            'rg_mean': float(np.mean([c['rg_ratio'] for c in right_cols])),
            'bg_mean': float(np.mean([c['bg_ratio'] for c in right_cols])),
        },
        'top_edge': {
            'rg_mean': float(np.mean([c['rg_ratio'] for c in top_rows])),
            'bg_mean': float(np.mean([c['bg_ratio'] for c in top_rows])),
        },
        'center_row': {
            'rg_mean': float(np.mean([c['rg_ratio'] for c in center_rows])),
            'bg_mean': float(np.mean([c['bg_ratio'] for c in center_rows])),
        },
        'bottom_edge': {
            'rg_mean': float(np.mean([c['rg_ratio'] for c in bottom_rows])),
            'bg_mean': float(np.mean([c['bg_ratio'] for c in bottom_rows])),
        },
    }

    return {
        'cells': cells,
        'spatial': spatial,
        'overall_rg_ratio': float(np.mean(rg_map)),
        'overall_bg_ratio': float(np.mean(bg_map)),
        'rg_std': float(np.std(rg_map)),
        'bg_std': float(np.std(bg_map)),
    }


def compute_rmse(test_arr, ref_arr):
    """Compute RMSE between test and reference arrays."""
    if test_arr.shape != ref_arr.shape:
        if test_arr.shape[0] == ref_arr.shape[1] and test_arr.shape[1] == ref_arr.shape[0]:
            ref_arr = np.transpose(ref_arr, (1, 0, 2))
        else:
            # Try to crop to common size
            min_h = min(test_arr.shape[0], ref_arr.shape[0])
            min_w = min(test_arr.shape[1], ref_arr.shape[1])
            test_arr = test_arr[:min_h, :min_w, :]
            ref_arr = ref_arr[:min_h, :min_w, :]

    diff = test_arr - ref_arr
    rmse = float(np.sqrt(np.mean(diff ** 2)))

    # Per-channel
    channels = {}
    ch_names = ['R', 'G', 'B']
    num_ch = min(test_arr.shape[2], ref_arr.shape[2], 3)
    for ci in range(num_ch):
        ch_diff = test_arr[:, :, ci] - ref_arr[:, :, ci]
        channels[ch_names[ci]] = {
            'rmse': float(np.sqrt(np.mean(ch_diff ** 2))),
            'mae': float(np.mean(np.abs(ch_diff))),
            'mean_error': float(np.mean(ch_diff)),
        }

    return {'rmse': rmse, 'channels': channels}


def print_grid_table(cells, grid_size):
    """Print a formatted table of R/G and B/G ratios."""
    print(f"\n{'='*80}")
    print(f"R/G RATIO GRID ({grid_size}x{grid_size})")
    print(f"{'='*80}")
    print("         ", end="")
    for j in range(grid_size):
        print(f"  Col {j:2d}  ", end="")
    print()
    for i in range(grid_size):
        print(f"Row {i:2d}: ", end="")
        for j in range(grid_size):
            cell = cells[i * grid_size + j]
            rg = cell['rg_ratio']
            if rg < 0.8:
                symbol = " --"
            elif rg < 0.9:
                symbol = " -"
            elif rg > 1.2:
                symbol = " ++"
            elif rg > 1.1:
                symbol = " +"
            else:
                symbol = "  "
            print(f"  {rg:.4f}{symbol}", end="")
        print()

    print(f"\n{'='*80}")
    print(f"B/G RATIO GRID ({grid_size}x{grid_size})")
    print(f"{'='*80}")
    print("         ", end="")
    for j in range(grid_size):
        print(f"  Col {j:2d}  ", end="")
    print()
    for i in range(grid_size):
        print(f"Row {i:2d}: ", end="")
        for j in range(grid_size):
            cell = cells[i * grid_size + j]
            bg = cell['bg_ratio']
            if bg < 0.8:
                symbol = " --"
            elif bg < 0.9:
                symbol = " -"
            elif bg > 1.2:
                symbol = " ++"
            elif bg > 1.1:
                symbol = " +"
            else:
                symbol = "  "
            print(f"  {bg:.4f}{symbol}", end="")
        print()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <test_tiff> [<reference_tiff>]")
        sys.exit(1)

    test_path = sys.argv[1]
    ref_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isfile(test_path):
        print(f"Error: Test TIFF not found: {test_path}")
        sys.exit(1)

    print(f"Test image: {test_path}")
    test_arr = load_tiff(test_path)
    print(f"  Shape: {test_arr.shape}, dtype: {test_arr.dtype}")

    # Compute grid ratios
    results = compute_grid_ratios(test_arr, grid_size=7)

    print(f"\nOverall Stats:")
    print(f"  Mean R/G ratio: {results['overall_rg_ratio']:.4f} (std={results['rg_std']:.4f})")
    print(f"  Mean B/G ratio: {results['overall_bg_ratio']:.4f} (std={results['bg_std']:.4f})")

    # Print grid tables
    print_grid_table(results['cells'], grid_size=7)

    # Spatial comparison
    print(f"\n{'='*80}")
    print(f"SPATIAL RATIO COMPARISON (Left vs Center vs Right)")
    print(f"{'='*80}")
    sp = results['spatial']
    print(f"  {'Location':<20s} {'R/G Ratio':>10s} {'B/G Ratio':>10s}")
    print(f"  {'-'*40}")
    for loc in ['left_edge', 'center', 'right_edge']:
        print(f"  {loc:<20s} {sp[loc]['rg_mean']:>10.4f} {sp[loc]['bg_mean']:>10.4f}")

    # Compute left-to-right drift
    rg_lr_drift = sp['right_edge']['rg_mean'] - sp['left_edge']['rg_mean']
    bg_lr_drift = sp['right_edge']['bg_mean'] - sp['left_edge']['bg_mean']
    print(f"\n  Left-to-Right Drift:")
    print(f"    R/G delta: {rg_lr_drift:+.4f}")
    print(f"    B/G delta: {bg_lr_drift:+.4f}")

    # Top-to-bottom drift
    rg_tb_drift = sp['bottom_edge']['bg_mean'] - sp['top_edge']['bg_mean']
    bg_tb_drift = sp['bottom_edge']['bg_mean'] - sp['top_edge']['bg_mean']
    print(f"  Top-to-Bottom Drift:")
    print(f"    R/G delta: {rg_tb_drift:+.4f}")
    print(f"    B/G delta: {bg_tb_drift:+.4f}")

    # RMSE against reference
    if ref_path:
        if not os.path.isfile(ref_path):
            print(f"\nError: Reference TIFF not found: {ref_path}")
        else:
            print(f"\nReference image: {ref_path}")
            ref_arr = load_tiff(ref_path)
            print(f"  Shape: {ref_arr.shape}")

            rmse_results = compute_rmse(test_arr, ref_arr)
            print(f"\n{'='*80}")
            print(f"RMSE vs Reference")
            print(f"{'='*80}")
            print(f"  Overall RMSE: {rmse_results['rmse']:.4f}")
            print(f"  Per-Channel:")
            for ch_name, ch_data in rmse_results['channels'].items():
                print(f"    {ch_name}: RMSE={ch_data['rmse']:.4f}, MAE={ch_data['mae']:.4f}, MeanErr={ch_data['mean_error']:.4f}")


if __name__ == '__main__':
    main()
