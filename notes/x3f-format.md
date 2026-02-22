# X3F File Format Technical Notes

## Overview

X3F is the raw image format used by Sigma digital cameras featuring Foveon X3 sensors. The format was originally developed by Foveon Inc. and is sometimes referred to as "FOVb" (the magic bytes at the start of the file).

## File Structure

### Header
The file begins with a header structure:
- **Magic bytes**: "FOVb" (0x62564F46)
- **Version**: 16-bit major + 16-bit minor (e.g., 2.0, 2.1, 2.2, 2.3, 3.0, 4.0, 4.1)
- **Unique identifier**: 16 bytes
- **Mark bits**: Used for marking/deleting images
- **Columns/Rows**: Image dimensions before rotation
- **Rotation**: 0, 90, 180, or 270 degrees
- **White balance string**: Introduced in version 2.1
- **Color mode**: Introduced in version 2.3
- **Extended data**: 32-64 float values for adjustments (exposure, contrast, etc.)

### Directory Section
After the header is a directory section (identifier "SECd"):
- Number of directory entries
- Array of directory entries, each with:
  - Input offset and size
  - Output offset and size  
  - Type identifier
  - Header with section-specific data

### Section Types

#### 1. CAMF (Camera Metadata) - "SECc"
**CRITICAL**: This section is ENCRYPTED with a simple stream cipher.

Structure:
```c
struct CAMF_DATA {
    DWORD m_dwordSectionIdentifier; // "SECc"
    DWORD m_dwordSectionFormatVersion;
    DWORD m_dwordTypeOfInfoData;
    DWORD m_dwordReserved;
    DWORD m_dwordInfoType;          // "FCEb"
    DWORD m_dwordInfoTypeVersion;
    DWORD m_dwordCryptKey;          // Encryption key
}
```

Decryption algorithm (LCG + S-box):
```c
for (DWORD i = 0; i < dataSize; i++) {
    lcg = ((lcg * 1597) + 51749) % 244944;
    sbox = (lcg * 301593171LL) >> 24;
    data[i] ^= ((((lcg << 8) - sbox) >> 1) + sbox) >> 17;
}
```

The decrypted CAMF contains:
- Camera calibration data
- White balance matrices
- Color correction matrices
- Spatial gain tables
- Bad pixel maps
- Sensor adjustment factors

#### 2. Property Section - "SECp"
Contains image metadata as name-value pairs (UTF-16):
- Camera model (CAMMODEL)
- Sensor ID (SENSORID)
- Focal length (FLENGTH)
- ISO settings
- Exposure info
- And more...

#### 3. Image Section - "SECi"
Contains actual image data. Format depends on type/format values:

| Type | Format | Description |
|------|--------|-------------|
| 2 | 3 | Uncompressed 8/8/8 RGB (preview) |
| 2 | 11 | Huffman DPCM 8/8/8 RGB (preview) |
| 2 | 18 | JPEG compressed (thumbnail) |
| 3 | 6 | Huffman DPCM 16/16/16 RGB (RAW - older) |
| 1 | 0x1e (30) | TRUE engine RAW (Merrill) |
| 1 | 0x23 (35) | Quattro RAW |
| 1 | 0x25 (37) | SD Quattro RAW |
| 1 | 0x27 (39) | SD Quattro H RAW |

## Foveon X3 Sensor

### How It Works
Unlike Bayer sensors which capture one color per pixel using a color filter array, the Foveon X3 captures all three colors (R, G, B) at every pixel location by exploiting silicon's natural light absorption:

1. **Blue light** absorbs near the surface (~0.2μm depth)
2. **Green light** penetrates deeper (~0.6μm depth)
3. **Red light** penetrates deepest (~2.0μm depth)

The sensor has three stacked photodiode layers, each capturing one color channel. This eliminates:
- Demosaicing artifacts
- Moiré patterns
- Color aliasing

### Sensor Layers
- **Top layer**: Blue channel
- **Middle layer**: Green channel  
- **Bottom layer**: Red channel

### Merrill Sensor Specifics
- Resolution: 4800 × 3200 × 3 layers = 15.4 MP (46 MP equivalent Bayer)
- Sensor size: APS-C (23.5 × 15.7mm)
- Pixel pitch: ~4.9μm
- TRUE II image processor
- X3F version: 2.x (version < 4.0)

## Processing Pipeline

### 1. Load and Parse
- Read header, validate "FOVb" magic
- Parse directory entries
- Identify section types (CAMF, PROP, IMAG)

### 2. Decrypt CAMF
- Extract encryption key from CAMF header
- Decrypt using LCG+S-box cipher
- Parse decrypted entries for calibration data

### 3. Load Raw Image Data
For Merrill (format 0x1e):
- Huffman-encoded DPCM data
- 1024-word pixel value table
- 1024-entry Huffman table
- Decode to 16-bit per channel RGB

### 4. Black Level Subtraction
- Compute black level from masked pixels:
  - DarkShieldTop (top masked rows)
  - DarkShieldBottom (bottom masked rows)
  - Left/Right column masks
- Subtract black level per channel

### 5. Bad Pixel Interpolation
- Read bad pixel maps from CAMF
- Interpolate over bad pixels using neighbors

### 6. White Balance and Color Conversion
- Apply white balance gains
- Convert from camera raw to XYZ color space
- Convert from XYZ to target color space (sRGB, Adobe RGB, ProPhoto RGB)

### 7. Spatial Gain Correction
**Important for Merrill cameras!**

Spatial gain compensates for:
- Lens vignetting
- Color casts across the frame
- Illumination non-uniformity

For Merrill, spatial gain is:
- Based on aperture and focus distance
- Interpolated from calibration tables
- Applied per-channel across the image

Enabled by default for X3F version < 4.0 (Merrill and earlier)

### 8. Gamma Encoding
- sRGB: Complex gamma with linear segment
- Adobe RGB: Gamma 2.2
- ProPhoto RGB: Gamma 1.8

## Key CAMF Entries

### White Balance
- `WhiteBalanceGains` or `DP1_WhiteBalanceGains` - per-channel gains
- `WhiteBalanceIlluminants` - XYZ values for WB light sources
- `WhiteBalanceCorrections` - correction matrices
- `WhiteBalanceColorCorrections` or `DP1_WhiteBalanceColorCorrections`

### Color Matrices
- Convert from sensor raw values to XYZ
- White balance dependent

### Spatial Gain Tables
- `SpatialGain_Fstop` - f-stop values for tables
- `SpatialGainsProps_<aperture>_<distance>` - gain tables per aperture/distance
- `GainsTableR/G/B` - per-channel gain maps
- `MinGainsR/G/B`, `DeltaR/G/B` - gain parameters

### Bad Pixels
- `BadPixels` - pixel coordinates
- `BadPixelsF20` - format 20 bad pixels
- `BadPixelsChromaF23` - F23 chroma bad pixels
- `HighlightPixelsInfo` - highlight pixel info

### Sensor Info
- `SensorISO` - sensor base ISO
- `CaptureISO` - actual capture ISO
- `SensorAdjustmentGainFact` - sensor gain factors
- `TempGainFact` - temperature gain factors
- `FNumberGainFact` - f-number gain factors

## Key Codebase Files

| File | Purpose |
|------|---------|
| `x3f_io.c/h` | File parsing, section decoding |
| `x3f_process.c` | Image processing pipeline |
| `x3f_meta.c` | CAMF metadata extraction |
| `x3f_spatial_gain.c` | Spatial gain correction |
| `x3f_matrix.c` | Color space conversions |
| `x3f_denoise.c` | Noise reduction |
| `x3f_output_tiff.c` | TIFF file writing |

## Version Differences

### Version 2.x (Merrill, SD1, DP1/2/3, etc.)
- Spatial gain enabled by default
- Standard TRUE engine format
- 3-layer full resolution

### Version 4.x (Quattro)
- Different sensor layout (top layer 2x resolution)
- Spatial gain disabled by default (pre-applied?)
- Quattro-specific decompression

## References

1. Official X3F Specification (partial): https://libopenraw.freedesktop.org/formats/x3f/x3f-raw-format.pdf
2. X3F Documentation Project: http://www.photofo.com/x3f-raw-format/
3. Kalpanika/x3f GitHub: https://github.com/Kalpanika/x3f
4. Foveon X3 technical papers
5. dcraw source code by Dave Coffin

## Notes for Implementation

1. **Encryption is mandatory**: Cannot read useful data without decrypting CAMF
2. **Spatial gain is critical**: Merrill images will look wrong without it
3. **Black level varies**: Must compute from masked pixels per image
4. **White balance is embedded**: Multiple WB presets stored in CAMF
5. **Bad pixels are mapped**: Factory-calibrated bad pixel locations in CAMF
6. **Color matrices are WB-dependent**: Different matrices for each WB preset
