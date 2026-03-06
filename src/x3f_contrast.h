/* X3F_CONTRAST.H
 *
 * Header file for micro-contrast enhancement using guided filter
 *
 */

#ifndef X3F_CONTRAST_H
#define X3F_CONTRAST_H

#include "x3f_image.h"

#ifdef __cplusplus
extern "C" {
#endif

void x3f_micro_contrast(x3f_area16_t *image,
                        double radius,
                        double amount,
                        double epsilon);

#ifdef __cplusplus
}
#endif

#endif
