#ifndef X3F_EXIF_H
#define X3F_EXIF_H

#include <stdint.h>
#include "x3f_io.h"

typedef struct {
    char make[64];
    char model[64];
    char datetime[20];
    uint32_t exposure_time_us;
    double fnumber;
    uint16_t iso;
    uint32_t focal_length_mm;
    uint16_t focal_35mm_mm;
    double exposure_bias;
    uint16_t flash;
    uint16_t white_balance;
    uint16_t color_space;
    char software[64];
    char serial_number[32];
} x3f_exif_metadata_t;

void x3f_unix_to_exif_datetime(uint32_t unix_time, char *buf, size_t buf_size);

int x3f_extract_exif_metadata(x3f_t *x3f, x3f_exif_metadata_t *meta);

int x3f_write_exif_metadata(void *tif, x3f_exif_metadata_t *meta);

#endif
