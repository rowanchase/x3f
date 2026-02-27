#!/usr/bin/env python3
"""Analyze 16-bit TIFF histogram properly"""

from PIL import Image
import numpy as np
import sys

def analyze_16bit_tiff(tiff_path):
    """Analyze a 16-bit TIFF file by reading raw bytes"""
    img = Image.open(tiff_path)
    
    # Get image dimensions
    width, height = img.size
    channels = len(img.getbands())
    
    print(f"Image: {width}x{height}, {channels} channels")
    print(f"PIL Mode: {img.mode}")
    
    # Read raw bytes as uint16
    raw_bytes = img.tobytes()
    data_uint16 = np.frombuffer(raw_bytes, dtype=np.uint16)
    
    print(f"\nRaw data length: {len(data_uint16)}")
    print(f"Expected (h*w*c): {height * width * channels}")
    
    # Check if sizes match
    if len(data_uint16) != height * width * channels:
        print(f"WARNING: Size mismatch! Using available data.")
        # Just analyze what's there
        print(f"\n16-bit Data Analysis (raw):")
        print(f"  dtype: uint16")
        print(f"  length: {len(data_uint16)}")
        print(f"  min: {data_uint16.min()}")
        print(f"  max: {data_uint16.max()}")
        print(f"  mean: {data_uint16.mean():.1f}")
        
        # Reshape to (-1, 3) for RGB channels
        data = data_uint16.reshape((-1, 3))
    else:
        # Reshape to (height, width, channels)
        data = data_uint16.reshape((height, width, channels))
    
    print(f"\n16-bit Data Analysis:")
    print(f"  dtype: {data.dtype}")
    print(f"  shape: {data.shape}")
    print(f"  min: {data.min()}")
    print(f"  max: {data.max()}")
    print(f"  mean: {data.mean():.1f}")
    
    # Convert to float 0-1 range
    data_float = data / 65535.0
    print(f"\nFloat 0-1 range:")
    print(f"  min: {data_float.min():.4f}")
    print(f"  max: {data_float.max():.4f}")
    print(f"  mean: {data_float.mean():.4f}")
    
    # Analyze histogram (convert to 8-bit bins for readability)
    data_8bit = (data / 257).astype(np.uint8)
    
    channels_names = ['R', 'G', 'B']
    for i, ch in enumerate(channels_names):
        hist, bins = np.histogram(data_8bit[:,i], bins=256, range=(0, 256))
        
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
            
            print(f"\n{ch} channel (8-bit equivalent):")
            print(f"  Range: {min_val}-{max_val}")
            print(f"  Mean value: {np.average(range(256), weights=hist):.1f}")
            print(f"  Shadows (0-49): {shadows} ({shadows/hist.sum()*100:.1f}%)")
            print(f"  Midtones (50-199): {midtones} ({midtones/hist.sum()*100:.1f}%)")
            print(f"  Soft highlights (200-229): {soft_highlights} ({soft_highlights/hist.sum()*100:.1f}%)")
            print(f"  Hard highlights (230-255): {hard_highlights} ({hard_highlights/hist.sum()*100:.1f}%)")
            
            # Show top 5 histogram bins
            top_bins = np.argsort(hist)[-5:][::-1]
            print(f"  Top 5 histogram bins:")
            for b in top_bins:
                print(f"    {b}: {hist[b]} pixels ({hist[b]/hist.sum()*100:.2f}%)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_16bit.py <tiff_file>")
        sys.exit(1)
    
    analyze_16bit_tiff(sys.argv[1])
