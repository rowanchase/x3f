#!/usr/bin/env python3
"""
Analyze 7x7 grid RGB means and compute spatial color correction factors.

Compares x3f_extract output against SPP reference to derive per-cell
correction multipliers needed to match SPP color balance.
"""

import argparse
import sys
import os
import numpy as np
from PIL import Image


DEFAULT_GRID_ROWS = 7
DEFAULT_GRID_COLS = 7
DEFAULT_DARK_THRESHOLD = 10


def load_tiff(filepath):
    """Load TIFF and return numpy array with bit depth info."""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    
    img = Image.open(filepath)
    width, height = img.size
    bands = len(img.getbands())
    
    if bands != 3:
        print(f"Error: Expected 3-channel RGB image, got {bands} channels", file=sys.stderr)
        sys.exit(1)
    
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


def analyze_cell(data, y_start, y_end, x_start, x_end, dark_threshold):
    """Analyze a single cell and return mean RGB values."""
    cell = data[y_start:y_end, x_start:x_end]
    
    # Calculate mean per channel, excluding dark pixels
    r = cell[:, :, 0].astype(np.float64)
    g = cell[:, :, 1].astype(np.float64)
    b = cell[:, :, 2].astype(np.float64)
    
    # Create mask for valid (non-dark) pixels
    brightness = (r + g + b) / 3.0
    valid_mask = brightness > dark_threshold
    
    valid_count = np.sum(valid_mask)
    total_count = r.size
    
    if valid_count == 0:
        return {
            'mean_r': np.mean(r),
            'mean_g': np.mean(g),
            'mean_b': np.mean(b),
            'std_r': 0,
            'std_g': 0,
            'std_b': 0,
            'valid_count': 0,
            'total_count': total_count,
            'is_valid': False,
            'suspicious': False
        }
    
    # Compute means and stds over valid pixels only
    mean_r = np.mean(r[valid_mask])
    mean_g = np.mean(g[valid_mask])
    mean_b = np.mean(b[valid_mask])
    
    std_r = np.std(r[valid_mask])
    std_g = np.std(g[valid_mask])
    std_b = np.std(b[valid_mask])
    
    # Flag suspicious if high variance or low sample count
    high_variance = (std_r > 50 or std_g > 50 or std_b > 50)
    low_sample_ratio = valid_count / total_count < 0.1
    
    is_valid = mean_r > dark_threshold or mean_g > dark_threshold or mean_b > dark_threshold
    
    return {
        'mean_r': mean_r,
        'mean_g': mean_g,
        'mean_b': mean_b,
        'std_r': std_r,
        'std_g': std_g,
        'std_b': std_b,
        'valid_count': valid_count,
        'total_count': total_count,
        'is_valid': is_valid,
        'suspicious': high_variance or low_sample_ratio
    }


def analyze_grid(data, grid_rows, grid_cols, dark_threshold):
    """
    Analyze image using a grid and compute mean RGB values per cell.
    Returns 2D list of cell results.
    """
    h, w = data.shape[:2]
    
    # Calculate cell dimensions (crop to fit exact grid)
    cell_h = h // grid_rows
    cell_w = w // grid_cols
    
    results = []
    for row in range(grid_rows):
        row_results = []
        for col in range(grid_cols):
            y_start = row * cell_h
            y_end = (row + 1) * cell_h if row < grid_rows - 1 else h
            x_start = col * cell_w
            x_end = (col + 1) * cell_w if col < grid_cols - 1 else w
            
            cell_result = analyze_cell(data, y_start, y_end, x_start, x_end, dark_threshold)
            cell_result['row'] = row
            cell_result['col'] = col
            row_results.append(cell_result)
        results.append(row_results)
    
    return results


def compute_corrections(x3f_results, spp_results, grid_rows, grid_cols):
    """Compute correction factors needed to make x3f match SPP."""
    corrections = []
    
    for row in range(grid_rows):
        for col in range(grid_cols):
            x3f = x3f_results[row][col]
            spp = spp_results[row][col]
            
            # Calculate correction factors
            if x3f['mean_r'] > 0:
                corr_r = spp['mean_r'] / x3f['mean_r']
            else:
                corr_r = 1.0
                
            if x3f['mean_g'] > 0:
                corr_g = spp['mean_g'] / x3f['mean_g']
            else:
                corr_g = 1.0
                
            if x3f['mean_b'] > 0:
                corr_b = spp['mean_b'] / x3f['mean_b']
            else:
                corr_b = 1.0
            
            # Flag suspicious corrections
            suspicious = False
            if corr_r < 0.5 or corr_r > 2.0 or \
               corr_g < 0.5 or corr_g > 2.0 or \
               corr_b < 0.5 or corr_b > 2.0:
                suspicious = True
            
            # Flag if x3f cell was invalid
            if not x3f['is_valid']:
                suspicious = True
            
            corrections.append({
                'row': row,
                'col': col,
                'corr_r': corr_r,
                'corr_g': corr_g,
                'corr_b': corr_b,
                'x3f_r': x3f['mean_r'],
                'x3f_g': x3f['mean_g'],
                'x3f_b': x3f['mean_b'],
                'spp_r': spp['mean_r'],
                'spp_g': spp['mean_g'],
                'spp_b': spp['mean_b'],
                'suspicious': suspicious
            })
    
    return corrections


def compute_rmse(x3f_results, spp_results, grid_rows, grid_cols):
    """Compute RMSE between x3f and SPP per channel."""
    errors_r = []
    errors_g = []
    errors_b = []
    
    for row in range(grid_rows):
        for col in range(grid_cols):
            x3f = x3f_results[row][col]
            spp = spp_results[row][col]
            
            if x3f['is_valid']:
                errors_r.append(x3f['mean_r'] - spp['mean_r'])
                errors_g.append(x3f['mean_g'] - spp['mean_g'])
                errors_b.append(x3f['mean_b'] - spp['mean_b'])
    
    rmse_r = np.sqrt(np.mean([e**2 for e in errors_r])) if errors_r else 0
    rmse_g = np.sqrt(np.mean([e**2 for e in errors_g])) if errors_g else 0
    rmse_b = np.sqrt(np.mean([e**2 for e in errors_b])) if errors_b else 0
    
    return rmse_r, rmse_g, rmse_b


def print_grid_means(x3f_results, spp_results, grid_rows, grid_cols, title, bit_depth):
    """Print grid means in a formatted table."""
    max_val = 255 if bit_depth == 8 else 65535
    
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")
    print(f"\n{'Cell':>8} | {'R':>10} | {'G':>10} | {'B':>10} | {'R%':>8} | {'G%':>8} | {'B%':>8}")
    print("-" * 70)
    
    for row in range(grid_rows):
        print(f"\nRow {row}:")
        for col in range(grid_cols):
            cell = x3f_results[row][col]
            status = "" if cell['is_valid'] else "[DARK]"
            susp = " [!]" if cell['suspicious'] else ""
            print(f"  Col {col}{status}{susp} | "
                  f"{cell['mean_r']:>10.1f} | {cell['mean_g']:>10.1f} | {cell['mean_b']:>10.1f} | "
                  f"{100*cell['mean_r']/max_val:>7.1f}% | {100*cell['mean_g']/max_val:>7.1f}% | {100*cell['mean_b']/max_val:>7.1f}%")


def print_corrections(corrections, grid_rows, grid_cols):
    """Print correction factors in a formatted table."""
    print(f"\n{'='*80}")
    print("Correction Factors (SPP / x3f_extract)")
    print(f"{'='*80}")
    
    print(f"\n{'Cell':>8} | {'R_mult':>10} | {'G_mult':>10} | {'B_mult':>10}")
    print("-" * 55)
    
    for row in range(grid_rows):
        print(f"\nRow {row}:")
        for col in range(grid_cols):
            c = corrections[row * grid_cols + col]
            susp = " [!]" if c['suspicious'] else ""
            print(f"  Col {col}{susp} | "
                  f"{c['corr_r']:>10.6f} | {c['corr_g']:>10.6f} | {c['corr_b']:>10.6f}")


def print_c_array(corrections, grid_rows, grid_cols):
    """Print correction table in C array format."""
    print(f"\n{'='*80}")
    print("C Array Format")
    print(f"{'='*80}")
    print()
    print("static const double merrill_color_correction_table[MERRILL_COLOR_GRID_ROWS][MERRILL_COLOR_GRID_COLS][MERRILL_COLOR_CHANNELS] = {")
    
    for row in range(grid_rows):
        print(f"    /* Row {row} */ {{")
        for col in range(grid_cols):
            c = corrections[row * grid_cols + col]
            comma = "," if col < grid_cols - 1 else ""
            print(f"        {{{c['corr_r']:.6f}, {c['corr_g']:.6f}, {c['corr_b']:.6f}}}{comma}")
        if row < grid_rows - 1:
            print("    },")
        else:
            print("    }")
    
    print("};")


def print_summary(x3f_results, spp_results, corrections, grid_rows, grid_cols, bit_depth):
    """Print summary of analysis."""
    rmse_r, rmse_g, rmse_b = compute_rmse(x3f_results, spp_results, grid_rows, grid_cols)
    
    # Calculate overall means
    total_x3f_r = np.mean([[c['mean_r'] for c in row] for row in x3f_results])
    total_x3f_g = np.mean([[c['mean_g'] for c in row] for row in x3f_results])
    total_x3f_b = np.mean([[c['mean_b'] for c in row] for row in x3f_results])
    
    total_spp_r = np.mean([[c['mean_r'] for c in row] for row in spp_results])
    total_spp_g = np.mean([[c['mean_g'] for c in row] for row in spp_results])
    total_spp_b = np.mean([[c['mean_b'] for c in row] for row in spp_results])
    
    suspicious_count = sum(1 for c in corrections if c['suspicious'])
    
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"\nOverall Means:")
    print(f"  x3f_extract: R={total_x3f_r:.1f}, G={total_x3f_g:.1f}, B={total_x3f_b:.1f}")
    print(f"  SPP:         R={total_spp_r:.1f}, G={total_spp_g:.1f}, B={total_spp_b:.1f}")
    print(f"\nRMSE (error per channel):")
    print(f"  R: {rmse_r:.2f}")
    print(f"  G: {rmse_g:.2f}")
    print(f"  B: {rmse_b:.2f}")
    print(f"\nSuspicious cells: {suspicious_count}/{grid_rows * grid_cols}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze 7x7 grid RGB means and compute spatial color correction factors'
    )
    parser.add_argument('x3f_tiff', help='x3f_extract output TIFF')
    parser.add_argument('spp_tiff', help='SPP reference TIFF')
    parser.add_argument('--grid-rows', '-r', type=int, default=DEFAULT_GRID_ROWS,
                       help=f'Number of grid rows (default: {DEFAULT_GRID_ROWS})')
    parser.add_argument('--grid-cols', '-c', type=int, default=DEFAULT_GRID_COLS,
                       help=f'Number of grid columns (default: {DEFAULT_GRID_COLS})')
    parser.add_argument('--dark-threshold', '-t', type=int, default=DEFAULT_DARK_THRESHOLD,
                       help=f'Exclude pixels below this brightness from mean (default: {DEFAULT_DARK_THRESHOLD})')
    
    args = parser.parse_args()
    
    print(f"Loading x3f_extract output: {args.x3f_tiff}")
    x3f_data, x3f_depth = load_tiff(args.x3f_tiff)
    
    print(f"Loading SPP reference: {args.spp_tiff}")
    spp_data, spp_depth = load_tiff(args.spp_tiff)
    
    # Check dimensions match
    if x3f_data.shape != spp_data.shape:
        print(f"Error: Image dimensions don't match!")
        print(f"  x3f_extract: {x3f_data.shape}")
        print(f"  SPP: {spp_data.shape}")
        sys.exit(1)
    
    h, w = x3f_data.shape[:2]
    print(f"\nImage: {w}x{h}, x3f={x3f_depth}-bit, spp={spp_depth}-bit")
    print(f"Grid: {args.grid_rows}x{args.grid_cols} (cell size: {w//args.grid_cols}x{h//args.grid_rows})")
    print(f"Dark threshold: {args.dark_threshold}")
    
    # Analyze both images
    print(f"\nAnalyzing grid...")
    x3f_results = analyze_grid(x3f_data, args.grid_rows, args.grid_cols, args.dark_threshold)
    spp_results = analyze_grid(spp_data, args.grid_rows, args.grid_cols, args.dark_threshold)
    
    # Compute corrections
    corrections = compute_corrections(x3f_results, spp_results, args.grid_rows, args.grid_cols)
    
    # Print results
    print_grid_means(x3f_results, spp_results, args.grid_rows, args.grid_cols, 
                    "x3f_extract Grid Means", x3f_depth)
    print_grid_means(spp_results, spp_results, args.grid_rows, args.grid_cols,
                    "SPP Reference Grid Means", spp_depth)
    print_corrections(corrections, args.grid_rows, args.grid_cols)
    print_c_array(corrections, args.grid_rows, args.grid_cols)
    print_summary(x3f_results, spp_results, corrections, args.grid_rows, args.grid_cols, x3f_depth)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
