# Benchmark (mean of 20 seeds, ML delay model, synthetic data)

Seeds 1..20; mean ± standard deviation over seeds.

| intensity | strategy | Average delay (min) | Punctuality (% <= 5 min late) | Throughput (trains/hour) | Priority-weighted delay | Actions per day | runs |
|---|---|---|---|---|---|---|---|
| low | No control | 9.47 ± 2.79 | 66.00 ± 5.88 | 0.93 ± 0.01 | 631.30 ± 197.80 | 0.00 ± 0.00 | 20 |
| low | FCFS | 9.31 ± 2.47 | 65.80 ± 6.01 | 0.93 ± 0.01 | 619.80 ± 190.32 | 9.70 ± 1.53 | 20 |
| low | Priority rule | 8.40 ± 2.63 | 66.20 ± 5.87 | 0.93 ± 0.01 | 521.90 ± 181.99 | 1.55 ± 0.76 | 20 |
| low | CP-SAT | 7.99 ± 2.56 | 67.40 ± 6.52 | 0.93 ± 0.01 | 496.85 ± 179.61 | 2.30 ± 0.98 | 20 |
| medium | No control | 13.87 ± 3.70 | 58.00 ± 7.51 | 0.93 ± 0.01 | 916.55 ± 259.51 | 0.00 ± 0.00 | 20 |
| medium | FCFS | 14.29 ± 4.12 | 58.00 ± 7.51 | 0.93 ± 0.01 | 953.70 ± 302.71 | 9.30 ± 1.66 | 20 |
| medium | Priority rule | 13.31 ± 3.83 | 59.20 ± 7.06 | 0.93 ± 0.01 | 835.65 ± 271.50 | 2.00 ± 1.17 | 20 |
| medium | CP-SAT | 12.63 ± 3.60 | 59.40 ± 7.37 | 0.93 ± 0.01 | 798.30 ± 255.98 | 2.20 ± 1.20 | 20 |
| high | No control | 20.75 ± 5.07 | 43.00 ± 6.47 | 0.93 ± 0.01 | 1329.90 ± 336.83 | 0.00 ± 0.00 | 20 |
| high | FCFS | 21.04 ± 5.41 | 43.00 ± 7.44 | 0.93 ± 0.01 | 1348.70 ± 365.18 | 10.90 ± 2.43 | 20 |
| high | Priority rule | 20.02 ± 4.88 | 43.60 ± 7.33 | 0.93 ± 0.01 | 1225.75 ± 307.71 | 2.85 ± 1.27 | 20 |
| high | CP-SAT | 19.54 ± 5.26 | 43.00 ± 7.55 | 0.93 ± 0.01 | 1216.70 ± 343.86 | 2.70 ± 1.08 | 20 |

## CP-SAT vs the priority rule (same seeds)

| intensity | metric | CP-SAT minus priority (mean) | 95% interval | seeds CP-SAT better | worse |
|---|---|---|---|---|---|
| low | Average delay (min) | -0.41 | [-0.63, -0.20] | 13/20 | 1/20 |
| low | Punctuality (% <= 5 min late) | +1.20 | [+0.20, +2.40] | 6/20 | 1/20 |
| low | Throughput (trains/hour) | +0.00 | [+0.00, +0.00] | 0/20 | 0/20 |
| low | Priority-weighted delay | -25.05 | [-40.30, -11.50] | 12/20 | 1/20 |
| low | Actions per day | +0.75 | [+0.50, +1.05] | 0/20 | 13/20 |
| medium | Average delay (min) | -0.68 | [-1.04, -0.37] | 13/20 | 1/20 |
| medium | Punctuality (% <= 5 min late) | +0.20 | [-1.00, +1.40] | 3/20 | 3/20 |
| medium | Throughput (trains/hour) | +0.00 | [+0.00, +0.00] | 0/20 | 0/20 |
| medium | Priority-weighted delay | -37.35 | [-57.45, -19.75] | 12/20 | 2/20 |
| medium | Actions per day | +0.20 | [-0.30, +0.65] | 6/20 | 9/20 |
| high | Average delay (min) | -0.48 | [-0.95, -0.04] | 11/20 | 5/20 |
| high | Punctuality (% <= 5 min late) | -0.60 | [-1.80, +0.40] | 2/20 | 4/20 |
| high | Throughput (trains/hour) | +0.00 | [+0.00, +0.00] | 0/20 | 0/20 |
| high | Priority-weighted delay | -9.05 | [-37.50, +19.80] | 10/20 | 6/20 |
| high | Actions per day | -0.15 | [-0.55, +0.25] | 7/20 | 6/20 |

CP-SAT solver: 30918 solves, 3081 cache hits, 0 fallbacks to the priority rule, 0 not-optimal plans; median solve 18 ms, worst solve 228 ms; a full simulated day takes 46.3 s on average.
