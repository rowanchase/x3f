/* X3F_HIGHLIGHT_RECOVERY.H
 *
 * Library for Foveon X3F highlight recovery using multi-layer reconstruction.
 *
 * Copyright 2025 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#ifndef X3F_HIGHLIGHT_RECOVERY_H
#define X3F_HIGHLIGHT_RECOVERY_H

#include "x3f_process.h"
#include "x3f_io.h"
#include <stdint.h>

/* Clipping state for a single pixel - bitmask */
typedef enum {
  CLIP_STATE_NONE = 0,      /* 000 - No channels clipped */
  CLIP_STATE_BLUE = 1,      /* 001 - Blue clipped only */
  CLIP_STATE_GREEN = 2,     /* 010 - Green clipped only */
  CLIP_STATE_RED = 4,       /* 100 - Red clipped only */
  CLIP_STATE_BG = 3,        /* 011 - Blue+Green clipped */
  CLIP_STATE_BR = 5,        /* 101 - Blue+Red clipped */
  CLIP_STATE_GR = 6,        /* 110 - Green+Red clipped */
  CLIP_STATE_ALL = 7        /* 111 - All channels clipped */
} x3f_clip_state_t;

/* Detailed clipping information per pixel */
typedef struct {
  x3f_clip_state_t state;           /* Bitmask of clipped channels */
  float raw_values[3];              /* Original raw values (0-1 normalized) */
  float clip_thresholds[3];         /* Per-channel clipping thresholds */
  float distance_to_boundary;       /* Distance to nearest unclipped pixel */
  uint8_t has_unclipped_neighbor;   /* Boolean: has valid neighbors? */
} x3f_pixel_clip_info_t;

/* Image-wide clipping map */
typedef struct {
  int width;
  int height;
  x3f_pixel_clip_info_t *pixels;    /* Flat array [row * width + col] */
  int total_clipped_pixels;         /* Statistics */
  int single_channel_clipped;       /* Case 1 count */
  int two_channel_clipped;          /* Case 2 count */
  int all_channel_clipped;          /* Case 3 count */
} x3f_clip_map_t;

/* Boundary analysis results */
typedef struct {
  float *boundary_ratios_bg;        /* Blue/Green ratios at boundary [width * height] */
  float *boundary_ratios_br;        /* Blue/Red ratios at boundary */
  float *boundary_ratios_gr;        /* Green/Red ratios at boundary */
  float *gradient_magnitude;        /* Local gradient strength */
} x3f_boundary_data_t;

/* Initialize and destroy clipping map */
x3f_clip_map_t* x3f_create_clip_map(int width, int height);
void x3f_destroy_clip_map(x3f_clip_map_t *map);

/* Main clipping detection */
int x3f_detect_clipping(x3f_area16_t *image, x3f_image_levels_t *ilevels,
                        double hl_threshold, x3f_clip_map_t *map);

/* Boundary analysis - quality prioritized (larger search radius) */
int x3f_analyze_boundaries(x3f_area16_t *image, x3f_clip_map_t *map,
                           x3f_boundary_data_t *boundary);

/* Allocate and free boundary data */
x3f_boundary_data_t* x3f_create_boundary_data(int width, int height);
void x3f_free_boundary_data(x3f_boundary_data_t *boundary);

/* Phase 2: Multi-channel highlight reconstruction */
int x3f_reconstruct_highlights(
    x3f_area16_t *image,
    x3f_clip_map_t *clip_map,
    x3f_boundary_data_t *boundary,
    double hl_sat_factor,
    x3f_area16_t *output
);

/* Utility: count bits in clipping state */
static inline int x3f_count_clipped_channels(x3f_clip_state_t state) {
  return ((state & 1) ? 1 : 0) + ((state & 2) ? 1 : 0) + ((state & 4) ? 1 : 0);
}

#endif /* X3F_HIGHLIGHT_RECOVERY_H */
