/* X3F_SHARPEN.C
 *
 * Richardson-Lucy deconvolution for X3F image sharpening
 *
 * Copyright 2015 - Roland and Erik Karlsson
 * BSD-style - see doc/copyright.txt
 *
 */

#include <iostream>
#include <cmath>
#include <cstring>
#include <algorithm>

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wclass-memaccess"
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#pragma GCC diagnostic pop

#include "x3f_sharpen.h"
#include "x3f_printf.h"

using namespace cv;

static void generate_gaussian_psf(Mat& kernel, double sigma)
{
    int radius = (int)ceil(3.0 * sigma);
    int size = 2 * radius + 1;
    
    kernel.create(size, size, CV_32F);
    float* k = (float*)kernel.data;
    
    double sum = 0.0;
    for (int y = 0; y < size; y++) {
        for (int x = 0; x < size; x++) {
            double dx = x - radius;
            double dy = y - radius;
            double val = exp(-(dx*dx + dy*dy) / (2.0 * sigma * sigma));
            k[y * size + x] = (float)val;
            sum += val;
        }
    }
    
    kernel /= sum;
}

static Mat create_flipped_psf(const Mat& psf)
{
    Mat flipped;
    flip(psf, flipped, -1);
    return flipped;
}

static void rl_iteration(const Mat& observed, Mat& estimate, 
                         const Mat& psf, const Mat& psf_flipped,
                         double damping)
{
    Mat blurred;
    filter2D(estimate, blurred, CV_32F, psf, Point(-1, -1), 0.0, BORDER_CONSTANT);
    
    Mat ratio(observed.size(), CV_32F);
    const float* obs = (const float*)observed.data;
    const float* blur = (const float*)blurred.data;
    float* rat = (float*)ratio.data;
    
    for (int i = 0; i < observed.rows * observed.cols; i++) {
        if (blur[i] > 1e-10f) {
            rat[i] = obs[i] / blur[i];
        } else {
            rat[i] = 1.0f;
        }
    }
    
    if (damping > 0.0) {
        float* r = (float*)ratio.data;
        const float* est = (const float*)estimate.data;
        for (int i = 0; i < observed.rows * observed.cols; i++) {
            float dev = fabsf(obs[i] - est[i]);
            if (dev < damping) {
                float factor = dev / damping;
                r[i] = 1.0f + factor * (r[i] - 1.0f);
            }
        }
    }
    
    Mat ratio_blurred;
    filter2D(ratio, ratio_blurred, CV_32F, psf_flipped, Point(-1, -1), 0.0, BORDER_CONSTANT);
    
    const float* rat_blur = (const float*)ratio_blurred.data;
    float* est = (float*)estimate.data;
    
    for (int i = 0; i < observed.rows * observed.cols; i++) {
        est[i] *= rat_blur[i];
    }
}

static void clamp_image(Mat& img, float min_val, float max_val)
{
    float* data = (float*)img.data;
    for (int i = 0; i < img.rows * img.cols; i++) {
        data[i] = std::max(min_val, std::min(max_val, data[i]));
    }
}

void x3f_rl_deconv(x3f_area16_t *image,
                   double psf_sigma,
                   int iterations,
                   double damping)
{
    x3f_printf(DEBUG, "Starting Richardson-Lucy deconvolution\n");
    x3f_printf(DEBUG, "  PSF sigma: %f\n", psf_sigma);
    x3f_printf(DEBUG, "  Iterations: %d\n", iterations);
    x3f_printf(DEBUG, "  Damping: %f\n", damping);
    
    Mat psf;
    generate_gaussian_psf(psf, psf_sigma);
    Mat psf_flipped = create_flipped_psf(psf);
    
    x3f_printf(DEBUG, "  PSF size: %dx%d\n", psf.rows, psf.cols);
    
    const float max_val = 65535.0f;
    
    for (int ch = 0; ch < 3; ch++) {
        x3f_printf(DEBUG, "  Processing channel %d\n", ch);
        
        Mat input(image->rows, image->columns, CV_32F);
        float* in_data = (float*)input.data;
        
        for (uint32_t row = 0; row < image->rows; row++) {
            for (uint32_t col = 0; col < image->columns; col++) {
                uint16_t val = image->data[image->row_stride * row + 
                                            image->channels * col + ch];
                in_data[row * image->columns + col] = (float)val;
            }
        }
        
        Mat estimate = input.clone();
        
        for (int iter = 0; iter < iterations; iter++) {
            rl_iteration(input, estimate, psf, psf_flipped, damping);
            clamp_image(estimate, 0.0f, max_val);
        }
        
        float* out_data = (float*)estimate.data;
        for (uint32_t row = 0; row < image->rows; row++) {
            for (uint32_t col = 0; col < image->columns; col++) {
                float val = out_data[row * image->columns + col];
                uint16_t out_val = (uint16_t)std::max(0.0f, std::min(max_val, val));
                image->data[image->row_stride * row + 
                           image->channels * col + ch] = out_val;
            }
        }
    }
    
    x3f_printf(DEBUG, "Richardson-Lucy deconvolution complete\n");
}
