# Delay model: test-set metrics

Synthetic data only. Test = the latest days of the dataset, never used for training or early stopping. Delays in minutes; MAE = mean absolute error, RMSE = root mean squared error.

## Split by day

| part | rows | days | first_day | last_day |
|---|---|---|---|---|
| train | 26000 | 125 | 2025-10-01 | 2026-02-02 |
| validation | 5616 | 27 | 2026-02-03 | 2026-03-01 |
| test | 5824 | 28 | 2026-03-02 | 2026-03-29 |

## Test error by model and station horizon (minutes)

| horizon | model | n | mae | rmse |
|---|---|---|---|---|
| 1 | mean | 5824 | 12.40 | 18.08 |
| 1 | ridge | 5824 | 0.79 | 2.13 |
| 1 | persistence | 5824 | 1.25 | 2.67 |
| 1 | lightgbm | 5824 | 0.33 | 2.01 |
| 2 | mean | 5124 | 13.00 | 18.69 |
| 2 | ridge | 5124 | 2.67 | 5.36 |
| 2 | persistence | 5124 | 3.12 | 6.18 |
| 2 | lightgbm | 5124 | 1.78 | 5.27 |
| 3 | mean | 4424 | 13.65 | 19.36 |
| 3 | ridge | 4424 | 4.46 | 7.63 |
| 3 | persistence | 4424 | 4.97 | 9.04 |
| 3 | lightgbm | 4424 | 3.13 | 7.40 |

## LightGBM gain over persistence (MAE, minutes; positive = LightGBM better)

| horizon | persistence | lightgbm | gain_min |
|---|---|---|---|
| 1 | 1.25 | 0.33 | 0.92 |
| 2 | 3.12 | 1.78 | 1.34 |
| 3 | 4.97 | 3.13 | 1.84 |

## Late or not (delay > 5 min): precision and recall

| horizon | model | precision | recall | f1 | n_late |
|---|---|---|---|---|---|
| 1 | mean | 0.32 | 1.00 | 0.48 | 1864 |
| 1 | ridge | 0.95 | 0.99 | 0.97 | 1864 |
| 1 | persistence | 0.97 | 0.97 | 0.97 | 1864 |
| 1 | lightgbm | 0.96 | 0.99 | 0.98 | 1864 |
| 2 | mean | 0.35 | 1.00 | 0.52 | 1782 |
| 2 | ridge | 0.89 | 0.90 | 0.90 | 1782 |
| 2 | persistence | 0.96 | 0.84 | 0.89 | 1782 |
| 2 | lightgbm | 0.95 | 0.88 | 0.91 | 1782 |
| 3 | mean | 0.38 | 1.00 | 0.55 | 1683 |
| 3 | ridge | 0.78 | 0.87 | 0.82 | 1683 |
| 3 | persistence | 0.96 | 0.71 | 0.81 | 1683 |
| 3 | lightgbm | 0.93 | 0.81 | 0.86 | 1683 |

## Disruption ahead (any disruption on the next blocks) vs none: LightGBM vs persistence (MAE)

| disruption | horizon | persistence | lightgbm | gain_min | n |
|---|---|---|---|---|---|
| disruption ahead | 1 | 6.69 | 4.82 | 1.86 | 156 |
| disruption ahead | 2 | 10.61 | 7.28 | 3.34 | 153 |
| disruption ahead | 3 | 13.85 | 8.71 | 5.14 | 143 |
| no disruption | 1 | 1.10 | 0.21 | 0.89 | 5668 |
| no disruption | 2 | 2.88 | 1.61 | 1.28 | 4971 |
| no disruption | 3 | 4.67 | 2.94 | 1.73 | 4281 |

## Disruption ahead (any disruption on the next blocks) vs none: all models

| disruption | horizon | model | n | mae | rmse |
|---|---|---|---|---|---|
| disruption ahead | 1 | mean | 156 | 17.87 | 26.62 |
| disruption ahead | 1 | ridge | 156 | 5.98 | 9.68 |
| disruption ahead | 1 | persistence | 156 | 6.69 | 12.47 |
| disruption ahead | 1 | lightgbm | 156 | 4.82 | 9.86 |
| disruption ahead | 2 | mean | 153 | 20.16 | 28.40 |
| disruption ahead | 2 | ridge | 153 | 8.24 | 10.54 |
| disruption ahead | 2 | persistence | 153 | 10.61 | 15.72 |
| disruption ahead | 2 | lightgbm | 153 | 7.28 | 11.01 |
| disruption ahead | 3 | mean | 143 | 21.89 | 29.82 |
| disruption ahead | 3 | ridge | 143 | 9.60 | 12.03 |
| disruption ahead | 3 | persistence | 143 | 13.85 | 19.01 |
| disruption ahead | 3 | lightgbm | 143 | 8.71 | 12.37 |
| no disruption | 1 | mean | 5668 | 12.25 | 17.79 |
| no disruption | 1 | ridge | 5668 | 0.65 | 1.44 |
| no disruption | 1 | persistence | 5668 | 1.10 | 1.75 |
| no disruption | 1 | lightgbm | 5668 | 0.21 | 1.21 |
| no disruption | 2 | mean | 4971 | 12.78 | 18.31 |
| no disruption | 2 | ridge | 4971 | 2.50 | 5.12 |
| no disruption | 2 | persistence | 4971 | 2.88 | 5.64 |
| no disruption | 2 | lightgbm | 4971 | 1.61 | 4.99 |
| no disruption | 3 | mean | 4281 | 13.37 | 18.91 |
| no disruption | 3 | ridge | 4281 | 4.28 | 7.44 |
| no disruption | 3 | persistence | 4281 | 4.67 | 8.51 |
| no disruption | 3 | lightgbm | 4281 | 2.94 | 7.17 |

## Delay above 5 minutes vs not (split by the real outcome): LightGBM vs persistence (MAE)

| actual_late | horizon | persistence | lightgbm | gain_min | n |
|---|---|---|---|---|---|
| late (>5 min) | 1 | 1.78 | 0.85 | 0.93 | 1864 |
| late (>5 min) | 2 | 5.50 | 4.17 | 1.33 | 1782 |
| late (>5 min) | 3 | 8.99 | 6.83 | 2.16 | 1683 |
| on time | 1 | 1.00 | 0.09 | 0.91 | 3960 |
| on time | 2 | 1.84 | 0.50 | 1.34 | 3342 |
| on time | 3 | 2.50 | 0.86 | 1.64 | 2741 |

## Delay above 5 minutes vs not (split by the real outcome): all models

| actual_late | horizon | model | n | mae | rmse |
|---|---|---|---|---|---|
| late (>5 min) | 1 | mean | 1864 | 20.96 | 28.80 |
| late (>5 min) | 1 | ridge | 1864 | 1.32 | 3.50 |
| late (>5 min) | 1 | persistence | 1864 | 1.78 | 4.37 |
| late (>5 min) | 1 | lightgbm | 1864 | 0.85 | 3.47 |
| late (>5 min) | 2 | mean | 1782 | 20.24 | 28.35 |
| late (>5 min) | 2 | ridge | 1782 | 4.77 | 8.59 |
| late (>5 min) | 2 | persistence | 1782 | 5.50 | 10.01 |
| late (>5 min) | 2 | lightgbm | 1782 | 4.17 | 8.76 |
| late (>5 min) | 3 | mean | 1683 | 19.49 | 27.85 |
| late (>5 min) | 3 | ridge | 1683 | 7.29 | 11.51 |
| late (>5 min) | 3 | persistence | 1683 | 8.99 | 14.07 |
| late (>5 min) | 3 | lightgbm | 1683 | 6.83 | 11.77 |
| on time | 1 | mean | 3960 | 8.37 | 9.50 |
| on time | 1 | ridge | 3960 | 0.54 | 0.96 |
| on time | 1 | persistence | 3960 | 1.00 | 1.22 |
| on time | 1 | lightgbm | 3960 | 0.09 | 0.51 |
| on time | 2 | mean | 3342 | 9.14 | 10.34 |
| on time | 2 | ridge | 3342 | 1.56 | 2.17 |
| on time | 2 | persistence | 3342 | 1.84 | 2.27 |
| on time | 2 | lightgbm | 3342 | 0.50 | 1.28 |
| on time | 3 | mean | 2741 | 10.06 | 11.35 |
| on time | 3 | ridge | 2741 | 2.71 | 3.56 |
| on time | 3 | persistence | 2741 | 2.50 | 3.22 |
| on time | 3 | lightgbm | 2741 | 0.86 | 1.81 |

## By train type: LightGBM vs persistence (MAE)

| train_category | horizon | persistence | lightgbm | gain_min | n |
|---|---|---|---|---|---|
| express | 1 | 1.27 | 0.51 | 0.76 | 1792 |
| express | 2 | 3.34 | 2.27 | 1.07 | 1596 |
| express | 3 | 5.33 | 3.96 | 1.37 | 1400 |
| freight | 1 | 1.82 | 0.22 | 1.60 | 1456 |
| freight | 2 | 3.97 | 1.04 | 2.93 | 1288 |
| freight | 3 | 5.97 | 2.04 | 3.93 | 1120 |
| passenger | 1 | 1.03 | 0.38 | 0.65 | 1456 |
| passenger | 2 | 2.80 | 2.62 | 0.17 | 1232 |
| passenger | 3 | 5.25 | 4.39 | 0.86 | 1008 |
| premium | 1 | 0.74 | 0.13 | 0.62 | 1120 |
| premium | 2 | 2.07 | 0.91 | 1.16 | 1008 |
| premium | 3 | 2.84 | 1.79 | 1.06 | 896 |

## By train type: all models

| train_category | horizon | model | n | mae | rmse |
|---|---|---|---|---|---|
| express | 1 | mean | 1792 | 12.31 | 19.38 |
| express | 1 | ridge | 1792 | 1.09 | 2.59 |
| express | 1 | persistence | 1792 | 1.27 | 3.07 |
| express | 1 | lightgbm | 1792 | 0.51 | 2.41 |
| express | 2 | mean | 1596 | 12.91 | 20.02 |
| express | 2 | ridge | 1596 | 3.31 | 6.35 |
| express | 2 | persistence | 1596 | 3.34 | 7.37 |
| express | 2 | lightgbm | 1596 | 2.27 | 6.04 |
| express | 3 | mean | 1400 | 13.43 | 20.60 |
| express | 3 | ridge | 1400 | 5.45 | 8.98 |
| express | 3 | persistence | 1400 | 5.33 | 10.78 |
| express | 3 | lightgbm | 1400 | 3.96 | 8.36 |
| freight | 1 | mean | 1456 | 15.18 | 17.92 |
| freight | 1 | ridge | 1456 | 0.64 | 2.00 |
| freight | 1 | persistence | 1456 | 1.82 | 2.93 |
| freight | 1 | lightgbm | 1456 | 0.22 | 1.59 |
| freight | 2 | mean | 1288 | 16.20 | 18.68 |
| freight | 2 | ridge | 1288 | 2.07 | 4.91 |
| freight | 2 | persistence | 1288 | 3.97 | 5.72 |
| freight | 2 | lightgbm | 1288 | 1.04 | 4.87 |
| freight | 3 | mean | 1120 | 17.30 | 19.57 |
| freight | 3 | ridge | 1120 | 3.73 | 6.85 |
| freight | 3 | persistence | 1120 | 5.97 | 7.75 |
| freight | 3 | lightgbm | 1120 | 2.04 | 6.87 |
| passenger | 1 | mean | 1456 | 11.79 | 19.77 |
| passenger | 1 | ridge | 1456 | 0.75 | 2.27 |
| passenger | 1 | persistence | 1456 | 1.03 | 2.67 |
| passenger | 1 | lightgbm | 1456 | 0.38 | 2.50 |
| passenger | 2 | mean | 1232 | 12.26 | 20.61 |
| passenger | 2 | ridge | 1232 | 3.18 | 5.76 |
| passenger | 2 | persistence | 1232 | 2.80 | 6.57 |
| passenger | 2 | lightgbm | 1232 | 2.62 | 5.92 |
| passenger | 3 | mean | 1008 | 12.95 | 21.69 |
| passenger | 3 | ridge | 1008 | 5.00 | 8.35 |
| passenger | 3 | persistence | 1008 | 5.25 | 10.34 |
| passenger | 3 | lightgbm | 1008 | 4.39 | 8.44 |
| premium | 1 | mean | 1120 | 9.71 | 13.16 |
| premium | 1 | ridge | 1120 | 0.56 | 0.98 |
| premium | 1 | persistence | 1120 | 0.74 | 1.26 |
| premium | 1 | lightgbm | 1120 | 0.13 | 0.50 |
| premium | 2 | mean | 1008 | 10.00 | 13.27 |
| premium | 2 | ridge | 1008 | 1.81 | 3.31 |
| premium | 2 | persistence | 1008 | 2.07 | 3.69 |
| premium | 2 | lightgbm | 1008 | 0.91 | 3.20 |
| premium | 3 | mean | 896 | 10.23 | 13.39 |
| premium | 3 | ridge | 896 | 3.20 | 4.95 |
| premium | 3 | persistence | 896 | 2.84 | 5.16 |
| premium | 3 | lightgbm | 896 | 1.79 | 4.71 |
