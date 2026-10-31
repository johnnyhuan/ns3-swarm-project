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
#include <set>
#include <tuple>
#include <string>

using namespace ns3;
using namespace ns3::lrwpan;

std::ofstream g_runLogFile;
std::streambuf* g_originalCoutBuffer = nullptr;

NS_LOG_COMPONENT_DEFINE("LrWpanSwarm");

// --- 系統常數設定 ---
const uint32_t MINI_BEACON_SIZE = 2; 
const uint32_t DATA_PACKET_SIZE = 50;
double g_p2TxPower = -2.0; // Phase 2 TX Power (configurable via cmd line, optimal at -2 dBm)
double g_p1TxPower = 0.0;  // Phase 1 TX Power (configurable via cmd line)
double g_p1AvoidDist = 50.0; // RX Deafness defense distance in meters
double g_p1AvoidRssi = -999.0; // Specific defense RSSI threshold in dBm (-106 to -90, overrides p1AvoidDist if set)
bool g_enableDefense = true; // Defense design switch: true = spatial slot exclusion, false = exact cell avoidance only
int g_numDataChannels = 6;   // Phase 2 Data Channels (configurable via cmd line, 0 to 10)
int g_numDataSlots = 10;     // Phase 2 Data Slots (configurable via cmd line, 5 to 20)

double g_p1DurationMs = 25.0; // Phase 1 Duration in ms (configurable via cmd line, 10 to 40)
double g_phase1DurationUs = 25000.0;
double g_cycleMs = 51.0;            // Dynamically computed: g_p1DurationMs + 1 + (g_numDataSlots * 2.5)
const double GAP_US = 1000.0; 
const int MAX_DATA_SLOTS = 32;            // Maximum supported slots (up to 31 in 5-bit encoding)
const int MAX_DATA_CHANNELS = 16;        // Maximum supported data channels
const double DATA_SLOT_US = 2500.0; 

const uint8_t BROADCAST_CHANNEL = 11;

// --- 目標條件設定 ---
const double M_RADIUS_METERS = 50.0;    // 評估指標用的實際距離 (Ground Truth)
// (Old threshold removed)
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
static std::stringstream g_singleDroneReport;

// Phase 1 專用統計
static int g_p1TxAttempts = 0;
static int g_p1TxAbort = 0;
static int g_p1TxSuccess = 0;
static int g_p1RxSuccess = 0;

// --- Phase 1 Ground Truth Physical Drop Tracking ---
enum P1DropCategory {
    REASON_SUCCESS = 0,
    REASON_SENDER_CSMA_ABORT,
    REASON_RX_DEAFNESS_BUSY_TX,
    REASON_PREAMBLE_COLLISION_BUSY_RX,
    REASON_PAYLOAD_INTERFERENCE_CORRUPTION,
    REASON_PREAMBLE_LOW_SINR,
    REASON_OUT_OF_RANGE_OR_FADING,
    NUM_P1_REASONS
};

static const char* P1ReasonStrings[] = {
    "SUCCESS",
    "SENDER_CSMA_ABORT",
    "RX_DEAFNESS_BUSY_TX",
    "PREAMBLE_COLLISION_BUSY_RX",
    "PAYLOAD_INTERFERENCE_CORRUPTION",
    "PREAMBLE_LOW_SINR",
    "OUT_OF_RANGE_OR_FADING"
};

struct P1PacketMeta {
    uint8_t senderId;
    uint32_t epoch;
    double txStartTime;
};

struct P1LinkRecord {
    uint32_t epoch;
    uint8_t receiver;
    uint8_t sender;
    double distance;
    P1DropCategory category;
};

static PhyEnumeration g_dronePhyState[256];
static uint64_t g_droneReceivingUid[256];
static std::map<uint64_t, P1PacketMeta> g_p1PacketsMeta;
static std::map<std::pair<uint32_t, uint8_t>, std::vector<uint64_t>> g_p1TxUidsInEpoch;
static std::map<std::pair<uint64_t, uint8_t>, PhyEnumeration> g_rxStateAtTxStart;
static std::map<std::tuple<uint32_t, uint8_t, uint8_t>, P1DropCategory> g_p1RxDropEvent;
static std::map<uint32_t, std::map<uint8_t, std::set<uint8_t>>> g_p1ReceivedInEpoch;
static std::map<uint32_t, std::map<uint8_t, int>> g_p1TxSuccessInEpoch;

static std::vector<P1LinkRecord> g_p1LinkRecords;
static int g_p1ReasonCounts[NUM_P1_REASONS] = {0};
static int g_p1TotalTargetLinks = 0;

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

// --- Phase 2 Ground Truth Physical Drop Tracking ---
enum P2DropCategory {
    P2_REASON_SUCCESS = 0,
    P2_REASON_P1_DISCOVERY_MISS,             // Unscheduled in P2 because P1 discovery failed
    P2_REASON_TX_DEAFNESS_SAME_SLOT,         // Half-duplex: receiver transmitting in same slot
    P2_REASON_RX_DEAFNESS_SLOT_CONFLICT,     // Receiver listening to another neighbor in this slot
    P2_REASON_PAYLOAD_INTERFERENCE_DROP,     // Receiver locked preamble, but mid-flight packet corrupted by interference
    P2_REASON_PREAMBLE_COLLISION_OR_LOW_SINR,// Preamble collided with another packet or SINR <= -5dB during preamble
    P2_REASON_RECEIVER_CHANNEL_MISMATCH,     // Receiver radio was on a different channel
    P2_REASON_RADIO_TURNAROUND_BUSY,         // Receiver was on correct channel but in turnaround/transient busy
    P2_REASON_SENDER_CSMA_ABORT,             // Sender aborted transmission due to busy channel at slot start
    NUM_P2_REASONS
};

static const char* P2ReasonStrings[] = {
    "SUCCESS",
    "P1_DISCOVERY_MISS",
    "TX_DEAFNESS_SAME_SLOT",
    "RX_DEAFNESS_SLOT_CONFLICT",
    "PAYLOAD_INTERFERENCE_DROP",
    "PREAMBLE_COLLISION_OR_LOW_SINR",
    "RECEIVER_CHANNEL_MISMATCH",
    "RADIO_TURNAROUND_BUSY",
    "SENDER_CSMA_ABORT"
};

struct P2PacketMeta {
    uint8_t senderId;
    uint32_t epoch;
    uint8_t slot;
    uint8_t channel;
    double txStartTime;
};

struct P2LinkRecord {
    uint32_t epoch;
    uint8_t receiver;
    uint8_t sender;
    double distance;
    P2DropCategory category;
};

static std::vector<P2LinkRecord> g_p2LinkRecords;
static int g_p2ReasonCounts[NUM_P2_REASONS] = {0};
static int g_p2TotalTargetLinks = 0;

static uint8_t g_droneCurrentChannel[256];
static std::map<uint64_t, P2PacketMeta> g_p2PacketsMeta;
static std::map<std::pair<uint32_t, uint8_t>, std::vector<uint64_t>> g_p2TxUidsInEpoch;
static std::map<std::pair<uint64_t, uint8_t>, PhyEnumeration> g_p2RxStateAtTxStart;
static std::map<std::pair<uint64_t, uint8_t>, uint8_t> g_p2RxChannelAtTxStart;
static std::map<std::tuple<uint32_t, uint8_t, uint8_t>, P2DropCategory> g_p2RxDropEvent;
static std::map<std::tuple<uint32_t, uint8_t, uint8_t>, bool> g_p2RxBeginEvent;
static std::map<std::tuple<uint32_t, uint8_t, uint8_t>, double> g_p2RxEndSinr;

static std::map<uint32_t, std::map<uint8_t, std::set<uint8_t>>> g_p2ReceivedInEpoch;
static std::map<uint32_t, std::map<uint8_t, bool>> g_p2TxAbortInEpoch;
static std::map<uint32_t, std::map<uint8_t, uint8_t>> g_droneClaimedSlot;
static std::map<uint32_t, std::map<uint8_t, uint8_t>> g_droneClaimedChannel;
static std::map<uint32_t, std::map<uint8_t, std::set<uint8_t>>> g_p2DiscoveredInP1;
static std::map<uint32_t, std::map<uint8_t, std::map<int, ScheduleSlot::Action>>> g_p2SlotAction;
static std::map<uint32_t, std::map<uint8_t, std::map<int, uint8_t>>> g_p2SlotTarget;

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
        
        // Connect PHY Traces for exact physical ground truth
        Ptr<LrWpanPhy> phy = m_device->GetPhy();
        g_dronePhyState[m_id] = IEEE_802_15_4_PHY_TRX_OFF;
        g_droneReceivingUid[m_id] = 0;
        g_droneCurrentChannel[m_id] = BROADCAST_CHANNEL;
        phy->TraceConnectWithoutContext("TrxState", MakeCallback(&SwarmSchedulerApp::NotifyPhyTrxStateChange, this));
        phy->TraceConnectWithoutContext("PhyRxBegin", MakeCallback(&SwarmSchedulerApp::NotifyPhyRxBegin, this));
        phy->TraceConnectWithoutContext("PhyRxEnd", MakeCallback(&SwarmSchedulerApp::NotifyPhyRxEnd, this));
        phy->TraceConnectWithoutContext("PhyRxDrop", MakeCallback(&SwarmSchedulerApp::NotifyPhyRxDrop, this));
        phy->TraceConnectWithoutContext("PhyTxBegin", MakeCallback(&SwarmSchedulerApp::NotifyPhyTxBegin, this));

        Simulator::Schedule(Seconds(0.999), &SwarmSchedulerApp::PrintMetrics, this);
    }

    void NotifyPhyTrxStateChange(Time time, PhyEnumeration oldState, PhyEnumeration newState) {
        g_dronePhyState[m_id] = newState;
    }

    void NotifyPhyRxBegin(Ptr<const Packet> p) {
        uint64_t uid = p->GetUid();
        g_droneReceivingUid[m_id] = uid;

        auto it2 = g_p2PacketsMeta.find(uid);
        if (it2 != g_p2PacketsMeta.end()) {
            g_p2RxBeginEvent[{it2->second.epoch, it2->second.senderId, m_id}] = true;
        }
    }

    void NotifyPhyRxEnd(Ptr<const Packet> p, double sinr) {
        uint64_t uid = p->GetUid();
        if (g_droneReceivingUid[m_id] == uid) {
            g_droneReceivingUid[m_id] = 0;
        }
        auto it2 = g_p2PacketsMeta.find(uid);
        if (it2 != g_p2PacketsMeta.end()) {
            g_p2RxEndSinr[{it2->second.epoch, it2->second.senderId, m_id}] = sinr;
        }
    }

    void NotifyPhyRxDrop(Ptr<const Packet> p) {
        uint64_t uid = p->GetUid();
        auto it = g_p1PacketsMeta.find(uid);
        if (it != g_p1PacketsMeta.end()) {
            uint8_t sender = it->second.senderId;
            uint32_t epoch = it->second.epoch;
            if (g_droneReceivingUid[m_id] == uid) {
                g_p1RxDropEvent[{epoch, sender, m_id}] = REASON_PAYLOAD_INTERFERENCE_CORRUPTION;
                g_droneReceivingUid[m_id] = 0;
            } else {
                g_p1RxDropEvent[{epoch, sender, m_id}] = REASON_PREAMBLE_LOW_SINR;
            }
        }

        auto it2 = g_p2PacketsMeta.find(uid);
        if (it2 != g_p2PacketsMeta.end()) {
            uint8_t sender = it2->second.senderId;
            uint32_t epoch = it2->second.epoch;
            if (g_droneReceivingUid[m_id] == uid) {
                g_p2RxDropEvent[{epoch, sender, m_id}] = P2_REASON_PAYLOAD_INTERFERENCE_DROP;
                g_droneReceivingUid[m_id] = 0;
            } else {
                g_p2RxDropEvent[{epoch, sender, m_id}] = P2_REASON_PREAMBLE_COLLISION_OR_LOW_SINR;
            }
        }
    }

    void NotifyPhyTxBegin(Ptr<const Packet> p) {
        uint64_t uid = p->GetUid();
        auto it = g_p1PacketsMeta.find(uid);
        if (it != g_p1PacketsMeta.end()) {
            it->second.txStartTime = Simulator::Now().GetMilliSeconds();
            uint32_t numNodes = NodeList::GetNNodes();
            for (uint32_t j = 0; j < numNodes; j++) {
                if (j == m_id) continue;
                g_rxStateAtTxStart[{uid, (uint8_t)j}] = g_dronePhyState[j];
            }
        }

        auto it2 = g_p2PacketsMeta.find(uid);
        if (it2 != g_p2PacketsMeta.end()) {
            it2->second.txStartTime = Simulator::Now().GetMilliSeconds();
            uint32_t numNodes = NodeList::GetNNodes();
            for (uint32_t j = 0; j < numNodes; j++) {
                if (j == m_id) continue;
                g_p2RxStateAtTxStart[{uid, (uint8_t)j}] = g_dronePhyState[j];
                g_p2RxChannelAtTxStart[{uid, (uint8_t)j}] = g_droneCurrentChannel[j];
            }
        }
    }

    void StartApplication() override {
        if (m_id == 0) std::cout << "All Drones StartApplication called! Running for 1.0s..." << std::endl;
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
    ScheduleSlot m_schedule[MAX_DATA_SLOTS];

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
        g_droneCurrentChannel[m_id] = ch;
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

        // Phase 1 (Broadcast): Configurable range
        SwitchChannelAndPower(BROADCAST_CHANNEL, (int8_t)g_p1TxPower);
        
        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
        double maxDelayUs = std::max(1000.0, g_phase1DurationUs - 2000.0);
        double randomDelayUs = uv->GetValue(0, maxDelayUs);
        
        Simulator::Schedule(MicroSeconds(randomDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        if (m_id == 0) {
            Simulator::Schedule(MicroSeconds(g_phase1DurationUs), &SwarmSchedulerApp::EvaluatePhase1Epoch, this, m_epoch);
            double p2DoneUs = g_phase1DurationUs + GAP_US + (g_numDataSlots * DATA_SLOT_US) + 100.0;
            Simulator::Schedule(MicroSeconds(p2DoneUs), &SwarmSchedulerApp::EvaluatePhase2Epoch, this, m_epoch);
        }
        Simulator::Schedule(MicroSeconds(g_phase1DurationUs + GAP_US), &SwarmSchedulerApp::ComputeSchedule, this);
        Simulator::Schedule(MilliSeconds(g_cycleMs), &SwarmSchedulerApp::ScheduleCycle, this);
    }

    void PickResourceAndSendBeacon() {
        g_p1TxAttempts++;
        uint32_t myId = m_device->GetNode()->GetId();
        double now = Simulator::Now().GetMilliSeconds();
        std::cout << "[P1_ATTEMPT] Time: " << now << "ms, Drone: " << myId << std::endl;

        if (g_numDataChannels <= 0 || g_numDataSlots <= 0) {
            m_myClaimedSlot = 0;
            m_myClaimedChannel = 0;
            g_droneClaimedSlot[m_epoch][m_id] = 0;
            g_droneClaimedChannel[m_epoch][m_id] = 0;
            uint16_t payload = (m_id & 0x7F);
            uint8_t buffer[2] = { (uint8_t)(payload & 0xFF), (uint8_t)((payload >> 8) & 0xFF) };
            Ptr<Packet> p = Create<Packet>(buffer, 2);
            uint64_t uid = p->GetUid();
            P1PacketMeta meta;
            meta.senderId = m_id;
            meta.epoch = m_epoch;
            meta.txStartTime = 0.0;
            g_p1PacketsMeta[uid] = meta;
            g_p1TxUidsInEpoch[{m_epoch, m_id}].push_back(uid);
            SendPacket(MINI_BEACON_SIZE, p, 1);
            return;
        }
        
        int cost[MAX_DATA_SLOTS][MAX_DATA_CHANNELS] = {0};
        
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
        for (const auto& n : m_monitorList) {
            if (n.claimedSlot < g_numDataSlots && n.claimedChannel < g_numDataChannels) {
                cost[n.claimedSlot][n.claimedChannel] += 10000;
            }
            
            // 加入空間防禦：利用距離或指定之 RSSI 門檻判斷是否為鄰近無人機 (利用 Friis 公式反推 RSSI 門檻)
            if (g_enableDefense && g_p1AvoidDist > 0.0) {
                double avoidRssi = -97.65; // 預設 ~ -98 dBm (50m Friis 門檻)
                if (g_p1AvoidRssi > -900.0) {
                    avoidRssi = g_p1AvoidRssi;
                } else if (g_p1AvoidDist > 0.0) {
                    avoidRssi = g_p1TxPower - 46.6777 - 30.0 * std::log10(std::max(1.0, g_p1AvoidDist));
                }
                if (n.rssi >= avoidRssi && n.claimedSlot < g_numDataSlots) {
                    for (int c = 0; c < g_numDataChannels; c++) {
                        cost[n.claimedSlot][c] += 1000;
                    }
                }
            }
        }
        
        int minCost = 999999;
        std::vector<std::pair<int, int>> bestOptions;
        
        for (int s = 0; s < g_numDataSlots; s++) {
            for (int c = 0; c < g_numDataChannels; c++) {
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
        g_droneClaimedSlot[m_epoch][m_id] = m_myClaimedSlot;
        g_droneClaimedChannel[m_epoch][m_id] = m_myClaimedChannel;

        // 位元封裝 (Bit-packing): ID(7 bits), Slot(5 bits), Channel(4 bits) -> Total 16 bits
        uint16_t payload = (m_id & 0x7F) | ((m_myClaimedSlot & 0x1F) << 7) | ((m_myClaimedChannel & 0x0F) << 12);
        uint8_t buffer[2] = { (uint8_t)(payload & 0xFF), (uint8_t)((payload >> 8) & 0xFF) };
        Ptr<Packet> p = Create<Packet>(buffer, 2);
        uint64_t uid = p->GetUid();
        P1PacketMeta meta;
        meta.senderId = m_id;
        meta.epoch = m_epoch;
        meta.txStartTime = 0.0;
        g_p1PacketsMeta[uid] = meta;
        g_p1TxUidsInEpoch[{m_epoch, m_id}].push_back(uid);
                  
        SendPacket(MINI_BEACON_SIZE, p, 1); // msduHandle = 1 (Mini-beacon)
    }

    void ComputeSchedule() {
        // 第一步：過濾出 50m 避撞安全監控半徑內的鄰機 (固定以 50m / -98 dBm 評估或最近鄰居)
        double safetyRssi = g_p1TxPower - 46.6777 - 30.0 * std::log10(50.0); // -97.65 dBm ~ -98 dBm
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
        std::vector<NeighborInfo> filteredList;
        for (auto& n : m_monitorList) {
            if (n.rssi >= safetyRssi) {
                filteredList.push_back(n);
            }
        }

        std::sort(filteredList.begin(), filteredList.end(), [](const NeighborInfo& a, const NeighborInfo& b) {
            return a.rssi > b.rssi;
        });

        for (int i = 0; i < g_numDataSlots; i++) {
            m_schedule[i].action = ScheduleSlot::IDLE;
        }

        if (g_numDataChannels <= 0 || g_numDataSlots <= 0) {
            return;
        }

        m_schedule[m_myClaimedSlot].action = ScheduleSlot::TX;
        m_schedule[m_myClaimedSlot].channel = m_myClaimedChannel + 12;

        int expected = std::min(K_CLOSEST, (int)filteredList.size());
        g_totalExpectedRx += expected;

        int assigned = 0;
        m_lastScheduledRx.clear();
        for (auto& n : filteredList) {
            if (assigned >= K_CLOSEST) break; 
            if (n.claimedSlot >= g_numDataSlots) continue;
            
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

        for (int i = 0; i < g_numDataSlots; i++) {
            g_p2SlotAction[m_epoch][m_id][i] = m_schedule[i].action;
            g_p2SlotTarget[m_epoch][m_id][i] = m_schedule[i].targetId;
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
            uint64_t uid = p->GetUid();

            P2PacketMeta meta;
            meta.senderId = myId;
            meta.epoch = m_epoch;
            meta.slot = slotIndex;
            meta.channel = s.channel;
            meta.txStartTime = now;
            g_p2PacketsMeta[uid] = meta;
            g_p2TxUidsInEpoch[{m_epoch, (uint8_t)myId}].push_back(uid);

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
                if (now < m_epochStartTime + g_p1DurationMs - 2.0) {
                    // 隨機等待 0.1 ~ 0.5 毫秒，讓對方的情報傳達過來，也錯開重試時間
                    Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
                    double retryDelay = uv->GetValue(0.1, 0.5);
                    Simulator::Schedule(MilliSeconds(retryDelay), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
                }
            } else if (params.m_status == MacStatus::SUCCESS) {
                g_p1TxSuccess++;
                g_p1TxSuccessInEpoch[m_epoch][myId]++;
                std::cout << "[P1_SUCCESS] Time: " << now << "ms, Drone: " << myId << std::endl;
            }
        } else if (params.m_msduHandle == 2) {
            if (params.m_status == MacStatus::CHANNEL_ACCESS_FAILURE) {
                g_p2TxAbortInEpoch[m_epoch][myId] = true;
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
            
            uint8_t senderId = payload & 0x7F;
            g_p1ReceivedInEpoch[m_epoch][myId].insert(senderId);
            g_p2DiscoveredInP1[m_epoch][myId].insert(senderId);
            std::cout << "[P1_RX] Time: " << now << "ms, Receiver: " << myId << ", Sender: " << (int)senderId << ", RSSI: " << (int)rssi << std::endl;
            uint8_t claimedSlot = (payload >> 7) & 0x1F;
            uint8_t claimedChannel = (payload >> 12) & 0x0F;
            
            m_monitorList.push_back({senderId, rssi, m_epoch, claimedSlot, claimedChannel});
            m_discoveryReceivedCount[senderId]++;
            
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
            g_p2ReceivedInEpoch[m_epoch][myId].insert(srcId);
            
            std::cout << "[P2_RX] Time: " << now << "ms, Receiver: " << myId << ", Sender: " << (int)srcId << ", RSSI: " << (int)rssi << std::endl;

            m_beaconReceivedCount[srcId]++;
            g_totalDataPacketsReceived++;
            
            // 更新 AoI Generation Time (Just-in-Time 採樣模型：在專屬時槽起點才採樣)
            // 每個時槽 2.5ms，所以封包產生的時間大約是抵達時間 (now) 往前推 2.5ms
            m_lastGenerationTime[srcId] = now - 2.5;
        }
    }

    void EvaluatePhase1Epoch(uint32_t epoch) {
        uint32_t numNodes = NodeList::GetNNodes();
        for (uint32_t r = 0; r < numNodes; r++) {
            Ptr<MobilityModel> rMob = NodeList::GetNode(r)->GetObject<MobilityModel>();
            std::vector<std::pair<uint8_t, double>> dists;
            for (uint32_t s = 0; s < numNodes; s++) {
                if (s == r) continue;
                Ptr<MobilityModel> sMob = NodeList::GetNode(s)->GetObject<MobilityModel>();
                double d = rMob->GetDistanceFrom(sMob);
                if (d <= M_RADIUS_METERS) {
                    dists.push_back({(uint8_t)s, d});
                }
            }
            std::sort(dists.begin(), dists.end(), [](const auto& a, const auto& b) {
                return a.second < b.second;
            });

            int topK = std::min(K_CLOSEST, (int)dists.size());
            for (int i = 0; i < topK; i++) {
                uint8_t sender = dists[i].first;
                double dist = dists[i].second;

                bool heard = false;
                auto itEp = g_p1ReceivedInEpoch.find(epoch);
                if (itEp != g_p1ReceivedInEpoch.end()) {
                    auto itRcv = itEp->second.find((uint8_t)r);
                    if (itRcv != itEp->second.end()) {
                        heard = (itRcv->second.count(sender) > 0);
                    }
                }

                P1DropCategory cat = REASON_SUCCESS;
                if (heard) {
                    cat = REASON_SUCCESS;
                } else {
                    int txSucc = 0;
                    auto itTxEp = g_p1TxSuccessInEpoch.find(epoch);
                    if (itTxEp != g_p1TxSuccessInEpoch.end()) {
                        auto itTxNode = itTxEp->second.find(sender);
                        if (itTxNode != itTxEp->second.end()) {
                            txSucc = itTxNode->second;
                        }
                    }

                    if (txSucc == 0) {
                        cat = REASON_SENDER_CSMA_ABORT;
                    } else {
                        uint64_t txUid = 0;
                        auto uidsIt = g_p1TxUidsInEpoch.find({epoch, sender});
                        if (uidsIt != g_p1TxUidsInEpoch.end() && !uidsIt->second.empty()) {
                            txUid = uidsIt->second.back();
                        }

                        PhyEnumeration rStateAtTx = IEEE_802_15_4_PHY_TRX_OFF;
                        auto stIt = g_rxStateAtTxStart.find({txUid, (uint8_t)r});
                        if (stIt != g_rxStateAtTxStart.end()) {
                            rStateAtTx = stIt->second;
                        }

                        if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_TX || rStateAtTx == IEEE_802_15_4_PHY_TX_ON) {
                            cat = REASON_RX_DEAFNESS_BUSY_TX;
                        } else if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_RX) {
                            cat = REASON_PREAMBLE_COLLISION_BUSY_RX;
                        } else {
                            auto dropIt = g_p1RxDropEvent.find({epoch, sender, (uint8_t)r});
                            if (dropIt != g_p1RxDropEvent.end()) {
                                cat = dropIt->second;
                            } else {
                                cat = REASON_OUT_OF_RANGE_OR_FADING;
                            }
                        }
                    }
                }

                P1LinkRecord rec;
                rec.epoch = epoch;
                rec.receiver = (uint8_t)r;
                rec.sender = sender;
                rec.distance = dist;
                rec.category = cat;
                g_p1LinkRecords.push_back(rec);
                g_p1ReasonCounts[cat]++;
                g_p1TotalTargetLinks++;
            }
        }
    }

    void EvaluatePhase2Epoch(uint32_t epoch) {
        uint32_t numNodes = NodeList::GetNNodes();
        for (uint32_t r = 0; r < numNodes; r++) {
            Ptr<MobilityModel> rMob = NodeList::GetNode(r)->GetObject<MobilityModel>();
            std::vector<std::pair<uint8_t, double>> dists;
            for (uint32_t s = 0; s < numNodes; s++) {
                if (s == r) continue;
                Ptr<MobilityModel> sMob = NodeList::GetNode(s)->GetObject<MobilityModel>();
                double d = rMob->GetDistanceFrom(sMob);
                if (d <= M_RADIUS_METERS) {
                    dists.push_back({(uint8_t)s, d});
                }
            }
            std::sort(dists.begin(), dists.end(), [](const auto& a, const auto& b) {
                return a.second < b.second;
            });

            int topK = std::min(K_CLOSEST, (int)dists.size());
            for (int i = 0; i < topK; i++) {
                uint8_t sender = dists[i].first;
                double dist = dists[i].second;

                bool delivered = false;
                auto itEp = g_p2ReceivedInEpoch.find(epoch);
                if (itEp != g_p2ReceivedInEpoch.end()) {
                    auto itRcv = itEp->second.find((uint8_t)r);
                    if (itRcv != itEp->second.end()) {
                        delivered = (itRcv->second.count(sender) > 0);
                    }
                }

                P2DropCategory cat = P2_REASON_SUCCESS;
                if (delivered) {
                    cat = P2_REASON_SUCCESS;
                } else {
                    bool discoveredInP1 = false;
                    auto itP1Ep = g_p2DiscoveredInP1.find(epoch);
                    if (itP1Ep != g_p2DiscoveredInP1.end()) {
                        auto itP1R = itP1Ep->second.find((uint8_t)r);
                        if (itP1R != itP1Ep->second.end()) {
                            discoveredInP1 = (itP1R->second.count(sender) > 0);
                        }
                    }

                    if (!discoveredInP1) {
                        cat = P2_REASON_P1_DISCOVERY_MISS;
                    } else if (g_p2TxAbortInEpoch[epoch][sender]) {
                        cat = P2_REASON_SENDER_CSMA_ABORT;
                    } else {
                        // Sender actually transmitted a packet into the air!
                        // Find sender's transmitted UID in this epoch
                        uint64_t txUid = 0;
                        auto uidsIt = g_p2TxUidsInEpoch.find({epoch, sender});
                        if (uidsIt != g_p2TxUidsInEpoch.end() && !uidsIt->second.empty()) {
                            txUid = uidsIt->second.back();
                        }

                        uint8_t sChannel = 0;
                        auto metaIt = g_p2PacketsMeta.find(txUid);
                        if (metaIt != g_p2PacketsMeta.end()) {
                            sChannel = metaIt->second.channel;
                        }

                        // Inspect receiver r's radio at takeoff
                        PhyEnumeration rStateAtTx = IEEE_802_15_4_PHY_TRX_OFF;
                        uint8_t rChannelAtTx = 0;
                        auto stIt = g_p2RxStateAtTxStart.find({txUid, (uint8_t)r});
                        if (stIt != g_p2RxStateAtTxStart.end()) {
                            rStateAtTx = stIt->second;
                        }
                        auto chIt = g_p2RxChannelAtTxStart.find({txUid, (uint8_t)r});
                        if (chIt != g_p2RxChannelAtTxStart.end()) {
                            rChannelAtTx = chIt->second;
                        }

                        // 1. Was receiver r transmitting (half-duplex deaf)?
                        if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_TX || rStateAtTx == IEEE_802_15_4_PHY_TX_ON) {
                            cat = P2_REASON_TX_DEAFNESS_SAME_SLOT;
                        }
                        // 2. Was receiver r on a different channel?
                        else if (rChannelAtTx != sChannel) {
                            uint8_t sSlot = g_droneClaimedSlot[epoch][sender];
                            if (g_p2SlotAction[epoch][(uint8_t)r][sSlot] == ScheduleSlot::RX &&
                                g_p2SlotTarget[epoch][(uint8_t)r][sSlot] != sender) {
                                cat = P2_REASON_RX_DEAFNESS_SLOT_CONFLICT;
                            } else {
                                cat = P2_REASON_RECEIVER_CHANNEL_MISMATCH;
                            }
                        }
                        // 3. r was on the SAME channel as s!
                        else {
                            // Check exact PHY drop event recorded for this packet at r
                            auto dropIt = g_p2RxDropEvent.find({epoch, sender, (uint8_t)r});
                            if (dropIt != g_p2RxDropEvent.end()) {
                                cat = dropIt->second; // PAYLOAD_INTERFERENCE_DROP or PREAMBLE_COLLISION_OR_LOW_SINR
                            } else if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_RX) {
                                cat = P2_REASON_PREAMBLE_COLLISION_OR_LOW_SINR;
                            } else if (rStateAtTx == IEEE_802_15_4_PHY_TRX_OFF) {
                                cat = P2_REASON_RADIO_TURNAROUND_BUSY;
                            } else {
                                cat = P2_REASON_PREAMBLE_COLLISION_OR_LOW_SINR;
                            }
                        }
                    }
                }

                P2LinkRecord rec;
                rec.epoch = epoch;
                rec.receiver = (uint8_t)r;
                rec.sender = sender;
                rec.distance = dist;
                rec.category = cat;
                g_p2LinkRecords.push_back(rec);
                g_p2ReasonCounts[cat]++;
                g_p2TotalTargetLinks++;
            }
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


        static bool s_printedSampleDrone = false;
        if (!s_printedSampleDrone && (godDistances.size() > 0 || m_id == 0)) {
            s_printedSampleDrone = true;
            g_singleDroneReport << "\n=== Drone " << std::setw(2) << (int)m_id << " Metrics Report (Top " << K_CLOSEST << " within " << M_RADIUS_METERS << "m) ===\n";
            g_singleDroneReport << "Target (Dist)  | Disc. Ratio | Bcn Ratio | Avg Disc. IAT | Max Disc. IAT | Mean Bcn AoI | Max Bcn AoI\n";
            g_singleDroneReport << "-----------------------------------------------------------------------------------------------------\n";
            
            for (int i = 0; i < std::min(K_CLOSEST, (int)godDistances.size()); i++) {
                uint8_t target = godDistances[i].first;
                double dist = godDistances[i].second;
                
                double discRatio = (double)m_discoveryReceivedCount[target] / m_epoch;
                double bcnRatio = (double)m_beaconReceivedCount[target] / m_epoch;
                double avgDiscIat = (m_countDiscoveryIat[target] > 0) ? (m_sumDiscoveryIat[target] / m_countDiscoveryIat[target]) : 0;
                double maxDiscIat = (m_maxDiscoveryIat.find(target) != m_maxDiscoveryIat.end()) ? m_maxDiscoveryIat[target] : 0;
                double meanAoI = (m_countAoI[target] > 0) ? (m_sumAoI[target] / m_countAoI[target]) : 0;
                double maxAoI = (m_maxAoI.find(target) != m_maxAoI.end()) ? m_maxAoI[target] : 0;
                
                g_singleDroneReport << "Drone " << std::setw(2) << (int)target << " (" << std::setw(3) << (int)dist << "m) | "
                                    << std::fixed << std::setprecision(1) << std::setw(11) << discRatio * 100 << " | "
                                    << std::fixed << std::setprecision(1) << std::setw(9) << bcnRatio * 100 << " | "
                                    << std::fixed << std::setprecision(1) << std::setw(13) << avgDiscIat << " | "
                                    << std::fixed << std::setprecision(1) << std::setw(13) << maxDiscIat << " | "
                                    << std::fixed << std::setprecision(1) << std::setw(12) << meanAoI << " | "
                                    << std::fixed << std::setprecision(1) << std::setw(11) << maxAoI << "\n";
            }
        }
    }
};

void PrintGroundTruthReport() {
    std::stringstream ss;
    ss << "\n========================================================================================\n";
    ss << "       🔬 PHASE 1 PHYSICAL & MAC GROUND TRUTH ANALYSIS (Top-K within 50m) 🔬           \n";
    ss << "========================================================================================\n";
    ss << "Total Expected P1 Neighbor Links (Epochs x Top-K) : " << g_p1TotalTargetLinks << "\n";
    double succPct = (g_p1TotalTargetLinks > 0) ? (100.0 * g_p1ReasonCounts[REASON_SUCCESS] / g_p1TotalTargetLinks) : 0;
    int totalFails = g_p1TotalTargetLinks - g_p1ReasonCounts[REASON_SUCCESS];
    double failPct = 100.0 - succPct;
    ss << "  ✅ Successfully Received (Delivered)            : " << g_p1ReasonCounts[REASON_SUCCESS] 
       << " (" << std::fixed << std::setprecision(1) << succPct << "%)\n";
    ss << "  ❌ Failed Link Receptions (Dropped/Missed)      : " << totalFails 
       << " (" << std::fixed << std::setprecision(1) << failPct << "%)\n";
    ss << "----------------------------------------------------------------------------------------\n";
    ss << "EXACT PHYSICAL ROOT CAUSE BREAKDOWN (Zero Estimation / Direct From ns-3 State Machine):\n";
    
    for (int c = 1; c < NUM_P1_REASONS; c++) {
        int cnt = g_p1ReasonCounts[c];
        double pctOfFail = (totalFails > 0) ? (100.0 * cnt / totalFails) : 0.0;
        double pctOfTotal = (g_p1TotalTargetLinks > 0) ? (100.0 * cnt / g_p1TotalTargetLinks) : 0.0;
        ss << "  " << std::left << std::setw(38) << P1ReasonStrings[c] << " : "
           << std::right << std::setw(5) << cnt << " ("
           << std::setw(5) << std::fixed << std::setprecision(1) << pctOfFail << "% of fails | "
           << std::setw(5) << std::fixed << std::setprecision(1) << pctOfTotal << "% of all links)\n";
    }
    ss << "========================================================================================\n";

    // Distance Bracket Breakdown
    ss << "\n--- Distance Bracket Breakdown (0-10m, 10-20m, 20-30m, 30-40m, 40-50m) ---\n";
    ss << "Bracket   | Total | Success | CSMA Abort | RX Deafness | Preamble Coll | Interference | Low SINR | Fading\n";
    ss << "----------------------------------------------------------------------------------------------------------\n";
    double brackets[5][2] = {{0, 10}, {10, 20}, {20, 30}, {30, 40}, {40, 50}};
    for (int b = 0; b < 5; b++) {
        int bTotal = 0;
        int bCounts[NUM_P1_REASONS] = {0};
        for (const auto& rec : g_p1LinkRecords) {
            if (rec.distance >= brackets[b][0] && (b == 4 ? rec.distance <= brackets[b][1] : rec.distance < brackets[b][1])) {
                bTotal++;
                bCounts[rec.category]++;
            }
        }
        char bName[16];
        snprintf(bName, sizeof(bName), "%2.0f-%2.0fm", brackets[b][0], brackets[b][1]);
        ss << std::left << std::setw(9) << bName << " | "
           << std::right << std::setw(5) << bTotal << " | "
           << std::setw(7) << bCounts[REASON_SUCCESS] << " | "
           << std::setw(10) << bCounts[REASON_SENDER_CSMA_ABORT] << " | "
           << std::setw(11) << bCounts[REASON_RX_DEAFNESS_BUSY_TX] << " | "
           << std::setw(13) << bCounts[REASON_PREAMBLE_COLLISION_BUSY_RX] << " | "
           << std::setw(12) << bCounts[REASON_PAYLOAD_INTERFERENCE_CORRUPTION] << " | "
           << std::setw(8) << bCounts[REASON_PREAMBLE_LOW_SINR] << " | "
           << std::setw(6) << bCounts[REASON_OUT_OF_RANGE_OR_FADING] << "\n";
    }
    ss << "========================================================================================\n\n";

    std::cout << ss.str();

    // Write to report file
    std::ofstream rptFile("p1_ground_truth_report.txt");
    if (rptFile.is_open()) {
        rptFile << ss.str();
        rptFile.close();
    }

    // Write exact CSV
    std::ofstream csvFile("p1_exact_drop_reasons.csv");
    if (csvFile.is_open()) {
        csvFile << "Epoch,Receiver,Sender,Distance_m,Status,ExactReason\n";
        for (const auto& rec : g_p1LinkRecords) {
            csvFile << rec.epoch << "," << (int)rec.receiver << "," << (int)rec.sender << ","
                    << std::fixed << std::setprecision(2) << rec.distance << ","
                    << ((rec.category == REASON_SUCCESS) ? "SUCCESS" : "FAILED") << ","
                    << P1ReasonStrings[rec.category] << "\n";
        }
        csvFile.close();
        std::cout << "✅ Exact ground truth link data exported to p1_exact_drop_reasons.csv\n";
        std::cout << "✅ Ground truth summary report saved to p1_ground_truth_report.txt\n";
    }
}

void PrintPhase2GroundTruthReport() {
    std::stringstream ss;
    ss << "\n========================================================================================\n";
    ss << "       🔬 PHASE 2 PHYSICAL & MAC GROUND TRUTH ANALYSIS (Top-K within 50m) 🔬           \n";
    ss << "========================================================================================\n";
    ss << "Total Expected P2 Neighbor Links (Epochs x Top-K) : " << g_p2TotalTargetLinks << "\n";
    double succPct = (g_p2TotalTargetLinks > 0) ? (100.0 * g_p2ReasonCounts[P2_REASON_SUCCESS] / g_p2TotalTargetLinks) : 0;
    int totalFails = g_p2TotalTargetLinks - g_p2ReasonCounts[P2_REASON_SUCCESS];
    double failPct = 100.0 - succPct;
    ss << "  ✅ Successfully Received (Delivered)            : " << g_p2ReasonCounts[P2_REASON_SUCCESS] 
       << " (" << std::fixed << std::setprecision(1) << succPct << "%)\n";
    ss << "  ❌ Failed Link Receptions (Dropped/Missed)      : " << totalFails 
       << " (" << std::fixed << std::setprecision(1) << failPct << "%)\n";
    ss << "----------------------------------------------------------------------------------------\n";
    ss << "EXACT PHYSICAL ROOT CAUSE BREAKDOWN (Zero Estimation / Direct From Protocol Pipeline):\n";
    
    for (int c = 1; c < NUM_P2_REASONS; c++) {
        int cnt = g_p2ReasonCounts[c];
        double pctOfFail = (totalFails > 0) ? (100.0 * cnt / totalFails) : 0.0;
        double pctOfTotal = (g_p2TotalTargetLinks > 0) ? (100.0 * cnt / g_p2TotalTargetLinks) : 0.0;
        ss << "  " << std::left << std::setw(38) << P2ReasonStrings[c] << " : "
           << std::right << std::setw(5) << cnt << " ("
           << std::setw(5) << std::fixed << std::setprecision(1) << pctOfFail << "% of fails | "
           << std::setw(5) << std::fixed << std::setprecision(1) << pctOfTotal << "% of all links)\n";
    }
    ss << "========================================================================================\n";

    // Distance Bracket Breakdown
    ss << "\n--- Distance Bracket Breakdown (0-10m, 10-20m, 20-30m, 30-40m, 40-50m) ---\n";
    ss << "Bracket   | Total | Success | P1 Miss | TX Deaf | RX Deaf | Payload Drop | Preamble Drop | Ch Mismatch | Turnaround | CSMA Abort\n";
    ss << "----------------------------------------------------------------------------------------------------------------------------\n";
    double brackets[5][2] = {{0, 10}, {10, 20}, {20, 30}, {30, 40}, {40, 50}};
    for (int b = 0; b < 5; b++) {
        int bTotal = 0;
        int bCounts[NUM_P2_REASONS] = {0};
        for (const auto& rec : g_p2LinkRecords) {
            if (rec.distance >= brackets[b][0] && (b == 4 ? rec.distance <= brackets[b][1] : rec.distance < brackets[b][1])) {
                bTotal++;
                bCounts[rec.category]++;
            }
        }
        char bName[16];
        snprintf(bName, sizeof(bName), "%2.0f-%2.0fm", brackets[b][0], brackets[b][1]);
        ss << std::left << std::setw(9) << bName << " | "
           << std::right << std::setw(5) << bTotal << " | "
           << std::setw(7) << bCounts[P2_REASON_SUCCESS] << " | "
           << std::setw(7) << bCounts[P2_REASON_P1_DISCOVERY_MISS] << " | "
           << std::setw(7) << bCounts[P2_REASON_TX_DEAFNESS_SAME_SLOT] << " | "
           << std::setw(7) << bCounts[P2_REASON_RX_DEAFNESS_SLOT_CONFLICT] << " | "
           << std::setw(12) << bCounts[P2_REASON_PAYLOAD_INTERFERENCE_DROP] << " | "
           << std::setw(13) << bCounts[P2_REASON_PREAMBLE_COLLISION_OR_LOW_SINR] << " | "
           << std::setw(11) << bCounts[P2_REASON_RECEIVER_CHANNEL_MISMATCH] << " | "
           << std::setw(10) << bCounts[P2_REASON_RADIO_TURNAROUND_BUSY] << " | "
           << std::setw(10) << bCounts[P2_REASON_SENDER_CSMA_ABORT] << "\n";
    }
    ss << "============================================================================================================================\n\n";

    std::cout << ss.str();

    // Write to report file
    std::ofstream rptFile("p2_ground_truth_report.txt");
    if (rptFile.is_open()) {
        rptFile << ss.str();
        rptFile.close();
    }

    // Write exact CSV
    std::ofstream csvFile("p2_exact_drop_reasons.csv");
    if (csvFile.is_open()) {
        csvFile << "Epoch,Receiver,Sender,Distance_m,Status,ExactReason\n";
        for (const auto& rec : g_p2LinkRecords) {
            csvFile << rec.epoch << "," << (int)rec.receiver << "," << (int)rec.sender << ","
                    << std::fixed << std::setprecision(2) << rec.distance << ","
                    << ((rec.category == P2_REASON_SUCCESS) ? "SUCCESS" : "FAILED") << ","
                    << P2ReasonStrings[rec.category] << "\n";
        }
        csvFile.close();
        std::cout << "✅ Exact Phase 2 ground truth link data exported to p2_exact_drop_reasons.csv\n";
        std::cout << "✅ Phase 2 ground truth summary report saved to p2_ground_truth_report.txt\n";
    }
}

int main(int argc, char *argv[]) {
    g_runLogFile.open("run.log");
    if (g_runLogFile.is_open()) {
        g_originalCoutBuffer = std::cout.rdbuf();
        std::cout.rdbuf(g_runLogFile.rdbuf());
    }

    double spaceSize = 300.0;
    double spaceZ = 100.0;
    int numNodes = 75;
    double nodeSpeed = 10.0; // UAV mobility speed in m/s (default: 10 m/s ~ 36 km/h, 0 for static hover)
    bool autoPush = false;

    CommandLine cmd;
    cmd.AddValue("p2TxPower", "Phase 2 TX Power in dBm (e.g., -9, -4, 0)", g_p2TxPower);
    cmd.AddValue("p1TxPower", "Phase 1 TX Power in dBm (e.g., 0, 1, 3)", g_p1TxPower);
    cmd.AddValue("p1Duration", "Phase 1 duration in ms (e.g., 10 to 40)", g_p1DurationMs);
    cmd.AddValue("p1AvoidDist", "RX Deafness defense distance in meters", g_p1AvoidDist);
    cmd.AddValue("p1AvoidRssi", "Defense RSSI threshold in dBm (-106 to -90)", g_p1AvoidRssi);
    cmd.AddValue("enableDefense", "Enable spatial slot defense (default true)", g_enableDefense);
    cmd.AddValue("numChannels", "Number of Phase 2 data channels (e.g., 0 to 10)", g_numDataChannels);
    cmd.AddValue("numSlots", "Number of Phase 2 data slots (e.g., 5 to 20)", g_numDataSlots);
    cmd.AddValue("numNodes", "Number of UAV nodes in swarm (e.g., 50, 100)", numNodes);
    cmd.AddValue("nodeSpeed", "Speed of UAVs in m/s (default 10.0 m/s, 0 for static hover)", nodeSpeed);
    cmd.AddValue("spaceSize", "Side length of 3D box (X and Y) in meters", spaceSize);
    cmd.AddValue("spaceZ", "Height of 3D box in meters", spaceZ);
    cmd.AddValue("autoPush", "Auto git push results", autoPush);
    cmd.Parse(argc, argv);

    if (g_numDataSlots > MAX_DATA_SLOTS) {
        std::cerr << "Warning: numSlots (" << g_numDataSlots << ") exceeds MAX_DATA_SLOTS (" << MAX_DATA_SLOTS << "), clamping to " << MAX_DATA_SLOTS << std::endl;
        g_numDataSlots = MAX_DATA_SLOTS;
    }

    g_phase1DurationUs = g_p1DurationMs * 1000.0;
    g_cycleMs = (g_phase1DurationUs + GAP_US + g_numDataSlots * DATA_SLOT_US) / 1000.0;

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
    
    // 3D Random Box Topology (spaceSize x spaceSize x spaceZ)
    Ptr<RandomBoxPositionAllocator> alloc = CreateObject<RandomBoxPositionAllocator>();
    Ptr<UniformRandomVariable> xVar = CreateObject<UniformRandomVariable>();
    xVar->SetAttribute("Min", DoubleValue(0.0));
    xVar->SetAttribute("Max", DoubleValue(spaceSize));
    alloc->SetX(xVar);
    
    Ptr<UniformRandomVariable> yVar = CreateObject<UniformRandomVariable>();
    yVar->SetAttribute("Min", DoubleValue(0.0));
    yVar->SetAttribute("Max", DoubleValue(spaceSize));
    alloc->SetY(yVar);
    
    Ptr<UniformRandomVariable> zVar = CreateObject<UniformRandomVariable>();
    zVar->SetAttribute("Min", DoubleValue(10.0));
    zVar->SetAttribute("Max", DoubleValue(10.0 + spaceZ)); // height difference
    alloc->SetZ(zVar);
    
    mobility.SetPositionAllocator(alloc);
    if (nodeSpeed > 0.0) {
        std::stringstream ssSpeed;
        ssSpeed << "ns3::UniformRandomVariable[Min=" << (nodeSpeed * 0.8) << "|Max=" << (nodeSpeed * 1.2) << "]";
        mobility.SetMobilityModel("ns3::RandomWaypointMobilityModel",
                                  "Speed", StringValue(ssSpeed.str()),
                                  "Pause", StringValue("ns3::ConstantRandomVariable[Constant=0.0]"),
                                  "PositionAllocator", PointerValue(alloc));
    } else {
        mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    }
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
    
    double globalDiscRatio = (g_totalExpectedTopKxEpochs > 0) ? (double)g_totalReceivedDiscoveryTopK / g_totalExpectedTopKxEpochs : 0;
    double globalBcnRatio = (g_totalExpectedTopKxEpochs > 0) ? (double)g_totalReceivedBeaconTopK / g_totalExpectedTopKxEpochs : 0;
    double globalAvgDiscIat = (g_totalCountDiscoveryIatTopK > 0) ? (g_totalSumDiscoveryIatTopK / g_totalCountDiscoveryIatTopK) : 0;
    double globalMeanAoI = (g_totalCountAoITopK > 0) ? (g_totalSumAoITopK / g_totalCountAoITopK) : 0;
    
    std::stringstream ss;
    ss << "\n=================================================\n";
    ss << "          GLOBAL NETWORK METRICS (1.0s)          \n";
    ss << "=================================================\n";
    ss << "Discovery Message Reception Ratio: " << std::fixed << std::setprecision(1) << globalDiscRatio * 100 << "%\n";
    ss << "Beacon Packet Reception Ratio   : " << std::fixed << std::setprecision(1) << globalBcnRatio * 100 << "%\n";
    ss << "Avg Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << globalAvgDiscIat << " ms\n";
    ss << "Max Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << g_globalMaxDiscoveryIatTopK << " ms\n";
    ss << "Mean Beacon Packet AoI (Top-K)  : " << std::fixed << std::setprecision(1) << globalMeanAoI << " ms\n";
    ss << "Max Beacon Packet AoI (Top-K)   : " << std::fixed << std::setprecision(1) << g_globalMaxAoITopK << " ms\n";
    ss << "-------------------------------------------------\n";
    ss << "=== PHASE 2 CONTENTION & DEAFNESS METRICS ===\n";
    ss << "Total Scheduled Top-K Neighbor Beacons: " << g_totalExpectedRx << "\n";
    ss << "TX Deafness (Same slot as TX)         : " << g_txDeafnessCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_txDeafnessCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "RX Deafness (Slot conflict)           : " << g_rxDeafnessCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_rxDeafnessCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "Resource Collision (Same S+C)         : " << g_resourceCollisionCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_resourceCollisionCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "=================================================\n\n";

    if (g_originalCoutBuffer) {
        std::cout.rdbuf(g_originalCoutBuffer);
    }
    
    std::cout << g_singleDroneReport.str() << "\n";
    std::cout << ss.str();

    PrintGroundTruthReport();
    PrintPhase2GroundTruthReport();
    
    if (g_runLogFile.is_open()) {
        g_runLogFile << g_singleDroneReport.str() << "\n";
        g_runLogFile << ss.str();
        g_runLogFile.close();
        if (autoPush) {
            int ret = system("git add run.log p1_exact_drop_reasons.csv p1_ground_truth_report.txt p2_exact_drop_reasons.csv p2_ground_truth_report.txt && git commit -m 'Auto upload Phase 1 & Phase 2 ground truth results' && git push origin main");
            if (ret != 0) {
                std::cerr << "Note: system git push returned non-zero (you can manually commit & push)." << std::endl;
            } else {
                std::cout << "Results successfully uploaded to GitHub!" << std::endl;
            }
        }
    }

    Simulator::Destroy();

    return 0;
}
