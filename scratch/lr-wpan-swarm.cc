#include <ns3/core-module.h>
#include <ns3/network-module.h>
#include <ns3/mobility-module.h>
#include <ns3/spectrum-module.h>
#include <ns3/lr-wpan-module.h>
#include <iostream>
#include <vector>
#include <algorithm>
#include <iomanip>
#include <map>

#include <fstream>

using namespace ns3;
using namespace ns3::lrwpan;

NS_LOG_COMPONENT_DEFINE("LrWpanSwarm");
std::ofstream g_debugLogFile;
// --- 系統常數設定 ---
const uint32_t MINI_BEACON_SIZE = 2; 
const uint32_t DATA_PACKET_SIZE = 50;

const double CYCLE_MS = 96.0;            // 25 + 1 + 70
const double PHASE1_DURATION_US = 25000.0;
const double GAP_US = 1000.0;
const int NUM_DATA_SLOTS = 10;
const int NUM_DATA_CHANNELS = 6;         // 6 channels * 10 slots = 60 blocks
const double DATA_SLOT_US = 7000.0; 

const uint8_t BROADCAST_CHANNEL = 11;
const uint8_t BROADCAST_CHANNEL_2 = 26;

// --- 目標條件設定 ---
const double M_RADIUS_METERS = 100.0;    // 只考慮半徑 M 公尺內的無人機
const int K_CLOSEST = 5;                 // 從 M 公尺內挑選最近的 K 個

// 全域統計
static int g_totalDataPacketsReceived = 0;
static int g_totalExpectedTopKxEpochs = 0;
static int g_totalReceivedDiscoveryTopK = 0;
static int g_totalReceivedBeaconTopK = 0;
static double g_totalSumDiscoveryIatTopK = 0;
static int g_totalCountDiscoveryIatTopK = 0;
static double g_globalMaxDiscoveryIatTopK = 0;
static double g_totalSumAoITopK = 0;
static int g_totalCountAoITopK = 0;
static double g_globalMaxAoITopK = 0;
static int g_totalTopologyMatchCount = 0;
static int g_totalTopologyCheckCount = 0;

struct NeighborInfo {
    uint8_t id;
    int8_t rssi;
    uint32_t epoch;
    uint8_t claimedSlot;
    uint8_t claimedChannel;
};

struct ScheduleSlot {
    enum Action { IDLE, TX, RX } action;
    uint8_t channel;
    uint8_t targetId;
};

class SwarmSchedulerApp : public Application {
public:
    SwarmSchedulerApp() : m_epoch(0), m_myClaimedSlot(0), m_myClaimedChannel(0), m_topologyMatchCount(0), m_topologyCheckCount(0), m_epochStartTime(0) {}

    void Setup(Ptr<LrWpanNetDevice> dev1, Ptr<LrWpanNetDevice> dev2, uint8_t id) {
        m_device1 = dev1;
        m_device2 = dev2;
        m_id = id;
        
        // Setup Radio 1
        Ptr<LrWpanMac> mac1 = m_device1->GetMac();
        Ptr<LrWpanCsmaCa> csma1 = CreateObject<LrWpanCsmaCa>();
        csma1->SetMacMinBE(0); 
        csma1->SetMacMaxCSMABackoffs(4); 
        mac1->SetCsmaCa(csma1);
        csma1->SetMac(mac1);
        csma1->SetLrWpanMacStateCallback(MakeCallback(&LrWpanMac::SetLrWpanMacState, mac1));
        m_device1->GetPhy()->SetPlmeCcaConfirmCallback(MakeCallback(&LrWpanCsmaCa::PlmeCcaConfirm, csma1));
        mac1->SetPanId(1);
        mac1->SetRxOnWhenIdle(true);
        mac1->SetMcpsDataIndicationCallback(MakeCallback(&SwarmSchedulerApp::ReceivePacket, this));
        mac1->SetMcpsDataConfirmCallback(MakeCallback(&SwarmSchedulerApp::DataConfirm, this));

        // Setup Radio 2
        Ptr<LrWpanMac> mac2 = m_device2->GetMac();
        Ptr<LrWpanCsmaCa> csma2 = CreateObject<LrWpanCsmaCa>();
        csma2->SetMacMinBE(0); 
        csma2->SetMacMaxCSMABackoffs(4); 
        mac2->SetCsmaCa(csma2);
        csma2->SetMac(mac2);
        csma2->SetLrWpanMacStateCallback(MakeCallback(&LrWpanMac::SetLrWpanMacState, mac2));
        m_device2->GetPhy()->SetPlmeCcaConfirmCallback(MakeCallback(&LrWpanCsmaCa::PlmeCcaConfirm, csma2));
        mac2->SetPanId(1);
        mac2->SetRxOnWhenIdle(true);
        mac2->SetMcpsDataIndicationCallback(MakeCallback(&SwarmSchedulerApp::ReceivePacket, this));
        mac2->SetMcpsDataConfirmCallback(MakeCallback(&SwarmSchedulerApp::DataConfirm, this));
        
        Simulator::Schedule(Seconds(0.999), &SwarmSchedulerApp::PrintMetrics, this);
    }

    void StartApplication() override {
        if (m_id == 0) std::cout << "All 50 Drones StartApplication called! Running for 1.0s..." << std::endl;
        ScheduleCycle();
    }
    
    void StopApplication() override {}

private:
    Ptr<LrWpanNetDevice> m_device1;
    Ptr<LrWpanNetDevice> m_device2;
    uint8_t m_id;
    uint32_t m_epoch;
    double m_epochStartTime;
    uint8_t m_myClaimedSlot;
    uint8_t m_myClaimedChannel;
    std::vector<NeighborInfo> m_monitorList;
    std::vector<NeighborInfo> m_lastMonitorList;
    ScheduleSlot m_schedule1[NUM_DATA_SLOTS];
    ScheduleSlot m_schedule2[NUM_DATA_SLOTS];

    // 數據統計變數
    std::map<uint8_t, int> m_discoveryReceivedCount;
    std::map<uint8_t, int> m_beaconReceivedCount;
    
    std::map<uint8_t, double> m_lastDiscoveryTime;
    std::map<uint8_t, double> m_sumDiscoveryIat;
    std::map<uint8_t, int> m_countDiscoveryIat;
    std::map<uint8_t, double> m_maxDiscoveryIat;
    
    // AoI 統計變數 (For 50B Beacon Packet)
    std::map<uint8_t, double> m_lastGenerationTime;
    std::map<uint8_t, double> m_sumAoI;
    std::map<uint8_t, int> m_countAoI;
    std::map<uint8_t, double> m_maxAoI;
    
    std::vector<uint8_t> m_lastScheduledRx;
    int m_topologyMatchCount;
    int m_topologyCheckCount;

    void SwitchChannel1(uint8_t ch) {
        Ptr<PhyPibAttributes> attrs = Create<PhyPibAttributes>();
        attrs->phyCurrentChannel = ch;
        m_device1->GetPhy()->PlmeSetAttributeRequest(phyCurrentChannel, attrs);
    }
    void SwitchChannel2(uint8_t ch) {
        Ptr<PhyPibAttributes> attrs = Create<PhyPibAttributes>();
        attrs->phyCurrentChannel = ch;
        m_device2->GetPhy()->PlmeSetAttributeRequest(phyCurrentChannel, attrs);
    }

    void SendPacket(uint32_t size, Ptr<Packet> p, int radioIndex = 1) {
        McpsDataRequestParams params;
        params.m_srcAddrMode = SHORT_ADDR;
        params.m_dstAddrMode = SHORT_ADDR;
        params.m_dstPanId = 1;
        params.m_dstAddr = Mac16Address("FF:FF"); 
        params.m_msduHandle = 0;
        params.m_txOptions = TX_OPTION_NONE;
        if (radioIndex == 1) {
            m_device1->GetMac()->McpsDataRequest(params, p);
        } else {
            m_device2->GetMac()->McpsDataRequest(params, p);
        }
    }

    void ScheduleCycle() {
        m_epoch++;
        m_lastMonitorList = m_monitorList;
        m_monitorList.clear();

        double now = Simulator::Now().GetMilliSeconds();
        
        // 結算上一回合的 AoI (For 50B Beacon Packet)
        if (m_epoch > 1) {
            for (uint8_t i = 0; i < NodeList::GetNNodes(); i++) {
                if (i == m_id) continue;
                if (m_lastGenerationTime.find(i) == m_lastGenerationTime.end()) {
                    m_lastGenerationTime[i] = now; // Initialize
                    m_maxAoI[i] = 0;
                    m_sumAoI[i] = 0;
                    m_countAoI[i] = 0;
                }
                double aoi = now - m_lastGenerationTime[i];
                m_sumAoI[i] += aoi;
                m_countAoI[i]++;
                if (aoi > m_maxAoI[i]) m_maxAoI[i] = aoi;
            }
        }
        m_epochStartTime = now;

        SwitchChannel1(BROADCAST_CHANNEL);
        SwitchChannel2(BROADCAST_CHANNEL_2); 
        
        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
        double randomDelayUs = uv->GetValue(0, PHASE1_DURATION_US - 2000.0);
        
        Simulator::Schedule(MicroSeconds(randomDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        Simulator::Schedule(MicroSeconds(PHASE1_DURATION_US + GAP_US), &SwarmSchedulerApp::ComputeSchedule, this);
        Simulator::Schedule(MilliSeconds(CYCLE_MS), &SwarmSchedulerApp::ScheduleCycle, this);
    }

    void PickResourceAndSendBeacon() {
        int cost[NUM_DATA_SLOTS][NUM_DATA_CHANNELS] = {0};
        
        Ptr<MobilityModel> myMobility = m_device1->GetNode()->GetObject<MobilityModel>();
        for (const auto& n : m_lastMonitorList) {
            cost[n.claimedSlot][n.claimedChannel] += 10000;
            
            // 加入空間防禦：如果對方在半徑 M 內，增加該 Slot 全頻道的成本
            Ptr<MobilityModel> otherMobility = NodeList::GetNode(n.id)->GetObject<MobilityModel>();
            double dist = myMobility->GetDistanceFrom(otherMobility);
            if (dist <= M_RADIUS_METERS) {
                for (int c = 0; c < NUM_DATA_CHANNELS; c++) {
                    cost[n.claimedSlot][c] += 1000;
                }
            }
        }
        
        int minCost = 999999;
        std::vector<std::pair<int, int>> bestOptions;
        
        for (int s = 0; s < NUM_DATA_SLOTS; s++) {
            for (int c = 0; c < NUM_DATA_CHANNELS; c++) {
                if (cost[s][c] < minCost) {
                    minCost = cost[s][c];
                    bestOptions.clear();
                    bestOptions.push_back({s, c});
                } else if (cost[s][c] == minCost) {
                    bestOptions.push_back({s, c});
                }
            }
        }
        
        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
        int pickIdx = uv->GetInteger(0, bestOptions.size() - 1);
        m_myClaimedSlot = bestOptions[pickIdx].first;
        m_myClaimedChannel = bestOptions[pickIdx].second;

        // 位元封裝 (Bit-packing): ID(6 bits), Slot(4 bits), Channel(3 bits) -> Total 13 bits
        uint16_t payload = (m_id & 0x3F) | ((m_myClaimedSlot & 0x0F) << 6) | ((m_myClaimedChannel & 0x07) << 10);
        uint8_t buffer[2] = { (uint8_t)(payload & 0xFF), (uint8_t)((payload >> 8) & 0xFF) };
        Ptr<Packet> p = Create<Packet>(buffer, 2);
                  
        Ptr<UniformRandomVariable> radioUv = CreateObject<UniformRandomVariable>();
        int chosenRadio = radioUv->GetInteger(1, 2);
        
        g_debugLogFile << "[PHASE1_TX] Time: " << Simulator::Now().GetMilliSeconds() 
              << "ms, Drone: " << (int)m_id << ", Radio: " << chosenRadio 
              << ", ClaimedSlot: " << (int)m_myClaimedSlot 
              << ", ClaimedCh: " << (int)m_myClaimedChannel << "\n";
              
        SendPacket(MINI_BEACON_SIZE, p, chosenRadio);
    }

    
    void ComputeSchedule() {
        Ptr<MobilityModel> myMobility = m_device1->GetNode()->GetObject<MobilityModel>();
        std::vector<NeighborInfo> filteredList;
        for (auto& n : m_monitorList) {
            Ptr<MobilityModel> otherMobility = NodeList::GetNode(n.id)->GetObject<MobilityModel>();
            double dist = myMobility->GetDistanceFrom(otherMobility);
            if (dist <= M_RADIUS_METERS) {
                filteredList.push_back(n);
            }
        }

        std::sort(filteredList.begin(), filteredList.end(), [](const NeighborInfo& a, const NeighborInfo& b) {
            return a.rssi > b.rssi;
        });

        for (int i = 0; i < NUM_DATA_SLOTS; i++) {
            m_schedule1[i].action = ScheduleSlot::IDLE;
            m_schedule2[i].action = ScheduleSlot::IDLE;
        }

        m_schedule1[m_myClaimedSlot].action = ScheduleSlot::TX;
        m_schedule1[m_myClaimedSlot].channel = m_myClaimedChannel + 12;

        g_debugLogFile << "[COMPUTE_SCHED] Time: " << Simulator::Now().GetMilliSeconds() 
              << "ms, Drone: " << (int)m_id << ", MySlot: " << (int)m_myClaimedSlot 
              << ", MyCh: " << (int)m_myClaimedChannel << "\n";

        int assigned = 0;
        m_lastScheduledRx.clear();
        for (auto& n : filteredList) {
            if (assigned >= K_CLOSEST) {
                g_debugLogFile << "  [SCHED_IGNORE] Target: " << (int)n.id << ", Reason: AssignedMax\n";
                break; 
            }
            if (n.claimedSlot == m_myClaimedSlot) {
                g_debugLogFile << "  [SCHED_CONFLICT] Target: " << (int)n.id 
                      << ", TargetSlot: " << (int)n.claimedSlot 
                      << ", TargetCh: " << (int)n.claimedChannel 
                      << ", Reason: MyTxSlot\n";
                // Even though it's my TX slot, in Full-Duplex I CAN receive on Radio 2!
                // Let's NOT continue, let's TRY to assign it to Radio 2!
                // Wait! I already fixed this by removing the continue!
            }
            
            // Assign to Radio 1 if idle
            if (m_schedule1[n.claimedSlot].action == ScheduleSlot::IDLE) {
                m_schedule1[n.claimedSlot].action = ScheduleSlot::RX;
                m_schedule1[n.claimedSlot].channel = n.claimedChannel + 12;
                m_schedule1[n.claimedSlot].targetId = n.id;
                m_lastScheduledRx.push_back(n.id);
                assigned++;
                g_debugLogFile << "  [SCHED_ASSIGN] Target: " << (int)n.id 
                      << ", TargetSlot: " << (int)n.claimedSlot 
                      << ", TargetCh: " << (int)n.claimedChannel 
                      << ", AssignedTo: Radio1\n";
            } 
            // Assign to Radio 2 if Radio 1 is busy but Radio 2 is idle
            else if (m_schedule2[n.claimedSlot].action == ScheduleSlot::IDLE) {
                m_schedule2[n.claimedSlot].action = ScheduleSlot::RX;
                m_schedule2[n.claimedSlot].channel = n.claimedChannel + 12;
                m_schedule2[n.claimedSlot].targetId = n.id;
                m_lastScheduledRx.push_back(n.id);
                assigned++;
                g_debugLogFile << "  [SCHED_ASSIGN] Target: " << (int)n.id 
                      << ", TargetSlot: " << (int)n.claimedSlot 
                      << ", TargetCh: " << (int)n.claimedChannel 
                      << ", AssignedTo: Radio2\n";
            } else {
                g_debugLogFile << "  [SCHED_CONFLICT] Target: " << (int)n.id 
                      << ", TargetSlot: " << (int)n.claimedSlot 
                      << ", TargetCh: " << (int)n.claimedChannel 
                      << ", Reason: BothRadiosBusy\n";
            }
        }

        int match = 0;
        std::vector<std::pair<uint8_t, double>> godDistances;
        for (int i = 0; i < 50; i++) {
            if (i == m_id) continue;
            Ptr<MobilityModel> otherMob = NodeList::GetNode(i)->GetObject<MobilityModel>();
            double dist = myMobility->GetDistanceFrom(otherMob);
            if (dist <= M_RADIUS_METERS) {
                godDistances.push_back({i, dist});
            }
        }
        std::sort(godDistances.begin(), godDistances.end(), [](const std::pair<uint8_t, double>& a, const std::pair<uint8_t, double>& b) {
            return a.second < b.second;
        });

        int expectedTop = std::min(K_CLOSEST, (int)godDistances.size());
        for (int i = 0; i < expectedTop; i++) {
            uint8_t target = godDistances[i].first;
            if (std::find(m_lastScheduledRx.begin(), m_lastScheduledRx.end(), target) != m_lastScheduledRx.end()) {
                match++;
            }
        }
        m_topologyMatchCount += match;
        m_topologyCheckCount += expectedTop;

        for (int i = 0; i < NUM_DATA_SLOTS; i++) {
            Simulator::Schedule(MicroSeconds(i * DATA_SLOT_US), &SwarmSchedulerApp::ExecuteDataSlot, this, i);
        }
    }

    void ExecuteDataSlot(int slotIndex) {
        ScheduleSlot s1 = m_schedule1[slotIndex];
        ScheduleSlot s2 = m_schedule2[slotIndex];

        if (m_id == 0 || m_id == 25 || m_id == 49) {
            g_debugLogFile << "[PHASE2_SLOT] Time: " << Simulator::Now().GetMilliSeconds() 
                  << "ms, Drone: " << (int)m_id << ", Slot: " << slotIndex 
                  << ", S1_Act: " << (int)s1.action << ", S1_Ch: " << (int)s1.channel 
                  << ", S2_Act: " << (int)s2.action << ", S2_Ch: " << (int)s2.channel << "\n";
        }

        if (s1.action == ScheduleSlot::TX) {
            SwitchChannel1(s1.channel);
            if (s2.action == ScheduleSlot::RX) {
                SwitchChannel2(s2.channel);
            }
            Ptr<Packet> p = Create<Packet>(DATA_PACKET_SIZE);
            SendPacket(DATA_PACKET_SIZE, p);
        } else {
            if (s1.action == ScheduleSlot::RX) {
                SwitchChannel1(s1.channel);
            }
            if (s2.action == ScheduleSlot::RX) {
                SwitchChannel2(s2.channel);
            }
        }
    }
void DataConfirm(McpsDataConfirmParams params) {}

    void ReceivePacket(McpsDataIndicationParams params, Ptr<Packet> p) {
        int8_t rssi = params.m_rssi;

        if (p->GetSize() == MINI_BEACON_SIZE) {
            uint8_t buffer[2];
            p->CopyData(buffer, 2);
            uint16_t payload = buffer[0] | (buffer[1] << 8);
            
            uint8_t senderId = payload & 0x3F;
            uint8_t claimedSlot = (payload >> 6) & 0x0F;
            uint8_t claimedChannel = (payload >> 10) & 0x07;
            
            if (m_id == 0 || m_id == 25 || m_id == 49) {
                g_debugLogFile << "[PHASE1_RX] Time: " << Simulator::Now().GetMilliSeconds() 
                      << "ms, Drone: " << (int)m_id << ", From: " << (int)senderId 
                      << ", ClSlot: " << (int)claimedSlot << ", ClCh: " << (int)claimedChannel 
                      << ", RSSI: " << (int)rssi << "\n";
            }
            
            m_monitorList.push_back({senderId, rssi, m_epoch, claimedSlot, claimedChannel});
            m_discoveryReceivedCount[senderId]++;
            
            double now = Simulator::Now().GetMilliSeconds();
            if (m_lastDiscoveryTime.find(senderId) != m_lastDiscoveryTime.end()) {
                double iat = now - m_lastDiscoveryTime[senderId];
                m_sumDiscoveryIat[senderId] += iat;
                m_countDiscoveryIat[senderId]++;
                if (m_maxDiscoveryIat.find(senderId) == m_maxDiscoveryIat.end() || iat > m_maxDiscoveryIat[senderId]) {
                    m_maxDiscoveryIat[senderId] = iat;
                }
            }
            m_lastDiscoveryTime[senderId] = now;
        } else if (p->GetSize() == DATA_PACKET_SIZE) {
            uint8_t addrBuffer[2];
            params.m_srcAddr.CopyTo(addrBuffer);
            uint8_t srcId = addrBuffer[1];
            
            if (m_id == 0 || m_id == 25 || m_id == 49) {
                g_debugLogFile << "[PHASE2_DATA_RX] Time: " << Simulator::Now().GetMilliSeconds() 
                      << "ms, Drone: " << (int)m_id << ", From: " << (int)srcId 
                      << ", RSSI: " << (int)rssi << "\n";
            }
            
            m_beaconReceivedCount[srcId]++;
            g_totalDataPacketsReceived++;
            
            double now = Simulator::Now().GetMilliSeconds();
            
            // 更新 AoI Generation Time (將產生時間直接設為收到的瞬間，不計算空中傳輸延遲)
            m_lastGenerationTime[srcId] = now;
        }
    }

    void PrintMetrics() {
        Ptr<MobilityModel> myMobility = m_device1->GetNode()->GetObject<MobilityModel>();
        std::vector<std::pair<uint8_t, double>> godDistances;
        for (uint32_t i = 0; i < NodeList::GetNNodes(); i++) {
            if (i == m_id) continue;
            Ptr<MobilityModel> otherMobility = NodeList::GetNode(i)->GetObject<MobilityModel>();
            double dist = myMobility->GetDistanceFrom(otherMobility);
            if (dist <= M_RADIUS_METERS) {
                godDistances.push_back({i, dist});
            }
        }
        std::sort(godDistances.begin(), godDistances.end(), [](const auto& a, const auto& b) {
            return a.second < b.second;
        });

        int expectedTop = std::min(K_CLOSEST, (int)godDistances.size());
        g_totalExpectedTopKxEpochs += expectedTop * m_epoch;
        
        for (int i = 0; i < expectedTop; i++) {
            uint8_t target = godDistances[i].first;
            g_totalReceivedDiscoveryTopK += m_discoveryReceivedCount[target];
            g_totalReceivedBeaconTopK += m_beaconReceivedCount[target];
            
            g_totalSumDiscoveryIatTopK += m_sumDiscoveryIat[target];
            g_totalCountDiscoveryIatTopK += m_countDiscoveryIat[target];
            if (m_maxDiscoveryIat.find(target) != m_maxDiscoveryIat.end() && m_maxDiscoveryIat[target] > g_globalMaxDiscoveryIatTopK) {
                g_globalMaxDiscoveryIatTopK = m_maxDiscoveryIat[target];
            }
            
            g_totalSumAoITopK += m_sumAoI[target];
            g_totalCountAoITopK += m_countAoI[target];
            if (m_maxAoI.find(target) != m_maxAoI.end() && m_maxAoI[target] > g_globalMaxAoITopK) {
                g_globalMaxAoITopK = m_maxAoI[target];
            }
        }
        
        g_totalTopologyMatchCount += m_topologyMatchCount;
        g_totalTopologyCheckCount += m_topologyCheckCount;

        if (m_id != 0 && m_id != 25 && m_id != 49) return; // 只印出幾台代表性的無人機避免洗版

        std::cout << "\n=== Drone " << std::setw(2) << (int)m_id << " Metrics Report (Top " << K_CLOSEST << " within " << M_RADIUS_METERS << "m) ===" << std::endl;
        std::cout << "Target (Dist)  | Disc. Ratio | Bcn Ratio | Avg Disc. IAT | Max Disc. IAT | Mean Bcn AoI | Max Bcn AoI" << std::endl;
        std::cout << "-----------------------------------------------------------------------------------------------------" << std::endl;
        
        for (int i = 0; i < std::min(K_CLOSEST, (int)godDistances.size()); i++) {
            uint8_t target = godDistances[i].first;
            double dist = godDistances[i].second;
            
            double discRatio = (double)m_discoveryReceivedCount[target] / m_epoch;
            double bcnRatio = (double)m_beaconReceivedCount[target] / m_epoch;
            double avgDiscIat = (m_countDiscoveryIat[target] > 0) ? (m_sumDiscoveryIat[target] / m_countDiscoveryIat[target]) : 0;
            double maxDiscIat = (m_maxDiscoveryIat.find(target) != m_maxDiscoveryIat.end()) ? m_maxDiscoveryIat[target] : 0;
            double meanAoI = (m_countAoI[target] > 0) ? (m_sumAoI[target] / m_countAoI[target]) : 0;
            double maxAoI = (m_maxAoI.find(target) != m_maxAoI.end()) ? m_maxAoI[target] : 0;
            
            std::cout << "Drone " << std::setw(2) << (int)target << " (" << std::setw(3) << (int)dist << "m) | "
                      << std::fixed << std::setprecision(1) << std::setw(11) << discRatio * 100 << " | "
                      << std::fixed << std::setprecision(1) << std::setw(9) << bcnRatio * 100 << " | "
                      << std::fixed << std::setprecision(1) << std::setw(13) << avgDiscIat << " | "
                      << std::fixed << std::setprecision(1) << std::setw(13) << maxDiscIat << " | "
                      << std::fixed << std::setprecision(1) << std::setw(12) << meanAoI << " | "
                      << std::fixed << std::setprecision(1) << std::setw(11) << maxAoI << std::endl;
        }
        
        double topAcc = (m_topologyCheckCount > 0) ? ((double)m_topologyMatchCount / m_topologyCheckCount) : 0;
        std::cout << "--> Monitor Member List Match Ratio: " << std::fixed << std::setprecision(1) << topAcc * 100 << "%" << std::endl;
    }
};

int main(int argc, char *argv[]) {
    g_debugLogFile.open("debug_log.txt", std::ios::out);
    CommandLine cmd;
    cmd.Parse(argc, argv);

    int numNodes = 50; 
    NodeContainer nodes;
    nodes.Create(numNodes);

    Ptr<SingleModelSpectrumChannel> channel = CreateObject<SingleModelSpectrumChannel>();
    Ptr<LogDistancePropagationLossModel> propModel = CreateObject<LogDistancePropagationLossModel>();
    Ptr<ConstantSpeedPropagationDelayModel> delayModel = CreateObject<ConstantSpeedPropagationDelayModel>();
    channel->AddPropagationLossModel(propModel);
    channel->SetPropagationDelayModel(delayModel);

    
    LrWpanHelper lrWpanHelper1;
    lrWpanHelper1.SetChannel(channel);
    NetDeviceContainer devices1 = lrWpanHelper1.Install(nodes);
    
    LrWpanHelper lrWpanHelper2;
    lrWpanHelper2.SetChannel(channel);
    NetDeviceContainer devices2 = lrWpanHelper2.Install(nodes);

    MobilityHelper mobility;

    
    // 3D Random Box Topology (300m x 300m x 100m)
    Ptr<RandomBoxPositionAllocator> alloc = CreateObject<RandomBoxPositionAllocator>();
    Ptr<UniformRandomVariable> xVar = CreateObject<UniformRandomVariable>();
    xVar->SetAttribute("Min", DoubleValue(0.0));
    xVar->SetAttribute("Max", DoubleValue(300.0));
    alloc->SetX(xVar);
    
    Ptr<UniformRandomVariable> yVar = CreateObject<UniformRandomVariable>();
    yVar->SetAttribute("Min", DoubleValue(0.0));
    yVar->SetAttribute("Max", DoubleValue(300.0));
    alloc->SetY(yVar);
    
    Ptr<UniformRandomVariable> zVar = CreateObject<UniformRandomVariable>();
    zVar->SetAttribute("Min", DoubleValue(10.0));
    zVar->SetAttribute("Max", DoubleValue(110.0)); // 100m height difference
    alloc->SetZ(zVar);
    
    mobility.SetPositionAllocator(alloc);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    
    for (int i = 0; i < numNodes; i++) {
        Ptr<LrWpanNetDevice> dev1 = DynamicCast<LrWpanNetDevice>(devices1.Get(i));
        Ptr<LrWpanNetDevice> dev2 = DynamicCast<LrWpanNetDevice>(devices2.Get(i));
        
        char extMacStr1[32];
        snprintf(extMacStr1, sizeof(extMacStr1), "00:00:00:00:00:00:01:%02x", i);
        dev1->GetMac()->SetExtendedAddress(Mac64Address(extMacStr1));
        
        char macStr1[16];
        snprintf(macStr1, sizeof(macStr1), "01:%02x", i);
        dev1->GetMac()->SetShortAddress(Mac16Address(macStr1));

        char extMacStr2[32];
        snprintf(extMacStr2, sizeof(extMacStr2), "00:00:00:00:00:00:02:%02x", i);
        dev2->GetMac()->SetExtendedAddress(Mac64Address(extMacStr2));
        
        char macStr2[16];
        snprintf(macStr2, sizeof(macStr2), "02:%02x", i);
        dev2->GetMac()->SetShortAddress(Mac16Address(macStr2));

        Ptr<SwarmSchedulerApp> app = CreateObject<SwarmSchedulerApp>();
        app->Setup(dev1, dev2, i);
        nodes.Get(i)->AddApplication(app);
        app->SetStartTime(Seconds(0.0));
        app->SetStopTime(Seconds(1.0)); 
    }
std::cout << "Starting Simulation for 1.0s..." << std::endl;
    Simulator::Stop(Seconds(1.0));
    Simulator::Run();
    
    int totalEpochs = 1000 / CYCLE_MS; 
    int totalSlots = totalEpochs * NUM_DATA_SLOTS;
    double srf = (double)g_totalDataPacketsReceived / totalSlots;
    double globalDiscRatio = (g_totalExpectedTopKxEpochs > 0) ? (double)g_totalReceivedDiscoveryTopK / g_totalExpectedTopKxEpochs : 0;
    double globalBcnRatio = (g_totalExpectedTopKxEpochs > 0) ? (double)g_totalReceivedBeaconTopK / g_totalExpectedTopKxEpochs : 0;
    double globalAvgDiscIat = (g_totalCountDiscoveryIatTopK > 0) ? (g_totalSumDiscoveryIatTopK / g_totalCountDiscoveryIatTopK) : 0;
    double globalMeanAoI = (g_totalCountAoITopK > 0) ? (g_totalSumAoITopK / g_totalCountAoITopK) : 0;
    double globalTopAcc = (g_totalTopologyCheckCount > 0) ? ((double)g_totalTopologyMatchCount / g_totalTopologyCheckCount) : 0;
    
    std::cout << "\n=================================================" << std::endl;
    std::cout << "          GLOBAL NETWORK METRICS (1.0s)          " << std::endl;
    std::cout << "=================================================" << std::endl;
    std::cout << "Total 50B Data Packets Delivered: " << g_totalDataPacketsReceived << std::endl;
    std::cout << "Total Network Slots Elapsed     : " << totalSlots << " slots" << std::endl;
    std::cout << "Spatial Reuse Factor (SRF)      : " << std::fixed << std::setprecision(2) << srf << " packets/slot" << std::endl;
    std::cout << "Discovery Message Reception Ratio: " << std::fixed << std::setprecision(1) << globalDiscRatio * 100 << "%" << std::endl;
    std::cout << "Beacon Packet Reception Ratio   : " << std::fixed << std::setprecision(1) << globalBcnRatio * 100 << "%" << std::endl;
    std::cout << "Monitor Member List Match Ratio : " << std::fixed << std::setprecision(1) << globalTopAcc * 100 << "%" << std::endl;
    std::cout << "Avg Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << globalAvgDiscIat << " ms" << std::endl;
    std::cout << "Max Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << g_globalMaxDiscoveryIatTopK << " ms" << std::endl;
    std::cout << "Mean Beacon Packet AoI (Top-K)  : " << std::fixed << std::setprecision(1) << globalMeanAoI << " ms" << std::endl;
    std::cout << "Max Beacon Packet AoI (Top-K)   : " << std::fixed << std::setprecision(1) << g_globalMaxAoITopK << " ms" << std::endl;
    std::cout << "=================================================\n" << std::endl;

    Simulator::Destroy();
    g_debugLogFile.close();
    return 0;
}
