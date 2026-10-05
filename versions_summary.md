# NS-3 Swarm Project 版本演進與核心指標總結

以下是我們在 NS-3 中開發與測試的四個核心架構版本，整理了各版本在不同機制下的關鍵表現：

| 版本名稱 / 核心機制 | 評估半徑 | Monitor Member List Match Ratio | Discovery Message Reception Ratio | Beacon Packet Reception Ratio | Mean Beacon Packet AoI | 版本意義與物理現象 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. 完全基礎版 (Baseline)**<br>(有 CSMA，無記憶) | 100m | 64.6% | 70.4% | 24.2% | 136.3 ms | ⚠️ **Paper 基準點 (失憶症)**<br>因為沒有記憶，只要在廣播期漏聽封包 (30%) 就無法排程。Monitor Member List Match Ratio 直接被 Discovery Message Reception Ratio 的天花板綁死。 |
| **2. Advanced Stability**<br>(加入 持久化記憶 + 智能避讓) | 100m | 87.7% | 68.7% | 32.0% | 135 ms | ✅ **重大突破 (打破天花板)**<br>無人機有了記憶，即使漏聽那 30% 的廣播也能維持排程！Match Ratio 從 70% 飛躍至 87.7%，總封包量創下 2426。 |
| **3. 雙廣播頻道架構版**<br>(Ch11/Ch26 分流廣播) | 100m | 88.9% | 79.5% | 34.1% | 211 ms | 🚀 **突破廣播極限 (偶發當機)**<br>利用雙網卡分流廣播，解決高密度碰撞，Discovery Message Reception Ratio 瞬間飆升逼近 80%！但 51ms 週期太緊導致 CSMA 當機。 |
| **4. 近距離聚焦 + 防當機版**<br>(週期 55ms + 聚焦 50m) | 50m | 90.1% | 43.8%* | 46.0% | 165 ms | 🌟 **物理最穩定 (當前最新)**<br>加長週期解決當機。受惠於 Capture Effect，近距離 Beacon Packet Reception Ratio 創最高 46%！<br>*(註：Discovery Message Reception Ratio 下降是因為 50m 內 CSMA 退避飢餓效應)* |

---
**當前分支狀態：**
目前專案的程式碼 (`lr-wpan-swarm.cc`) 已經鎖定在 **版本 4 (近距離聚焦 + 防當機版)** 的狀態：
* `CYCLE_MS` = 55.0
* `DATA_SLOT_US` = 2900.0
* `M_RADIUS_METERS` = 50.0
* 已啟用持久化記憶 (`m_lastMonitorList`) 與雙網卡廣播分流。
