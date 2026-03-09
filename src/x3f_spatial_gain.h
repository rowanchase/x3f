/* X3F_SPATIAL_GAIN.H
 *
 * Library for adjusting for spatial gain in X3F images.
 *
 * Copyright 2015 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#ifndef X3F_SPATIAL_GAIN_H
#define X3F_SPATIAL_GAIN_H

#include "x3f_io.h"

typedef struct {
  double weight;

  uint32_t *gain;
  double mingain, delta;
} x3f_spatial_gain_corr_merrill_t;

typedef struct {
  double *gain;		    /* final gain (interpolated if necessary) */
  int malloc;		    /* 1 if gain is allocated with malloc() */

  int rows, cols;
  int rowoff, coloff, rowpitch, colpitch;
  int chan, channels;

  x3f_spatial_gain_corr_merrill_t mgain[4]; /* raw Merrill-type gains */
  int mgain_num;
} x3f_spatial_gain_corr_t;

#define MAXCORR 6 /* Quattro HP: R, G, B0, B1, B2, B3 */

#define MERRILL_COLOR_GRID_ROWS 7
#define MERRILL_COLOR_GRID_COLS 7
#define MERRILL_COLOR_CHANNELS 3

/* 7x7 grid of per-channel correction factors for Merrill spatial color correction */
typedef struct {
  double gain[MERRILL_COLOR_CHANNELS];  /* [0]=R, [1]=G, [2]=B multipliers */
} x3f_merrill_color_cell_t;

typedef struct {
  x3f_merrill_color_cell_t grid[MERRILL_COLOR_GRID_ROWS][MERRILL_COLOR_GRID_COLS];
  int is_loaded;  /* Flag to indicate if correction is available */
} x3f_merrill_spatial_color_t;

extern int x3f_load_merrill_spatial_color(x3f_t *x3f, x3f_merrill_spatial_color_t *color_corr);
extern double x3f_calc_merrill_color_gain(x3f_merrill_spatial_color_t *color_corr,
                                          int row, int col, int chan,
                                          int rows, int cols);

extern int x3f_get_merrill_type_spatial_gain(x3f_t *x3f, int hp_flag,
					     x3f_spatial_gain_corr_t *corr);
extern int x3f_get_interp_merrill_type_spatial_gain(x3f_t *x3f, int hp_flag,
						    x3f_spatial_gain_corr_t *corr);
extern int x3f_get_classic_spatial_gain(x3f_t *x3f, char *wb,
					x3f_spatial_gain_corr_t *corr);
extern int x3f_get_spatial_gain(x3f_t *x3f, char *wb,
				x3f_spatial_gain_corr_t *corr);
extern void x3f_cleanup_spatial_gain(x3f_spatial_gain_corr_t *corr,
				     int corr_num);
extern double x3f_calc_spatial_gain(x3f_spatial_gain_corr_t *corr,
				    int corr_num,
				    int row, int col, int chan,
				    int rows, int cols);
extern double x3f_calc_color_shading_correction(double *csf_matrix,
						 int row, int col,
						 int rows, int cols,
						 int chan);

#endif
