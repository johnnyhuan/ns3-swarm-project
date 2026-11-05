# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA

- **Generated At**: 2026-11-05 17:58:35
- **Swarm Setup**: 75 UAVs in 200m x 200m x 80m
- **Phase 1 Duration**: 10.0 ms | **Slot Width**: 500.0 µs

| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |
| :--- | :--- | :--- | :--- |
| **Phase 1 PRR** | **89.0%** | **44.2%** | **-44.8%** |
| Delivered Links | 90994 | 45188 | -45806 |
| Total Dropped Links | 11203 | 57009 | +45806 |
| CSMA Aborts | 1849 | 0 | -1849 |
| RX Deafness (Half-Duplex) | 0 | 0 | +0 |
| Preamble Collisions | 6170 | 27316 | +21146 |
| Preamble Low SINR Drops | 1810 | 19708 | +17898 |
| Turnaround Busy Drops | 0 | 0 | +0 |
| Payload Interference Drops | 304 | 413 | +109 |
| Power Capture Rescued Packets | 51520 | 998 | -50522 |
| Phase 2 PRR | 0.0% | 0.0% | +0.0% |
| Phase 1 Mean IAT | 0.00 ms | 0.00 ms | +0.00 ms |
| Phase 2 Mean AoI | 0.00 ms | 0.00 ms | +0.00 ms |
