/* X3F_HIGHLIGHT_RECOVERY.C
 *
 * Library for Foveon X3F highlight recovery using multi-layer reconstruction.
 * Phase 1: Clipping detection and boundary analysis
 *
 * Copyright 2025 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#include "x3f_highlight_recovery.h"
#include "x3f_printf.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define SEARCH_RADIUS 32  /* Quality priority: larger radius for better boundary analysis */

/* Create clipping map structure */
x3f_clip_map_t* x3f_create_clip_map(int width, int height)
{
  x3f_clip_map_t *map = (x3f_clip_map_t*)calloc(1, sizeof(x3f_clip_map_t));
  if (!map) {
    x3f_printf(ERR, "Failed to allocate clip map structure\n");
    return NULL;
  }
  
  map->width = width;
  map->height = height;
  map->pixels = (x3f_pixel_clip_info_t*)calloc(width * height, 
                                                  sizeof(x3f_pixel_clip_info_t));
  if (!map->pixels) {
    x3f_printf(ERR, "Failed to allocate clip map pixels (%d x %d)\n", width, height);
    free(map);
    return NULL;
  }
  
  /* Initialize all states to NONE */
  int i;
  for (i = 0; i < width * height; i++) {
    map->pixels[i].state = CLIP_STATE_NONE;
    map->pixels[i].distance_to_boundary = -1.0f;
    map->pixels[i].has_unclipped_neighbor = 0;
  }
  
  x3f_printf(DEBUG, "Created clip map: %d x %d pixels\n", width, height);
  return map;
}

/* Destroy clipping map */
void x3f_destroy_clip_map(x3f_clip_map_t *map)
{
  if (!map) return;
  
  if (map->pixels) {
    free(map->pixels);
  }
  
  x3f_printf(DEBUG, "Destroyed clip map\n");
  free(map);
}

/* Detect clipping in image - core algorithm */
int x3f_detect_clipping(x3f_area16_t *image, x3f_image_levels_t *ilevels,
                        double hl_threshold, x3f_clip_map_t *map)
{
  int row, col, color;
  
  if (!image || !ilevels || !map) {
    x3f_printf(ERR, "Invalid parameters for clipping detection\n");
    return 0;
  }
  
  if (map->width != image->columns || map->height != image->rows) {
    x3f_printf(ERR, "Clip map dimensions (%dx%d) don't match image (%dx%d)\n",
               map->width, map->height, image->columns, image->rows);
    return 0;
  }
  
  /* Reset statistics */
  map->total_clipped_pixels = 0;
  map->single_channel_clipped = 0;
  map->two_channel_clipped = 0;
  map->all_channel_clipped = 0;
  
  x3f_printf(INFO, "Detecting clipping with threshold %.3f...\n", hl_threshold);
  
  for (row = 0; row < image->rows; row++) {
    for (col = 0; col < image->columns; col++) {
      x3f_pixel_clip_info_t *info = &map->pixels[row * map->width + col];
      info->state = CLIP_STATE_NONE;
      
      /* Get raw values and normalize */
      for (color = 0; color < 3; color++) {
        uint16_t raw_val = image->data[image->row_stride * row + 
                                       image->channels * col + color];
        
        /* Normalize to 0-1 range after black subtraction */
        double range = (double)(ilevels->white[color] - ilevels->black[color]);
        double normalized;
        
        if (range > 0) {
          normalized = (double)(raw_val - ilevels->black[color]) / range;
        } else {
          normalized = 0.0;
        }
        
        /* Clamp to valid range */
        if (normalized < 0.0) normalized = 0.0;
        if (normalized > 1.0) normalized = 1.0;
        
        info->raw_values[color] = (float)normalized;
        info->clip_thresholds[color] = (float)hl_threshold;
        
        /* Check if clipped - Foveon: Blue=0, Green=1, Red=2 */
        if (normalized > hl_threshold) {
          info->state |= (1 << color);
        }
      }
      
      /* Update statistics */
      if (info->state != CLIP_STATE_NONE) {
        map->total_clipped_pixels++;
        int num_clipped = ((info->state & 1) ? 1 : 0) + 
                         ((info->state & 2) ? 1 : 0) + 
                         ((info->state & 4) ? 1 : 0);
        
        if (num_clipped == 1) {
          map->single_channel_clipped++;
        } else if (num_clipped == 2) {
          map->two_channel_clipped++;
        } else if (num_clipped == 3) {
          map->all_channel_clipped++;
        }
      }
    }
  }
  
  x3f_printf(INFO, "Clipping detection complete:\n");
  x3f_printf(INFO, "  Total clipped pixels: %d (%.2f%%)\n", 
             map->total_clipped_pixels,
             100.0 * map->total_clipped_pixels / (map->width * map->height));
  x3f_printf(INFO, "  Single channel: %d\n", map->single_channel_clipped);
  x3f_printf(INFO, "  Two channels: %d\n", map->two_channel_clipped);
  x3f_printf(INFO, "  All channels: %d\n", map->all_channel_clipped);
  
  return 1;
}

/* Analyze boundaries for clipped pixels */
int x3f_analyze_boundaries(x3f_area16_t *image, x3f_clip_map_t *map,
                           x3f_boundary_data_t *boundary)
{
  int row, col, drow, dcol;
  
  if (!image || !map || !boundary) {
    x3f_printf(ERR, "Invalid parameters for boundary analysis\n");
    return 0;
  }
  
  x3f_printf(INFO, "Analyzing boundaries (search radius: %d)...\n", SEARCH_RADIUS);
  
  for (row = 0; row < map->height; row++) {
    for (col = 0; col < map->width; col++) {
      x3f_pixel_clip_info_t *info = &map->pixels[row * map->width + col];
      int idx = row * map->width + col;
      
      if (info->state == CLIP_STATE_NONE) {
        /* Not clipped - mark boundary ratios as invalid */
        boundary->boundary_ratios_bg[idx] = -1.0f;
        boundary->boundary_ratios_br[idx] = -1.0f;
        boundary->boundary_ratios_gr[idx] = -1.0f;
        boundary->gradient_magnitude[idx] = 0.0f;
        continue;
      }
      
      /* Search for unclipped neighbors in expanding rings */
      float sum_bg = 0.0f, sum_br = 0.0f, sum_gr = 0.0f;
      float weight_sum = 0.0f;
      float min_distance = (float)SEARCH_RADIUS;
      int found_neighbor = 0;
      
      for (drow = -SEARCH_RADIUS; drow <= SEARCH_RADIUS; drow++) {
        for (dcol = -SEARCH_RADIUS; dcol <= SEARCH_RADIUS; dcol++) {
          int nrow = row + drow;
          int ncol = col + dcol;
          
          /* Bounds check */
          if (nrow < 0 || nrow >= map->height || ncol < 0 || ncol >= map->width)
            continue;
          
          /* Skip if this neighbor is also clipped */
          x3f_pixel_clip_info_t *neighbor = &map->pixels[nrow * map->width + ncol];
          if (neighbor->state != CLIP_STATE_NONE)
            continue;
          
          /* Calculate distance and weight */
          float distance = sqrtf((float)(drow * drow + dcol * dcol));
          
          /* Quality priority: Gaussian weighting for smoother results */
          float sigma = (float)SEARCH_RADIUS / 3.0f;
          float weight = expf(-(distance * distance) / (2.0f * sigma * sigma));
          
          /* Get neighbor's unclipped values */
          float nb = neighbor->raw_values[0];  /* Blue */
          float ng = neighbor->raw_values[1];  /* Green */
          float nr = neighbor->raw_values[2];  /* Red */
          
          /* Compute color ratios for reconstruction */
          /* Blue/Green ratio */
          if (ng > 0.001f) {
            sum_bg += (nb / ng) * weight;
          }
          
          /* Blue/Red ratio */
          if (nr > 0.001f) {
            sum_br += (nb / nr) * weight;
          }
          
          /* Green/Red ratio */
          if (nr > 0.001f) {
            sum_gr += (ng / nr) * weight;
          }
          
          weight_sum += weight;
          if (distance < min_distance) {
            min_distance = distance;
          }
          found_neighbor = 1;
        }
      }
      
      /* Store results */
      info->distance_to_boundary = min_distance;
      info->has_unclipped_neighbor = found_neighbor;
      
      if (found_neighbor && weight_sum > 0.0f) {
        boundary->boundary_ratios_bg[idx] = sum_bg / weight_sum;
        boundary->boundary_ratios_br[idx] = sum_br / weight_sum;
        boundary->boundary_ratios_gr[idx] = sum_gr / weight_sum;
      } else {
        /* No unclipped neighbors found within search radius */
        boundary->boundary_ratios_bg[idx] = -1.0f;
        boundary->boundary_ratios_br[idx] = -1.0f;
        boundary->boundary_ratios_gr[idx] = -1.0f;
      }
      
      /* Calculate local gradient magnitude for Poisson weighting */
      float grad = 0.0f;
      if (col > 0 && col < map->width - 1 && row > 0 && row < map->height - 1) {
        /* Horizontal gradient */
        float diff_b_h = info->raw_values[0] - map->pixels[row * map->width + col - 1].raw_values[0];
        float diff_g_h = info->raw_values[1] - map->pixels[row * map->width + col - 1].raw_values[1];
        float diff_r_h = info->raw_values[2] - map->pixels[row * map->width + col - 1].raw_values[2];
        
        /* Vertical gradient */
        float diff_b_v = info->raw_values[0] - map->pixels[(row - 1) * map->width + col].raw_values[0];
        float diff_g_v = info->raw_values[1] - map->pixels[(row - 1) * map->width + col].raw_values[1];
        float diff_r_v = info->raw_values[2] - map->pixels[(row - 1) * map->width + col].raw_values[2];
        
        /* Total gradient magnitude */
        grad = sqrtf(diff_b_h * diff_b_h + diff_g_h * diff_g_h + diff_r_h * diff_r_h +
                     diff_b_v * diff_b_v + diff_g_v * diff_g_v + diff_r_v * diff_r_v);
      }
      boundary->gradient_magnitude[idx] = grad;
    }
  }
  
  x3f_printf(INFO, "Boundary analysis complete\n");
  return 1;
}

/* Create boundary data structure */
x3f_boundary_data_t* x3f_create_boundary_data(int width, int height)
{
  x3f_boundary_data_t *boundary = (x3f_boundary_data_t*)calloc(1, sizeof(x3f_boundary_data_t));
  if (!boundary) {
    x3f_printf(ERR, "Failed to allocate boundary data structure\n");
    return NULL;
  }
  
  size_t pixel_count = (size_t)width * height;
  
  boundary->boundary_ratios_bg = (float*)calloc(pixel_count, sizeof(float));
  boundary->boundary_ratios_br = (float*)calloc(pixel_count, sizeof(float));
  boundary->boundary_ratios_gr = (float*)calloc(pixel_count, sizeof(float));
  boundary->gradient_magnitude = (float*)calloc(pixel_count, sizeof(float));
  
  if (!boundary->boundary_ratios_bg || !boundary->boundary_ratios_br ||
      !boundary->boundary_ratios_gr || !boundary->gradient_magnitude) {
    x3f_printf(ERR, "Failed to allocate boundary data arrays\n");
    x3f_free_boundary_data(boundary);
    return NULL;
  }
  
  /* Initialize to invalid values */
  size_t i;
  for (i = 0; i < pixel_count; i++) {
    boundary->boundary_ratios_bg[i] = -1.0f;
    boundary->boundary_ratios_br[i] = -1.0f;
    boundary->boundary_ratios_gr[i] = -1.0f;
    boundary->gradient_magnitude[i] = 0.0f;
  }
  
  x3f_printf(DEBUG, "Created boundary data: %d x %d pixels\n", width, height);
  return boundary;
}

/* Free boundary data */
void x3f_free_boundary_data(x3f_boundary_data_t *boundary)
{
  if (!boundary) return;
  
  if (boundary->boundary_ratios_bg) free(boundary->boundary_ratios_bg);
  if (boundary->boundary_ratios_br) free(boundary->boundary_ratios_br);
  if (boundary->boundary_ratios_gr) free(boundary->boundary_ratios_gr);
  if (boundary->gradient_magnitude) free(boundary->gradient_magnitude);
  
  x3f_printf(DEBUG, "Freed boundary data\n");
  free(boundary);
}

/* =========================================================================
 * Phase 2: Multi-Channel Highlight Reconstruction
 * ========================================================================= */

/* Spectral constants from Fent & Meldrum (2016) - QE at 500-575nm */
static const float QE_BLUE = 10.6f;
static const float QE_GREEN = 13.2f;
static const float QE_RED = 9.0f;

/* Smoothstep function for blending (Hermite interpolation) */
static inline float smoothstep(float edge0, float edge1, float x)
{
  float t = (x - edge0) / (edge1 - edge0);
  t = (t < 0.0f) ? 0.0f : ((t > 1.0f) ? 1.0f : t);
  return t * t * (3.0f - 2.0f * t);
}

/* Linear interpolation */
static inline float lerp(float a, float b, float t)
{
  return a + t * (b - a);
}

/* Case 1: Single channel clipped - reconstruct from two unclipped channels */
static void reconstruct_single_channel(
    x3f_pixel_clip_info_t *info,
    x3f_boundary_data_t *boundary,
    int idx,
    float *output)
{
  x3f_clip_state_t state = info->state;
  float blend, reconstructed[3];
  float max_dist = 32.0f; /* SEARCH_RADIUS */
  
  /* Initialize with original values */
  reconstructed[0] = info->raw_values[0];
  reconstructed[1] = info->raw_values[1];
  reconstructed[2] = info->raw_values[2];
  
  switch (state) {
    case CLIP_STATE_BLUE:
      /* Blue clipped, use Green and Red with boundary ratios */
      {
        float ratio_bg = boundary->boundary_ratios_bg[idx];
        float ratio_br = boundary->boundary_ratios_br[idx];
        float estimate_bg, estimate_br;
        
        /* Estimate from B/G ratio: B = G * (B/G) */
        if (ratio_bg > 0.0f && info->raw_values[1] > 0.001f) {
          estimate_bg = info->raw_values[1] * ratio_bg;
        } else {
          estimate_bg = info->raw_values[1] * (QE_BLUE / QE_GREEN);
        }
        
        /* Estimate from B/R ratio: B = R * (B/R) */
        if (ratio_br > 0.0f && info->raw_values[2] > 0.001f) {
          estimate_br = info->raw_values[2] * ratio_br;
        } else {
          estimate_br = info->raw_values[2] * (QE_BLUE / QE_RED);
        }
        
        /* Weighted average: prefer B/G as it's more stable (closer layers) */
        reconstructed[0] = 0.6f * estimate_bg + 0.4f * estimate_br;
      }
      break;
      
    case CLIP_STATE_GREEN:
      /* Green clipped, use Blue and Red with boundary ratios */
      {
        float ratio_bg = boundary->boundary_ratios_bg[idx];
        float ratio_gr = boundary->boundary_ratios_gr[idx];
        float estimate_bg, estimate_gr;
        
        /* Estimate from G/B ratio: G = B / (B/G) */
        if (ratio_bg > 0.0f && info->raw_values[0] > 0.001f) {
          estimate_bg = info->raw_values[0] / ratio_bg;
        } else {
          estimate_bg = info->raw_values[0] * (QE_GREEN / QE_BLUE);
        }
        
        /* Estimate from G/R ratio: G = R * (G/R) */
        if (ratio_gr > 0.0f && info->raw_values[2] > 0.001f) {
          estimate_gr = info->raw_values[2] * ratio_gr;
        } else {
          estimate_gr = info->raw_values[2] * (QE_GREEN / QE_RED);
        }
        
        /* Average the two estimates */
        reconstructed[1] = (estimate_bg + estimate_gr) / 2.0f;
      }
      break;
      
    case CLIP_STATE_RED:
      /* Red clipped, use Blue and Green with boundary ratios */
      {
        float ratio_br = boundary->boundary_ratios_br[idx];
        float ratio_gr = boundary->boundary_ratios_gr[idx];
        float estimate_br, estimate_gr;
        
        /* Estimate from R/B ratio: R = B / (B/R) */
        if (ratio_br > 0.0f && info->raw_values[0] > 0.001f) {
          estimate_br = info->raw_values[0] / ratio_br;
        } else {
          estimate_br = info->raw_values[0] * (QE_RED / QE_BLUE);
        }
        
        /* Estimate from R/G ratio: R = G / (G/R) */
        if (ratio_gr > 0.0f && info->raw_values[1] > 0.001f) {
          estimate_gr = info->raw_values[1] / ratio_gr;
        } else {
          estimate_gr = info->raw_values[1] * (QE_RED / QE_GREEN);
        }
        
        /* Average the two estimates */
        reconstructed[2] = (estimate_br + estimate_gr) / 2.0f;
      }
      break;
      
    default:
      /* Should not reach here for single channel case */
      break;
  }
  
  /* Apply smoothstep blending based on distance to boundary (30% zone) */
  blend = smoothstep(0.0f, 0.3f * max_dist, info->distance_to_boundary);
  
  output[0] = lerp(info->raw_values[0], reconstructed[0], blend);
  output[1] = lerp(info->raw_values[1], reconstructed[1], blend);
  output[2] = lerp(info->raw_values[2], reconstructed[2], blend);
}

/* Case 2: Two channels clipped - simplified spectral estimation (no hierarchy) */
static void reconstruct_two_channels(
    x3f_pixel_clip_info_t *info,
    float *output)
{
  x3f_clip_state_t state = info->state;
  float blend, reconstructed[3];
  float max_dist = 32.0f; /* SEARCH_RADIUS */
  
  /* Initialize with original values */
  reconstructed[0] = info->raw_values[0];
  reconstructed[1] = info->raw_values[1];
  reconstructed[2] = info->raw_values[2];
  
  switch (state) {
    case CLIP_STATE_BG:
      /* Blue+Green clipped, Red valid - estimate from Red */
      reconstructed[2] = info->raw_values[2]; /* Red preserved */
      /* Conservative estimates from spectral response */
      reconstructed[0] = info->raw_values[2] * (QE_BLUE / QE_RED) * 0.75f;
      reconstructed[1] = info->raw_values[2] * (QE_GREEN / QE_RED) * 0.95f;
      break;
      
    case CLIP_STATE_BR:
      /* Blue+Red clipped, Green valid - estimate from Green */
      reconstructed[1] = info->raw_values[1]; /* Green preserved */
      reconstructed[0] = info->raw_values[1] * (QE_BLUE / QE_GREEN) * 0.95f;
      reconstructed[2] = info->raw_values[1] * (QE_RED / QE_GREEN) * 1.05f;
      break;
      
    case CLIP_STATE_GR:
      /* Green+Red clipped, Blue valid - estimate from Blue */
      reconstructed[0] = info->raw_values[0]; /* Blue preserved */
      reconstructed[1] = info->raw_values[0] * (QE_GREEN / QE_BLUE) * 1.05f;
      reconstructed[2] = info->raw_values[0] * (QE_RED / QE_BLUE) * 0.85f;
      break;
      
    default:
      /* Should not reach here for two channel case */
      break;
  }
  
  /* Apply smoothstep blending based on distance to boundary (30% zone) */
  blend = smoothstep(0.0f, 0.3f * max_dist, info->distance_to_boundary);
  
  output[0] = lerp(info->raw_values[0], reconstructed[0], blend);
  output[1] = lerp(info->raw_values[1], reconstructed[1], blend);
  output[2] = lerp(info->raw_values[2], reconstructed[2], blend);
}

/* Case 3: All channels clipped - graceful desaturation */
static void reconstruct_all_channels(
    x3f_pixel_clip_info_t *info,
    double hl_sat_factor,
    float *output)
{
  float max_luminance = 0.0f;
  float desat, reconstructed[3];
  float variation = 0.0f;
  int c;
  
  /* Find the "least clipped" channel (highest value) */
  for (c = 0; c < 3; c++) {
    if (info->raw_values[c] > max_luminance) {
      max_luminance = info->raw_values[c];
    }
  }
  
  /* Cap at white point */
  if (max_luminance > 1.0f) max_luminance = 1.0f;
  
  /* Apply desaturation factor from metadata (limit to max 0.8) */
  desat = (float)hl_sat_factor;
  if (desat > 0.8f) desat = 0.8f;
  
  /* Generate desaturated color towards white */
  for (c = 0; c < 3; c++) {
    reconstructed[c] = max_luminance * (0.5f + 0.5f * desat);
  }
  
  /* Add subtle variation if we have unclipped neighbors */
  if (info->has_unclipped_neighbor) {
    variation = (max_luminance - 0.98f) * 10.0f;
    if (variation < 0.0f) variation = 0.0f;
    if (variation > 0.2f) variation = 0.2f;
    
    for (c = 0; c < 3; c++) {
      reconstructed[c] -= variation * 0.05f;
    }
  }
  
  /* For all-channel clipping, use stronger blending near boundary */
  float blend = smoothstep(0.0f, 0.3f * 32.0f, info->distance_to_boundary);
  
  for (c = 0; c < 3; c++) {
    output[c] = lerp(info->raw_values[c], reconstructed[c], blend);
  }
}

/* Main Phase 2 reconstruction function */
int x3f_reconstruct_highlights(
    x3f_area16_t *image,
    x3f_clip_map_t *clip_map,
    x3f_boundary_data_t *boundary,
    double hl_sat_factor,
    x3f_area16_t *output)
{
  int row, col, idx;
  int width, height;
  size_t data_size;
  
  if (!image || !clip_map || !boundary || !output) {
    x3f_printf(ERR, "Invalid parameters for highlight reconstruction\n");
    return 0;
  }
  
  width = image->columns;
  height = image->rows;
  
  /* Allocate output buffer */
  data_size = (size_t)width * height * 3 * sizeof(uint16_t);
  output->data = (uint16_t*)malloc(data_size);
  if (!output->data) {
    x3f_printf(ERR, "Failed to allocate reconstruction buffer (%zu bytes)\n", data_size);
    return 0;
  }
  
  output->rows = height;
  output->columns = width;
  output->channels = 3;
  output->row_stride = width * 3;
  output->buf = output->data;  /* For proper cleanup */
  
  x3f_printf(INFO, "Reconstructing highlights: %d clipped pixels...\n",
             clip_map->total_clipped_pixels);
  
  /* Process all pixels */
  for (row = 0; row < height; row++) {
    for (col = 0; col < width; col++) {
      idx = row * width + col;
      x3f_pixel_clip_info_t *info = &clip_map->pixels[idx];
      float reconstructed[3];
      int c;
      
      if (info->state == CLIP_STATE_NONE) {
        /* Unclipped pixel - copy directly */
        for (c = 0; c < 3; c++) {
          reconstructed[c] = info->raw_values[c];
        }
      } else {
        int num_clipped = x3f_count_clipped_channels(info->state);
        
        if (num_clipped == 1) {
          /* Case 1: Single channel clipped */
          reconstruct_single_channel(info, boundary, idx, reconstructed);
        } else if (num_clipped == 2) {
          /* Case 2: Two channels clipped (simplified) */
          reconstruct_two_channels(info, reconstructed);
        } else {
          /* Case 3: All channels clipped */
          reconstruct_all_channels(info, hl_sat_factor, reconstructed);
        }
      }
      
      /* Convert float [0-1] to uint16_t [0-65535] */
      for (c = 0; c < 3; c++) {
        float val = reconstructed[c];
        /* Clamp to valid range */
        if (val < 0.0f) val = 0.0f;
        if (val > 1.0f) val = 1.0f;
        output->data[idx * 3 + c] = (uint16_t)(val * 65535.0f);
      }
    }
  }
  
  x3f_printf(INFO, "Highlight reconstruction complete\n");
  return 1;
}
