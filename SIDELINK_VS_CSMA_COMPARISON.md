# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA

- **Generated At**: 2026-11-05 18:44:27
- **Swarm Setup**: 75 UAVs in 200m x 200m x 80m
- **Phase 1 Duration**: 10.0 ms | **Slot Width**: 500.0 µs

| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |
| :--- | :--- | :--- | :--- |
| **Phase 1 PRR** | **62.3%** | **34.6%** | **-27.7%** |
| Delivered Links | 63625 | 35311 | -28314 |
| Total Dropped Links | 38572 | 66886 | +28314 |
| CSMA Aborts | 32919 | 0 | -32919 |
| RX Deafness (Half-Duplex) | 589 | 9562 | +8973 |
| Preamble Collisions | 1784 | 17583 | +15799 |
| Preamble Low SINR Drops | 3273 | 39740 | +36467 |
| Turnaround Busy Drops | 0 | 0 | +0 |
| Payload Interference Drops | 7 | 1 | -6 |
| Power Capture Rescued Packets | 167972 | 130889 | -37083 |
| Phase 2 PRR | 37.7% | 25.6% | -12.1% |
| Phase 1 Mean IAT | 60.90 ms | 83.40 ms | +22.50 ms |
| Phase 2 Mean AoI | 70.00 ms | 184.50 ms | +114.50 ms |
