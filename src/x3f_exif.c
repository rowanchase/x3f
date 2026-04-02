#include "x3f_exif.h"
#include "x3f_meta.h"
#include "x3f_printf.h"
#include <tiffio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int get_camf_string(x3f_t *x3f, char *name, char *dest, size_t dest_size)
{
    char *value;
    if (x3f_get_camf_text(x3f, name, &value)) {
        strncpy(dest, value, dest_size - 1);
        dest[dest_size - 1] = '\0';
        return 1;
    }
    dest[0] = '\0';
    return 0;
}

static int get_camf_uint16(x3f_t *x3f, char *name, uint16_t *dest)
{
    uint32_t val;
    if (x3f_get_camf_unsigned(x3f, name, &val)) {
        *dest = (uint16_t)val;
        return 1;
    }
    return 0;
}

static int get_camf_double(x3f_t *x3f, char *name, double *dest)
{
    return x3f_get_camf_float(x3f, name, dest);
}

int x3f_extract_exif_metadata(x3f_t *x3f, x3f_exif_metadata_t *meta)
{
    memset(meta, 0, sizeof(x3f_exif_metadata_t));

    strcpy(meta->software, "x3f_extract");
    strcpy(meta->make, "Sigma");
    strcpy(meta->model, "DP2 Merrill");
    meta->white_balance = 0;
    meta->color_space = 1;

    get_camf_string(x3f, "CAMSERIAL", meta->serial_number, sizeof(meta->serial_number));
    get_camf_string(x3f, "Runtime", meta->datetime, sizeof(meta->datetime));

    get_camf_uint16(x3f, "CaptureISO", &meta->iso);
    get_camf_double(x3f, "CaptureAperture", &meta->fnumber);
    get_camf_double(x3f, "EXPCOMP", &meta->exposure_bias);

    double shutter;
    if (get_camf_double(x3f, "CaptureShutter", &shutter)) {
        meta->exposure_time_us = (uint32_t)(shutter * 1000000.0);
    } else if (get_camf_double(x3f, "CaptureExpTime", &shutter)) {
        meta->exposure_time_us = (uint32_t)(shutter * 1000000.0);
    }

    double focal_length;
    if (get_camf_double(x3f, "FocalLength", &focal_length)) {
        meta->focal_length_mm = (uint32_t)focal_length;
    }

    get_camf_uint16(x3f, "FLEQ35MM", &meta->focal_35mm_mm);

    x3f_printf(DEBUG, "EXIF: ISO=%u, aperture=%.1f, shutter=%uus, focal=%umm\n",
               meta->iso, meta->fnumber, meta->exposure_time_us, meta->focal_length_mm);

    return 1;
}

static void write_rational(TIFF *tif, uint32_t tag, uint32_t num, uint32_t den)
{
    uint32_t rational[2] = { num, den };
    TIFFSetField(tif, tag, 1, rational);
}

int x3f_write_exif_metadata(void *tif_ptr, x3f_exif_metadata_t *meta)
{
    TIFF *tif = (TIFF *)tif_ptr;

    if (meta->exposure_time_us > 0 && meta->exposure_time_us < 10000000) {
        uint32_t exposure_us = meta->exposure_time_us;
        if (exposure_us >= 1000000) {
            write_rational(tif, EXIFTAG_EXPOSURETIME, 1, exposure_us / 1000000);
        } else {
            write_rational(tif, EXIFTAG_EXPOSURETIME, exposure_us, 1000000);
        }
    }

    if (meta->fnumber > 0 && meta->fnumber < 100) {
        uint32_t fnum_x10 = (uint32_t)(meta->fnumber * 10);
        write_rational(tif, EXIFTAG_FNUMBER, fnum_x10, 10);
    }

    if (meta->iso > 0 && meta->iso < 100000) {
        TIFFSetField(tif, EXIFTAG_ISOSPEEDRATINGS, (uint16_t)meta->iso);
    }

    if (meta->focal_length_mm > 0 && meta->focal_length_mm < 10000) {
        write_rational(tif, EXIFTAG_FOCALLENGTH, meta->focal_length_mm, 1);
    }

    if (meta->focal_35mm_mm > 0 && meta->focal_35mm_mm < 10000) {
        TIFFSetField(tif, EXIFTAG_FOCALLENGTHIN35MMFILM, (uint16_t)meta->focal_35mm_mm);
    }

    if (meta->color_space > 0) {
        TIFFSetField(tif, EXIFTAG_COLORSPACE, (uint16_t)meta->color_space);
    }

    TIFFSetField(tif, EXIFTAG_WHITEBALANCE, (uint16_t)meta->white_balance);

    return 1;
}
