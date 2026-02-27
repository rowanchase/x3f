#!/usr/bin/env python3
"""Analyze TIFF output from x3f_extract with detailed analysis"""

import numpy as np
from PIL import Image
import sys

def analyze_tiff(tiff_path):
    """Analyze a 16-bit TIFF file"""
    img = Image.open(tiff_path)
    data = np.array(img)
    
    print(f"Image shape: {data.shape}")
    print(f"Data dtype: {data.dtype}")
    print(f"Data range: {data.min()} - {data.max()}")
    
    # Show unique values
    unique_vals = np.unique(data)
    print(f"\nUnique values (first 20): {unique_vals[:20]}")
    print(f"Total unique values: {len(unique_vals)}")
    
    # Check for all zeros
    if data.max() == 0:
        print("\nWARNING: All pixel values are 0!")
        return
    
    # Convert to 0-255 range for histogram bins
    data_8bit = (data / 257).astype(np.uint8)
    
    channels = ['R', 'G', 'B']
    for i, ch in enumerate(channels):
        hist, bins = np.histogram(data_8bit[:,:,i], bins=256, range=(0, 256))
        
        # Find non-zero ranges
        nonzero = np.where(hist > 0)[0]
        if len(nonzero) > 0:
            min_val = nonzero[0]
            max_val = nonzero[-1]
            
            # Count pixels in key ranges
            shadows = hist[0:50].sum()
            midtones = hist[50:200].sum()
            soft_highlights = hist[200:230].sum()
            hard_highlights = hist[230:256].sum()
            
            print(f"\n{ch} channel:")
            print(f"  Range: {min_val}-{max_val} (8-bit equivalent)")
            print(f"  Shadows (0-49): {shadows} pixels")
            print(f"  Midtones (50-199): {midtones} pixels") 
            print(f"  Soft highlights (200-229): {soft_highlights} pixels")
            print(f"  Hard highlights (230-255): {hard_highlights} pixels")
            
            # Show first few non-zero bins
            nonzero_bins = np.where(hist > 0)[0][:10]
            print(f"  First non-zero bins (8-bit value: count):")
            for b in nonzero_bins:
                print(f"    {b}: {hist[b]}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_tiff.py <tiff_file>")
        sys.exit(1)
    
    analyze_tiff(sys.argv[1])
