/* X3F_SPATIAL_GAIN.C
 *
 * Library for adjusting for spatial gain in X3F images.
 *
 * Copyright 2015 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#include "x3f_spatial_gain.h"
#include "x3f_meta.h"
#include "x3f_printf.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Multiplier for spatial gain Delta values
 * Increases the spatial variation of vignette correction
 * Default: 1.0 (use camera's native values)
 * Higher values (e.g., 1.5-2.0) increase vignette correction strength
 */
#define SPATIAL_GAIN_DELTA_MULTIPLIER 1.6

static double lens_position(double focal_length, double object_distance)
{
  return 1.0/(1.0/focal_length - 1.0/object_distance);
}

static double get_focal_length(x3f_t *x3f)
{
  char *flength;
  double focal_length;

  if (x3f_get_prop_entry(x3f, "FLENGTH", &flength))
    focal_length = atof(flength);
  else {
    focal_length = 30.0;
    x3f_printf(WARN, "Could not get focal length, assuming %g mm\n",
	       focal_length);
  }

  return focal_length;
}

static double get_object_distance(x3f_t *x3f)
{
  double object_distance;

  if (x3f_get_camf_float(x3f, "ObjectDistance", &object_distance))
    object_distance *= 10.0;	/* Convert cm to mm */
  else {
    object_distance = INFINITY;
    x3f_printf(WARN, "Could not get object distance, assuming %g mm\n",
	       object_distance);
  }

  return object_distance;
}

/* Get the minimum object distance (MOD)  */
static double get_MOD(x3f_t *x3f)
{
  int32_t lens_information;
  double mod;

  if (!x3f_get_camf_signed(x3f, "LensInformation", &lens_information))
    lens_information = -1;

  /* TODO: is there any better way of obtaining MOD? */
  switch (lens_information) {
  case 1003:			/* DP1 Merrill */
    mod = 200.0;
    break;
  case 1004:			/* DP2 Merrill */
    mod = 280.0;
    break;
  case 1005:			/* DP3 Merrill */
    mod = 226.0;
    break;
  default:
    mod = 280.0;
    x3f_printf(WARN, "Could not get MOD, assuming %g mm\n", mod);
  }

  return mod;
}

static int get_merrill_type_gains_table(x3f_t *x3f, char *name, char *chan,
					uint32_t **mgain, int *rows, int *cols,
					double *mingain, double *delta)
{
  char table[32], *val;
  int rows_tmp, cols_tmp;

  sprintf(table, "GainsTable%s", chan);
  if (!x3f_get_camf_property(x3f, name, table, &val) ||
      !x3f_get_camf_matrix_var(x3f, val, &rows_tmp, &cols_tmp, NULL,
			       M_UINT, (void **)mgain) ||
      (*rows != -1 && *rows != rows_tmp) ||
      (*cols != -1 && *cols != cols_tmp))
    return 0;
  *rows = rows_tmp;
  *cols = cols_tmp;

  sprintf(table, "MinGains%s", chan);
  if (!x3f_get_camf_property(x3f, name, table, &val)) return 0;
  *mingain = atof(val);

  sprintf(table, "Delta%s", chan);
  if (!x3f_get_camf_property(x3f, name, table, &val)) return 0;
  *delta = atof(val) * SPATIAL_GAIN_DELTA_MULTIPLIER;

  return 1;
}

typedef struct merrill_spatial_gain_s {
  char *name;
  double x,y;
  struct merrill_spatial_gain_s *next;
} merrill_spatial_gain_t;


int x3f_get_merrill_type_spatial_gain(x3f_t *x3f, int hp_flag,
				      x3f_spatial_gain_corr_t *corr)
{
  char **include_blocks, **include_blocks_val;
  uint32_t include_blocks_num;
  double capture_aperture;
  double *spatial_gain_fstop;
  int num_fstop;
  int corr_num = 3;

  merrill_spatial_gain_t *gains = NULL, *g;
  merrill_spatial_gain_t *q_closest[4] = {NULL, NULL, NULL, NULL};
  double q_closest_dx[4] = {INFINITY, -INFINITY, -INFINITY, INFINITY};
  double q_closest_dy[4] = {INFINITY, INFINITY, -INFINITY, -INFINITY};
  double q_closest_d2[4] = {INFINITY, INFINITY, INFINITY, INFINITY};
  double q_weight_x[4], q_weight_y[4], q_weight[4];
  double x,y;
  int i;

  if (!x3f_get_camf_float(x3f, "CaptureAperture", &capture_aperture)) return 0;

  if (!x3f_get_camf_property_list(x3f, "IncludeBlocks",
				  &include_blocks, &include_blocks_val,
				  &include_blocks_num))
    return 0;

  if (hp_flag) {		/* Quattro HP */
    if (!x3f_get_camf_matrix_var(x3f, "SpatialGainHP_Fstop",
				 &num_fstop, NULL, NULL,
				 M_FLOAT, (void **)&spatial_gain_fstop))
      return 0;
    corr_num = 6; /* R, G, B0, B1, B2, B3 */

    for (i=0; i<include_blocks_num; i++) {
      char **names, **values;
      uint32_t num, aperture_index;
      char dummy;

      if (sscanf(include_blocks[i], "SpatialGainHPProps_%d%c",
		 &aperture_index, &dummy) == 1 &&
	  x3f_get_camf_property_list(x3f, include_blocks[i],
				     &names, &values, &num) &&
	  aperture_index >= 0 && aperture_index < num_fstop) {
	g = alloca(sizeof(merrill_spatial_gain_t));
	g->name = include_blocks[i];
	g->x = 1.0/spatial_gain_fstop[aperture_index];
	g->y = 0.0;		/* unused */
	g->next = gains;
	gains = g;
      }
    }

    x = 1.0/capture_aperture;
    y = 0.0;			/* unused */
  }
  else {			/* Merrill and Quattro */
    if (x3f_get_camf_matrix_var(x3f, "SpatialGain_Fstop",
				&num_fstop, NULL, NULL,
				M_FLOAT, (void **)&spatial_gain_fstop))
      for (i=0; i<include_blocks_num; i++) {
	char **names, **values;
	uint32_t num, aperture_index;
	char focus_distance[4], dummy;

	if (sscanf(include_blocks[i], "SpatialGainsProps_%d_%3s%c",
		   &aperture_index, focus_distance, &dummy) == 2 &&
	    x3f_get_camf_property_list(x3f, include_blocks[i],
				       &names, &values, &num) &&
	    aperture_index >= 0 && aperture_index < num_fstop) {
	  double lenspos;

	  if (!strcmp(focus_distance, "INF"))
	    lenspos = lens_position(get_focal_length(x3f), INFINITY);
	  else if (!strcmp(focus_distance, "MOD"))
	    lenspos = lens_position(get_focal_length(x3f), get_MOD(x3f));
	  else continue;

	  g = alloca(sizeof(merrill_spatial_gain_t));
	  g->name = include_blocks[i];
	  g->x = 1.0/spatial_gain_fstop[aperture_index];
	  g->y = lenspos;
	  g->next = gains;
	  gains = g;
	}
      }
    else
      for (i=0; i<include_blocks_num; i++) {
	char **names, **values;
	uint32_t num;
	double aperture, lenspos;
	char dummy;

	if (sscanf(include_blocks[i], "SpatialGainsProps_%lf_%lf%c",
		   &aperture, &lenspos, &dummy) == 2 &&
	    x3f_get_camf_property_list(x3f, include_blocks[i],
				       &names, &values, &num)) {
	  g = alloca(sizeof(merrill_spatial_gain_t));
	  g->name = include_blocks[i];
	  g->x = 1.0/aperture;
	  g->y = lenspos;
	  g->next = gains;
	  gains = g;
	}
      }

    /* TODO: doing bilinear interpolation with respect to 1/aperture
       and lens position. Is that correct? */
    x = 1.0/capture_aperture;
    y = lens_position(get_focal_length(x3f), get_object_distance(x3f));
  }

  for (g=gains; g; g=g->next) {
    double dx = g->x - x;
    double dy = g->y - y;
    double d2 = dx*dx + dy*dy;
    int q;

    if      (dx > 0.0 && dy > 0.0) q = 0;
    else if (dx > 0.0)             q = 3;
    else if (dy > 0.0)             q = 1;
    else                           q = 2;

    if (d2 < q_closest_d2[q]) {
      q_closest[q] = g;
      q_closest_dx[q] = dx;
      q_closest_dy[q] = dy;
      q_closest_d2[q] = d2;
    }
  }

  /* TODO: bilinear interpolation requires that the points be laid out
     in a more or less rectilinear grid. Is that assumption good
     enough? It appears to be valid for the current cameras. */
  q_weight_x[0] = q_closest_dx[1]/(q_closest_dx[1] - q_closest_dx[0]);
  q_weight_x[1] = q_closest_dx[0]/(q_closest_dx[0] - q_closest_dx[1]);
  q_weight_x[2] = q_closest_dx[3]/(q_closest_dx[3] - q_closest_dx[2]);
  q_weight_x[3] = q_closest_dx[2]/(q_closest_dx[2] - q_closest_dx[3]);

  q_weight_y[0] = q_closest_dy[3]/(q_closest_dy[3] - q_closest_dy[0]);
  q_weight_y[1] = q_closest_dy[2]/(q_closest_dy[2] - q_closest_dy[1]);
  q_weight_y[2] = q_closest_dy[1]/(q_closest_dy[1] - q_closest_dy[2]);
  q_weight_y[3] = q_closest_dy[0]/(q_closest_dy[0] - q_closest_dy[3]);

  x3f_printf(DEBUG, "x = %f y = %f\n", x, y);
  for (i=0; i<4; i++) {
    if (q_closest[i])
      x3f_printf(DEBUG, "q = %d name = %s x = %f y = %f\n",
		 i, q_closest[i]->name, q_closest[i]->x, q_closest[i]->y);
    else
      x3f_printf(DEBUG, "q = %d name = NULL\n", i);
    x3f_printf(DEBUG, "q = %d dx = %f dy = %f d2 = %f wx = %f wy = %f\n",
	       i, q_closest_dx[i], q_closest_dy[i], q_closest_d2[i],
	       q_weight_x[i], q_weight_y[i]);
  }

  for (i=0; i<4; i++) {
    if (isnan(q_weight_x[i])) q_weight_x[i] = 1.0;
    if (isnan(q_weight_y[i])) q_weight_y[i] = 1.0;
    q_weight[i] = q_weight_x[i]*q_weight_y[i];
  }

  for (i=0; i<4; i++)
    x3f_printf(DEBUG, "q = %d name = %s w = %f\n",
	       i, q_closest[i] ? q_closest[i]->name : "NULL", q_weight[i]);

  for (i=0; i<corr_num; i++) {
    x3f_spatial_gain_corr_t *c = &corr[i];
    c->gain = NULL;		/* No interploated gains present */
    c->malloc = 0;

    c->rows = c->cols = -1;
    c->rowoff = c->coloff = 0;
    c->rowpitch = c->colpitch = 1;
    c->chan = i;
    c->channels = 1;

    c->mgain_num = 0;
  }

  if (hp_flag) {
    corr[2].rowoff = 0;
    corr[2].coloff = 0;
    corr[2].rowpitch = corr[2].colpitch = 2;
    corr[2].chan = 2;

    corr[3].rowoff = 0;
    corr[3].coloff = 1;
    corr[3].rowpitch = corr[3].colpitch = 2;
    corr[3].chan = 2;

    corr[4].rowoff = 1;
    corr[4].coloff = 0;
    corr[4].rowpitch = corr[4].colpitch = 2;
    corr[4].chan = 2;

    corr[5].rowoff = 1;
    corr[5].coloff = 1;
    corr[5].rowpitch = corr[5].colpitch = 2;
    corr[5].chan = 2;
  }

  for (i=0; i<4; i++) {
    char *name;
    char *channels_normal[3] = {"R", "G", "B"};
    char *channels_hp[6] = {"R", "G", "B0", "B1", "B2", "B3"};
    char **channels = hp_flag ? channels_hp : channels_normal;
    int j;

    if (!q_closest[i]) continue;
    name = q_closest[i]->name;

    for (j=0; j<corr_num; j++) {
      x3f_spatial_gain_corr_t *c = &corr[j];
      x3f_spatial_gain_corr_merrill_t *m = &c->mgain[c->mgain_num++];

      m->weight = q_weight[i];
      if (!get_merrill_type_gains_table(x3f, name, channels[j],
					&m->gain, &c->rows, &c->cols,
					&m->mingain, &m->delta))
	return 0;
    }
  }

  for (i=0; i<corr_num; i++)
    if (corr[i].mgain_num == 0) return 0;

  return corr_num;
}

int x3f_get_interp_merrill_type_spatial_gain(x3f_t *x3f, int hp_flag,
					     x3f_spatial_gain_corr_t *corr)
{
  int corr_num = x3f_get_merrill_type_spatial_gain(x3f, hp_flag, corr);
  int i;

  for (i=0; i<corr_num; i++) {
    x3f_spatial_gain_corr_t *c = &corr[i];
    int j, num = c->rows*c->cols*c->channels;

    c->gain = malloc(num*sizeof(double));
    c->malloc = 1;

    for (j=0; j<num; j++) {
      int g;

      c->gain[j] = 0.0;
      for (g=0; g < c->mgain_num; g++) {
	x3f_spatial_gain_corr_merrill_t *m = &c->mgain[g];
	c->gain[j] += m->weight*(m->mingain + m->delta*m->gain[j]);
      }
    }
  }

  return corr_num;
}

int x3f_get_classic_spatial_gain(x3f_t *x3f, char *wb,
				 x3f_spatial_gain_corr_t *corr)
{
  char *gain_name;

  if ((x3f_get_camf_property(x3f, "SpatialGainTables", wb, &gain_name) &&
       x3f_get_camf_matrix_var(x3f, gain_name,
			       &corr->rows, &corr->cols, &corr->channels,
			       M_FLOAT, (void **)&corr->gain)) ||
      x3f_get_camf_matrix_var(x3f, "SpatialGain",
			      &corr->rows, &corr->cols, &corr->channels,
			      M_FLOAT, (void **)&corr->gain)) {
    corr->malloc = 0;
    corr->rowoff = corr->coloff = 0;
    corr->rowpitch = corr->colpitch = 1;
    corr->chan = 0;
    corr->mgain_num = 0;

    return 1;
  }

  return 0;
}

int x3f_get_spatial_gain(x3f_t *x3f, char *wb, x3f_spatial_gain_corr_t *corr)
{
  int corr_num = 0;

  corr_num += x3f_get_interp_merrill_type_spatial_gain(x3f, 0, &corr[corr_num]);
  if (corr_num == 0)
    corr_num += x3f_get_classic_spatial_gain(x3f, wb, &corr[corr_num]);

  return corr_num;
}

void x3f_cleanup_spatial_gain(x3f_spatial_gain_corr_t *corr, int corr_num)
{
  int i;

  for (i=0; i<corr_num; i++)
    if (corr[i].malloc) free(corr[i].gain);
}

double x3f_calc_spatial_gain(x3f_spatial_gain_corr_t *corr, int corr_num,
			     int row, int col, int chan, int rows, int cols)
{
  double gain = 1.0;
  double rrel = (double)row/rows;
  double crel = (double)col/cols;
  int i;

  for (i=0; i<corr_num; i++) {
    x3f_spatial_gain_corr_t *c = &corr[i];
    double rc, cc;
    int ri, ci;
    double rf, cf;
    double *r1, *r2;
    int co1, co2;
    double gr1, gr2;
    int ch = chan - c->chan;

    if (ch < 0 || ch >= c->channels) continue;

    if (row%c->rowpitch != c->rowoff) continue;
    if (col%c->colpitch != c->coloff) continue;

    rc = rrel*(c->rows-1);
    ri = (int)floor(rc);
    rf = rc - ri;

    cc = crel*(c->cols-1);
    ci = (int)floor(cc);
    cf = cc - ci;

    if (ri < 0)
      r1 = r2 = &c->gain[0];
    else if (ri >= c->rows-1)
      r1 = r2 = &c->gain[(c->rows-1)*c->cols*c->channels];
    else {
      r1 = &c->gain[ri*c->cols*c->channels];
      r2 = &c->gain[(ri+1)*c->cols*c->channels];
    }

    if (ci < 0)
      co1 = co2 = ch;
    if (ci >= c->cols-1)
      co1 = co2 = (c->cols-1)*c->channels + ch;
    else {
      co1 = ci*c->channels + ch;
      co2 = (ci+1)*c->channels + ch;
    }

    gr1 = r1[co1] + cf*(r1[co2]-r1[co1]);
    gr2 = r2[co1] + cf*(r2[co2]-r2[co1]);

    gain *= gr1 + rf*(gr2-gr1);
  }

  return gain;
}

/* Calculate color shading correction using gradient interpolation
 * 
 * The ColorShadingFactor is a 2x2 matrix [[a, b], [c, d]]:
 *   - Row 0 [a,b]: R channel gradient (a = column gradient, b = row gradient)
 *   - Row 1 [c,d]: B channel gradient (c = column gradient, d = row gradient)
 * 
 * The correction is applied as:
 *   - R channel: 1.0 + a * col_norm + b * row_norm
 *   - G channel: 1.0 (no correction)
 *   - B channel: 1.0 + c * col_norm + d * row_norm
 *
 * Parameters:
 *   csf_matrix: 2x2 ColorShadingFactor matrix [a, b, c, d]
 *   row, col:   Pixel position
 *   rows, cols: Image dimensions
 *   chan:       Color channel (0=R, 1=G, 2=B)
 *
 * Returns:
 *   Multiplicative correction factor to apply to the pixel
 */
double x3f_calc_color_shading_correction(double *csf_matrix,
					 int row, int col,
					 int rows, int cols,
					 int chan)
{
  double row_norm = (double)row / (rows - 1);
  double col_norm = (double)col / (cols - 1);
  
  double r_col = csf_matrix[0];  /* R column gradient */
  double r_row = csf_matrix[1];  /* R row gradient */
  double b_col = csf_matrix[2];  /* B column gradient */
  double b_row = csf_matrix[3];  /* B row gradient */
  
  double correction = 1.0;
  
  if (chan == 0) {
    /* R channel: gradient from top-left */
    correction = 1.0 + r_col * col_norm + r_row * row_norm;
  } else if (chan == 2) {
    /* B channel: gradient from top-left */
    correction = 1.0 + b_col * col_norm + b_row * row_norm;
  }
  /* G channel: no correction (1.0) */
  
  return correction;
}

/* ============================================================================
 * MERRILL SPATIAL COLOR CORRECTION
 * ============================================================================
 *
 * The Merrill sensor has spatial color non-uniformity that cannot be corrected
 * by the existing luminance spatial gain system. This system uses a 7x7 grid
 * of per-channel R/G/B correction factors derived from empirical analysis of
 * white reference image vs SPP reference output.
 *
 * CORRECTION IS APPLIED AFTER COLOR CONVERSION (in output space).
 */

static const double merrill_color_correction_table[MERRILL_COLOR_GRID_ROWS][MERRILL_COLOR_GRID_COLS][MERRILL_COLOR_CHANNELS] = {
    /* Row 0 - TOP */
    {
        {1.182510, 1.201552, 0.953607},
        {1.184163, 1.212690, 0.979337},
        {1.183083, 1.219224, 1.001994},
        {1.183080, 1.219244, 1.016785},
        {1.186714, 1.208818, 1.018644},
        {1.310000, 1.186439, 1.006264},
        {1.300000, 1.165908, 0.982249}
    },
    /* Row 1 */
    {
        {1.180737, 1.211718, 0.955971},
        {1.177344, 1.231839, 0.981390},
        {1.168929, 1.245773, 0.998648},
        {1.168708, 1.246803, 1.013681},
        {1.179936, 1.233400, 1.022711},
        {1.310000, 1.201253, 1.013695},
        {1.305000, 1.169347, 0.991013}
    },
    /* Row 2 */
    {
        {1.179150, 1.220055, 0.956984},
        {1.174356, 1.249279, 0.985440},
        {1.162494, 1.270016, 0.999771},
        {1.162850, 1.270771, 1.013922},
        {1.174491, 1.248738, 1.023331},
        {1.310000, 1.210008, 1.018987},
        {1.310000, 1.169300, 0.998819}
    },
    /* Row 3 - CENTER */
    {
        {1.170224, 1.215557, 0.949127},
        {1.166887, 1.252994, 0.982103},
        {1.155000, 1.280222, 1.001351},
        {1.141999, 1.277949, 1.012580},
        {1.165000, 1.254153, 1.026322},
        {1.315000, 1.211187, 1.028135},
        {1.320000, 1.163786, 1.010264}
    },
    /* Row 4 */
    {
        {1.173434, 1.201658, 0.954082},
        {1.162615, 1.239526, 0.982874},
        {1.142000, 1.269274, 1.001124},
        {1.110318, 1.266398, 1.012108},
        {1.162092, 1.241639, 1.028482},
        {1.320000, 1.178275, 1.033223},
        {1.330000, 1.150259, 1.019223}
    },
    /* Row 5 */
    {
        {1.245000, 1.175116, 0.958121},
        {1.230000, 1.205667, 0.980993},
        {1.158173, 1.237206, 1.006264},
        {1.162692, 1.217770, 1.021442},
        {1.177275, 1.202341, 1.034574},
        {1.330000, 1.161226, 1.040782},
        {1.340000, 1.126290, 1.025053}
    },
    /* Row 6 - BOT */
    {
        {1.250000, 1.152223, 0.960129},
        {1.235000, 1.173600, 0.981934},
        {1.168851, 1.200156, 1.008140},
        {1.171477, 1.201359, 1.025906},
        {1.185289, 1.177891, 1.037623},
        {1.340000, 1.143525, 1.043020},
        {1.340000, 1.109953, 1.024526}
    }
};

/* Load spatial color correction data for Merrill cameras
 * Returns 1 if correction is available, 0 if not (non-Merrill camera or unsupported) */
int x3f_load_merrill_spatial_color(x3f_t *x3f, x3f_merrill_spatial_color_t *color_corr)
{
    char *cammodel;
    int is_merrill = 0;
    int row, col, ch;

    /* Check if this is a Merrill camera */
    if (x3f_get_prop_entry(x3f, "CAMMODEL", &cammodel)) {
        if (!strcmp(cammodel, "SIGMA DP1 Merrill") ||
            !strcmp(cammodel, "SIGMA DP2 Merrill") ||
            !strcmp(cammodel, "SIGMA DP3 Merrill")) {
            is_merrill = 1;
        }
    }

    if (!is_merrill) {
        color_corr->is_loaded = 0;
        return 0;
    }

    /* Copy the static correction table to the structure */
    for (row = 0; row < MERRILL_COLOR_GRID_ROWS; row++) {
        for (col = 0; col < MERRILL_COLOR_GRID_COLS; col++) {
            for (ch = 0; ch < MERRILL_COLOR_CHANNELS; ch++) {
                color_corr->grid[row][col].gain[ch] =
                    merrill_color_correction_table[row][col][ch];
            }
        }
    }

    color_corr->is_loaded = 1;
    x3f_printf(DEBUG, "Merrill spatial color correction loaded (7x7 grid)\n");

    return 1;
}

/* Calculate spatial color gain for a specific pixel
 * Uses bilinear interpolation within the 7x7 grid
 * Returns 1.0 if correction not available or outside grid */
double x3f_calc_merrill_color_gain(x3f_merrill_spatial_color_t *color_corr,
                                   int row, int col, int chan,
                                   int rows, int cols)
{
    double rrel, crel;
    int ri, ci;
    double rf, cf;
    double g00, g01, g10, g11, gain;

    if (!color_corr || !color_corr->is_loaded) {
        return 1.0;
    }

    if (chan < 0 || chan >= MERRILL_COLOR_CHANNELS) {
        return 1.0;
    }

    /* Normalize row and column to grid coordinates */
    rrel = (double)row / (double)rows * (MERRILL_COLOR_GRID_ROWS - 1);
    crel = (double)col / (double)cols * (MERRILL_COLOR_GRID_COLS - 1);

    /* Get integer grid indices */
    ri = (int)rrel;
    ci = (int)crel;

    /* Clamp to valid range */
    if (ri < 0) ri = 0;
    if (ri >= MERRILL_COLOR_GRID_ROWS - 1) ri = MERRILL_COLOR_GRID_ROWS - 2;
    if (ci < 0) ci = 0;
    if (ci >= MERRILL_COLOR_GRID_COLS - 1) ci = MERRILL_COLOR_GRID_COLS - 2;

    /* Fractional parts */
    rf = rrel - ri;
    cf = crel - ci;

    /* Bilinear interpolation of the 4 surrounding grid points */
    g00 = color_corr->grid[ri][ci].gain[chan];
    g01 = color_corr->grid[ri][ci + 1].gain[chan];
    g10 = color_corr->grid[ri + 1][ci].gain[chan];
    g11 = color_corr->grid[ri + 1][ci + 1].gain[chan];

    gain = (1.0 - rf) * (1.0 - cf) * g00 +
           (1.0 - rf) * cf * g01 +
           rf * (1.0 - cf) * g10 +
           rf * cf * g11;

    return gain;
}
