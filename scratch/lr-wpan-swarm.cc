#include <ns3/core-module.h>
#include <ns3/network-module.h>
#include <ns3/mobility-module.h>
#include <ns3/spectrum-module.h>
#include <ns3/lr-wpan-module.h>
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <algorithm>
#include <iomanip>
#include <map>

using namespace ns3;
using namespace ns3::lrwpan;

std::ofstream g_runLogFile;
std::streambuf* g_originalCoutBuffer = nullptr;

NS_LOG_COMPONENT_DEFINE("LrWpanSwarm");

// --- 系統常數設定 ---
const uint32_t MINI_BEACON_SIZE = 2; 
const uint32_t DATA_PACKET_SIZE = 50;
double g_p2TxPower = -4.0; // Phase 2 TX Power (configurable via cmd line)

const double CYCLE_MS = 51.0;            // 25 + 1 + 25
const double PHASE1_DURATION_US = 25000.0; // 恢復為 25ms 最佳狀態
const double GAP_US = 1000.0; 
const int NUM_DATA_SLOTS = 10;
const int NUM_DATA_CHANNELS = 6;         // 6 channels * 10 slots = 60 blocks
const double DATA_SLOT_US = 2500.0; 

const uint8_t BROADCAST_CHANNEL = 11;

// --- 目標條件設定 ---
const double M_RADIUS_METERS = 50.0;    // 評估指標用的實際距離 (Ground Truth)
const double RSSI_50M_THRESHOLD = -97.65; // 相對應的 50m RSSI 門檻
const int K_CLOSEST = 5;                 // 從鄰居中挑選最近的 K 個

// 全域統計
static int g_totalDataPacketsReceived = 0;
static int g_totalExpectedRx = 0; 
static int g_txDeafnessCount = 0; 
static int g_rxDeafnessCount = 0; 
static int g_resourceCollisionCount = 0;
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

// Phase 1 專用統計
static int g_p1TxAttempts = 0;
static int g_p1TxAbort = 0;
static int g_p1TxSuccess = 0;
static int g_p1RxSuccess = 0;

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

    void Setup(Ptr<LrWpanNetDevice> dev, uint8_t id) {
        m_device = dev;
        m_id = id;
        
        Ptr<LrWpanMac> mac = m_device->GetMac();
        Ptr<LrWpanCsmaCa> csma = CreateObject<LrWpanCsmaCa>();
        csma->SetMacMinBE(0); 
        csma->SetMacMaxCSMABackoffs(0); // 設為 0，只要有人講話就立刻放棄並回報失敗
        mac->SetCsmaCa(csma);
        csma->SetMac(mac);
        
        csma->SetLrWpanMacStateCallback(MakeCallback(&LrWpanMac::SetLrWpanMacState, mac));
        m_device->GetPhy()->SetPlmeCcaConfirmCallback(MakeCallback(&LrWpanCsmaCa::PlmeCcaConfirm, csma));

        mac->SetPanId(1);
        mac->SetRxOnWhenIdle(true);

        mac->SetMcpsDataIndicationCallback(MakeCallback(&SwarmSchedulerApp::ReceivePacket, this));
        mac->SetMcpsDataConfirmCallback(MakeCallback(&SwarmSchedulerApp::DataConfirm, this));
        
        Simulator::Schedule(Seconds(0.999), &SwarmSchedulerApp::PrintMetrics, this);
    }

    void StartApplication() override {
        if (m_id == 0) std::cout << "All 50 Drones StartApplication called! Running for 1.0s..." << std::endl;
        ScheduleCycle();
    }
    
    void StopApplication() override {}

private:
    Ptr<LrWpanNetDevice> m_device;
    uint8_t m_id;
    uint32_t m_epoch;
    double m_epochStartTime;
    uint8_t m_myClaimedSlot;
    uint8_t m_myClaimedChannel;
    std::vector<NeighborInfo> m_monitorList;
    ScheduleSlot m_schedule[NUM_DATA_SLOTS];

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

    void SwitchChannelAndPower(uint8_t ch, int8_t txPowerDbm) {
        Ptr<PhyPibAttributes> attrs = Create<PhyPibAttributes>();
        attrs->phyCurrentChannel = ch;
        // Pack txPowerDbm into 6-bit two's complement for phyTransmitPower
        attrs->phyTransmitPower = txPowerDbm & 0x3F;
        
        m_device->GetMac()->GetPhy()->PlmeSetAttributeRequest(phyCurrentChannel, attrs);
        m_device->GetMac()->GetPhy()->PlmeSetAttributeRequest(phyTransmitPower, attrs);
    }

    void SendPacket(uint32_t size, Ptr<Packet> p, uint8_t msduHandle) {
        McpsDataRequestParams params;
        params.m_srcAddrMode = SHORT_ADDR;
        params.m_dstAddrMode = SHORT_ADDR;
        params.m_dstPanId = 1;
        params.m_dstAddr = Mac16Address("FF:FF"); 
        params.m_msduHandle = msduHandle;
        params.m_txOptions = TX_OPTION_NONE;
        m_device->GetMac()->McpsDataRequest(params, p);
    }

    void ScheduleCycle() {
        m_epoch++;
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

        // Phase 1 (Broadcast): 100m range -> 0 dBm
        SwitchChannelAndPower(BROADCAST_CHANNEL, 0);
        
        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
        double randomDelayUs = uv->GetValue(0, PHASE1_DURATION_US - 2000.0);
        
        Simulator::Schedule(MicroSeconds(randomDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        Simulator::Schedule(MicroSeconds(PHASE1_DURATION_US + GAP_US), &SwarmSchedulerApp::ComputeSchedule, this);
        Simulator::Schedule(MilliSeconds(CYCLE_MS), &SwarmSchedulerApp::ScheduleCycle, this);
    }

    void PickResourceAndSendBeacon() {
        g_p1TxAttempts++;
        uint32_t myId = m_device->GetNode()->GetId();
        double now = Simulator::Now().GetMilliSeconds();
        std::cout << "[P1_ATTEMPT] Time: " << now << "ms, Drone: " << myId << std::endl;
        
        int cost[NUM_DATA_SLOTS][NUM_DATA_CHANNELS] = {0};
        
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
        for (const auto& n : m_monitorList) {
            cost[n.claimedSlot][n.claimedChannel] += 10000;
            
            // 加入空間防禦：利用 RSSI 判斷是否為鄰近無人機 (取代上帝視角的距離計算)
            if (n.rssi >= RSSI_50M_THRESHOLD) {
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
                  
        SendPacket(MINI_BEACON_SIZE, p, 1); // msduHandle = 1 (Mini-beacon)
    }

    void ComputeSchedule() {
        // 第一步：利用 RSSI 過濾出真正靠近的鄰機 (取代上帝視角的距離計算)
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
        std::vector<NeighborInfo> filteredList;
        for (auto& n : m_monitorList) {
            if (n.rssi >= RSSI_50M_THRESHOLD) {
                filteredList.push_back(n);
            }
        }

        std::sort(filteredList.begin(), filteredList.end(), [](const NeighborInfo& a, const NeighborInfo& b) {
            return a.rssi > b.rssi;
        });

        for (int i = 0; i < NUM_DATA_SLOTS; i++) {
            m_schedule[i].action = ScheduleSlot::IDLE;
        }

        m_schedule[m_myClaimedSlot].action = ScheduleSlot::TX;
        m_schedule[m_myClaimedSlot].channel = m_myClaimedChannel + 12;

        int expected = std::min(K_CLOSEST, (int)filteredList.size());
        g_totalExpectedRx += expected;

        int assigned = 0;
        m_lastScheduledRx.clear();
        for (auto& n : filteredList) {
            if (assigned >= K_CLOSEST) break; 
            
            if (n.claimedSlot == m_myClaimedSlot) {
                g_txDeafnessCount++;
                continue; 
            }
            if (m_schedule[n.claimedSlot].action != ScheduleSlot::IDLE) {
                g_rxDeafnessCount++;
                continue; 
            }

            bool collided = false;
            for (auto& other : m_monitorList) {
                if (other.id != n.id && other.claimedSlot == n.claimedSlot && other.claimedChannel == n.claimedChannel) {
                    collided = true;
                    break;
                }
            }
            if (collided) {
                g_resourceCollisionCount++;
            }

            m_schedule[n.claimedSlot].action = ScheduleSlot::RX;
            m_schedule[n.claimedSlot].channel = n.claimedChannel + 12;
            m_schedule[n.claimedSlot].targetId = n.id;
            m_lastScheduledRx.push_back(n.id);
            assigned++;
        }

        // 上帝視角：計算拓樸準確度
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

        int match = 0;
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
        ScheduleSlot s = m_schedule[slotIndex];
        if (s.action == ScheduleSlot::TX) {
            // Phase 2 (Data): Use globally configured TX power
            SwitchChannelAndPower(s.channel, g_p2TxPower);
            uint32_t myId = m_device->GetNode()->GetId();
            double now = Simulator::Now().GetMilliSeconds();
            std::cout << "[P2_ATTEMPT] Time: " << now << "ms, Drone: " << myId << ", Slot: " << slotIndex << ", Channel: " << (int)s.channel << std::endl;
            Ptr<Packet> p = Create<Packet>(DATA_PACKET_SIZE);
            SendPacket(DATA_PACKET_SIZE, p, 2); // msduHandle = 2 (Data packet)
        } else if (s.action == ScheduleSlot::RX) {
            SwitchChannelAndPower(s.channel, g_p2TxPower);
        }
    }

    void DataConfirm(McpsDataConfirmParams params) {
        uint32_t myId = m_device->GetNode()->GetId();
        double now = Simulator::Now().GetMilliSeconds();
        // 如果是 Mini-beacon (msduHandle == 1)
        if (params.m_msduHandle == 1) {
            if (params.m_status == MacStatus::CHANNEL_ACCESS_FAILURE) {
                g_p1TxAbort++;
                std::cout << "[P1_ABORT] Time: " << now << "ms, Drone: " << myId << std::endl;
                // 如果還在 Phase 1 的有效時間內 (保留最後 2ms 緩衝)，則安排重新決策
                if (now < m_epochStartTime + (PHASE1_DURATION_US / 1000.0) - 2.0) {
                    // 隨機等待 0.1 ~ 0.5 毫秒，讓對方的情報傳達過來，也錯開重試時間
                    Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
                    double retryDelay = uv->GetValue(0.1, 0.5);
                    Simulator::Schedule(MilliSeconds(retryDelay), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
                }
            } else if (params.m_status == MacStatus::SUCCESS) {
                g_p1TxSuccess++;
                std::cout << "[P1_SUCCESS] Time: " << now << "ms, Drone: " << myId << std::endl;
            }
        } else if (params.m_msduHandle == 2) {
            if (params.m_status == MacStatus::CHANNEL_ACCESS_FAILURE) {
                std::cout << "[P2_ABORT] Time: " << now << "ms, Drone: " << myId << std::endl;
            } else if (params.m_status == MacStatus::SUCCESS) {
                std::cout << "[P2_SUCCESS] Time: " << now << "ms, Drone: " << myId << std::endl;
            }
        }
    }

    void ReceivePacket(McpsDataIndicationParams params, Ptr<Packet> p) {
        int8_t rssi = params.m_rssi;
        uint32_t myId = m_device->GetNode()->GetId();
        double now = Simulator::Now().GetMilliSeconds();

        if (p->GetSize() == MINI_BEACON_SIZE) {
            g_p1RxSuccess++;
            uint8_t buffer[2];
            p->CopyData(buffer, 2);
            uint16_t payload = buffer[0] | (buffer[1] << 8);
            
            uint8_t senderId = payload & 0x3F;
            std::cout << "[P1_RX] Time: " << now << "ms, Receiver: " << myId << ", Sender: " << (int)senderId << ", RSSI: " << (int)rssi << std::endl;
            uint8_t claimedSlot = (payload >> 6) & 0x0F;
            uint8_t claimedChannel = (payload >> 10) & 0x07;
            
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
            
            std::cout << "[P2_RX] Time: " << now << "ms, Receiver: " << myId << ", Sender: " << (int)srcId << ", RSSI: " << (int)rssi << std::endl;

            m_beaconReceivedCount[srcId]++;
            g_totalDataPacketsReceived++;
            
            double now = Simulator::Now().GetMilliSeconds();
            
            // 更新 AoI Generation Time (Just-in-Time 採樣模型：在專屬時槽起點才採樣)
            // 每個時槽 2.5ms，所以封包產生的時間大約是抵達時間 (now) 往前推 2.5ms
            m_lastGenerationTime[srcId] = now - 2.5;
        }
    }

    void PrintMetrics() {
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
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
    g_runLogFile.open("run.log");
    if (g_runLogFile.is_open()) {
        g_originalCoutBuffer = std::cout.rdbuf();
        std::cout.rdbuf(g_runLogFile.rdbuf());
    }

    CommandLine cmd;
    cmd.AddValue("p2TxPower", "Phase 2 TX Power in dBm (e.g., -9, -4, 0)", g_p2TxPower);
    cmd.Parse(argc, argv);

    int numNodes = 50; 
    NodeContainer nodes;
    nodes.Create(numNodes);

    Ptr<SingleModelSpectrumChannel> channel = CreateObject<SingleModelSpectrumChannel>();
    Ptr<LogDistancePropagationLossModel> propModel = CreateObject<LogDistancePropagationLossModel>();
    Ptr<ConstantSpeedPropagationDelayModel> delayModel = CreateObject<ConstantSpeedPropagationDelayModel>();
    channel->AddPropagationLossModel(propModel);
    channel->SetPropagationDelayModel(delayModel);

    LrWpanHelper lrWpanHelper;
    lrWpanHelper.SetChannel(channel);
    NetDeviceContainer devices = lrWpanHelper.Install(nodes);

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
        Ptr<LrWpanNetDevice> dev = DynamicCast<LrWpanNetDevice>(devices.Get(i));
        
        char extMacStr[32];
        snprintf(extMacStr, sizeof(extMacStr), "00:00:00:00:00:00:00:%02x", i);
        dev->GetMac()->SetExtendedAddress(Mac64Address(extMacStr));
        
        char macStr[16];
        snprintf(macStr, sizeof(macStr), "00:%02x", i);
        dev->GetMac()->SetShortAddress(Mac16Address(macStr));

        Ptr<SwarmSchedulerApp> app = CreateObject<SwarmSchedulerApp>();
        app->Setup(dev, i);
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
    
    std::stringstream ss;
    ss << "\n=================================================\n";
    ss << "          GLOBAL NETWORK METRICS (1.0s)          \n";
    ss << "=================================================\n";
    ss << "Phase 1 TX Attempts             : " << g_p1TxAttempts << " times\n";
    ss << "Phase 1 TX Aborts (CSMA Busy)   : " << g_p1TxAbort << " times\n";
    ss << "Phase 1 TX Success (Sent)       : " << g_p1TxSuccess << " times\n";
    ss << "Phase 1 RX Success (Total Rcvd) : " << g_p1RxSuccess << " packets\n";
    ss << "-------------------------------------------------\n";
    ss << "=== DEAFNESS & COLLISION STATS ===\n";
    ss << "Total Top-K Neighbors Wanted : " << g_totalExpectedRx << " packets\n";
    ss << "TX Deafness (Same slot as TX): " << g_txDeafnessCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_txDeafnessCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "RX Deafness (Slot conflict)  : " << g_rxDeafnessCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_rxDeafnessCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "Resource Collision (Same S+C): " << g_resourceCollisionCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_resourceCollisionCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "-------------------------------------------------\n";
    ss << "Total 50B Data Packets Delivered: " << g_totalDataPacketsReceived << "\n";
    ss << "Total Network Slots Elapsed     : " << totalSlots << " slots\n";
    ss << "Spatial Reuse Factor (SRF)      : " << std::fixed << std::setprecision(2) << srf << " packets/slot\n";
    ss << "Discovery Message Reception Ratio: " << std::fixed << std::setprecision(1) << globalDiscRatio * 100 << "%\n";
    ss << "Beacon Packet Reception Ratio   : " << std::fixed << std::setprecision(1) << globalBcnRatio * 100 << "%\n";
    ss << "Monitor Member List Match Ratio : " << std::fixed << std::setprecision(1) << globalTopAcc * 100 << "%\n";
    ss << "Avg Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << globalAvgDiscIat << " ms\n";
    ss << "Max Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << g_globalMaxDiscoveryIatTopK << " ms\n";
    ss << "Mean Beacon Packet AoI (Top-K)  : " << std::fixed << std::setprecision(1) << globalMeanAoI << " ms\n";
    ss << "Max Beacon Packet AoI (Top-K)   : " << std::fixed << std::setprecision(1) << g_globalMaxAoITopK << " ms\n";
    ss << "=================================================\n\n";

    if (g_originalCoutBuffer) {
        std::cout.rdbuf(g_originalCoutBuffer);
    }
    
    std::cout << ss.str();
    
    if (g_runLogFile.is_open()) {
        g_runLogFile << ss.str();
        g_runLogFile.close();
        int ret = system("git add run.log && git commit -m 'Auto upload run.log' && git push origin main");
        if (ret != 0) {
            std::cerr << "Failed to auto-upload run.log to GitHub!" << std::endl;
        } else {
            std::cout << "Log successfully uploaded to GitHub!" << std::endl;
        }
    }

    Simulator::Destroy();

    return 0;
}
