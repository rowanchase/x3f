/* X3F_OUTPUT_TIFF.C
 *
 * Library for writing the image as TIFF.
 *
 * Copyright 2015 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#include "x3f_output_tiff.h"
#include "x3f_process.h"
#include "x3f_io.h"

#include <stdlib.h>
#include <tiffio.h>

static void rotate_image_90_cw(x3f_area16_t *image)
{
  uint16_t *new_data;
  uint32_t new_rows = image->columns;
  uint32_t new_columns = image->rows;
  uint32_t new_row_stride = new_columns * image->channels;
  uint32_t row, col, ch;

  new_data = (uint16_t *)malloc(new_rows * new_row_stride * sizeof(uint16_t));

  for (row = 0; row < image->rows; row++) {
    for (col = 0; col < image->columns; col++) {
      for (ch = 0; ch < image->channels; ch++) {
        uint16_t val = image->data[row * image->row_stride + col * image->channels + ch];
        uint32_t new_row = col;
        uint32_t new_col = image->rows - 1 - row;
        new_data[new_row * new_row_stride + new_col * image->channels + ch] = val;
      }
    }
  }

  free(image->buf);
  image->data = image->buf = new_data;
  image->rows = new_rows;
  image->columns = new_columns;
  image->row_stride = new_row_stride;
}

static void rotate_image_90_ccw(x3f_area16_t *image)
{
  uint16_t *new_data;
  uint32_t new_rows = image->columns;
  uint32_t new_columns = image->rows;
  uint32_t new_row_stride = new_columns * image->channels;
  uint32_t row, col, ch;

  new_data = (uint16_t *)malloc(new_rows * new_row_stride * sizeof(uint16_t));

  for (row = 0; row < image->rows; row++) {
    for (col = 0; col < image->columns; col++) {
      for (ch = 0; ch < image->channels; ch++) {
        uint16_t val = image->data[row * image->row_stride + col * image->channels + ch];
        uint32_t new_row = image->columns - 1 - col;
        uint32_t new_col = row;
        new_data[new_row * new_row_stride + new_col * image->channels + ch] = val;
      }
    }
  }

  free(image->buf);
  image->data = image->buf = new_data;
  image->rows = new_rows;
  image->columns = new_columns;
  image->row_stride = new_row_stride;
}

static void rotate_image_180(x3f_area16_t *image)
{
  uint32_t row, col, ch;
  uint32_t half_rows = image->rows / 2;

  for (row = 0; row < half_rows; row++) {
    for (col = 0; col < image->columns; col++) {
      for (ch = 0; ch < image->channels; ch++) {
        uint32_t idx1 = row * image->row_stride + col * image->channels + ch;
        uint32_t idx2 = (image->rows - 1 - row) * image->row_stride + 
                        (image->columns - 1 - col) * image->channels + ch;
        uint16_t tmp = image->data[idx1];
        image->data[idx1] = image->data[idx2];
        image->data[idx2] = tmp;
      }
    }
  }

  if (image->rows % 2 == 1) {
    row = half_rows;
    for (col = 0; col < image->columns / 2; col++) {
      for (ch = 0; ch < image->channels; ch++) {
        uint32_t idx1 = row * image->row_stride + col * image->channels + ch;
        uint32_t idx2 = row * image->row_stride + 
                        (image->columns - 1 - col) * image->channels + ch;
        uint16_t tmp = image->data[idx1];
        image->data[idx1] = image->data[idx2];
        image->data[idx2] = tmp;
      }
    }
  }
}

/* extern */
x3f_return_t x3f_dump_raw_data_as_tiff(x3f_t *x3f,
				       char *outfilename,
				       x3f_color_encoding_t encoding,
				       int crop,
				       int fix_bad,
				       int denoise,
				       int apply_sgain,
				       char *wb,
				       int compress)
{
  x3f_area16_t image;
  TIFF *f_out = TIFFOpen(outfilename, "w");
  int row;

  if (f_out == NULL) return X3F_OUTFILE_ERROR;

  if (!x3f_get_image(x3f, &image, NULL, encoding,
		     crop, fix_bad, denoise, apply_sgain,
		     wb)) {
    TIFFClose(f_out);
    return X3F_ARGUMENT_ERROR;
  }

  switch (x3f->header.rotation) {
  case 90:
    rotate_image_90_cw(&image);
    break;
  case 180:
    rotate_image_180(&image);
    break;
  case 270:
    rotate_image_90_ccw(&image);
    break;
  }

  TIFFSetField(f_out, TIFFTAG_IMAGEWIDTH, image.columns);
  TIFFSetField(f_out, TIFFTAG_IMAGELENGTH, image.rows);
  TIFFSetField(f_out, TIFFTAG_ROWSPERSTRIP, 32);
  TIFFSetField(f_out, TIFFTAG_SAMPLESPERPIXEL, image.channels);
  TIFFSetField(f_out, TIFFTAG_BITSPERSAMPLE, 16);
  TIFFSetField(f_out, TIFFTAG_PLANARCONFIG, PLANARCONFIG_CONTIG);
  TIFFSetField(f_out, TIFFTAG_COMPRESSION,
	       compress ? COMPRESSION_DEFLATE : COMPRESSION_NONE);
  TIFFSetField(f_out, TIFFTAG_PHOTOMETRIC, image.channels == 1 ?
	       PHOTOMETRIC_MINISBLACK : PHOTOMETRIC_RGB);
  TIFFSetField(f_out, TIFFTAG_ORIENTATION, ORIENTATION_TOPLEFT);
  TIFFSetField(f_out, TIFFTAG_XRESOLUTION, 72.0);
  TIFFSetField(f_out, TIFFTAG_YRESOLUTION, 72.0);
  TIFFSetField(f_out, TIFFTAG_RESOLUTIONUNIT, RESUNIT_INCH);

  for (row=0; row < image.rows; row++)
    TIFFWriteScanline(f_out, image.data + image.row_stride*row, row, 0);

  TIFFWriteDirectory(f_out);
  TIFFClose(f_out);
  free(image.buf);

  return X3F_OK;
}
