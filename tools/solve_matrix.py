#!/usr/bin/env python3
"""
Proper matrix solver using least-squares optimization on all reference images.

This script:
1. Uses x3f_extract to generate output TIFFs with current matrix
2. Compares against SPP reference TIFFs
3. Solves for optimal 3x3 matrix using least-squares
4. Outputs the derived matrix in C format

Usage: python3 tools/solve_matrix.py
"""

import numpy as np
from PIL import Image
import subprocess
import os
import tempfile
import glob

def load_tiff_as_array(tiff_path):
    """Load TIFF and return as normalized numpy array (0-1 range)."""
    img = Image.open(tiff_path)
    arr = np.array(img).astype(np.float64)
    # Normalize to 0-1
    if arr.max() > 1.0:
        arr = arr / 255.0
    return arr

def compare_images(output_arr, ref_arr, sample_stride=50):
    """
    Compare two images and return error metrics.
    Returns: (output_samples, ref_samples) for matrix solving.
    """
    h, w = output_arr.shape[:2]
    
    # Sample pixels uniformly
    samples = []
    for y in range(0, h, sample_stride):
        for x in range(0, w, sample_stride):
            if y < h and x < w:
                samples.append((y, x))
    
    output_samples = np.array([output_arr[y, x] for y, x in samples])
    ref_samples = np.array([ref_arr[y, x] for y, x in samples])
    
    return output_samples, ref_samples

def solve_optimal_matrix(all_output, all_ref):
    """
    Solve for optimal 3x3 matrix using least-squares.
    
    We want: ref ≈ output @ M
    So: M = (output^T @ output)^-1 @ output^T @ ref
    
    But we want to solve for the matrix that converts raw to RGB.
    Since our current matrix is wrong, we need to find the correction.
    
    Alternative approach: Treat this as a linear system where we want
    to find matrix M such that: raw @ M = ref
    
    But we don't have raw... we have output (which is raw @ current_matrix).
    
    So: ref ≈ raw @ optimal_M
        output = raw @ current_M
        
    Therefore: ref ≈ output @ (current_M^-1 @ optimal_M)
    
    Or we can think of it as: we need to find a correction matrix C such that:
        ref ≈ output @ C
        where optimal_M = current_M @ C
    """
    print(f"\nSolving for optimal matrix...")
    print(f"  Total samples: {len(all_output)}")
    print(f"  Output range: [{all_output.min():.4f}, {all_output.max():.4f}]")
    print(f"  Ref range: [{all_ref.min():.4f}, {all_ref.max():.4f}]")
    
    # Method: Find correction matrix C such that ref ≈ output @ C
    # This gives us: C = (output^T @ output)^-1 @ output^T @ ref
    
    try:
        # Solve using least-squares
        C, residuals, rank, s = np.linalg.lstsq(all_output, all_ref, rcond=None)
        
        print(f"\nCorrection Matrix C (ref ≈ output @ C):")
        print(f"  R: [{C[0,0]:8.4f}, {C[0,1]:8.4f}, {C[0,2]:8.4f}]")
        print(f"  G: [{C[1,0]:8.4f}, {C[1,1]:8.4f}, {C[1,2]:8.4f}]")
        print(f"  B: [{C[2,0]:8.4f}, {C[2,1]:8.4f}, {C[2,2]:8.4f}]")
        
        # Calculate fit quality
        predicted = all_output @ C
        mae = np.mean(np.abs(predicted - all_ref))
        rmse = np.sqrt(np.mean((predicted - all_ref)**2))
        
        print(f"\nFit Quality:")
        print(f"  MAE:  {mae:.4f}")
        print(f"  RMSE: {rmse:.4f}")
        
        return C.T  # Transpose to match expected format
        
    except Exception as e:
        print(f"Error solving: {e}")
        return None

def main():
    print("="*70)
    print("Matrix Solver - Least-Squares Optimization")
    print("="*70)
    
    # Find all X3F files with corresponding TIFF references
    x3f_files = sorted(glob.glob("reference_files/X3Fs/_P2M*.X3F"))
    
    print(f"\nFound {len(x3f_files)} X3F files")
    
    all_output_samples = []
    all_ref_samples = []
    
    for i, x3f_file in enumerate(x3f_files, 1):
        # Derive reference TIFF path
        basename = os.path.basename(x3f_file).replace('.X3F', '.tif')
        ref_tiff = f"reference_files/TIFFs/{basename}"
        
        if not os.path.exists(ref_tiff):
            print(f"  [{i}/{len(x3f_files)}] SKIP: {basename} (no reference)")
            continue
        
        print(f"  [{i}/{len(x3f_files)}] Processing {basename}...")
        
        # Extract X3F
        output_tiff = x3f_file + ".tif"
        if not os.path.exists(output_tiff):
            result = subprocess.run(
                ["./bin/linux-x86_64/x3f_extract", x3f_file],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"    ERROR: Extraction failed")
                continue
        
        # Load both images
        try:
            output_arr = load_tiff_as_array(output_tiff)
            ref_arr = load_tiff_as_array(ref_tiff)
            
            # Sample pixels
            out_samp, ref_samp = compare_images(output_arr, ref_arr, sample_stride=100)
            
            all_output_samples.extend(out_samp)
            all_ref_samples.extend(ref_samp)
            
            print(f"    Samples: {len(out_samp)}, Output mean: {out_samp.mean():.3f}, Ref mean: {ref_samp.mean():.3f}")
            
        except Exception as e:
            print(f"    ERROR: {e}")
            continue
    
    if len(all_output_samples) == 0:
        print("\nERROR: No valid samples collected")
        return 1
    
    # Convert to numpy arrays
    all_output = np.array(all_output_samples)
    all_ref = np.array(all_ref_samples)
    
    print(f"\n{'='*70}")
    print(f"Total samples collected: {len(all_output)}")
    print(f"{'='*70}")
    
    # Solve for optimal matrix
    matrix = solve_optimal_matrix(all_output, all_ref)
    
    if matrix is not None:
        print(f"\n{'='*70}")
        print("C CODE FORMAT")
        print(f"{'='*70}")
        print("double derived_matrix[9] = {")
        print(f"  {matrix[0,0]:10.6f}, {matrix[0,1]:10.6f}, {matrix[0,2]:10.6f},  /* Red */")
        print(f"  {matrix[1,0]:10.6f}, {matrix[1,1]:10.6f}, {matrix[1,2]:10.6f},  /* Green */")
        print(f"  {matrix[2,0]:10.6f}, {matrix[2,1]:10.6f}, {matrix[2,2]:10.6f}   /* Blue */")
        print("};")
        
        # Save to file
        with open("solved_matrix.c", 'w') as f:
            f.write("/* Auto-solved color matrix from SPP references */\n")
            f.write("/* Generated using least-squares optimization */\n\n")
            f.write("double solved_matrix[9] = {\n")
            f.write(f"  {matrix[0,0]:10.6f}, {matrix[0,1]:10.6f}, {matrix[0,2]:10.6f},  /* Red output */\n")
            f.write(f"  {matrix[1,0]:10.6f}, {matrix[1,1]:10.6f}, {matrix[1,2]:10.6f},  /* Green output */\n")
            f.write(f"  {matrix[2,0]:10.6f}, {matrix[2,1]:10.6f}, {matrix[2,2]:10.6f}   /* Blue output */\n")
            f.write("};\n")
        
        print(f"\nMatrix saved to: solved_matrix.c")
        
        return 0
    
    return 1

if __name__ == "__main__":
    exit(main())
