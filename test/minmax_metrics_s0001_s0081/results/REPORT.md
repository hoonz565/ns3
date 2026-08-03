# RSSI / RSSI Slope / MAC Retry — scenarios 0001–0081

## Input

- Expected files: 810
- Usable files: 810
- Rows scanned: 46,132,618
- Complete: True
- Empty scenarios: none

The missing scenarios are excluded rather than silently treated as zeros.

## Min–Max scaling

Each feature uses one global range over every valid row:

`x_norm = (x - global_min) / (global_max - global_min)`

Exact global constants and distribution statistics are in `statistics.json`.
Normalized per-scenario summaries are in `per_scenario_statistics.csv`.
Exact histogram counts with both raw and normalized bin edges are in `histogram_bins.csv`.

## Distribution notes

- **RSSI**: lệch phải mạnh (skew=1.435); outlier IQR xấp xỉ 3.06%; Min–Max dễ nén phần lớn dữ liệu vì biên bị chi phối bởi cực trị.
- **RSSI Slope**: khá đối xứng (skew=0.024); outlier IQR xấp xỉ 4.69%; Min–Max dễ nén phần lớn dữ liệu vì biên bị chi phối bởi cực trị.
- **MAC Retry**: lệch trái mạnh (skew=-1.329); outlier IQR xấp xỉ 6.56%; 98% dữ liệu sử dụng phần đáng kể của khoảng Min–Max.

Quantiles and boxplots use a deterministic 1/100 sample. Counts, min, max,
mean, standard deviation, skewness, and histogram bins use all valid rows.
