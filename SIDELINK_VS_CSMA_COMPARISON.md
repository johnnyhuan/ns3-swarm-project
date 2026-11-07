# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA

- **Generated At**: 2026-11-07 11:09:56
- **Swarm Setup**: 75 UAVs in 200m x 200m x 80m
- **Phase 1 Duration**: 10.0 ms | **Slot Width**: 250.0 µs

| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |
| :--- | :--- | :--- | :--- |
| **Phase 1 PRR (Overall 0~10s)** | **89.0%** | **75.3%** | **-13.7%** |
| **Phase 1 Steady-State PRR (Last 2s)** | **87.7%** | **73.2%** | **-14.5%** |
| Delivered Links | 90994 | 76913 | -14081 |
| Total Dropped Links | 11203 | 25284 | +14081 |
| CSMA Aborts | 1849 | 101 | -1748 |
| RX Deafness (Half-Duplex) | 1070 | 5854 | +4784 |
| Preamble Collisions | 6170 | 12989 | +6819 |
| Preamble Low SINR Drops | 1810 | 5847 | +4037 |
| Turnaround Busy Drops | 0 | 0 | +0 |
| Payload Interference Drops | 304 | 493 | +189 |
| Power Capture Rescued Packets | 51520 | 85115 | +33595 |
| Phase 2 PRR | 82.1% | 67.3% | -14.8% |
| Phase 1 Mean IAT | 43.10 ms | 49.30 ms | +6.20 ms |
| Phase 2 Mean AoI | 13.20 ms | 40.30 ms | +27.10 ms |
