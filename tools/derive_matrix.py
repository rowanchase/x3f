#!/usr/bin/env python3
"""
Derive optimal 3x3 color matrix from X3F raw data and SPP reference TIFFs.

This script:
1. Loads raw X3F sensor data (before color conversion)
2. Loads corresponding SPP reference TIFF
3. Solves for optimal matrix coefficients using least-squares
4. Outputs the derived matrix and test results
"""

import numpy as np
import subprocess
import tempfile
import os
from PIL import Image
import struct

def extract_raw_data(x3f_file, x3f_extract_bin="./bin/linux-x86_64/x3f_extract"):
    """
    Extract raw sensor data from X3F file before color matrix application.
    Returns raw RGB data as numpy array (height, width, 3).
    """
    # For now, we'll use the intermediate DNG output and extract raw values
    # The DNG contains the raw sensor data before color conversion
    dng_file = x3f_file + ".dng"
    
    # Extract DNG if it doesn't exist
    if not os.path.exists(dng_file):
        subprocess.run([
            x3f_extract_bin,
            "-dng",
            x3f_file
        ], capture_output=True)
    
    # Read DNG file to get raw data
    # DNG is essentially TIFF with raw sensor data
    try:
        import rawpy
        with rawpy.imread(dng_file) as raw:
            # Get raw sensor data (before demosaicing/color conversion)
            raw_data = raw.raw_image  # This is the Bayer pattern or Foveon raw
            # For Foveon, we need to extract the 3-layer data
            # Foveon has 3 color channels at each pixel
            print(f"Raw data shape: {raw_data.shape}")
            print(f"Raw data dtype: {raw_data.dtype}")
            return raw_data
    except ImportError:
        print("rawpy not available, trying alternative approach...")
        # Fallback: use dcraw or other tool
        return None

def load_tiff_reference(tiff_file):
    """Load SPP reference TIFF as numpy array (normalized to 0-1)."""
    img = Image.open(tiff_file)
    # Convert to numpy array
    ref_data = np.array(img).astype(np.float64)
    # Normalize to 0-1 range
    if ref_data.max() > 1.0:
        ref_data = ref_data / 255.0
    return ref_data

def solve_color_matrix(raw_data, ref_data, sample_stride=100):
    """
    Solve for optimal 3x3 color matrix using least-squares.
    
    Matrix equation: RGB_output = Matrix * RGB_raw
    
    We want to find M that minimizes: ||M * raw - ref||^2
    
    Solving: M = ref * raw^T * (raw * raw^T)^-1
    """
    # Subsample pixels to speed up computation (stride every N pixels)
    h, w = raw_data.shape[:2]
    
    # Sample pixels uniformly
    y_indices = np.arange(0, h, sample_stride)
    x_indices = np.arange(0, w, sample_stride)
    
    # Extract sampled pixels
    raw_samples = []
    ref_samples = []
    
    for y in y_indices:
        for x in x_indices:
            if y < raw_data.shape[0] and x < raw_data.shape[1]:
                # Get raw pixel (3 channels)
                raw_pixel = raw_data[y, x]
                # Get reference pixel
                ref_pixel = ref_data[y, x]
                
                raw_samples.append(raw_pixel)
                ref_samples.append(ref_pixel)
    
    raw_samples = np.array(raw_samples)  # Shape: (N, 3)
    ref_samples = np.array(ref_samples)  # Shape: (N, 3)
    
    print(f"Sampled {len(raw_samples)} pixels")
    print(f"Raw samples range: [{raw_samples.min():.2f}, {raw_samples.max():.2f}]")
    print(f"Ref samples range: [{ref_samples.min():.2f}, {ref_samples.max():.2f}]")
    
    # Solve for matrix using least-squares
    # We want: ref ≈ raw @ M.T
    # M = (raw^T @ raw)^-1 @ raw^T @ ref
    
    try:
        # Method 1: Direct least-squares solution
        M, residuals, rank, s = np.linalg.lstsq(raw_samples, ref_samples, rcond=None)
        
        print(f"\nDerived Matrix (each row = output channel):")
        print(f"  Red output:   [{M[0,0]:7.4f}, {M[0,1]:7.4f}, {M[0,2]:7.4f}]")
        print(f"  Green output: [{M[1,0]:7.4f}, {M[1,1]:7.4f}, {M[1,2]:7.4f}]")
        print(f"  Blue output:  [{M[2,0]:7.4f}, {M[2,1]:7.4f}, {M[2,2]:7.4f}]")
        
        # Calculate error
        predicted = raw_samples @ M
        mae = np.mean(np.abs(predicted - ref_samples))
        rmse = np.sqrt(np.mean((predicted - ref_samples)**2))
        
        print(f"\nFit Quality:")
        print(f"  MAE:  {mae:.4f}")
        print(f"  RMSE: {rmse:.4f}")
        
        return M.T  # Transpose to match expected format
        
    except Exception as e:
        print(f"Error solving matrix: {e}")
        return None

def test_matrix(x3f_file, ref_tiff, matrix, x3f_extract_bin="./bin/linux-x86_64/x3f_extract"):
    """
    Test the derived matrix by extracting X3F with new matrix and comparing.
    This requires modifying the C code temporarily.
    """
    print(f"\n--- Testing derived matrix ---")
    print(f"Matrix to apply:")
    print(matrix)
    
    # For now, just calculate theoretical performance
    # Full implementation would require rebuilding with new matrix
    print("(Full testing requires code rebuild - showing theoretical fit only)")

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Derive optimal color matrix from X3F/SPP pairs')
    parser.add_argument('x3f_file', help='Input X3F file')
    parser.add_argument('ref_tiff', help='Reference SPP TIFF file')
    parser.add_argument('--x3f-extract', default='./bin/linux-x86_64/x3f_extract',
                        help='Path to x3f_extract binary')
    parser.add_argument('--sample-stride', type=int, default=100,
                        help='Pixel sampling stride (higher = faster but less accurate)')
    
    args = parser.parse_args()
    
    print("="*60)
    print("Color Matrix Derivation Tool")
    print("="*60)
    print(f"X3F:  {args.x3f_file}")
    print(f"TIFF: {args.ref_tiff}")
    print(f"Sampling stride: {args.sample_stride}")
    print()
    
    # Extract raw data
    print("Extracting raw sensor data...")
    raw_data = extract_raw_data(args.x3f_file, args.x3f_extract)
    
    if raw_data is None:
        print("ERROR: Could not extract raw data")
        return 1
    
    # Load reference
    print("Loading reference TIFF...")
    ref_data = load_tiff_reference(args.ref_tiff)
    
    print(f"Raw data shape: {raw_data.shape}")
    print(f"Ref data shape: {ref_data.shape}")
    
    # Check dimensions match
    if raw_data.shape[:2] != ref_data.shape[:2]:
        print(f"WARNING: Dimension mismatch! Raw: {raw_data.shape}, Ref: {ref_data.shape}")
        print("Resizing reference to match raw...")
        from scipy.ndimage import zoom
        zoom_y = raw_data.shape[0] / ref_data.shape[0]
        zoom_x = raw_data.shape[1] / ref_data.shape[1]
        ref_data = zoom(ref_data, (zoom_y, zoom_x, 1), order=1)
    
    # Solve for matrix
    print("\nSolving for optimal color matrix...")
    matrix = solve_color_matrix(raw_data, ref_data, args.sample_stride)
    
    if matrix is not None:
        # Test the matrix
        test_matrix(args.x3f_file, args.ref_tiff, matrix, args.x3f_extract)
        
        # Output in C format
        print("\n" + "="*60)
        print("C Code Format:")
        print("="*60)
        print("double derived_matrix[9] = {")
        print(f"  {matrix[0,0]:8.5f}, {matrix[0,1]:8.5f}, {matrix[0,2]:8.5f},  /* Red */")
        print(f"  {matrix[1,0]:8.5f}, {matrix[1,1]:8.5f}, {matrix[1,2]:8.5f},  /* Green */")
        print(f"  {matrix[2,0]:8.5f}, {matrix[2,1]:8.5f}, {matrix[2,2]:8.5f}   /* Blue */")
        print("};")
        
        return 0
    else:
        print("Failed to derive matrix")
        return 1

if __name__ == "__main__":
    exit(main())
