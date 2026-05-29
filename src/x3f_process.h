/* X3F_PROCESS.H
 *
 * Library for processing X3F data.
 *
 * Copyright 2015 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#ifndef X3F_PROCESS_H
#define X3F_PROCESS_H

#include "x3f_io.h"

typedef enum x3f_color_encoding_e {
  NONE=0,		 /* Preprocessed but unconverted data */
  SRGB=1,		 /* Preproccesed and convered to sRGB */
  ARGB=2,		 /* Preproccesed and convered to Adobee RGB */
  PPRGB=3,		 /* Preproccesed and convered to ProPhoto RGB */
  UNPROCESSED=4,	 /* RAW data without any preprocessing */
  QTOP=5,		 /* Quattro top layer without any preprocessing */
  BW=6,			 /* Black & white output (single-channel) */
} x3f_color_encoding_t;

typedef struct {
  double black[3];
  uint32_t white[3];
} x3f_image_levels_t;

extern int x3f_get_gain(x3f_t *x3f, char *wb, double *gain);
extern int x3f_get_bmt_to_xyz(x3f_t *x3f, char *wb, double *bmt_to_xyz);
extern int x3f_get_raw_to_xyz(x3f_t *x3f, char *wb, double *raw_to_xyz);

extern int x3f_get_image(x3f_t *x3f,
			 x3f_area16_t *image,
			 x3f_image_levels_t *ilevels,
			 x3f_color_encoding_t encoding,
			 int crop,
			 int fix_bad,
			 int denoise,
			 int apply_sgain,
			 char *wb,
			 int use_tone_curve,
			 int apply_sharpen,
			 double sharpen_psf,
			 int sharpen_iter,
			 int apply_micro_contrast,
			 double mc_radius,
			 double mc_amount,
			 double mc_epsilon);

extern int x3f_get_preview(x3f_t *x3f,
			   x3f_area16_t *image,
			   x3f_image_levels_t *ilevels,
			   x3f_color_encoding_t encoding,
			   int apply_sgain,
			   char *wb,
			   uint32_t max_width,
			   x3f_area8_t *preview,
			   int use_tone_curve);

extern int x3f_get_bw_image(x3f_t *x3f,
			    x3f_area16_t *image,
			    x3f_image_levels_t *ilevels,
			    int crop);

#endif
