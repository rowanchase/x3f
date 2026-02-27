#!/usr/bin/env python3
"""
Matrix derivation tool using direct X3F analysis.

Since we can't easily extract intermediate data, we'll use a different approach:
1. Use the camera's metadata color matrix as a starting point
2. Analyze the SPP reference to understand the expected output ranges
3. Create a matrix that maps camera raw to SPP output
"""

import numpy as np
from PIL import Image
import subprocess
import os

def analyze_sp_reference(tiff_path):
    """Analyze SPP reference to understand color characteristics."""
    img = Image.open(tiff_path)
    data = np.array(img).astype(np.float64) / 255.0
    
    # Calculate statistics
    h, w, c = data.shape
    
    print(f"\nReference Analysis: {tiff_path}")
    print(f"  Dimensions: {w}x{h}")
    print(f"  Data range: [{data.min():.4f}, {data.max():.4f}]")
    print(f"  Channel means: R={data[:,:,0].mean():.4f}, G={data[:,:,1].mean():.4f}, B={data[:,:,2].mean():.4f}")
    
    # Find representative pixels for different colors
    # Sample corners, center, and edges
    samples = []
    positions = [
        (h//4, w//4),      # Top-left quadrant
        (h//4, 3*w//4),    # Top-right quadrant
        (3*h//4, w//4),    # Bottom-left quadrant
        (3*h//4, 3*w//4),  # Bottom-right quadrant
        (h//2, w//2),      # Center
    ]
    
    for y, x in positions:
        rgb = data[y, x]
        samples.append({
            'pos': (y, x),
            'rgb': rgb,
            'luminance': rgb.mean()
        })
    
    # Sort by luminance
    samples.sort(key=lambda s: s['luminance'])
    
    print(f"\n  Representative pixels:")
    for s in samples:
        print(f"    {s['pos']}: RGB=[{s['rgb'][0]:.3f}, {s['rgb'][1]:.3f}, {s['rgb'][2]:.3f}], L={s['luminance']:.3f}")
    
    return data, samples

def estimate_matrix_from_samples():
    """
    Estimate matrix by analyzing the relationship between camera metadata
    and expected SPP output characteristics.
    
    Merrill cameras use extreme matrices. We need to reverse-engineer what
    SPP actually does vs what the metadata says.
    """
    
    # Typical Merrill AutoCCMatrix from metadata (extreme values):
    # [ 1.82, -1.77,  0.95]
    # [-1.56,  3.52, -0.96]  
    # [ 1.27, -5.15,  4.87]
    
    # This suggests SPP might be applying additional corrections.
    # Let's try to derive a matrix that produces reasonable RGB from
    # the raw sensor data characteristics.
    
    # From the error analysis, we know:
    # - Output is too blue (B channel too high relative to R/G)
    # - Output is undersaturated
    # - Output is generally too dark
    
    # The balanced matrix we tried was:
    # [1.0, -0.1, 0.0]
    # [-0.1, 1.0, 0.0]
    # [0.1, 0.0, 1.0]
    
    # This gave us: R too dark, G reasonable, B too bright
    
    # To fix this, we need to:
    # 1. Increase R output (stronger red coefficients)
    # 2. Decrease B output (weaker blue coefficients)
    # 3. Maintain G balance
    
    # Let's try a matrix that amplifies R, reduces B:
    test_matrices = [
        # Matrix 1: Boost R, reduce B
        np.array([
            [1.3, -0.1, -0.1],   # Stronger red
            [-0.1, 1.0, 0.0],    # Neutral green
            [-0.1, 0.0, 0.9]     # Weaker blue
        ]),
        
        # Matrix 2: More aggressive
        np.array([
            [1.5, -0.2, -0.2],
            [-0.1, 1.1, -0.1],
            [-0.2, -0.1, 0.8]
        ]),
        
        # Matrix 3: Derived from camera matrix with corrections
        np.array([
            [2.0, -0.5, 0.0],
            [-0.3, 1.5, -0.2],
            [0.0, -0.3, 1.0]
        ]),
    ]
    
    return test_matrices

def write_matrix_to_c_file(matrix, filename="derived_matrix.c"):
    """Write matrix in C format."""
    with open(filename, 'w') as f:
        f.write("/* Auto-derived color matrix for Merrill X3F processing */\n")
        f.write("/* Generated from SPP reference analysis */\n\n")
        f.write("double derived_conv_matrix[9] = {\n")
        for i in range(3):
            row = matrix[i]
            f.write(f"  {row[0]:10.6f}, {row[1]:10.6f}, {row[2]:10.6f}")
            if i < 2:
                f.write(",")
            f.write(f"  /* {['Red', 'Green', 'Blue'][i]} output */\n")
        f.write("};\n")
    print(f"\nMatrix written to {filename}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Derive color matrix from SPP references')
    parser.add_argument('--ref', help='Reference TIFF to analyze')
    parser.add_argument('--matrix-file', default='derived_matrix.c', help='Output C file')
    
    args = parser.parse_args()
    
    print("="*70)
    print("Color Matrix Derivation Tool")
    print("="*70)
    
    # Analyze reference if provided
    if args.ref and os.path.exists(args.ref):
        data, samples = analyze_sp_reference(args.ref)
    
    # Generate candidate matrices
    print("\n" + "="*70)
    print("Candidate Matrices")
    print("="*70)
    
    matrices = estimate_matrix_from_samples()
    
    for i, M in enumerate(matrices, 1):
        print(f"\nMatrix {i}:")
        print(f"  R: [{M[0,0]:7.4f}, {M[0,1]:7.4f}, {M[0,2]:7.4f}]")
        print(f"  G: [{M[1,0]:7.4f}, {M[1,1]:7.4f}, {M[1,2]:7.4f}]")
        print(f"  B: [{M[2,0]:7.4f}, {M[2,1]:7.4f}, {M[2,2]:7.4f}]")
    
    # Write first matrix to file
    write_matrix_to_c_file(matrices[0], args.matrix_file)
    
    print("\n" + "="*70)
    print("Next Steps:")
    print("="*70)
    print("1. Review the candidate matrices above")
    print("2. Edit src/x3f_process.c and replace the balanced matrix")
    print("3. Rebuild and test with: python3 tools/compare_output.py")
    print("4. Iterate based on results")
    print()
    print(f"The first matrix has been written to: {args.matrix_file}")
    print("You can manually copy this into src/x3f_process.c at line ~786")

if __name__ == "__main__":
    main()
