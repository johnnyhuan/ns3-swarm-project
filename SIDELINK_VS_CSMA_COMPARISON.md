# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA

- **Generated At**: 2026-11-06 08:36:25
- **Swarm Setup**: 75 UAVs in 200m x 200m x 80m
- **Phase 1 Duration**: 10.0 ms | **Slot Width**: 500.0 µs

| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |
| :--- | :--- | :--- | :--- |
| **Phase 1 PRR** | **91.1%** | **58.5%** | **-32.6%** |
| Delivered Links | 9402 | 6040 | -3362 |
| Total Dropped Links | 922 | 4284 | +3362 |
| CSMA Aborts | 138 | 0 | -138 |
| RX Deafness (Half-Duplex) | 86 | 689 | +603 |
| Preamble Collisions | 504 | 2159 | +1655 |
| Preamble Low SINR Drops | 167 | 1373 | +1206 |
| Turnaround Busy Drops | 0 | 0 | +0 |
| Payload Interference Drops | 27 | 63 | +36 |
| Power Capture Rescued Packets | 4202 | 237 | -3965 |
| Phase 2 PRR | 85.5% | 58.9% | -26.6% |
| Phase 1 Mean IAT | 39.40 ms | 49.60 ms | +10.20 ms |
| Phase 2 Mean AoI | 9.30 ms | 48.70 ms | +39.40 ms |
