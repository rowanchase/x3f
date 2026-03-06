/* X3F_SHARPEN.H
 *
 * Header file for Richardson-Lucy deconvolution sharpening
 *
 */

#ifndef X3F_SHARPEN_H
#define X3F_SHARPEN_H

#include "x3f_image.h"

#ifdef __cplusplus
extern "C" {
#endif

void x3f_rl_deconv(x3f_area16_t *image,
                   double psf_sigma,
                   int iterations,
                   double damping);

#ifdef __cplusplus
}
#endif

#endif
