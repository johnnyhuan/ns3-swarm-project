# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA

- **Generated At**: 2026-11-07 10:56:37
- **Swarm Setup**: 75 UAVs in 200m x 200m x 80m
- **Phase 1 Duration**: 10.0 ms | **Slot Width**: 500.0 µs

| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |
| :--- | :--- | :--- | :--- |
| **Phase 1 PRR (Overall 0~30s)** | **88.9%** | **53.5%** | **-35.4%** |
| **Phase 1 Steady-State PRR (Last 2s)** | **89.3%** | **54.7%** | **-34.6%** |
| Delivered Links | 269139 | 161846 | -107293 |
| Total Dropped Links | 33466 | 140759 | +107293 |
| CSMA Aborts | 5751 | 0 | -5751 |
| RX Deafness (Half-Duplex) | 3121 | 29865 | +26744 |
| Preamble Collisions | 18294 | 48854 | +30560 |
| Preamble Low SINR Drops | 5317 | 60893 | +55576 |
| Turnaround Busy Drops | 0 | 0 | +0 |
| Payload Interference Drops | 983 | 1147 | +164 |
| Power Capture Rescued Packets | 157133 | 67002 | -90131 |
| Phase 2 PRR | 81.9% | 53.1% | -28.8% |
| Phase 1 Mean IAT | 65.90 ms | 100.30 ms | +34.40 ms |
| Phase 2 Mean AoI | 32.90 ms | 152.10 ms | +119.20 ms |
