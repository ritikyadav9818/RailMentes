# Benchmark (mean of 20 seeds, persistence, synthetic data)

Seeds 1..20; mean ± standard deviation over seeds.

| intensity | strategy | Average delay (min) | Punctuality (% <= 5 min late) | Throughput (trains/hour) | Priority-weighted delay | Actions per day | runs |
|---|---|---|---|---|---|---|---|
| low | No control | 9.47 ± 2.79 | 66.00 ± 5.88 | 0.93 ± 0.01 | 631.30 ± 197.80 | 0.00 ± 0.00 | 20 |
| low | FCFS | 9.50 ± 2.86 | 65.40 ± 5.84 | 0.93 ± 0.01 | 634.70 ± 203.44 | 9.80 ± 1.67 | 20 |
| low | Priority rule | 8.22 ± 2.61 | 66.80 ± 6.88 | 0.93 ± 0.01 | 510.70 ± 186.49 | 1.45 ± 0.69 | 20 |
| low | CP-SAT | 8.14 ± 2.36 | 66.40 ± 7.04 | 0.93 ± 0.01 | 513.25 ± 167.93 | 2.45 ± 1.28 | 20 |
| medium | No control | 13.87 ± 3.70 | 58.00 ± 7.51 | 0.93 ± 0.01 | 916.55 ± 259.51 | 0.00 ± 0.00 | 20 |
| medium | FCFS | 14.01 ± 3.69 | 58.00 ± 7.05 | 0.93 ± 0.01 | 928.55 ± 257.34 | 9.45 ± 1.54 | 20 |
| medium | Priority rule | 13.01 ± 3.92 | 59.60 ± 7.33 | 0.93 ± 0.01 | 817.75 ± 272.71 | 1.80 ± 1.15 | 20 |
| medium | CP-SAT | 12.93 ± 3.74 | 58.20 ± 8.26 | 0.93 ± 0.01 | 825.20 ± 266.02 | 2.55 ± 1.05 | 20 |
| high | No control | 20.75 ± 5.07 | 43.00 ± 6.47 | 0.93 ± 0.01 | 1329.90 ± 336.83 | 0.00 ± 0.00 | 20 |
| high | FCFS | 21.26 ± 5.39 | 42.60 ± 7.02 | 0.93 ± 0.01 | 1369.60 ± 361.13 | 11.05 ± 2.31 | 20 |
| high | Priority rule | 19.54 ± 4.75 | 44.00 ± 6.87 | 0.93 ± 0.01 | 1199.65 ± 296.84 | 2.45 ± 1.43 | 20 |
| high | CP-SAT | 19.27 ± 5.15 | 43.80 ± 7.62 | 0.93 ± 0.01 | 1195.05 ± 332.04 | 2.60 ± 1.70 | 20 |

## CP-SAT vs the priority rule (same seeds)

| intensity | metric | CP-SAT minus priority (mean) | 95% interval | seeds CP-SAT better | worse |
|---|---|---|---|---|---|
| low | Average delay (min) | -0.08 | [-0.44, +0.19] | 5/20 | 9/20 |
| low | Punctuality (% <= 5 min late) | -0.40 | [-1.60, +0.60] | 2/20 | 3/20 |
| low | Throughput (trains/hour) | +0.00 | [+0.00, +0.00] | 0/20 | 0/20 |
| low | Priority-weighted delay | +2.55 | [-21.45, +24.10] | 4/20 | 10/20 |
| low | Actions per day | +1.00 | [+0.60, +1.40] | 0/20 | 12/20 |
| medium | Average delay (min) | -0.09 | [-0.31, +0.11] | 7/20 | 9/20 |
| medium | Punctuality (% <= 5 min late) | -1.40 | [-2.60, -0.60] | 0/20 | 6/20 |
| medium | Throughput (trains/hour) | +0.00 | [+0.00, +0.00] | 0/20 | 0/20 |
| medium | Priority-weighted delay | +7.45 | [-10.20, +25.90] | 5/20 | 11/20 |
| medium | Actions per day | +0.75 | [+0.40, +1.10] | 1/20 | 12/20 |
| high | Average delay (min) | -0.28 | [-0.69, +0.20] | 13/20 | 4/20 |
| high | Punctuality (% <= 5 min late) | -0.20 | [-1.40, +0.80] | 3/20 | 3/20 |
| high | Throughput (trains/hour) | +0.00 | [+0.00, +0.00] | 0/20 | 0/20 |
| high | Priority-weighted delay | -4.60 | [-33.40, +28.10] | 10/20 | 7/20 |
| high | Actions per day | +0.15 | [-0.45, +0.80] | 8/20 | 8/20 |

CP-SAT solver: 31665 solves, 5495 cache hits, 0 fallbacks to the priority rule, 0 not-optimal plans; median solve 9 ms, worst solve 143 ms; a full simulated day takes 13.3 s on average.
