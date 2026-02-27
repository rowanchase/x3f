# X3F Tools Architecture

This document provides a comprehensive technical overview of the X3F Tools codebase for processing Sigma Foveon X3F raw image files. It is intended to provide sufficient detail for implementing similar pipelines in other languages or toolsets.

## Table of Contents

1. [Overview](#overview)
2. [X3F File Format](#x3f-file-format)
3. [Processing Pipeline](#processing-pipeline)
4. [Merrill-Specific Handling](#merrill-specific-handling)
5. [Key Data Structures](#key-data-structures)
6. [Color Conversion](#color-conversion)
7. [Spatial Gain Compensation](#spatial-gain-compensation)
8. [Bad Pixel Handling](#bad-pixel-handling)
9. [Denoising](#denoising)
10. [Output Formats](#output-formats)

---

## Overview

X3F Tools is a C/C++ library and command-line tool for reading and processing Sigma Foveon X3F raw image files. The Foveon sensor uses a unique three-layer stacked photodiode design that captures red, green, and blue light at every pixel location, unlike Bayer sensors that use a color filter array.

### Supported Cameras

- **SD Series**: SD9, SD10, SD14, SD15 (Huffman compression)
- **DP Merrill Series**: DP1 Merrill, DP2 Merrill, DP3 Merrill (TRUE II, version 2.x)
- **Quattro Series**: DP0Q, DP1Q, DP2Q, DP3Q (version 4.x+)
- **sd Quattro**: SDQ, SDQH

### Architecture Components

```
┌─────────────────┐
│  x3f_extract    │  <- CLI entry point
├─────────────────┤
│  x3f_io         │  <- File format I/O
├─────────────────┤
│  x3f_process    │  <- Image processing pipeline
├─────────────────┤
│  x3f_meta       │  <- Metadata extraction (CAMF/PROP)
├─────────────────┤
│  x3f_image      │  <- Image area handling
├─────────────────┤
│  x3f_spatial    │  <- Spatial gain compensation
├─────────────────┤
│  x3f_matrix     │  <- Color space matrices
├─────────────────┤
│  x3f_denoise    │  <- Denoising algorithms (OpenCV)
├─────────────────┤
│  x3f_output_*   │  <- TIFF, DNG, PPM writers
└─────────────────┘
```

---

## X3F File Format

### File Structure

X3F files are structured as a directory-based container format (similar to TIFF):

```
┌─────────────────────────────────────┐
│         X3F Header                  │
│   - Identifier: "FOVb" (0x62564f46)  │
│   - Version (e.g., 0x00020001 = 2.1) │
│   - Image dimensions                 │
│   - White balance string             │
│   - Extended data arrays             │
└─────────────────────────────────────┘
│
├─────────────────────────────────────┐
│     Directory Section (SECd)         │
│   - Located at end of file          │
│   - Contains entry count            │
│   - Points to data sections          │
└─────────────────────────────────────┘
│
├─────────────────────────────────────┐
│     Directory Entries                │
│   1. Property Section (SECp)         │
│   2. Image Section (SECi)            │
│   3. CAMF Section (SECc)             │
│   4. SPPA Section (SECs) - Quattro   │
└─────────────────────────────────────┘
```

### File Versions

| Version | Cameras | Compression |
|---------|---------|-------------|
| 2.0 | SD9, SD10 | Huffman |
| 2.1 | SD14, DP1 (gen1) | Huffman |
| 2.2 | DP2 (gen1) | Huffman + JPEG thumb |
| 2.3 | Merrill series | TRUE compression |
| 3.0 | DP Merrill | TRUE + extended data |
| 4.0+ | Quattro series | TRUE + Quattro layout |

### Raw Image Formats

Different cameras use different raw encoding schemes:

```c
// Format identifiers from x3f_io.h
#define X3F_IMAGE_RAW_HUFFMAN_X530   (uint32_t)(0x00030005)  // SD9/SD10
#define X3F_IMAGE_RAW_HUFFMAN_10BIT  (uint32_t)(0x00030006)  // SD14
#define X3F_IMAGE_RAW_TRUE         (uint32_t)(0x0003001e)  // DP1/DP2 gen1
#define X3F_IMAGE_RAW_MERRILL      (uint32_t)(0x0001001e)  // Merrill
#define X3F_IMAGE_RAW_QUATTRO      (uint32_t)(0x00010023)  // Quattro
#define X3F_IMAGE_RAW_SDQ          (uint32_t)(0x00010025)  // sd Quattro
#define X3F_IMAGE_RAW_SDQH         (uint32_t)(0x00010027)  // sd Quattro H
```

### TRUE Compression

The TRUE (Three-layer Responsive Ultimate Engine) compression used in Merrill and later cameras:

1. **Seed Values**: Three 16-bit seed values (typically 512, 512, 512)
2. **Huffman Table**: Variable-length Huffman codes for delta encoding
3. **Plane Organization**: Three separate planes (0=bottom, 1=middle, 2=top)
4. **Delta Encoding**: Each pixel value is encoded as difference from previous

```c
typedef struct x3f_true_s {
  uint16_t seed[3];              // Always 512,512,512
  uint16_t unknown;              // Always 0
  x3f_true_huffman_t table;      // Huffman table
  x3f_table32_t plane_size;      // Size of 3 planes
  uint8_t *plane_address[3];     // Computed offsets
  x3f_hufftree_t tree;           // Decoding tree
  x3f_area16_t x3rgb16;          // Decoded 3x16-bit data
} x3f_true_t;
```

### CAMF Metadata Section

The CAMF (Camera Metadata Format) section contains encrypted/compressed metadata:

- **Type 2**: Basic metadata (older cameras)
- **Type 4**: Huffman-compressed metadata (Merrill)
- **Type 5**: Extended metadata (Quattro)

Key CAMF entries for processing:

```
WhiteBalanceGains          - 3x1 float vector
WhiteBalanceIlluminants  - 3x3 color matrix
WhiteBalanceCorrections  - 3x3 correction matrix
WhiteBalanceColorCorrections - 3x3 CC matrix
SensorAdjustmentGainFact - 3x1 gain factors
SpatialGain_*            - Vignetting correction tables
KeepImageArea            - 4x1 active area coords
BadPixels                - Bad pixel coordinates
DarkShieldTop/Bottom     - Black level areas
HighlightPixelsInfo      - Highlight pixel grid
```

---

## Processing Pipeline

The image processing pipeline in `x3f_process.c` follows these stages:

### 1. File Loading (`x3f_new_from_file()`)

```c
x3f_t *x3f = x3f_new_from_file(FILE *infile);
```

- Read header (identifier, version, dimensions)
- Parse directory section at EOF
- Build entry table (property, image, CAMF sections)
- Note: Does not load actual image data yet

### 2. Data Loading (`x3f_load_data()`)

```c
x3f_load_data(x3f, x3f_get_raw(x3f));     // Load RAW
x3f_load_data(x3f, x3f_get_camf(x3f));    // Load metadata
x3f_load_data(x3f, x3f_get_prop(x3f));    // Load properties
```

- Decompress Huffman/TRUE encoded data
- Decrypt/decompress CAMF metadata
- Convert to 16-bit RGB format (x3rgb16)

### 3. Preprocessing (`preprocess_data()`)

**Black Level Calculation**:
```c
static int get_black_level(x3f_t *x3f, x3f_area16_t *image, 
                          int rescale, int colors,
                          double *black_level, double *black_dev);
```

Uses optically shielded sensor areas:
- `DarkShieldTop` - Top masked rows
- `DarkShieldBottom` - Bottom masked rows (disabled for some cameras)
- Left/Right shielded columns (disabled for Merrill due to gradient bug)

For each channel:
1. Calculate mean of dark pixels
2. Calculate standard deviation
3. Return as `black_level[3]` and `black_dev[3]`

**Merrill Workaround**:
```c
// Right shielded area has linear exposure gradient
if (!strcmp(cammodel, "SIGMA DP1 Merrill") ||
    !strcmp(cammodel, "SIGMA DP2 Merrill") ||
    !strcmp(cammodel, "SIGMA DP3 Merrill"))
  use[RIGHT] = 0;  // Don't use right shielded area
```

### 4. Intermediate Scaling

Convert from sensor bit depth (typically 12-bit) to 14-bit intermediate:

```c
#define INTERMEDIATE_DEPTH 14
#define INTERMEDIATE_UNIT ((1<<INTERMEDIATE_DEPTH) - 1)
#define INTERMEDIATE_BIAS_FACTOR 4.0

// Scale calculation for each channel:
scale[color] = (max_intermediate - intermediate_bias) / 
               (max_raw - black_level[color]);

// Apply scaling:
out = round(scale[color] * (raw_value - black_level[color]) + 
            intermediate_bias);
```

The intermediate bias is calculated as:
```c
intermediate_bias = 4.0 * black_dev[color] * 
                    max_intermediate / (max_raw - black_level[color]);
```

### 5. Bad Pixel Interpolation (`interpolate_bad_pixels()`)

Sources of bad pixel data:
- `BadPixels` matrix - Direct coordinates
- `BadPixelsF20` - F20 sensor specific (rows/cols swapped due to bug)
- `Jpeg_BadClusters` - JPEG processing bad pixels
- `HighlightPixelsInfo` - Highlight pixel grid pattern
- `BadPixelsChromaF23` - Quattro chroma bad pixels (run-length encoded)

Interpolation algorithm:
```c
// Collect valid neighbors (up, down, left, right)
// If 4 neighbors: average all 4
// If 2 horizontal/vertical: average those 2
// If 2 diagonal (corner): average if no other option
// Iterative: Fixed pixels enable interpolation of neighbors
```

### 6. Denoising (Optional)

See [Denoising](#denoising) section below.

### 7. Color Conversion (`convert_data()`)

**White Balance Retrieval**:
```c
int x3f_get_gain(x3f_t *x3f, char *wb, double *gain);
```

Tries these sources in order:
1. `WhiteBalanceGains` matrix for specified WB
2. Calculate from `WhiteBalanceIlluminants` + `WhiteBalanceCorrections`
3. Apply `SensorAdjustmentGainFact` if available
4. Apply `TempGainFact` if available
5. Apply `FNumberGainFact` if available

**Color Matrix Construction**:
```c
int x3f_get_bmt_to_xyz(x3f_t *x3f, char *wb, double *bmt_to_xyz);
```

Tries:
1. `WhiteBalanceColorCorrections` matrix (converted via sRGB→XYZ)
2. Calculate from illuminants + corrections

**Final Raw→XYZ Matrix**:
```c
// raw_to_xyz = bmt_to_xyz * diag(gain)
x3f_3x3_diag(gain, gain_mat);
x3f_3x3_3x3_mul(bmt_to_xyz, gain_mat, raw_to_xyz);
```

**Target Color Space Conversion**:

For each pixel:
1. Get spatial gain (if enabled)
2. Normalize to 0-1 range
3. Apply raw→RGB matrix
4. Apply ISO scaling
5. Apply gamma/LUT encoding

Supported output color spaces:
- **sRGB**: sRGB gamma with sigmoid highlight handling
- **Adobe RGB**: Gamma 2.2
- **ProPhoto RGB**: Gamma 1.8 with D50 adaptation

### 8. Spatial Gain Application

See [Spatial Gain Compensation](#spatial-gain-compensation) section.

### 9. Output Generation

Write to TIFF, DNG, or PPM format with appropriate headers and compression.

---

## Merrill-Specific Handling

The Merrill cameras (DP1M, DP2M, DP3M) require special handling:

### Camera Detection

```c
#define X3F_CAMERAID_DP1M    (uint32_t)77
#define X3F_CAMERAID_DP2M    (uint32_t)78
#define X3F_CAMERAID_DP3M    (uint32_t)78  // Note: Same as DP2M!
```

Or via CAMF property:
```c
char *cammodel;
if (x3f_get_prop_entry(x3f, "CAMMODEL", &cammodel))
  if (!strcmp(cammodel, "SIGMA DP2 Merrill")) {
    // Merrill-specific processing
  }
```

### Merrill Data Format

- **X3F Version**: 2.x (pre-4.0)
- **Image Dimensions**: 4800 × 3200 pixels
- **Sensor**: Foveon X3 F20 (TRUE II)
- **Raw Format**: TRUE compression (X3F_IMAGE_RAW_MERRILL)
- **Bit Depth**: ~12-bit per channel
- **Channels**: 3 (stacked RGB at each pixel)

### Spatial Gain (Vignetting Correction)

Merrill uses a 2D interpolation approach based on:
- **Aperture** (1/f-stop)
- **Lens Position** (focus distance)

```c
// Get interpolation parameters
x = 1.0 / capture_aperture;
y = lens_position(focal_length, object_distance);

// Find 4 nearest calibration points
// Weight by inverse distance
// Bilinear interpolation of gain tables
```

Calibration data is stored in CAMF as `SpatialGainsProps_*` entries with associated `GainsTable*` matrices for each RGB channel.

### Empirical Corrections

The Merrill pipeline applies empirical corrections to match Sigma Photo Pro:

```c
// From x3f_process.c:

// SPP Exposure Compensation (2.5x in linear space)
double spp_exposure_comp = 2.5;
for (color = 0; color < 3; color++)
  output[color] *= spp_exposure_comp;

// Green cast correction
output[0] *= 1.17;   // Red boost
double green_correction = 0.895;
output[1] *= green_correction;  // Green reduction
double b_correction = 1.06;     // Blue boost (reduced from 1.19)
output[2] *= b_correction;

// Global desaturation (film-like)
double gray = (output[0] + output[1] + output[2]) / 3.0;
double desat_factor = 0.62;
for (color = 0; color < 3; color++) {
  output[color] = gray + (output[color] - gray) * desat_factor;
}

// Shadow desaturation
// (See code for implementation details)

// Highlight desaturation
// (See code for implementation details)
```

### Black Level Workaround

Merrill right shielded column has a linear exposure gradient:

```c
if (!strcmp(cammodel, "SIGMA DP1 Merrill") ||
    !strcmp(cammodel, "SIGMA DP2 Merrill") ||
    !strcmp(cammodel, "SIGMA DP3 Merrill"))
  use[RIGHT] = 0;  // Disable right shielded area
```

Without this, shadows get a green tint due to black level underestimation.

---

## Key Data Structures

### X3F Container

```c
typedef struct x3f_s {
  x3f_info_t info;              // File handles
  x3f_header_t header;        // Main header
  x3f_directory_section_t directory_section;  // Entry directory
} x3f_t;
```

### Image Area (16-bit)

```c
typedef struct {
  uint16_t *data;      // Pointer to pixel data (row-major, interleaved RGB)
  void *buf;           // Buffer for free()
  uint32_t rows;       // Height in pixels
  uint32_t columns;    // Width in pixels
  uint32_t channels;   // Number of channels (3 for RGB)
  uint32_t row_stride; // Bytes per row (columns * channels * sizeof(uint16_t))
} x3f_area16_t;

// Pixel access:
// value = image->data[row * image->row_stride + col * image->channels + channel];
// channel: 0=Red, 1=Green, 2=Blue (for Foveon: bottom/middle/top layers)
```

### Image Levels

```c
typedef struct {
  double black[3];     // Black level per channel (after preprocessing)
  uint32_t white[3];   // White level per channel (after preprocessing)
} x3f_image_levels_t;
```

### Spatial Gain Correction

```c
typedef struct {
  double weight;
  uint32_t *gain;      // Raw gain table indices
  double mingain;      // Minimum gain value
  double delta;        // Gain step size
} x3f_spatial_gain_corr_merrill_t;

typedef struct {
  double *gain;        // Final interpolated gain table
  int malloc;          // 1 if allocated with malloc
  int rows, cols;      // Gain table dimensions
  int rowoff, coloff;  // Phase offset for Quattro
  int rowpitch, colpitch;  // Subsampling pitch
  int chan, channels;  // Channel index/count
  x3f_spatial_gain_corr_merrill_t mgain[4];  // Raw Merrill gains
  int mgain_num;       // Number of Merrill gain entries
} x3f_spatial_gain_corr_t;
```

---

## Color Conversion

### Pipeline

```
Raw Sensor Data (BMT: Bottom/Middle/Top layers)
           ↓
    Black Level Subtraction
           ↓
    Intermediate Scaling (to 14-bit)
           ↓
    Spatial Gain Compensation
           ↓
    Raw → XYZ Matrix Application
           ↓
    XYZ → Target RGB Matrix
           ↓
    Tone Curve / Gamma Application
           ↓
    Output (sRGB/Adobe RGB/ProPhoto)
```

### Matrix Calculation

```c
// 1. Get white balance gains
x3f_get_gain(x3f, wb, gain);

// 2. Get BMT to XYZ matrix
x3f_get_bmt_to_xyz(x3f, wb, bmt_to_xyz);

// 3. Build raw_to_xyz matrix
// raw_to_xyz = bmt_to_xyz * diag(gain)
x3f_3x3_diag(gain, gain_mat);
x3f_3x3_3x3_mul(bmt_to_xyz, gain_mat, raw_to_xyz);

// 4. Get target RGB matrix (e.g., sRGB)
x3f_XYZ_to_sRGB(xyz_to_rgb);

// 5. Combine: raw_to_rgb = xyz_to_rgb * raw_to_xyz
x3f_3x3_3x3_mul(xyz_to_rgb, raw_to_xyz, raw_to_rgb);

// 6. Apply ISO scaling
x3f_scalar_3x3_mul(iso_scaling, raw_to_rgb, conv_matrix);
```

### Color Space Matrices

Standard conversion matrices (from `x3f_matrix.c`):

**XYZ→sRGB**:
```
|  3.2406  -1.5372  -0.4986 |
| -0.9689   1.8758   0.0415 |
|  0.0557  -0.2040   1.0570 |
```

**XYZ→Adobe RGB**:
```
|  2.04159  -0.56501  -0.34473 |
| -0.96924   1.87597   0.04156 |
|  0.01344  -0.11836   1.01517 |
```

**XYZ→ProPhoto RGB**:
```
|  1.3460  -0.2556  -0.0511 |
| -0.5446   1.5082   0.0205 |
|  0.0000   0.0000   1.2123 |
```

**Bradford D65→D50 Adaptation** (for ProPhoto):
```
|  1.0478112   0.0228866  -0.0501270 |
|  0.0295424   0.9904844  -0.0170491 |
| -0.0092345   0.0150436   0.7521316 |
```

### LUT Generation

**sRGB Sigmoid LUT** (with highlight handling):
```c
void x3f_sRGB_sigmoid_LUT(double *lut, int size, uint16_t max, 
                         double steepness, double highlight_threshold);
```

**Gamma LUT**:
```c
void x3f_gamma_LUT(double *lut, int size, uint16_t max, double gamma);
```

### Per-Pixel Conversion

```c
// For each pixel at (row, col):
for (color = 0; color < 3; color++) {
  // 1. Get spatial gain
  gain = x3f_calc_spatial_gain(sgain, sgain_num, row, col, color, rows, cols);
  
  // 2. Normalize input
  input[color] = gain * (val - black[color]) / (white[color] - black[color]);
}

// 3. Apply color matrix
x3f_3x3_3x1_mul(conv_matrix, input, output);

// 4. Apply tone curve
for (color = 0; color < 3; color++) {
  output[color] = x3f_LUT_lookup(lut, LUTSIZE, output[color]);
}
```

---

## Spatial Gain Compensation

Spatial gain (vignetting) correction compensates for:
- Lens vignetting (light falloff at edges)
- Sensor sensitivity variations
- Aperture-dependent effects

### Merrill Spatial Gain

Merrill uses a multi-dimensional interpolation based on:
- **Aperture**: f/2.8, f/4, f/5.6, f/8, etc.
- **Focus distance**: Infinity vs MOD (Minimum Object Distance)

**Algorithm**:

```c
// 1. Get current capture parameters
x = 1.0 / capture_aperture;
y = lens_position(focal_length, object_distance);

// 2. Find 4 nearest calibration points in (1/aperture, lens_pos) space
//    organized in quadrants around current point

// 3. Calculate bilinear interpolation weights
//    based on distance to calibration points

// 4. For each calibration point, load gain tables
//    from CAMF properties (GainsTableR, GainsTableG, GainsTableB)

// 5. Interpolate gain at each pixel
//    gain = mingain + delta * table[row][col]
```

### Gain Calculation at Runtime

```c
double x3f_calc_spatial_gain(x3f_spatial_gain_corr_t *corr, 
                            int corr_num,
                            int row, int col, int chan,
                            int rows, int cols);
```

For each pixel:
1. Calculate relative position: `rrel = row / rows`, `crel = col / cols`
2. Bilinear interpolation in gain table
3. Multiply gains from multiple correction tables

### Classic Spatial Gain (Older Cameras)

Pre-Merrill cameras use simpler spatial gain:
```c
x3f_get_camf_matrix_var(x3f, "SpatialGain", 
                       &corr->rows, &corr->cols, &corr->channels,
                       M_FLOAT, (void **)&corr->gain);
```

---

## Bad Pixel Handling

### Sources

Bad pixel data comes from multiple sources in the CAMF section:

```c
// Direct bad pixel list (packed coordinates)
"BadPixels"              -> uint32_t array: (row << 20) | (col << 8)

// F20 sensor specific (note: row/col swapped in firmware)
"BadPixelsF20"           -> uint32_t array: [col, row, flags]

// JPEG processing bad pixels (also row/col swapped)
"Jpeg_BadClusters"       -> uint32_t array: [col, row, flags]

// Quattro chroma bad pixels (run-length encoded)
"BadPixelsChromaF23"     -> uint32_t array: [row, col1, col2, ..., 0, row2, ...]

// Highlight pixel grid pattern
"HighlightPixelsInfo"    -> [start_col, start_row, pitch_col, pitch_row]
```

### Interpolation Algorithm

```c
static void interpolate_bad_pixels(x3f_t *x3f, x3f_area16_t *image, int colors);
```

**Process**:
1. **Collect** all bad pixel coordinates into a list and bit vector
2. **Iterative interpolation**:
   - For each bad pixel, check 4 neighbors (up, down, left, right)
   - If 4 valid neighbors: average all 4
   - If 2 valid linear neighbors: average those 2
   - If only corner neighbors: average if stuck (last resort)
3. **Mark as fixed** and remove from list
4. **Repeat** until all pixels fixed (or failure after corner fallback)

**Data Structures**:
```c
typedef struct bad_pixel_s {
  int c, r;                    // Column, row
  struct bad_pixel_s *prev, *next;  // Linked list
} bad_pixel_t;

// Bit vector for O(1) neighbor testing
uint32_t *bad_pixel_vec = calloc((rows*cols + 31)/32, sizeof(uint32_t));
// Test: vec[(r*cols + c) >> 5] & (1 << ((r*cols + c) & 0x1f))
```

### Special Cases

**sd Quattro AF Pixels**:
Hardcoded grid patterns for autofocus pixels:
```c
static const grid_t sdq_af_luma   = {217, 5641, 16, 1, 464, 3312, 32, 2};
static const grid_t sdq_af_chroma = {108, 2820,  8, 1, 232, 1656, 16, 1};
```

---

## Denoising

Denoising is implemented in C++ using OpenCV (`x3f_denoise.cpp`, `x3f_denoise_aniso.cpp`).

### Algorithm Selection

```c
typedef enum {
  X3F_DENOISE_STD=0,  // Standard
  X3F_DENOISE_F20=1,  // F20 sensor (Merrill)
  X3F_DENOISE_F23=2   // F23 sensor (Quattro)
} x3f_denoise_type_t;

// Auto-selection based on sensor
if (!strcmp(sensorid, "F20"))
  type = X3F_DENOISE_F20;
```

### Non-Local Means Denoising

Main algorithm: OpenCV `fastNlMeansDenoising`

```cpp
void denoise_nlm(Mat& img, float h) {
  float h1[3] = {0.0, h, h};  // YUV channels
  
  // 1. Full resolution NLM denoising
  fastNlMeansDenoising(img, out, std::vector<float>(h1, h1+3),
                      3, 11, NORM_L1);
  
  // 2. V channel median filtering (3x3)
  mixChannels(...);  // Extract V
  medianBlur(V, V, 3);
  mixChannels(...);  // Reinsert V
  
  // 3. Low-frequency denoising (downscale 4x, NLM, subtract, upscale)
  resize(out, sub, Size(), 1.0/4, 1.0/4, INTER_AREA);
  fastNlMeansDenoising(sub, sub_dn, ...);
  subtract(sub, sub_dn, sub_res, ...);
  resize(sub_res, res, out.size(), 0.0, 0.0, INTER_CUBIC);
  subtract(out, res, out, ...);
}
```

### Color Space Conversion for Denoising

BMT (Bottom/Middle/Top sensor layers) is converted to YUV for denoising:

```c
// BMT -> YUV conversion types
typedef struct {
  float h;
  conv_t BMT_to_YUV;
  conv_t YUV_to_BMT;
} denoise_desc_t;

const denoise_desc_t denoise_types[] = {
  {100.0, BMT_to_YUV_STD, YUV_to_BMT_STD},   // Standard
  {70.0,  BMT_to_YUV_YisT, YUV_to_BMT_YisT}, // F20: Y=Top layer
  {300.0, BMT_to_YUV_Yis4T, YUV_to_BMT_Yis4T} // F23: Y=4*Top
};
```

### Anisotropic Denoising (Alternative)

Custom implementation in `x3f_denoise_aniso.cpp`:
- Edge-preserving diffusion
- Morphological operations (`denoise_splotchify`)
- Custom median filter

---

## Output Formats

### TIFF Output (`x3f_output_tiff.c`)

**Supported variants**:
- Uncompressed 16-bit RGB
- ZIP-compressed (deflate)
- Tiled or stripped organization

**Structure**:
```c
TIFF header
├── Image Width/Height
├── BitsPerSample: 16,16,16
├── SamplesPerPixel: 3
├── PhotometricInterpretation: RGB
├── Compression: None or Deflate
├── PlanarConfiguration: Chunky (RGB RGB RGB...)
└── Image data
```

### DNG Output (`x3f_output_dng.c`)

DNG (Digital Negative) output for use in Adobe software:

**Key DNG Tags**:
- `DNGVersion`: 1.4.0.0
- `DNGBackwardVersion`: 1.1.0.0
- `CFARepeatPatternDim`: Not applicable (Foveon is not CFA)
- `CFAPattern`: Not applicable
- `ColorMatrix1/2`: Color conversion matrices
- `AsShotNeutral`: White balance multipliers
- `CalibrationIlluminant1/2`: D65, Standard Light A

**Note**: Foveon sensors don't use a Color Filter Array (CFA), so standard Bayer-based DNG tools may not handle them optimally.

### PPM Output (`x3f_output_ppm.c`)

**P6 Format** (Binary):
```
P6
{width} {height}
65535
[16-bit RGB data]
```

**P3 Format** (ASCII):
```
P3
{width} {height}
65535
R G B
R G B
...
```

---

## Implementation Notes

### Memory Management

- All image buffers use `malloc()`/`free()`
- `x3f_area16_t.buf` is allocated, `.data` points to actual pixel data
- Cleanup via `x3f_delete()` which frees all allocated memory

### Endianness

X3F files are little-endian. The code assumes:
- File is little-endian
- Host may be either endian (uses byte-swapping macros)
- Multi-byte elements stored in native endian

### OpenCV Integration

Denoising requires OpenCV 3.0+ with these modules:
- `opencv_core`: Mat/UMat containers
- `opencv_imgproc`: resize, medianBlur, mixChannels
- `opencv_photo`: fastNlMeansDenoising

---

## References

- X3F file format: Reverse-engineered from Sigma files
- Color matrices: Based on ICC/Adobe/ISO standards
- Denoising: Buades et al., "A non-local algorithm for image denoising"
- Merrill sensor: Fent & Meldrum (2016), "Quantum Efficiency Characterization of Foveon Sensors"

---

## License

BSD-style license - see `doc/copyright.txt`

Copyright (c) 2010-2015 Roland and Erik Karlsson
Copyright (c) 2015 Mark Roden (anisotropic denoising)
