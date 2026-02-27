# 27 Feb 2026 - Histogram Analysis Results

## Summary of Findings

Ran the enhanced histogram comparison tool on 3 reference files (_P2M0927, _P2M0930, _P2M0936). The results reveal interesting patterns about our clipping detection.

## Key Results

### File: _P2M0927 (Standard test file)
| Channel | Soft (200-230) | Hard (230-254) | Fully Clipped (254-256) |
|---------|----------------|-----------------|-------------------------|
| R       | 548,043 (3.72%) | 396,108 (2.69%) | 154,057 (1.04%) |
| G       | 386,539 (2.62%) | 265,463 (1.80%) | 137,594 (0.93%) |
| B       | 249,427 (1.69%) | 212,757 (1.44%) | 124,177 (0.84%) |

**Suspicious pattern detected:** G channel soft highlights differ by -1.41% (-207,331 pixels)

### File: _P2M0930 (Clipped file)
| Channel | Soft (200-230) | Hard (230-254) | Fully Clipped (254-256) |
|---------|----------------|-----------------|-------------------------|
| R       | 303,536 (2.06%) | 203,788 (1.38%) | 331,893 (2.25%) |
| G       | 218,837 (1.48%) | 164,050 (1.11%) | 324,917 (2.20%) |
| B       | 153,853 (1.04%) | 143,350 (0.97%) | 317,131 (2.15%) |

**No suspicious patterns**

### File: _P2M0936 (Severely clipped file)
| Channel | Soft (200-230) | Hard (230-254) | Fully Clipped (254-256) |
|---------|----------------|-----------------|-------------------------|
| R       | 342,634 (2.32%) | 338,772 (2.30%) | 1,018,948 (6.91%) |
| G       | 262,201 (1.78%) | 275,014 (1.86%) | 1,003,781 (6.80%) |
| B       | 167,741 (1.14%) | 241,608 (1.64%) | 987,146 (6.69%) |

**Suspicious pattern detected:** B channel max value clipping differs by +0.90% (output=6.69% vs ref=5.79%)

## Analysis

### 1. Clipping Detection IS Working
- We are detecting substantial numbers of clipped pixels
- Fully clipped range from 0.8% to 6.9% depending on file
- This contradicts the user's report of only 45 pixels being detected

### 2. Pattern: Soft Highlights vs Fully Clipped
- We generally have **FEWER** pixels in soft highlights (200-230) than SPP
- We generally have **MORE** pixels in fully clipped (254-256) than SPP
- This suggests our transition from soft to hard clipping is too aggressive

### 3. The User's Issue (45 pixels)
The user mentioned a file (_P2M1109) with large sky region showing only 45 clipped pixels. This suggests either:
- The sky pixels are in the 200-230 range (soft highlights) but not being counted as "clipped" by our detection
- The histogram shows plenty of pixels in 200-255 range, but our threshold (0.50) is only catching 45

### 4. Recommendation
The histogram analysis shows we have many pixels in the soft highlight range (200-230), but our clipping detection at threshold 0.50 might be:
1. Too conservative for some files (not catching enough)
2. Converting too aggressively to fully clipped (254-256)

**Next Steps:**
1. Lower the clipping threshold further (try 0.40 or 0.30)
2. Examine the "soft highlights" pixels more carefully - these are near-clipped but not being reconstructed
3. Consider lowering the boundary between "soft" and "hard" highlights in our analysis

## Tool Verification
The histogram comparison tool is working well and detected:
- Large soft highlight differences (G channel in 0927)
- Over-clipping issues (B channel in 0936)
- General patterns across multiple files

The tool successfully identifies when we have significantly different histogram distributions compared to SPP reference.
