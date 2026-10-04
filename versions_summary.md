# NS-3 Swarm Project 演進史與架構版本統整

這份文件記錄了我們在 NS-3 LR-WPAN 環境下，為了實現大規模無人機 (50 Drones) 的自定義 TDMA/CSMA 混合通訊協定，所經歷的所有架構演進與踩坑紀錄。

---

## 🟢 V1: 雛形探索期 (Baseline 3~6 Drones)
* **開發目標**：驗證 `ns-3` 的 `lr-wpan` 模組是否允許應用層「越權」控制 MAC 與 PHY 層，做出我們自己的 TDMA 週期。
* **主要特徵**：
  * 在 3 到 6 台無人機的小規模場景上測試。
  * 解決了 NS-3 內部初始化的 Null Pointer 崩潰問題。
  * 設定了正確的 MAC Short Address 與 Extended Address。
  * 綁定了 `McpsDataIndication` Callback 來攔截封包，並成功實作了動態呼叫 `SwitchChannel` 的機制。
* **開發結論**：證明了「應用層強制介入實體層 (PHY)」的構想是可行的，我們成功跳脫了預設的 802.15.4 被動接收框架。

---

## 🟡 V2: Pick & Claim 單無線電架構 (50 Drones)
* **開發目標**：將網路規模一口氣拉到 50 台，並實作核心的「兩階段演算法」(Phase 1: CSMA 廣播、Phase 2: TDMA 資料)。
* **主要特徵**：
  * 引入了 **2 Bytes 的位元封裝 (Bit-packing)**，讓無人機在 Phase 1 廣播自己選定的時槽與頻道 (Claim)，並在 Phase 2 依照廣播結果切換過去。
  * 引入了 AoI (Age of Information)、IAT (Inter-Arrival Time) 等全域評估指標 (Metrics)。
* **遇到瓶頸**：我們撞上了 **「半雙工 (Half-Duplex) 限制」** 與 **「接收者耳聾 (Receiver Deafness)」**。當無人機在 Phase 2 發射資料時，它完全聽不到別人的封包；如果兩個鄰居選了同一個時槽，它也只能聽一個，導致整體 Bcn Ratio (Beacon Reception Ratio) 慘不忍睹。

---

## 🔵 V3: 雙無線電全雙工架構 (Dual-Radio Full-Duplex)
* **開發目標**：徹底解決接收者耳聾問題，大幅提升頻譜利用率與接收成功率。
* **主要特徵**：這是一個**史詩級的架構升級**。我們為每台無人機裝上兩片獨立的網卡 (`dev1`, `dev2`)：
  * **Phase 1**：一半無人機用 Radio 1 (Ch 11) 廣播，一半用 Radio 2 (Ch 26) 廣播。頻寬瞬間翻倍！
  * **Phase 2**：`Radio 1` 負責發送 (TX) 時，`Radio 2` 依然可以同時在另一個頻道接收 (RX) 鄰居的資料。完全達成全雙工 (Full-Duplex) 的效果。
* **開發結論**：架構極度成功！Phase 1 的成功率瞬間飆升到 **79%**。但在 50 台無人機的壓力測試下，我們在 Phase 2 遇到了嚴重的 `NS_FATAL_ERROR Error changing transceiver state` 崩潰。

---

## 🔴 V4: 黑暗除錯深淵 (The CSMA Disable & Filters Rabbit Hole)
* **開發目標**：為了解決上述的 `Error changing transceiver state` 崩潰，我們進入了各種極端測試的死胡同。
* **主要特徵**：
  * **暴力關閉 CSMA**：誤以為是 CSMA 的隨機退避 (Backoff) 破壞了嚴格的 TDMA 時槽，於是嘗試將 `MinBE` 與 `MaxBE` 設為 0。這引發了 NS-3 核心 `assert(m_macMaxBE >= 3)` 報錯。
  * **幻覺式過濾器 (Promiscuous Filter)**：誤以為有非法封包混入，加入了一個充滿 Bug 的過濾器，試圖讀取封包 Payload 裡的 `targetId`，結果把 98% 的合法封包全當垃圾丟了。
  * **盲目擴容**：以為網路容量不足，把 Cycle 瘋狂拉長到 245ms。
* **開發結論**：數據完全崩盤 (Bcn Ratio 跌到 1.4%)，整個演算法失去原有的精準度。這是一次我們後來果斷捨棄的失敗分支。

---

## 🌟 V5: 乾淨雙天線 + 時槽擴容 (Slot Expansion Fix)
* **開發目標**：用最根本、符合物理規律的方式解決崩潰，並發揮 V3 架構的 100% 潛力。
* **主要特徵**：
  * 透過 `git reset --hard` 把 V4 所有黑暗期的爛 Code 全部抹除。
  * **一針見血的修正**：崩潰的真正原因是「Phase 2 的時槽 (2.5ms) 實在太短了」。一個 50B 的封包加上 CSMA 退避很容易超過 2.5ms。時間一到被強制切換頻道，網卡就會崩潰。
  * 保留了完美的 CSMA 機制，只將 **DATA_SLOT_US 從 2.5ms 拓寬至 7.0ms**。(總 Cycle 落在非常流暢的 96 ms)。
  * 加入 `m_lastMonitorList` 的排程記憶修復，讓 Phase 2 能完美錯開鄰機。
* **開發結論**：這是一個理論上極度穩定、且能最大化發揮「雙天線 + Pick&Claim 演算法」效能的終極版本。

---

## ⏳ V6: 時空倒流極限測試版 (Strict 2.5ms Slot / 當前所在分支)
* **開發目標**：學長特別要求還原最原始、不拓寬時槽的設定，以驗證最極限的物理崩潰狀況。
* **主要特徵**：
  * 在 V5 的乾淨架構下，**刻意將 DATA_SLOT_US 退回 2500.0 (2.5ms)**。
  * 總循環時間回到 **51.0 ms**。
  * 保留了 Github 自動上傳的腳本 (`metrics.txt`)。
* **預期結果**：因為嚴酷的物理時間限制，只要發生 CSMA 碰撞退避，必定引發 `SwitchChannel` 時的 `NS_FATAL_ERROR`，這是一份保留下來作為除錯與物理極限驗證的對照組版本。
