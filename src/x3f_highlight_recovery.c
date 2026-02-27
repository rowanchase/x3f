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
