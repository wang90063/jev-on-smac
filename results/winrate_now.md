# SMAClite win rates

Seeds `[1, 2, 3, 4, 5]`. Env: SMAClite / macsmac. Dummy = attack-move motor. Jev = Choice over legal jobs.

| Map | Diff | Dummy WR | Jev WR | Dummy ret | Jev ret | Jev asked | Jev ov |
|---|---|---:|---:|---:|---:|---|---:|
| 3m | Easy | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | tie:5 | 0 |
| 8m | Easy | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | tie:24 | 0 |
| 25m | Easy | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | tie:64 | 0 |
| 5m_vs_6m | Hard | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | tie:4 | 0 |
| 8m_vs_9m | Hard | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | tie:18 | 0 |
| 10m_vs_11m | Hard | 0% (0/5) | 0% (0/5) | 13.7 | 13.6 | tie:29 | 0 |
| 27m_vs_30m | Super Hard | 20% (1/5) | 60% (3/5) | 17.4 | 18.3 | tie:96 | 0 |
| MMM | Hard | 40% (2/5) | 60% (3/5) | 18.1 | 20.4 | target:65,tie:27,heal:201 | 7 |
| MMM2 | Super Hard | 0% (0/5) | 0% (0/5) | 7.5 | 7.4 | target:61,heal:111,tie:35 | 9 |
| 2s3z | Easy | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | target:22,melee:22 | 10 |
| 3s5z | Hard | 100% (5/5) | 100% (5/5) | 20.0 | 20.0 | target:43,melee:40,tie:3 | 5 |
| 3s5z_vs_3s6z | Super Hard | 0% (0/5) | 0% (0/5) | 13.8 | 12.5 | target:56,melee:55,ranged:3,kite:3 | 23 |
| 3s_vs_3z | Easy | 0% (0/5) | 100% (5/5) | 9.0 | 20.0 | ranged:15,kite:15,stand:40 | 5 |
| 3s_vs_4z | Hard | 0% (0/5) | 100% (5/5) | 7.3 | 20.0 | ranged:20,kite:20,stand:90,target:10 | 5 |
| 3s_vs_5z | Hard | 0% (0/5) | 100% (5/5) | 5.2 | 20.0 | ranged:25,kite:25,stand:135,target:10 | 5 |
| 1c3s5z | Hard | 0% (0/5) | 20% (1/5) | 15.7 | 17.3 | target:76,melee:47,mark:11 | 73 |
| 2m_vs_1z | Easy | 0% (0/5) | 0% (0/5) | 5.4 | 5.4 | - | 0 |
| corridor | Super Hard | 0% (0/5) | 100% (5/5) | 13.2 | 20.3 | melee:126,target:74 | 40 |
| 6h_vs_8z | Super Hard | 0% (0/5) | 0% (0/5) | 12.2 | 13.1 | mark:10,target:33 | 0 |
| 2s_vs_1sc | Easy | 100% (5/5) | 100% (5/5) | 20.5 | 20.5 | - | 0 |
| so_many_baneling | Hard | 0% (0/5) | 0% (0/5) | 1.6 | 6.3 | formation:35,melee:35,bait:20,target:5 | 20 |
| bane_vs_bane | Hard | 100% (5/5) | 100% (5/5) | 19.4 | 19.4 | formation:20,target:10,melee:10,bait:10 | 20 |
| 2c_vs_64zg | Super Hard | 100% (5/5) | 100% (5/5) | 20.2 | 20.2 | target:91 | 59 |

Dummy overall: **46.1%** (53/115)
Jev overall: **67.0%** (77/115)

## Per seed

| Policy | Map | Seed | Win | Return | Steps | A left | E left | Calls | Overrides |
|---|---|---:|---:|---:|---:|---|---|---:|---|
| def | 3m | 1 | 1 | 20.00 | 14 | [2, 42.0] | [0, 0] | 0 | - |
| def | 3m | 2 | 1 | 20.00 | 14 | [2, 42.0] | [0, 0] | 0 | - |
| def | 3m | 3 | 1 | 20.00 | 14 | [2, 42.0] | [0, 0] | 0 | - |
| def | 3m | 4 | 1 | 20.00 | 14 | [2, 36.0] | [0, 0] | 0 | - |
| def | 3m | 5 | 1 | 20.00 | 15 | [2, 36.0] | [0, 0] | 0 | - |
| def | 8m | 1 | 1 | 20.00 | 19 | [4, 120.0] | [0, 0] | 0 | - |
| def | 8m | 2 | 1 | 20.00 | 19 | [4, 132.0] | [0, 0] | 0 | - |
| def | 8m | 3 | 1 | 20.00 | 19 | [4, 114.0] | [0, 0] | 0 | - |
| def | 8m | 4 | 1 | 20.00 | 19 | [4, 126.0] | [0, 0] | 0 | - |
| def | 8m | 5 | 1 | 20.00 | 19 | [4, 132.0] | [0, 0] | 0 | - |
| def | 25m | 1 | 1 | 20.00 | 29 | [8, 264.0] | [0, 0] | 0 | - |
| def | 25m | 2 | 1 | 20.00 | 33 | [5, 153.0] | [0, 0] | 0 | - |
| def | 25m | 3 | 1 | 20.00 | 28 | [9, 315.0] | [0, 0] | 0 | - |
| def | 25m | 4 | 1 | 20.00 | 27 | [10, 348.0] | [0, 0] | 0 | - |
| def | 25m | 5 | 1 | 20.00 | 28 | [9, 321.0] | [0, 0] | 0 | - |
| def | 5m_vs_6m | 1 | 1 | 20.00 | 23 | [1, 21.0] | [0, 0] | 0 | - |
| def | 5m_vs_6m | 2 | 1 | 20.00 | 20 | [2, 30.0] | [0, 0] | 0 | - |
| def | 5m_vs_6m | 3 | 1 | 20.00 | 20 | [2, 42.0] | [0, 0] | 0 | - |
| def | 5m_vs_6m | 4 | 1 | 20.00 | 23 | [1, 21.0] | [0, 0] | 0 | - |
| def | 5m_vs_6m | 5 | 1 | 20.00 | 20 | [2, 42.0] | [0, 0] | 0 | - |
| def | 8m_vs_9m | 1 | 1 | 20.00 | 24 | [2, 30.0] | [0, 0] | 0 | - |
| def | 8m_vs_9m | 2 | 1 | 20.00 | 23 | [2, 54.0] | [0, 0] | 0 | - |
| def | 8m_vs_9m | 3 | 1 | 20.00 | 24 | [2, 30.0] | [0, 0] | 0 | - |
| def | 8m_vs_9m | 4 | 1 | 20.00 | 23 | [2, 54.0] | [0, 0] | 0 | - |
| def | 8m_vs_9m | 5 | 1 | 20.00 | 24 | [2, 30.0] | [0, 0] | 0 | - |
| def | 10m_vs_11m | 1 | 0 | 12.89 | 26 | [0, 0] | [2, 66.0] | 0 | - |
| def | 10m_vs_11m | 2 | 0 | 14.71 | 32 | [0, 0] | [1, 3.0] | 0 | - |
| def | 10m_vs_11m | 3 | 0 | 13.94 | 28 | [0, 0] | [2, 24.0] | 0 | - |
| def | 10m_vs_11m | 4 | 0 | 12.89 | 26 | [0, 0] | [2, 66.0] | 0 | - |
| def | 10m_vs_11m | 5 | 0 | 13.94 | 28 | [0, 0] | [2, 24.0] | 0 | - |
| def | 27m_vs_30m | 1 | 1 | 20.00 | 36 | [3, 111.0] | [0, 0] | 0 | - |
| def | 27m_vs_30m | 2 | 0 | 17.63 | 46 | [0, 0] | [1, 9.0] | 0 | - |
| def | 27m_vs_30m | 3 | 0 | 17.44 | 44 | [0, 0] | [1, 27.0] | 0 | - |
| def | 27m_vs_30m | 4 | 0 | 15.12 | 33 | [0, 0] | [5, 201.0] | 0 | - |
| def | 27m_vs_30m | 5 | 0 | 16.84 | 37 | [0, 0] | [2, 72.0] | 0 | - |
| def | MMM | 1 | 1 | 23.30 | 74 | [4, 444.5] | [0, 0] | 0 | - |
| def | MMM | 2 | 0 | 13.09 | 77 | [0, 0] | [4, 353.0] | 0 | - |
| def | MMM | 3 | 0 | 16.80 | 85 | [0, 0] | [3, 264.3] | 0 | - |
| def | MMM | 4 | 1 | 24.74 | 79 | [4, 362.8] | [0, 0] | 0 | - |
| def | MMM | 5 | 0 | 12.66 | 54 | [0, 0] | [5, 405.0] | 0 | - |
| def | MMM2 | 1 | 0 | 7.30 | 40 | [0, 0] | [8, 630.6] | 0 | - |
| def | MMM2 | 2 | 0 | 7.46 | 38 | [0, 0] | [9, 662.3] | 0 | - |
| def | MMM2 | 3 | 0 | 7.15 | 40 | [0, 0] | [8, 625.0] | 0 | - |
| def | MMM2 | 4 | 0 | 7.46 | 43 | [0, 0] | [8, 600.0] | 0 | - |
| def | MMM2 | 5 | 0 | 8.03 | 40 | [0, 0] | [8, 604.0] | 0 | - |
| def | 2s3z | 1 | 1 | 20.00 | 44 | [2, 196.0] | [0, 0] | 0 | - |
| def | 2s3z | 2 | 1 | 20.00 | 38 | [2, 284.0] | [0, 0] | 0 | - |
| def | 2s3z | 3 | 1 | 20.00 | 46 | [2, 179.0] | [0, 0] | 0 | - |
| def | 2s3z | 4 | 1 | 20.00 | 44 | [2, 196.0] | [0, 0] | 0 | - |
| def | 2s3z | 5 | 1 | 20.00 | 46 | [2, 179.0] | [0, 0] | 0 | - |
| def | 3s5z | 1 | 1 | 20.00 | 47 | [3, 387.8] | [0, 0] | 0 | - |
| def | 3s5z | 2 | 1 | 20.00 | 47 | [3, 393.9] | [0, 0] | 0 | - |
| def | 3s5z | 3 | 1 | 20.00 | 47 | [3, 387.6] | [0, 0] | 0 | - |
| def | 3s5z | 4 | 1 | 20.00 | 47 | [3, 387.6] | [0, 0] | 0 | - |
| def | 3s5z | 5 | 1 | 20.00 | 47 | [3, 393.9] | [0, 0] | 0 | - |
| def | 3s5z_vs_3s6z | 1 | 0 | 14.16 | 52 | [0, 0] | [2, 268.0] | 0 | - |
| def | 3s5z_vs_3s6z | 2 | 0 | 13.25 | 48 | [0, 0] | [3, 334.0] | 0 | - |
| def | 3s5z_vs_3s6z | 3 | 0 | 13.25 | 48 | [0, 0] | [3, 334.0] | 0 | - |
| def | 3s5z_vs_3s6z | 4 | 0 | 14.16 | 52 | [0, 0] | [2, 268.0] | 0 | - |
| def | 3s5z_vs_3s6z | 5 | 0 | 14.16 | 52 | [0, 0] | [2, 268.0] | 0 | - |
| def | 3s_vs_3z | 1 | 0 | 9.03 | 31 | [0, 0] | [2, 153.0] | 0 | - |
| def | 3s_vs_3z | 2 | 0 | 9.03 | 31 | [0, 0] | [2, 153.0] | 0 | - |
| def | 3s_vs_3z | 3 | 0 | 9.03 | 31 | [0, 0] | [2, 153.0] | 0 | - |
| def | 3s_vs_3z | 4 | 0 | 9.03 | 31 | [0, 0] | [2, 153.0] | 0 | - |
| def | 3s_vs_3z | 5 | 0 | 9.03 | 31 | [0, 0] | [2, 153.0] | 0 | - |
| def | 3s_vs_4z | 1 | 0 | 7.31 | 31 | [0, 0] | [3, 303.0] | 0 | - |
| def | 3s_vs_4z | 2 | 0 | 7.31 | 31 | [0, 0] | [3, 303.0] | 0 | - |
| def | 3s_vs_4z | 3 | 0 | 7.31 | 31 | [0, 0] | [3, 303.0] | 0 | - |
| def | 3s_vs_4z | 4 | 0 | 7.31 | 31 | [0, 0] | [3, 303.0] | 0 | - |
| def | 3s_vs_4z | 5 | 0 | 7.31 | 31 | [0, 0] | [3, 303.0] | 0 | - |
| def | 3s_vs_5z | 1 | 0 | 5.18 | 27 | [0, 0] | [4, 501.0] | 0 | - |
| def | 3s_vs_5z | 2 | 0 | 5.18 | 27 | [0, 0] | [4, 501.0] | 0 | - |
| def | 3s_vs_5z | 3 | 0 | 5.18 | 27 | [0, 0] | [4, 501.0] | 0 | - |
| def | 3s_vs_5z | 4 | 0 | 5.18 | 27 | [0, 0] | [4, 501.0] | 0 | - |
| def | 3s_vs_5z | 5 | 0 | 5.18 | 27 | [0, 0] | [4, 501.0] | 0 | - |
| def | 1c3s5z | 1 | 0 | 15.67 | 50 | [0, 0] | [3, 200.4] | 0 | - |
| def | 1c3s5z | 2 | 0 | 15.67 | 50 | [0, 0] | [3, 200.1] | 0 | - |
| def | 1c3s5z | 3 | 0 | 15.67 | 50 | [0, 0] | [3, 200.4] | 0 | - |
| def | 1c3s5z | 4 | 0 | 15.67 | 50 | [0, 0] | [3, 200.2] | 0 | - |
| def | 1c3s5z | 5 | 0 | 15.67 | 50 | [0, 0] | [3, 200.0] | 0 | - |
| def | 2m_vs_1z | 1 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| def | 2m_vs_1z | 2 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| def | 2m_vs_1z | 3 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| def | 2m_vs_1z | 4 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| def | 2m_vs_1z | 5 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| def | corridor | 1 | 0 | 13.09 | 39 | [0, 0] | [6, 195.1] | 0 | - |
| def | corridor | 2 | 0 | 13.36 | 40 | [0, 0] | [6, 178.7] | 0 | - |
| def | corridor | 3 | 0 | 13.84 | 42 | [0, 0] | [5, 163.2] | 0 | - |
| def | corridor | 4 | 0 | 12.39 | 38 | [0, 0] | [7, 229.2] | 0 | - |
| def | corridor | 5 | 0 | 13.39 | 40 | [0, 0] | [6, 178.5] | 0 | - |
| def | 6h_vs_8z | 1 | 0 | 12.05 | 30 | [0, 0] | [3, 358.0] | 0 | - |
| def | 6h_vs_8z | 2 | 0 | 12.35 | 30 | [0, 0] | [3, 336.0] | 0 | - |
| def | 6h_vs_8z | 3 | 0 | 12.35 | 30 | [0, 0] | [3, 336.0] | 0 | - |
| def | 6h_vs_8z | 4 | 0 | 12.35 | 30 | [0, 0] | [3, 336.0] | 0 | - |
| def | 6h_vs_8z | 5 | 0 | 12.05 | 30 | [0, 0] | [3, 358.0] | 0 | - |
| def | 2s_vs_1sc | 1 | 1 | 20.49 | 68 | [2, 4.1] | [0, 0] | 0 | - |
| def | 2s_vs_1sc | 2 | 1 | 20.49 | 68 | [2, 4.2] | [0, 0] | 0 | - |
| def | 2s_vs_1sc | 3 | 1 | 20.49 | 68 | [2, 4.0] | [0, 0] | 0 | - |
| def | 2s_vs_1sc | 4 | 1 | 20.49 | 68 | [2, 4.1] | [0, 0] | 0 | - |
| def | 2s_vs_1sc | 5 | 1 | 20.49 | 68 | [2, 4.2] | [0, 0] | 0 | - |
| def | so_many_baneling | 1 | 0 | 1.62 | 4 | [0, 0] | [28, 840.0] | 0 | - |
| def | so_many_baneling | 2 | 0 | 1.62 | 4 | [0, 0] | [28, 840.0] | 0 | - |
| def | so_many_baneling | 3 | 0 | 1.62 | 4 | [0, 0] | [28, 840.0] | 0 | - |
| def | so_many_baneling | 4 | 0 | 1.62 | 4 | [0, 0] | [28, 840.0] | 0 | - |
| def | so_many_baneling | 5 | 0 | 1.62 | 4 | [0, 0] | [28, 840.0] | 0 | - |
| def | bane_vs_bane | 1 | 1 | 19.36 | 10 | [0, 0] | [0, 0] | 0 | - |
| def | bane_vs_bane | 2 | 1 | 19.36 | 10 | [0, 0] | [0, 0] | 0 | - |
| def | bane_vs_bane | 3 | 1 | 19.36 | 10 | [0, 0] | [0, 0] | 0 | - |
| def | bane_vs_bane | 4 | 1 | 19.36 | 10 | [0, 0] | [0, 0] | 0 | - |
| def | bane_vs_bane | 5 | 1 | 19.36 | 10 | [0, 0] | [0, 0] | 0 | - |
| def | 2c_vs_64zg | 1 | 1 | 20.21 | 43 | [2, 700.0] | [0, 0] | 0 | - |
| def | 2c_vs_64zg | 2 | 1 | 20.24 | 46 | [2, 700.0] | [0, 0] | 0 | - |
| def | 2c_vs_64zg | 3 | 1 | 20.24 | 43 | [2, 700.0] | [0, 0] | 0 | - |
| def | 2c_vs_64zg | 4 | 1 | 20.22 | 46 | [2, 700.0] | [0, 0] | 0 | - |
| def | 2c_vs_64zg | 5 | 1 | 20.29 | 43 | [2, 700.0] | [0, 0] | 0 | - |
| jev | 3m | 1 | 1 | 20.00 | 14 | [2, 42.0] | [0, 0] | 1 | - |
| jev | 3m | 2 | 1 | 20.00 | 14 | [2, 42.0] | [0, 0] | 1 | - |
| jev | 3m | 3 | 1 | 20.00 | 14 | [2, 42.0] | [0, 0] | 1 | - |
| jev | 3m | 4 | 1 | 20.00 | 14 | [2, 36.0] | [0, 0] | 1 | - |
| jev | 3m | 5 | 1 | 20.00 | 15 | [2, 36.0] | [0, 0] | 1 | - |
| jev | 8m | 1 | 1 | 20.00 | 20 | [4, 96.0] | [0, 0] | 5 | - |
| jev | 8m | 2 | 1 | 20.00 | 19 | [4, 132.0] | [0, 0] | 4 | - |
| jev | 8m | 3 | 1 | 20.00 | 19 | [4, 120.0] | [0, 0] | 5 | - |
| jev | 8m | 4 | 1 | 20.00 | 20 | [4, 96.0] | [0, 0] | 5 | - |
| jev | 8m | 5 | 1 | 20.00 | 19 | [4, 120.0] | [0, 0] | 5 | - |
| jev | 25m | 1 | 1 | 20.00 | 29 | [8, 264.0] | [0, 0] | 12 | - |
| jev | 25m | 2 | 1 | 20.00 | 33 | [5, 153.0] | [0, 0] | 16 | - |
| jev | 25m | 3 | 1 | 20.00 | 28 | [9, 339.0] | [0, 0] | 12 | - |
| jev | 25m | 4 | 1 | 20.00 | 28 | [9, 339.0] | [0, 0] | 12 | - |
| jev | 25m | 5 | 1 | 20.00 | 27 | [9, 339.0] | [0, 0] | 12 | - |
| jev | 5m_vs_6m | 1 | 1 | 20.00 | 23 | [1, 21.0] | [0, 0] | 1 | - |
| jev | 5m_vs_6m | 2 | 1 | 20.00 | 20 | [2, 30.0] | [0, 0] | 0 | - |
| jev | 5m_vs_6m | 3 | 1 | 20.00 | 20 | [2, 42.0] | [0, 0] | 1 | - |
| jev | 5m_vs_6m | 4 | 1 | 20.00 | 23 | [1, 21.0] | [0, 0] | 1 | - |
| jev | 5m_vs_6m | 5 | 1 | 20.00 | 20 | [2, 42.0] | [0, 0] | 1 | - |
| jev | 8m_vs_9m | 1 | 1 | 20.00 | 24 | [2, 30.0] | [0, 0] | 4 | - |
| jev | 8m_vs_9m | 2 | 1 | 20.00 | 23 | [2, 54.0] | [0, 0] | 3 | - |
| jev | 8m_vs_9m | 3 | 1 | 20.00 | 24 | [2, 30.0] | [0, 0] | 4 | - |
| jev | 8m_vs_9m | 4 | 1 | 20.00 | 23 | [2, 54.0] | [0, 0] | 3 | - |
| jev | 8m_vs_9m | 5 | 1 | 20.00 | 24 | [2, 30.0] | [0, 0] | 4 | - |
| jev | 10m_vs_11m | 1 | 0 | 12.60 | 25 | [0, 0] | [2, 78.0] | 6 | - |
| jev | 10m_vs_11m | 2 | 0 | 14.71 | 32 | [0, 0] | [1, 3.0] | 5 | - |
| jev | 10m_vs_11m | 3 | 0 | 13.94 | 28 | [0, 0] | [2, 24.0] | 6 | - |
| jev | 10m_vs_11m | 4 | 0 | 12.60 | 25 | [0, 0] | [2, 78.0] | 6 | - |
| jev | 10m_vs_11m | 5 | 0 | 13.94 | 28 | [0, 0] | [2, 24.0] | 6 | - |
| jev | 27m_vs_30m | 1 | 1 | 20.00 | 35 | [5, 123.0] | [0, 0] | 19 | - |
| jev | 27m_vs_30m | 2 | 1 | 20.00 | 41 | [2, 18.0] | [0, 0] | 18 | - |
| jev | 27m_vs_30m | 3 | 1 | 20.00 | 40 | [3, 63.0] | [0, 0] | 19 | - |
| jev | 27m_vs_30m | 4 | 0 | 15.91 | 35 | [0, 0] | [4, 138.0] | 20 | - |
| jev | 27m_vs_30m | 5 | 0 | 15.78 | 35 | [0, 0] | [4, 150.0] | 20 | - |
| jev | MMM | 1 | 1 | 23.30 | 74 | [4, 444.5] | [0, 0] | 20 | t=0 target weakest_in_range->frontline |
| jev | MMM | 2 | 1 | 24.41 | 76 | [4, 334.8] | [0, 0] | 73 | t=0 target weakest_in_range->frontline |
| jev | MMM | 3 | 0 | 14.71 | 80 | [0, 0] | [4, 325.9] | 37 | t=0 target weakest_in_range->frontline; t=44 target weakest_in_range->frontline |
| jev | MMM | 4 | 1 | 24.17 | 76 | [4, 378.5] | [0, 0] | 73 | t=0 target weakest_in_range->frontline; t=30 target weakest_in_range->frontline |
| jev | MMM | 5 | 0 | 15.17 | 79 | [0, 0] | [4, 337.0] | 37 | t=0 target weakest_in_range->frontline |
| jev | MMM2 | 1 | 0 | 7.00 | 39 | [0, 0] | [7, 615.3] | 27 | t=0 target weakest_in_range->frontline; t=29 target weakest_in_range->frontline |
| jev | MMM2 | 2 | 0 | 7.14 | 37 | [0, 0] | [9, 673.9] | 27 | t=0 target weakest_in_range->frontline; t=28 target weakest_in_range->frontline |
| jev | MMM2 | 3 | 0 | 7.15 | 40 | [0, 0] | [8, 625.0] | 26 | t=0 target weakest_in_range->heaviest; t=28 target weakest_in_range->frontline |
| jev | MMM2 | 4 | 0 | 7.46 | 43 | [0, 0] | [8, 600.0] | 29 | t=0 target weakest_in_range->frontline |
| jev | MMM2 | 5 | 0 | 8.04 | 39 | [0, 0] | [8, 630.0] | 26 | t=0 target weakest_in_range->heaviest; t=27 target weakest_in_range->frontline |
| jev | 2s3z | 1 | 1 | 20.00 | 44 | [2, 196.0] | [0, 0] | 5 | t=0 target weakest_in_range->frontline; t=11 target weakest_in_range->frontline |
| jev | 2s3z | 2 | 1 | 20.00 | 38 | [2, 284.0] | [0, 0] | 5 | t=0 target weakest_in_range->frontline; t=11 target weakest_in_range->frontline |
| jev | 2s3z | 3 | 1 | 20.00 | 46 | [2, 179.0] | [0, 0] | 6 | t=0 target weakest_in_range->frontline; t=11 target weakest_in_range->frontline |
| jev | 2s3z | 4 | 1 | 20.00 | 44 | [2, 196.0] | [0, 0] | 5 | t=0 target weakest_in_range->frontline; t=11 target weakest_in_range->frontline |
| jev | 2s3z | 5 | 1 | 20.00 | 46 | [2, 179.0] | [0, 0] | 6 | t=0 target weakest_in_range->frontline; t=11 target weakest_in_range->frontline |
| jev | 3s5z | 1 | 1 | 20.00 | 47 | [3, 387.8] | [0, 0] | 11 | t=0 target weakest_in_range->frontline |
| jev | 3s5z | 2 | 1 | 20.00 | 47 | [3, 393.9] | [0, 0] | 9 | t=0 target weakest_in_range->frontline |
| jev | 3s5z | 3 | 1 | 20.00 | 47 | [3, 387.6] | [0, 0] | 11 | t=0 target weakest_in_range->frontline |
| jev | 3s5z | 4 | 1 | 20.00 | 47 | [3, 387.6] | [0, 0] | 11 | t=0 target weakest_in_range->frontline |
| jev | 3s5z | 5 | 1 | 20.00 | 47 | [3, 393.9] | [0, 0] | 9 | t=0 target weakest_in_range->frontline |
| jev | 3s5z_vs_3s6z | 1 | 0 | 13.34 | 50 | [0, 0] | [3, 330.1] | 12 | t=0 target weakest_in_range->frontline; t=19 melee charge->hold_choke; t=25 melee hold_choke->charge; t=31 target weakest_in_range->frontline; t=48 ranged stack->stutter; t=48 kite all->peel_tagged |
| jev | 3s5z_vs_3s6z | 2 | 0 | 11.43 | 43 | [0, 0] | [4, 476.0] | 14 | t=0 target weakest_in_range->frontline; t=7 melee charge->hold_choke |
| jev | 3s5z_vs_3s6z | 3 | 0 | 11.26 | 42 | [0, 0] | [4, 490.0] | 15 | t=0 target weakest_in_range->frontline; t=7 melee charge->hold_choke; t=21 target weakest_in_range->frontline |
| jev | 3s5z_vs_3s6z | 4 | 0 | 13.34 | 50 | [0, 0] | [3, 330.0] | 12 | t=0 target weakest_in_range->frontline; t=19 melee charge->hold_choke; t=25 melee hold_choke->charge; t=31 target weakest_in_range->frontline; t=48 ranged stack->stutter; t=48 kite all->peel_tagged |
| jev | 3s5z_vs_3s6z | 5 | 0 | 13.34 | 50 | [0, 0] | [3, 330.0] | 12 | t=0 target weakest_in_range->frontline; t=19 melee charge->hold_choke; t=25 melee hold_choke->charge; t=31 target weakest_in_range->frontline; t=48 ranged stack->stutter; t=48 kite all->peel_tagged |
| jev | 3s_vs_3z | 1 | 1 | 20.00 | 58 | [3, 326.4] | [0, 0] | 11 | t=0 ranged stack->stutter |
| jev | 3s_vs_3z | 2 | 1 | 20.00 | 58 | [3, 326.2] | [0, 0] | 11 | t=0 ranged stack->stutter |
| jev | 3s_vs_3z | 3 | 1 | 20.00 | 58 | [3, 326.4] | [0, 0] | 11 | t=0 ranged stack->stutter |
| jev | 3s_vs_3z | 4 | 1 | 20.00 | 58 | [3, 326.2] | [0, 0] | 11 | t=0 ranged stack->stutter |
| jev | 3s_vs_3z | 5 | 1 | 20.00 | 58 | [3, 326.2] | [0, 0] | 11 | t=0 ranged stack->stutter |
| jev | 3s_vs_4z | 1 | 1 | 20.00 | 92 | [3, 179.8] | [0, 0] | 21 | t=0 ranged stack->stutter |
| jev | 3s_vs_4z | 2 | 1 | 20.00 | 92 | [3, 179.1] | [0, 0] | 21 | t=0 ranged stack->stutter |
| jev | 3s_vs_4z | 3 | 1 | 20.00 | 92 | [3, 179.6] | [0, 0] | 21 | t=0 ranged stack->stutter |
| jev | 3s_vs_4z | 4 | 1 | 20.00 | 92 | [3, 179.8] | [0, 0] | 21 | t=0 ranged stack->stutter |
| jev | 3s_vs_4z | 5 | 1 | 20.00 | 92 | [3, 179.6] | [0, 0] | 21 | t=0 ranged stack->stutter |
| jev | 3s_vs_5z | 1 | 1 | 20.00 | 124 | [3, 150.4] | [0, 0] | 32 | t=0 ranged stack->stutter |
| jev | 3s_vs_5z | 2 | 1 | 20.00 | 124 | [3, 150.1] | [0, 0] | 32 | t=0 ranged stack->stutter |
| jev | 3s_vs_5z | 3 | 1 | 20.00 | 124 | [3, 150.4] | [0, 0] | 32 | t=0 ranged stack->stutter |
| jev | 3s_vs_5z | 4 | 1 | 20.00 | 124 | [3, 150.4] | [0, 0] | 32 | t=0 ranged stack->stutter |
| jev | 3s_vs_5z | 5 | 1 | 20.00 | 124 | [3, 150.1] | [0, 0] | 32 | t=0 ranged stack->stutter |
| jev | 1c3s5z | 1 | 0 | 16.67 | 75 | [0, 0] | [1, 101.0] | 19 | t=8 target clump->weakest_in_range; t=9 target clump->weakest_in_range; t=10 target clump->weakest_in_range; t=11 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=17 target clump->weakest_in_range; t=18 target clump->weakest_in_range; t=19 target clump->frontline |
| jev | 1c3s5z | 2 | 1 | 20.00 | 80 | [1, 101.0] | [0, 0] | 16 | t=8 melee charge->hold_choke; t=8 target clump->weakest_in_range; t=9 target clump->weakest_in_range; t=10 melee hold_choke->charge; t=10 target clump->weakest_in_range; t=11 target clump->weakest_in_range; t=15 target clump->weakest_in_range; t=18 target clump->weakest_in_range |
| jev | 1c3s5z | 3 | 0 | 16.67 | 75 | [0, 0] | [1, 101.0] | 19 | t=8 target clump->weakest_in_range; t=9 target clump->weakest_in_range; t=10 target clump->weakest_in_range; t=11 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=17 target clump->weakest_in_range; t=18 target clump->weakest_in_range; t=19 target clump->frontline |
| jev | 1c3s5z | 4 | 0 | 16.67 | 75 | [0, 0] | [1, 101.0] | 19 | t=8 target clump->weakest_in_range; t=9 target clump->weakest_in_range; t=10 target clump->weakest_in_range; t=11 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=17 target clump->weakest_in_range; t=18 target clump->weakest_in_range; t=19 target clump->frontline |
| jev | 1c3s5z | 5 | 0 | 16.67 | 75 | [0, 0] | [1, 101.0] | 19 | t=8 target clump->weakest_in_range; t=9 target clump->weakest_in_range; t=10 target clump->weakest_in_range; t=11 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=17 target clump->weakest_in_range; t=18 target clump->weakest_in_range; t=19 target clump->frontline |
| jev | 2m_vs_1z | 1 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| jev | 2m_vs_1z | 2 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| jev | 2m_vs_1z | 3 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| jev | 2m_vs_1z | 4 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| jev | 2m_vs_1z | 5 | 0 | 5.44 | 17 | [0, 0] | [1, 52.0] | 0 | - |
| jev | corridor | 1 | 1 | 20.32 | 94 | [1, 16.0] | [0, 0] | 25 | t=0 melee charge->hold_choke; t=14 melee hold_choke->charge; t=21 melee charge->hold_choke; t=27 melee hold_choke->charge; t=38 melee charge->hold_choke; t=44 melee hold_choke->charge; t=53 melee charge->hold_choke; t=58 melee hold_choke->charge |
| jev | corridor | 2 | 1 | 20.29 | 93 | [1, 44.0] | [0, 0] | 25 | t=0 melee charge->hold_choke; t=14 melee hold_choke->charge; t=21 melee charge->hold_choke; t=23 melee hold_choke->charge; t=31 melee charge->hold_choke; t=36 melee hold_choke->charge; t=42 melee charge->hold_choke; t=49 melee hold_choke->charge |
| jev | corridor | 3 | 1 | 20.28 | 93 | [1, 44.0] | [0, 0] | 25 | t=0 melee charge->hold_choke; t=14 melee hold_choke->charge; t=21 melee charge->hold_choke; t=27 melee hold_choke->charge; t=36 melee charge->hold_choke; t=38 melee hold_choke->charge; t=49 melee charge->hold_choke; t=51 melee hold_choke->charge |
| jev | corridor | 4 | 1 | 20.28 | 92 | [1, 52.0] | [0, 0] | 25 | t=0 melee charge->hold_choke; t=14 melee hold_choke->charge; t=21 melee charge->hold_choke; t=30 melee hold_choke->charge; t=41 melee charge->hold_choke; t=48 melee hold_choke->charge |
| jev | corridor | 5 | 1 | 20.36 | 87 | [1, 4.0] | [0, 0] | 26 | t=0 melee charge->hold_choke; t=14 melee hold_choke->charge; t=21 melee charge->hold_choke; t=30 melee hold_choke->charge; t=42 melee charge->hold_choke; t=52 melee hold_choke->charge |
| jev | 6h_vs_8z | 1 | 0 | 12.97 | 30 | [0, 0] | [2, 300.0] | 7 | - |
| jev | 6h_vs_8z | 2 | 0 | 13.13 | 30 | [0, 0] | [2, 288.0] | 8 | - |
| jev | 6h_vs_8z | 3 | 0 | 12.97 | 30 | [0, 0] | [2, 300.0] | 7 | - |
| jev | 6h_vs_8z | 4 | 0 | 13.13 | 30 | [0, 0] | [2, 288.0] | 8 | - |
| jev | 6h_vs_8z | 5 | 0 | 13.13 | 30 | [0, 0] | [2, 288.0] | 8 | - |
| jev | 2s_vs_1sc | 1 | 1 | 20.49 | 68 | [2, 4.1] | [0, 0] | 0 | - |
| jev | 2s_vs_1sc | 2 | 1 | 20.49 | 68 | [2, 4.2] | [0, 0] | 0 | - |
| jev | 2s_vs_1sc | 3 | 1 | 20.49 | 68 | [2, 4.0] | [0, 0] | 0 | - |
| jev | 2s_vs_1sc | 4 | 1 | 20.49 | 68 | [2, 4.1] | [0, 0] | 0 | - |
| jev | 2s_vs_1sc | 5 | 1 | 20.49 | 68 | [2, 4.2] | [0, 0] | 0 | - |
| jev | so_many_baneling | 1 | 0 | 6.08 | 14 | [0, 0] | [17, 510.0] | 7 | t=0 formation keep->open; t=0 melee charge->snipe; t=11 formation open->keep; t=13 melee snipe->charge |
| jev | so_many_baneling | 2 | 0 | 6.49 | 14 | [0, 0] | [16, 480.0] | 7 | t=0 formation keep->open; t=0 melee charge->snipe; t=11 formation open->keep; t=12 melee snipe->charge |
| jev | so_many_baneling | 3 | 0 | 6.49 | 14 | [0, 0] | [16, 480.0] | 7 | t=0 formation keep->open; t=0 melee charge->snipe; t=12 formation open->keep; t=12 melee snipe->charge |
| jev | so_many_baneling | 4 | 0 | 6.49 | 14 | [0, 0] | [16, 480.0] | 7 | t=0 formation keep->open; t=0 melee charge->snipe; t=12 formation open->keep; t=12 melee snipe->charge |
| jev | so_many_baneling | 5 | 0 | 6.08 | 14 | [0, 0] | [17, 510.0] | 7 | t=0 formation keep->open; t=0 melee charge->snipe; t=11 formation open->keep; t=13 melee snipe->charge |
| jev | bane_vs_bane | 1 | 1 | 19.36 | 12 | [16, 560.0] | [0, 0] | 4 | t=0 formation keep->open; t=6 melee charge->snipe; t=10 bait bait_one->bait_two |
| jev | bane_vs_bane | 2 | 1 | 19.36 | 12 | [16, 560.0] | [0, 0] | 4 | t=0 formation keep->open; t=5 formation open->keep; t=6 formation keep->open; t=6 melee charge->snipe; t=10 bait bait_one->bait_two |
| jev | bane_vs_bane | 3 | 1 | 19.36 | 12 | [16, 560.0] | [0, 0] | 4 | t=0 formation keep->open; t=6 melee charge->snipe; t=10 melee snipe->charge; t=10 bait bait_one->bait_two |
| jev | bane_vs_bane | 4 | 1 | 19.36 | 12 | [16, 560.0] | [0, 0] | 4 | t=0 formation keep->open; t=6 melee charge->snipe; t=10 bait bait_one->bait_two |
| jev | bane_vs_bane | 5 | 1 | 19.36 | 12 | [16, 560.0] | [0, 0] | 4 | t=0 formation keep->open; t=5 formation open->keep; t=6 formation keep->open; t=6 melee charge->snipe; t=10 bait bait_one->bait_two |
| jev | 2c_vs_64zg | 1 | 1 | 20.20 | 43 | [2, 700.0] | [0, 0] | 19 | t=3 target clump->weakest_in_range; t=5 target clump->weakest_in_range; t=7 target clump->weakest_in_range; t=10 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=21 target clump->weakest_in_range; t=23 target clump->weakest_in_range; t=25 target clump->weakest_in_range |
| jev | 2c_vs_64zg | 2 | 1 | 20.28 | 43 | [2, 700.0] | [0, 0] | 19 | t=5 target clump->weakest_in_range; t=7 target clump->weakest_in_range; t=12 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=23 target clump->weakest_in_range; t=28 target clump->weakest_in_range; t=30 target clump->weakest_in_range; t=32 target clump->weakest_in_range |
| jev | 2c_vs_64zg | 3 | 1 | 20.27 | 43 | [2, 700.0] | [0, 0] | 18 | t=3 target clump->weakest_in_range; t=5 target clump->weakest_in_range; t=7 target clump->weakest_in_range; t=12 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=23 target clump->weakest_in_range; t=28 target clump->weakest_in_range; t=30 target clump->weakest_in_range |
| jev | 2c_vs_64zg | 4 | 1 | 20.22 | 41 | [2, 700.0] | [0, 0] | 17 | t=3 target clump->weakest_in_range; t=5 target clump->weakest_in_range; t=7 target clump->weakest_in_range; t=10 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=21 target clump->weakest_in_range; t=23 target clump->weakest_in_range; t=25 target clump->weakest_in_range |
| jev | 2c_vs_64zg | 5 | 1 | 20.22 | 41 | [2, 700.0] | [0, 0] | 18 | t=3 target clump->weakest_in_range; t=5 target clump->weakest_in_range; t=7 target clump->weakest_in_range; t=16 target clump->weakest_in_range; t=21 target clump->weakest_in_range; t=23 target clump->weakest_in_range; t=25 target clump->weakest_in_range; t=28 target clump->weakest_in_range |
