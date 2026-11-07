# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA

- **Generated At**: 2026-11-07 10:48:37
- **Swarm Setup**: 75 UAVs in 200m x 200m x 80m
- **Phase 1 Duration**: 10.0 ms | **Slot Width**: 500.0 µs

| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |
| :--- | :--- | :--- | :--- |
| **Phase 1 PRR** | **91.1%** | **66.4%** | **-24.7%** |
| Delivered Links | 9402 | 6857 | -2545 |
| Total Dropped Links | 922 | 3467 | +2545 |
| CSMA Aborts | 138 | 0 | -138 |
| RX Deafness (Half-Duplex) | 86 | 689 | +603 |
| Preamble Collisions | 504 | 1342 | +838 |
| Preamble Low SINR Drops | 167 | 1373 | +1206 |
| Turnaround Busy Drops | 0 | 0 | +0 |
| Payload Interference Drops | 27 | 63 | +36 |
| Power Capture Rescued Packets | 4202 | 5040 | +838 |
| Phase 2 PRR | 85.5% | 64.0% | -21.5% |
| Phase 1 Mean IAT | 39.40 ms | 45.40 ms | +6.00 ms |
| Phase 2 Mean AoI | 9.30 ms | 41.60 ms | +32.30 ms |
