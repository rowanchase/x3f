/* X3F_CONTRAST.CPP
 *
 * Micro-contrast enhancement using Gaussian blur
 *
 * Copyright 2015 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#include <iostream>
#include <cmath>
#include <cstring>
#include <algorithm>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include "x3f_contrast.h"
#include "x3f_printf.h"

using namespace cv;

void x3f_micro_contrast(x3f_area16_t *image,
                        double radius,
                        double amount,
                        double epsilon)
{
    const float max_val = 65535.0f;
    
    x3f_printf(DEBUG, "Starting micro-contrast enhancement\n");
    x3f_printf(DEBUG, "  Radius: %f\n", radius);
    x3f_printf(DEBUG, "  Amount: %f\n", amount);
    
    // Process each RGB channel independently
    for (int ch = 0; ch < 3; ch++) {
        x3f_printf(DEBUG, "  Processing channel %d\n", ch);
        
        // Convert to float Mat
        Mat input(image->rows, image->columns, CV_32F);
        float* in_data = (float*)input.data;
        
        for (int row = 0; row < image->rows; row++) {
            for (int col = 0; col < image->columns; col++) {
                uint16_t val = image->data[image->row_stride * row + 
                                            image->channels * col + ch];
                in_data[row * image->columns + col] = (float)val;
            }
        }
        
        // Step 1: Get base layer using Gaussian blur
        Mat base;
        // GaussianBlur uses standard deviation (sigma), not radius
        // For a given radius in pixels, sigma = radius / 3 is a good rule of thumb
        double sigma = radius / 3.0;
        if (sigma < 0.5) sigma = 0.5;  // Minimum blur
        GaussianBlur(input, base, Size(0, 0), sigma, sigma, BORDER_REFLECT);
        
        // Step 2: Extract detail layer
        Mat detail;
        subtract(input, base, detail);
        
        // Step 3: Enhance detail layer
        Mat enhanced_detail;
        multiply(detail, amount, enhanced_detail);
        
        // Step 4: Reconstruct: output = base + enhanced_detail
        Mat output;
        add(base, enhanced_detail, output);
        
        // Step 5: Clamp to valid range
        float* out_data = (float*)output.data;
        for (int i = 0; i < image->rows * image->columns; i++) {
            out_data[i] = std::max(0.0f, std::min(max_val, out_data[i]));
        }
        
        // Step 6: Copy back to image
        for (int row = 0; row < image->rows; row++) {
            for (int col = 0; col < image->columns; col++) {
                float val = out_data[row * image->columns + col];
                uint16_t out_val = (uint16_t)val;
                image->data[image->row_stride * row + 
                           image->channels * col + ch] = out_val;
            }
        }
    }
    
    x3f_printf(DEBUG, "Micro-contrast enhancement complete\n");
}
