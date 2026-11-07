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
#include <cmath>
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
double g_simTime = 10.0;            // Total simulation duration in seconds (default 10.0s)
const double GAP_US = 1000.0; 
const int MAX_DATA_SLOTS = 32;            // Maximum supported slots (up to 31 in 5-bit encoding)
const int MAX_DATA_CHANNELS = 16;        // Maximum supported data channels
const double DATA_SLOT_US = 2500.0; 

// Sidelink S-SPS (Semi-Persistent Scheduling) for Phase 1
bool g_enableP1Sidelink = false; // Phase 1 Sidelink S-SPS mode switch (default: false for baseline compatibility)
double g_p1SlotUs = 100.0;       // Phase 1 Sidelink slot duration in microseconds (default 100 us -> 98 slots in 10ms)
double g_p1CcaThresholdDbm = -96.58; // Phase 1 CSMA CCA Energy Detection Threshold in dBm (default: -96.58, standard 802.15.4)

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

// Dynamic Real-Time Top-5 Metrics (Per-Cycle Moment Evaluation Across 0-10s)
static double g_dynSumDiscoveryIat = 0.0;
static int g_dynCountDiscoveryIat = 0;
static double g_dynMaxDiscoveryIat = 0.0;
static std::map<std::pair<uint8_t, uint8_t>, double> g_lastDiscoveryRxTime;

static double g_dynSumAoI = 0.0;
static int g_dynCountAoI = 0;
static double g_dynMaxAoI = 0.0;
static std::map<std::pair<uint8_t, uint8_t>, double> g_lastBeaconRxGenTime;

// Drone 0 real-time top-5 tracking for sample drone report
static std::map<uint8_t, int> g_d0Top5Expected;
static std::map<uint8_t, int> g_d0Top5DiscRx;
static std::map<uint8_t, int> g_d0Top5BcnRx;
static std::map<uint8_t, double> g_d0SumDiscIat;
static std::map<uint8_t, int> g_d0CountDiscIat;
static std::map<uint8_t, double> g_d0MaxDiscIat;
static std::map<uint8_t, double> g_d0SumAoI;
static std::map<uint8_t, int> g_d0CountAoI;
static std::map<uint8_t, double> g_d0MaxAoI;
static std::map<uint8_t, double> g_d0LastDist;

static int g_totalTopologyMatchCount = 0;
static int g_totalTopologyCheckCount = 0;
static std::stringstream g_singleDroneReport;

// Phase 1 專用統計
static int g_p1TxAttempts = 0;
static int g_p1TxAbort = 0;
static int g_p1TxSuccess = 0;
static int g_p1RxSuccess = 0;
static int g_totalCaptureEvents = 0;

// 空間拓撲與 50m 鄰居密度統計
static double g_spaceSize = 200.0;
static double g_spaceZ = 80.0;
static double g_sumNeighborsIn50m = 0.0;
static int g_countNeighborsIn50m = 0;
static int g_dronesWithGe5Neighbors = 0;

// --- Phase 1 Ground Truth Physical Drop Tracking ---
enum P1DropCategory {
    REASON_SUCCESS = 0,
    REASON_SENDER_CSMA_ABORT,
    REASON_RX_DEAFNESS_BUSY_TX,
    REASON_PREAMBLE_COLLISION_BUSY_RX,
    REASON_PREAMBLE_LOW_SINR,
    REASON_RADIO_TURNAROUND_BUSY,
    REASON_PAYLOAD_INTERFERENCE_CORRUPTION,
    NUM_P1_REASONS
};

static const char* P1ReasonStrings[] = {
    "SUCCESS",
    "SENDER_CSMA_ABORT",
    "RX_DEAFNESS_BUSY_TX",
    "PREAMBLE_COLLISION_BUSY_RX",
    "PREAMBLE_LOW_SINR",
    "RADIO_TURNAROUND_BUSY",
    "PAYLOAD_INTERFERENCE_CORRUPTION"
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
    double prx_dbm;
    double interf_dbm;
    double sinr_db;
    int coChannelCount;
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
    P2_REASON_RECEIVER_CHANNEL_MISMATCH,     // Receiver radio was on a different channel
    P2_REASON_RADIO_TURNAROUND_BUSY,         // Receiver was on correct channel but in turnaround/transient busy
    P2_REASON_SENDER_CSMA_ABORT,             // Sender aborted transmission due to busy channel at slot start
    P2_REASON_PREAMBLE_COLLISION_BUSY_RX,    // Receiver antenna was already locked onto another packet
    P2_REASON_PREAMBLE_LOW_SINR,             // Preamble arrived, but SINR <= -5 dB (co-channel interference/noise)
    P2_REASON_PAYLOAD_INTERFERENCE_DROP,     // Preamble locked, but mid-flight packet corrupted by interference
    NUM_P2_REASONS
};

static const char* P2ReasonStrings[] = {
    "SUCCESS",
    "P1_DISCOVERY_MISS",
    "TX_DEAFNESS_SAME_SLOT",
    "RX_DEAFNESS_SLOT_CONFLICT",
    "RECEIVER_CHANNEL_MISMATCH",
    "RADIO_TURNAROUND_BUSY",
    "SENDER_CSMA_ABORT",
    "PREAMBLE_COLLISION_BUSY_RX",
    "PREAMBLE_LOW_SINR",
    "PAYLOAD_INTERFERENCE_DROP"
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
    double prx_dbm;
    double interf_dbm;
    double sinr_db;
    int coChannelCount;
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
static std::map<uint32_t, std::map<uint8_t, int>> g_p1DroneClaimedSlot;
static std::map<uint32_t, std::map<uint8_t, std::set<uint8_t>>> g_p2DiscoveredInP1;
static std::map<uint32_t, std::map<uint8_t, std::map<int, ScheduleSlot::Action>>> g_p2SlotAction;
static std::map<uint32_t, std::map<uint8_t, std::map<int, uint8_t>>> g_p2SlotTarget;

class SwarmSchedulerApp : public Application {
public:
    SwarmSchedulerApp() : m_epoch(0), m_myClaimedSlot(0), m_myClaimedChannel(0), m_topologyMatchCount(0), m_topologyCheckCount(0), m_epochStartTime(0), m_p1ClaimedSlot(-1), m_p1ReselCounter(0), m_p1ConflictOccurred(false) {}

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
        m_csma = csma;
        m_device->GetPhy()->SetPlmeCcaConfirmCallback(MakeCallback(&SwarmSchedulerApp::CustomPlmeCcaConfirm, this));

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
        phy->TraceConnectWithoutContext("PhyRxCapture", MakeCallback(&SwarmSchedulerApp::NotifyPhyRxCapture, this));
        phy->TraceConnectWithoutContext("PhyTxBegin", MakeCallback(&SwarmSchedulerApp::NotifyPhyTxBegin, this));

        Simulator::Schedule(Seconds(g_simTime - 0.001), &SwarmSchedulerApp::PrintMetrics, this);
    }

    void CustomPlmeCcaConfirm(PhyEnumeration status) {
        if (g_enableP1Sidelink && g_droneCurrentChannel[m_id] == BROADCAST_CHANNEL) {
            // Sidelink S-SPS mode: Transmit directly in own slot without CSMA CCA backoff or abort!
            status = IEEE_802_15_4_PHY_IDLE;
        } else if (g_droneCurrentChannel[m_id] == BROADCAST_CHANNEL && g_p1CcaThresholdDbm > -900.0) {
            if (status == IEEE_802_15_4_PHY_IDLE) {
                double currentPsdDbm = m_device->GetPhy()->GetCurrentSignalPsd();
                if (currentPsdDbm >= g_p1CcaThresholdDbm) {
                    status = IEEE_802_15_4_PHY_BUSY;
                }
            }
        }
        if (m_csma) {
            m_csma->PlmeCcaConfirm(status);
        }
    }

    void NotifyPhyTrxStateChange(Time time, PhyEnumeration oldState, PhyEnumeration newState) {
        g_dronePhyState[m_id] = newState;
    }

    void NotifyPhyRxBegin(Ptr<const Packet> p) {
        uint64_t uid = p->GetUid();
        g_droneReceivingUid[m_id] = uid;

        if (g_enableP1Sidelink && g_droneCurrentChannel[m_id] == BROADCAST_CHANNEL) {
            double timeInP1Us = (Simulator::Now().GetMilliSeconds() - m_epochStartTime) * 1000.0;
            int numP1Slots = std::max(1, (int)((g_phase1DurationUs - 250.0) / g_p1SlotUs) + 1);
            int slotIdx = (int)(timeInP1Us / g_p1SlotUs);
            if (slotIdx >= 0 && slotIdx < numP1Slots) {
                m_p1OccupiedSlotsThisEpoch.insert(slotIdx);
                if ((int)m_slotSensedEnergy.size() != numP1Slots) {
                    m_slotSensedEnergy.assign(numP1Slots, 0.0);
                    m_slotPacketCount.assign(numP1Slots, 0);
                }
                m_slotPacketCount[slotIdx]++;
                double currentPsdDbm = m_device->GetPhy()->GetCurrentSignalPsd();
                double powerMw = std::pow(10.0, currentPsdDbm / 10.0);
                m_slotSensedEnergy[slotIdx] += powerMw;
            }
        }

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
            double now = Simulator::Now().GetMilliSeconds();
            if (g_droneReceivingUid[m_id] == uid) {
                g_p1RxDropEvent[{epoch, sender, m_id}] = REASON_PAYLOAD_INTERFERENCE_CORRUPTION;
                g_droneReceivingUid[m_id] = 0;
                std::cout << "[P1_PAYLOAD_DROP] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid << std::endl;
            } else {
                if (g_dronePhyState[m_id] == IEEE_802_15_4_PHY_BUSY_RX) {
                    g_p1RxDropEvent[{epoch, sender, m_id}] = REASON_PREAMBLE_COLLISION_BUSY_RX;
                    std::cout << "[P1_PREAMBLE_COLLISION] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid
                              << " | Antenna busy receiving Drone " << (int)g_droneReceivingUid[m_id] << std::endl;
                } else if (g_dronePhyState[m_id] == IEEE_802_15_4_PHY_TRX_OFF) {
                    g_p1RxDropEvent[{epoch, sender, m_id}] = REASON_RADIO_TURNAROUND_BUSY;
                    std::cout << "[P1_RADIO_OFF] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid
                              << " | Transceiver in TRX_OFF state" << std::endl;
                } else {
                    g_p1RxDropEvent[{epoch, sender, m_id}] = REASON_PREAMBLE_LOW_SINR;
                    std::cout << "[P1_PREAMBLE_LOW_SINR] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid
                              << " | Preamble SINR <= -5 dB threshold" << std::endl;
                }
            }
        }

        auto it2 = g_p2PacketsMeta.find(uid);
        if (it2 != g_p2PacketsMeta.end()) {
            uint8_t sender = it2->second.senderId;
            uint32_t epoch = it2->second.epoch;
            double now = Simulator::Now().GetMilliSeconds();
            if (g_droneReceivingUid[m_id] == uid) {
                g_p2RxDropEvent[{epoch, sender, m_id}] = P2_REASON_PAYLOAD_INTERFERENCE_DROP;
                g_droneReceivingUid[m_id] = 0;
                std::cout << "[P2_PAYLOAD_DROP] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid << std::endl;
            } else {
                if (g_dronePhyState[m_id] == IEEE_802_15_4_PHY_BUSY_RX) {
                    g_p2RxDropEvent[{epoch, sender, m_id}] = P2_REASON_PREAMBLE_COLLISION_BUSY_RX;
                    std::cout << "[P2_PREAMBLE_COLLISION] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid
                              << " | Antenna already busy receiving Drone " << (int)g_droneReceivingUid[m_id] << std::endl;
                } else {
                    g_p2RxDropEvent[{epoch, sender, m_id}] = P2_REASON_PREAMBLE_LOW_SINR;
                    std::cout << "[P2_PREAMBLE_LOW_SINR] Time: " << now << "ms, Rx: " << (int)m_id << ", Tx: " << (int)sender << ", Uid: " << uid
                              << " | Preamble SINR <= -5 dB threshold" << std::endl;
                }
            }
        }
    }

    void NotifyPhyRxCapture(Ptr<const Packet> capP, Ptr<const Packet> preP) {
        g_totalCaptureEvents++;
        uint64_t capUid = capP->GetUid();
        uint64_t preUid = preP->GetUid();
        double now = Simulator::Now().GetMilliSeconds();
        uint8_t capSender = 255;
        uint8_t preSender = 255;
        auto itCap = g_p1PacketsMeta.find(capUid);
        if (itCap != g_p1PacketsMeta.end()) capSender = itCap->second.senderId;
        auto itPre = g_p1PacketsMeta.find(preUid);
        if (itPre != g_p1PacketsMeta.end()) preSender = itPre->second.senderId;
        std::cout << "[P1_CAPTURE] Time: " << now << "ms, Rx: " << (int)m_id
                  << " CAPTURED Tx: " << (int)capSender << " (Uid: " << capUid << ")"
                  << ", PREEMPTED Tx: " << (int)preSender << " (Uid: " << preUid << ")" << std::endl;
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

    void AddCapturedNeighbor(uint8_t senderId, int8_t rssi, uint32_t epoch, uint8_t claimedSlot, uint8_t claimedCh) {
        bool exists = false;
        for (const auto& n : m_monitorList) {
            if (n.id == senderId) {
                exists = true;
                break;
            }
        }
        if (!exists) {
            m_monitorList.push_back({senderId, rssi, epoch, claimedSlot, claimedCh});
        }
    }

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

    // Phase 1 Sidelink S-SPS variables
    int m_p1ClaimedSlot;
    int m_p1ReselCounter;
    bool m_p1ConflictOccurred;
    std::set<int> m_p1OccupiedSlotsThisEpoch;
    std::vector<double> m_slotSensedEnergy;
    std::vector<int> m_slotPacketCount;
    Ptr<LrWpanCsmaCa> m_csma;

    void SwitchChannelAndPower(uint8_t ch, int8_t txPowerDbm) {
        g_droneCurrentChannel[m_id] = ch;
        Ptr<PhyPibAttributes> attrs = Create<PhyPibAttributes>();
        attrs->phyCurrentChannel = ch;
        // Pack txPowerDbm into 6-bit two's complement for phyTransmitPower
        attrs->phyTransmitPower = txPowerDbm & 0x3F;
        
        m_device->GetMac()->GetPhy()->PlmeSetAttributeRequest(phyCurrentChannel, attrs);
        m_device->GetMac()->GetPhy()->PlmeSetAttributeRequest(phyTransmitPower, attrs);
        m_device->GetMac()->GetPhy()->PlmeSetTRXStateRequest(IEEE_802_15_4_PHY_RX_ON);
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
        
        if (!g_enableP1Sidelink) {
            Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
            double maxDelayUs = std::max(500.0, g_phase1DurationUs - 500.0);
            double randomDelayUs = uv->GetValue(100.0, maxDelayUs);
            Simulator::Schedule(MicroSeconds(randomDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        } else {
            // Sidelink S-SPS mode for Phase 1
            int numP1Slots = std::max(1, (int)((g_phase1DurationUs - 250.0) / g_p1SlotUs) + 1);

            // Ensure slot statistics vectors are properly sized
            if ((int)m_slotSensedEnergy.size() != numP1Slots) {
                m_slotSensedEnergy.assign(numP1Slots, 0.0);
                m_slotPacketCount.assign(numP1Slots, 0);
            }

            Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();

            // Initial slot selection or reselection counter expired
            if (m_p1ClaimedSlot < 0 || m_p1ClaimedSlot >= numP1Slots) {
                // First time: pick any slot randomly
                m_p1ClaimedSlot = uv->GetInteger(0, numP1Slots - 1);
                // Draw initial reselection counter: uniform [5, 15] cycles
                m_p1ReselCounter = uv->GetInteger(5, 15);
            } else if (m_p1ReselCounter <= 0) {
                // Reselection period reached: pick from the other slots with lowest sensed signal strength/energy
                std::vector<std::pair<double, int>> candidateSlots;
                for (int s = 0; s < numP1Slots; s++) {
                    if (s == m_p1ClaimedSlot) continue; // select from other slots
                    candidateSlots.push_back({m_slotSensedEnergy[s], s});
                }
                
                if (!candidateSlots.empty()) {
                    std::sort(candidateSlots.begin(), candidateSlots.end());
                    // Candidate pool: lowest 25% of energy slots (at least 1)
                    int poolSize = std::max(1, (int)(candidateSlots.size() * 0.25));
                    if (poolSize > (int)candidateSlots.size()) poolSize = candidateSlots.size();
                    int chosenIdx = uv->GetInteger(0, poolSize - 1);
                    m_p1ClaimedSlot = candidateSlots[chosenIdx].second;
                }
                
                // Draw new reselection counter: uniform [5, 15] cycles
                m_p1ReselCounter = uv->GetInteger(5, 15);

                // Decay sensed energy history for the next observation window
                for (int s = 0; s < numP1Slots; s++) {
                    m_slotSensedEnergy[s] *= 0.5;
                    m_slotPacketCount[s] = (int)(m_slotPacketCount[s] * 0.5);
                }
            }
            m_p1OccupiedSlotsThisEpoch.clear();

            // Decrement reselection counter for this cycle
            m_p1ReselCounter--;

            // Record claimed slot in global registry for Phase 1 Sidelink
            g_p1DroneClaimedSlot[m_epoch][m_id] = m_p1ClaimedSlot;

            // Micro-jitter inside the claimed slot (0 to 15 us) for physical-layer tie-breaking
            double maxJitterUs = std::min(15.0, g_p1SlotUs * 0.05);
            double jitterUs = uv->GetValue(0.0, maxJitterUs);
            double txDelayUs = m_p1ClaimedSlot * g_p1SlotUs + jitterUs;

            Simulator::Schedule(MicroSeconds(txDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        }
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
                
                if (g_enableP1Sidelink) {
                    m_p1ConflictOccurred = true;
                    std::cout << "[P1_SIDELINK_CONFLICT] Time: " << now << "ms, Drone: " << myId 
                              << " lost slot " << m_p1ClaimedSlot << " (sensed busy). Slower node yielding!" << std::endl;
                    
                    // Attempt immediate migration to a later free slot in current epoch
                    double availP1Us = std::max(500.0, g_phase1DurationUs - 500.0);
                    int numP1Slots = std::max(1, (int)(availP1Us / g_p1SlotUs));
                    double timeInP1Us = (now - m_epochStartTime) * 1000.0;
                    int currentSlot = (int)(timeInP1Us / g_p1SlotUs);
                    
                    std::vector<int> laterFreeSlots;
                    for (int s = currentSlot + 1; s < numP1Slots; s++) {
                        if (m_p1OccupiedSlotsThisEpoch.find(s) == m_p1OccupiedSlotsThisEpoch.end()) {
                            laterFreeSlots.push_back(s);
                        }
                    }
                    if (!laterFreeSlots.empty()) {
                        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
                        int idx = uv->GetInteger(0, laterFreeSlots.size() - 1);
                        m_p1ClaimedSlot = laterFreeSlots[idx];
                        m_p1ConflictOccurred = false;
                        
                        double nextTxUs = m_p1ClaimedSlot * g_p1SlotUs + uv->GetValue(0, 50.0);
                        double delayUs = nextTxUs - timeInP1Us;
                        if (delayUs > 50.0) {
                            std::cout << "[P1_SIDELINK_MIGRATE] Drone " << myId << " migrating to later slot " 
                                      << m_p1ClaimedSlot << " in current epoch!" << std::endl;
                            Simulator::Schedule(MicroSeconds(delayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
                        }
                    }
                } else {
                    // 如果還在 Phase 1 的有效時間內 (保留最後 0.5ms 緩衝)，則安排重新決策
                    if (now < m_epochStartTime + g_p1DurationMs - 0.5) {
                        // 隨機等待 0.1 ~ 0.5 毫秒，讓對方的情報傳達過來，也錯開重試時間
                        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
                        double retryDelay = uv->GetValue(0.1, 0.5);
                        Simulator::Schedule(MilliSeconds(retryDelay), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
                    }
                }
            } else if (params.m_status == MacStatus::SUCCESS) {
                g_p1TxSuccess++;
                g_p1TxSuccessInEpoch[m_epoch][myId]++;
                if (g_enableP1Sidelink) {
                    m_p1ConflictOccurred = false; // Successfully retained
                }
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
            if (g_enableP1Sidelink) {
                double timeInP1Us = (now - m_epochStartTime) * 1000.0;
                if (timeInP1Us >= 0 && timeInP1Us < g_phase1DurationUs) {
                    int slotIdx = (int)(timeInP1Us / g_p1SlotUs);
                    m_p1OccupiedSlotsThisEpoch.insert(slotIdx);
                }
            }
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

    void ProcessSidelinkSlottedCapture(uint32_t epoch) {
        if (!g_enableP1Sidelink) return;

        uint32_t numNodes = NodeList::GetNNodes();
        int numP1Slots = std::max(1, (int)((g_phase1DurationUs - 250.0) / g_p1SlotUs) + 1);

        // Group transmitters by their claimed slot in this epoch
        std::map<int, std::vector<uint8_t>> transmittersInSlot;
        auto itEp = g_p1DroneClaimedSlot.find(epoch);
        if (itEp != g_p1DroneClaimedSlot.end()) {
            for (const auto& kv : itEp->second) {
                uint8_t droneId = kv.first;
                int slot = kv.second;
                if (slot >= 0 && slot < numP1Slots) {
                    transmittersInSlot[slot].push_back(droneId);
                }
            }
        }

        double noiseLinear = std::pow(10.0, (-106.58 - 30.0) / 10.0);

        // For every receiver R and every slot s
        for (uint32_t r = 0; r < numNodes; r++) {
            Ptr<MobilityModel> rMob = NodeList::GetNode(r)->GetObject<MobilityModel>();
            if (!rMob) continue;
            Ptr<SwarmSchedulerApp> rApp = DynamicCast<SwarmSchedulerApp>(NodeList::GetNode(r)->GetApplication(0));

            for (const auto& kv : transmittersInSlot) {
                const auto& senders = kv.second;
                if (senders.empty()) continue;

                // Check if receiver R was transmitting in this slot (Half-Duplex)
                bool rTransmittingInSlot = false;
                for (uint8_t sId : senders) {
                    if (sId == r) {
                        rTransmittingInSlot = true;
                        break;
                    }
                }
                if (rTransmittingInSlot) {
                    continue; // R cannot receive any packet in this slot
                }

                // Find closest transmitter to R among all senders in this slot
                uint8_t bestSender = 255;
                double minDist = 1e9;
                double bestPrxLinear = 0.0;
                double bestPrxDbm = -999.0;

                std::vector<std::pair<uint8_t, double>> senderPowers;
                for (uint8_t sId : senders) {
                    if (sId == r) continue;
                    Ptr<MobilityModel> sMob = NodeList::GetNode(sId)->GetObject<MobilityModel>();
                    if (!sMob) continue;
                    double d = rMob->GetDistanceFrom(sMob);
                    double prxDbm = g_p1TxPower - 46.6777 - 30.0 * std::log10(std::max(0.1, d));
                    double prxLinear = std::pow(10.0, (prxDbm - 30.0) / 10.0);
                    senderPowers.push_back({sId, prxLinear});

                    if (d < minDist) {
                        minDist = d;
                        bestSender = sId;
                        bestPrxLinear = prxLinear;
                        bestPrxDbm = prxDbm;
                    }
                }

                if (bestSender == 255) continue;

                // Calculate interference from all OTHER senders in the same slot
                double interfLinear = 0.0;
                for (const auto& sp : senderPowers) {
                    if (sp.first != bestSender) {
                        interfLinear += sp.second;
                    }
                }

                // SINR calculation
                double sinr = bestPrxLinear / (interfLinear + noiseLinear);
                double sinrDb = 10.0 * std::log10(sinr);

                // Capture threshold: standard IEEE 802.15.4 demodulation threshold (-5.0 dB)
                if (sinrDb >= -5.0) {
                    // Receiver R captures bestSender!
                    bool alreadyHeard = (g_p1ReceivedInEpoch[epoch][r].count(bestSender) > 0);
                    if (!alreadyHeard) {
                        g_p1ReceivedInEpoch[epoch][r].insert(bestSender);
                        g_p2DiscoveredInP1[epoch][r].insert(bestSender);
                        g_totalCaptureEvents++;

                        uint8_t claimedSlot = 0;
                        uint8_t claimedCh = 0;
                        auto itSlot = g_droneClaimedSlot.find(epoch);
                        if (itSlot != g_droneClaimedSlot.end()) {
                            auto itS = itSlot->second.find(bestSender);
                            if (itS != itSlot->second.end()) claimedSlot = itS->second;
                        }
                        auto itCh = g_droneClaimedChannel.find(epoch);
                        if (itCh != g_droneClaimedChannel.end()) {
                            auto itC = itCh->second.find(bestSender);
                            if (itC != itCh->second.end()) claimedCh = itC->second;
                        }

                        int8_t rssi = (int8_t)std::round(bestPrxDbm);

                        if (rApp) {
                            rApp->AddCapturedNeighbor(bestSender, rssi, epoch, claimedSlot, claimedCh);
                        }
                    }
                }
            }
        }
    }

    void EvaluatePhase1Epoch(uint32_t epoch) {
        if (g_enableP1Sidelink) {
            ProcessSidelinkSlottedCapture(epoch);
        }
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

            // Record true 50m neighbor density
            g_sumNeighborsIn50m += dists.size();
            g_countNeighborsIn50m++;
            if (dists.size() >= 5) {
                g_dronesWithGe5Neighbors++;
            }

            std::sort(dists.begin(), dists.end(), [](const auto& a, const auto& b) {
                return a.second < b.second;
            });

            int topK = std::min(K_CLOSEST, (int)dists.size());
            for (int i = 0; i < topK; i++) {
                uint8_t sender = dists[i].first;
                double dist = dists[i].second;

                // Sender's TX power in Phase 1 is g_p1TxPower (default 0 dBm)
                double sPrxDbm = g_p1TxPower - 46.6777 - 30.0 * std::log10(std::max(0.1, dist));

                // Find sender's transmitted UID and transmission start time
                uint64_t txUid = 0;
                double sTxTime = 0.0;
                auto uidsIt = g_p1TxUidsInEpoch.find({epoch, sender});
                if (uidsIt != g_p1TxUidsInEpoch.end() && !uidsIt->second.empty()) {
                    txUid = uidsIt->second.back();
                    auto metaIt = g_p1PacketsMeta.find(txUid);
                    if (metaIt != g_p1PacketsMeta.end()) {
                        sTxTime = metaIt->second.txStartTime;
                    }
                }

                // Check other concurrent transmissions during sender's mini-beacon (~0.384 ms window)
                double interfLinear = 0.0;
                int coChannelCount = 0;
                if (txUid != 0) {
                    for (uint32_t other = 0; other < numNodes; other++) {
                        if (other == sender || other == r) continue;
                        auto otherUidsIt = g_p1TxUidsInEpoch.find({epoch, (uint8_t)other});
                        if (otherUidsIt != g_p1TxUidsInEpoch.end() && !otherUidsIt->second.empty()) {
                            uint64_t oUid = otherUidsIt->second.back();
                            auto oMetaIt = g_p1PacketsMeta.find(oUid);
                            if (oMetaIt != g_p1PacketsMeta.end()) {
                                double diff = std::abs(oMetaIt->second.txStartTime - sTxTime);
                                if (diff < 0.25) { // Concurrent transmission on Broadcast Channel 11 (2 Mbps: ~244us air time)
                                    Ptr<MobilityModel> otherMob = NodeList::GetNode(other)->GetObject<MobilityModel>();
                                    double otherDist = rMob->GetDistanceFrom(otherMob);
                                    double otherPrxDbm = g_p1TxPower - 46.6777 - 30.0 * std::log10(std::max(0.1, otherDist));
                                    interfLinear += std::pow(10.0, (otherPrxDbm - 30.0) / 10.0);
                                    coChannelCount++;
                                }
                            }
                        }
                    }
                }

                double noiseLinear = std::pow(10.0, (-106.58 - 30.0) / 10.0);
                double interfDbm = (interfLinear > 0) ? (10.0 * std::log10(interfLinear) + 30.0) : -120.0;
                double sinrDb = 10.0 * std::log10(std::pow(10.0, (sPrxDbm - 30.0) / 10.0) / (interfLinear + noiseLinear));

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
                    double nowMs = Simulator::Now().GetMilliSeconds();
                    auto lastIt = g_lastDiscoveryRxTime.find({(uint8_t)r, sender});
                    if (lastIt != g_lastDiscoveryRxTime.end()) {
                        double iat = nowMs - lastIt->second;
                        if (iat > 0) {
                            g_dynSumDiscoveryIat += iat;
                            g_dynCountDiscoveryIat++;
                            if (iat > g_dynMaxDiscoveryIat) g_dynMaxDiscoveryIat = iat;

                            if (r == 0) {
                                g_d0SumDiscIat[sender] += iat;
                                g_d0CountDiscIat[sender]++;
                                if (iat > g_d0MaxDiscIat[sender]) g_d0MaxDiscIat[sender] = iat;
                            }
                        }
                    }
                    g_lastDiscoveryRxTime[{(uint8_t)r, sender}] = nowMs;
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
                        PhyEnumeration rStateAtTx = IEEE_802_15_4_PHY_TRX_OFF;
                        auto stIt = g_rxStateAtTxStart.find({txUid, (uint8_t)r});
                        if (stIt != g_rxStateAtTxStart.end()) {
                            rStateAtTx = stIt->second;
                        }

                        if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_TX || rStateAtTx == IEEE_802_15_4_PHY_TX_ON) {
                            cat = REASON_RX_DEAFNESS_BUSY_TX;
                        } else if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_RX) {
                            cat = REASON_PREAMBLE_COLLISION_BUSY_RX;
                        } else if (rStateAtTx == IEEE_802_15_4_PHY_TRX_OFF) {
                            cat = REASON_RADIO_TURNAROUND_BUSY;
                        } else {
                            auto dropIt = g_p1RxDropEvent.find({epoch, sender, (uint8_t)r});
                            if (dropIt != g_p1RxDropEvent.end()) {
                                cat = dropIt->second;
                            } else {
                                if (coChannelCount > 0 && sinrDb <= -5.0) {
                                    cat = REASON_PREAMBLE_LOW_SINR;
                                } else if (coChannelCount > 0 && sinrDb > -5.0) {
                                    cat = REASON_PREAMBLE_COLLISION_BUSY_RX;
                                } else {
                                    cat = REASON_PREAMBLE_LOW_SINR;
                                }
                            }
                        }
                    }
                }

                if (r == 0) {
                    g_d0Top5Expected[sender]++;
                    g_d0LastDist[sender] = dist;
                    if (heard) {
                        g_d0Top5DiscRx[sender]++;
                    }
                }

                P1LinkRecord rec;
                rec.epoch = epoch;
                rec.receiver = (uint8_t)r;
                rec.sender = sender;
                rec.distance = dist;
                rec.category = cat;
                rec.prx_dbm = sPrxDbm;
                rec.interf_dbm = interfDbm;
                rec.sinr_db = sinrDb;
                rec.coChannelCount = coChannelCount;
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

                // Compute exact RF metrics for this link (Physics & Channel model)
                double sPrxDbm = -48.6777 - 30.0 * std::log10(std::max(0.1, dist));
                double interfLinear = 0.0;
                int coChannelCount = 0;
                uint8_t sSlot = g_droneClaimedSlot[epoch][sender];
                uint8_t sCh = g_droneClaimedChannel[epoch][sender];
                for (uint32_t other = 0; other < numNodes; other++) {
                    if (other == sender || other == r) continue;
                    if (g_droneClaimedSlot[epoch][other] == sSlot &&
                        g_droneClaimedChannel[epoch][other] == sCh &&
                        !g_p2TxAbortInEpoch[epoch][other]) {
                        Ptr<MobilityModel> otherMob = NodeList::GetNode(other)->GetObject<MobilityModel>();
                        double otherDist = rMob->GetDistanceFrom(otherMob);
                        double otherPrxDbm = -48.6777 - 30.0 * std::log10(std::max(0.1, otherDist));
                        interfLinear += std::pow(10.0, (otherPrxDbm - 30.0) / 10.0);
                        coChannelCount++;
                    }
                }
                double noiseLinear = std::pow(10.0, (-106.58 - 30.0) / 10.0);
                double interfDbm = (interfLinear > 0) ? (10.0 * std::log10(interfLinear) + 30.0) : -120.0;
                double sinrDb = 10.0 * std::log10(std::pow(10.0, (sPrxDbm - 30.0) / 10.0) / (interfLinear + noiseLinear));

                bool delivered = false;
                auto itEp = g_p2ReceivedInEpoch.find(epoch);
                if (itEp != g_p2ReceivedInEpoch.end()) {
                    auto itRcv = itEp->second.find((uint8_t)r);
                    if (itRcv != itEp->second.end()) {
                        delivered = (itRcv->second.count(sender) > 0);
                    }
                }

                P2DropCategory cat = P2_REASON_SUCCESS;
                double nowMs = Simulator::Now().GetMilliSeconds();
                if (delivered) {
                    cat = P2_REASON_SUCCESS;
                    g_lastBeaconRxGenTime[{(uint8_t)r, sender}] = nowMs - 2.5;
                    if (r == 0) {
                        g_d0Top5BcnRx[sender]++;
                    }
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
                                cat = dropIt->second;
                            } else if (rStateAtTx == IEEE_802_15_4_PHY_BUSY_RX) {
                                cat = P2_REASON_PREAMBLE_COLLISION_BUSY_RX;
                            } else if (rStateAtTx == IEEE_802_15_4_PHY_TRX_OFF) {
                                cat = P2_REASON_RADIO_TURNAROUND_BUSY;
                            } else {
                                if (coChannelCount > 0 && sinrDb <= -5.0) {
                                    cat = P2_REASON_PREAMBLE_LOW_SINR;
                                } else if (coChannelCount > 0 && sinrDb > -5.0) {
                                    cat = P2_REASON_PREAMBLE_COLLISION_BUSY_RX;
                                } else {
                                    cat = P2_REASON_PREAMBLE_LOW_SINR;
                                }
                            }
                        }
                    }
                }

                auto genIt = g_lastBeaconRxGenTime.find({(uint8_t)r, sender});
                if (genIt != g_lastBeaconRxGenTime.end()) {
                    double aoi = nowMs - genIt->second;
                    if (aoi > 0) {
                        g_dynSumAoI += aoi;
                        g_dynCountAoI++;
                        if (aoi > g_dynMaxAoI) g_dynMaxAoI = aoi;

                        if (r == 0) {
                            g_d0SumAoI[sender] += aoi;
                            g_d0CountAoI[sender]++;
                            if (aoi > g_d0MaxAoI[sender]) g_d0MaxAoI[sender] = aoi;
                        }
                    }
                }

                P2LinkRecord rec;
                rec.epoch = epoch;
                rec.receiver = (uint8_t)r;
                rec.sender = sender;
                rec.distance = dist;
                rec.category = cat;
                rec.prx_dbm = sPrxDbm;
                rec.interf_dbm = interfDbm;
                rec.sinr_db = sinrDb;
                rec.coChannelCount = coChannelCount;
                g_p2LinkRecords.push_back(rec);
                g_p2ReasonCounts[cat]++;
                g_p2TotalTargetLinks++;
            }
        }
    }

    void PrintMetrics() {
        g_totalTopologyMatchCount += m_topologyMatchCount;
        g_totalTopologyCheckCount += m_topologyCheckCount;

        static bool s_printedSampleDrone = false;
        if (!s_printedSampleDrone && m_id == 0) {
            s_printedSampleDrone = true;
            g_singleDroneReport << "\n=== Drone  0 Metrics Report (Real-Time Top " << K_CLOSEST << " within " << M_RADIUS_METERS << "m) ===\n";
            g_singleDroneReport << "Target (Dist)  | Disc. Ratio | Bcn Ratio | Avg Disc. IAT | Max Disc. IAT | Mean Bcn AoI | Max Bcn AoI\n";
            g_singleDroneReport << "-----------------------------------------------------------------------------------------------------\n";
            
            // Pick Drone 0's top neighbors at final moment
            Ptr<MobilityModel> myMob = m_device->GetNode()->GetObject<MobilityModel>();
            std::vector<std::pair<uint8_t, double>> currDists;
            for (uint32_t i = 1; i < NodeList::GetNNodes(); i++) {
                Ptr<MobilityModel> otherMob = NodeList::GetNode(i)->GetObject<MobilityModel>();
                double dist = myMob->GetDistanceFrom(otherMob);
                if (dist <= M_RADIUS_METERS) {
                    currDists.push_back({(uint8_t)i, dist});
                }
            }
            std::sort(currDists.begin(), currDists.end(), [](const auto& a, const auto& b) {
                return a.second < b.second;
            });

            int expectedTop = std::min(K_CLOSEST, (int)currDists.size());
            for (int i = 0; i < expectedTop; i++) {
                uint8_t target = currDists[i].first;
                double dist = currDists[i].second;
                
                int expEpochs = g_d0Top5Expected[target];
                double discRatio = (expEpochs > 0) ? (100.0 * g_d0Top5DiscRx[target] / expEpochs) : 0.0;
                double bcnRatio = (expEpochs > 0) ? (100.0 * g_d0Top5BcnRx[target] / expEpochs) : 0.0;
                double avgDiscIat = (g_d0CountDiscIat[target] > 0) ? (g_d0SumDiscIat[target] / g_d0CountDiscIat[target]) : 0.0;
                double maxDiscIat = g_d0MaxDiscIat[target];
                double meanAoI = (g_d0CountAoI[target] > 0) ? (g_d0SumAoI[target] / g_d0CountAoI[target]) : 0.0;
                double maxAoI = g_d0MaxAoI[target];

                g_singleDroneReport << "Drone " << std::setw(2) << (int)target << " (" << std::setw(3) << (int)dist << "m) | "
                                    << std::fixed << std::setprecision(1) << std::setw(10) << discRatio << "% | "
                                    << std::fixed << std::setprecision(1) << std::setw(8) << bcnRatio << "% | "
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
    ss << "MAC Scheme                                        : " << (g_enableP1Sidelink ? "3GPP Sidelink Mode 4 S-SPS (No CSMA)" : "Continuous Random Delay + CSMA-CA") << "\n";
    if (g_enableP1Sidelink) {
        int numP1Slots = std::max(1, (int)((g_phase1DurationUs - 250.0) / g_p1SlotUs) + 1);
        ss << "Sidelink Configuration                            : Slot " << g_p1SlotUs << " us (" << numP1Slots << " slots in " << g_p1DurationMs << "ms)\n";
    }
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
    ss << "Bracket   | Total | Success | CSMA Abort | RX Deafness | Preamble Coll | Low SINR | Turnaround | Payload Drop\n";
    ss << "--------------------------------------------------------------------------------------------------------\n";
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
           << std::setw(8) << bCounts[REASON_PREAMBLE_LOW_SINR] << " | "
           << std::setw(10) << bCounts[REASON_RADIO_TURNAROUND_BUSY] << " | "
           << std::setw(12) << bCounts[REASON_PAYLOAD_INTERFERENCE_CORRUPTION] << "\n";
    }
    ss << "========================================================================================================\n\n";

    // Physical RF Signal Proofs
    double sumSinrSucc = 0, sumSinrDrop = 0, sumPrx = 0, sumInterf = 0;
    int cntSucc = 0, cntLowSinr = 0;
    for (const auto& rec : g_p1LinkRecords) {
        if (rec.category == REASON_SUCCESS) {
            sumSinrSucc += rec.sinr_db;
            cntSucc++;
        } else if (rec.category == REASON_PREAMBLE_LOW_SINR) {
            sumSinrDrop += rec.sinr_db;
            sumPrx += rec.prx_dbm;
            sumInterf += rec.interf_dbm;
            cntLowSinr++;
        }
    }
    double meanNeighbors = (g_countNeighborsIn50m > 0) ? (g_sumNeighborsIn50m / g_countNeighborsIn50m) : 0.0;
    double pctGe5 = (g_countNeighborsIn50m > 0) ? (100.0 * g_dronesWithGe5Neighbors / g_countNeighborsIn50m) : 0.0;
    ss << "📡 PHYSICAL RF SIGNAL PROOFS & SWARM DENSITY (Averages & Evidence):\n";
    ss << "  • Airspace Dimensions & Topology      : " << g_spaceSize << "m x " << g_spaceSize << "m x " << g_spaceZ << "m\n";
    ss << "  • Mean 50m Neighbors per UAV (Density): " << std::fixed << std::setprecision(2) << meanNeighbors << " UAVs\n";
    ss << "  • UAVs with >= 5 Neighbors in 50m     : " << std::fixed << std::setprecision(1) << pctGe5 << "%\n";
    ss << "  • Total Power Capture Events Triggered : " << g_totalCaptureEvents << " (rescued packets from closer neighbors)\n";
    if (cntSucc > 0) {
        ss << "  • Delivered Links Mean SINR           : " << std::fixed << std::setprecision(1) << (sumSinrSucc / cntSucc) << " dB (IEEE Threshold: > -5.0 dB)\n";
    }
    if (cntLowSinr > 0) {
        ss << "  • Low SINR Dropped Links Mean SINR    : " << std::fixed << std::setprecision(1) << (sumSinrDrop / cntLowSinr) << " dB (IEEE Threshold: <= -5.0 dB)\n";
        ss << "  • Low SINR Mean Received Power (Prx)  : " << std::fixed << std::setprecision(1) << (sumPrx / cntLowSinr) << " dBm\n";
        ss << "  • Low SINR Mean Interference Power (I): " << std::fixed << std::setprecision(1) << (sumInterf / cntLowSinr) << " dBm\n";
    }
    ss << "========================================================================================================\n\n";

    // -------------------------------------------------------------------------------------
    // Steady-State Converged Analysis (Last 2.0s: t = (simTime - 2.0)s to simTime)
    // -------------------------------------------------------------------------------------
    double steadyStartSec = std::max(0.0, g_simTime - 2.0);
    uint32_t steadyStartEpoch = (uint32_t)(steadyStartSec * 1000.0 / g_cycleMs) + 1;
    uint32_t steadyTotalLinks = 0;
    uint32_t steadyReasons[NUM_P1_REASONS] = {0};

    for (const auto& rec : g_p1LinkRecords) {
        if (rec.epoch >= steadyStartEpoch) {
            steadyTotalLinks++;
            steadyReasons[rec.category]++;
        }
    }

    if (steadyTotalLinks > 0) {
        double steadySuccPct = 100.0 * steadyReasons[REASON_SUCCESS] / steadyTotalLinks;
        uint32_t steadyFails = steadyTotalLinks - steadyReasons[REASON_SUCCESS];
        double steadyFailPct = 100.0 - steadySuccPct;

        ss << "========================================================================================\n";
        ss << "       🎯 STEADY-STATE CONVERGED ANALYSIS (Last 2.0s: t = " << std::fixed << std::setprecision(1) << steadyStartSec << "s ~ " << g_simTime << "s) 🎯\n";
        ss << "========================================================================================\n";
        ss << "Steady-State P1 Target Links (Epoch " << steadyStartEpoch << "+)           : " << steadyTotalLinks << "\n";
        ss << "  ✅ Successfully Received (Delivered)            : " << steadyReasons[REASON_SUCCESS] 
           << " (" << std::fixed << std::setprecision(1) << steadySuccPct << "%)\n";
        ss << "  ❌ Failed Link Receptions (Dropped/Missed)      : " << steadyFails 
           << " (" << std::fixed << std::setprecision(1) << steadyFailPct << "%)\n";
        ss << "----------------------------------------------------------------------------------------\n";
        ss << "STEADY-STATE EXACT PHYSICAL ROOT CAUSE BREAKDOWN:\n";
        for (int c = 1; c < NUM_P1_REASONS; c++) {
            int cnt = steadyReasons[c];
            double pctOfFail = (steadyFails > 0) ? (100.0 * cnt / steadyFails) : 0.0;
            double pctOfTotal = (steadyTotalLinks > 0) ? (100.0 * cnt / steadyTotalLinks) : 0.0;
            ss << "  " << std::left << std::setw(38) << P1ReasonStrings[c] << " : "
               << std::right << std::setw(5) << cnt << " ("
               << std::setw(5) << std::fixed << std::setprecision(1) << pctOfFail << "% of fails | "
               << std::setw(5) << std::fixed << std::setprecision(1) << pctOfTotal << "% of all links)\n";
        }
        ss << "========================================================================================\n\n";
    }

    std::cout << ss.str();

    // Write to report file
    std::ofstream rptFile("p1_ground_truth_report.txt");
    if (rptFile.is_open()) {
        rptFile << ss.str();
        rptFile.close();
    }

    // Write exact CSV with Ironclad Physical Evidence Columns
    std::ofstream csvFile("p1_exact_drop_reasons.csv");
    if (csvFile.is_open()) {
        csvFile << "Epoch,Receiver,Sender,Distance_m,Status,ExactReason,Prx_dBm,Interf_dBm,SINR_dB,CoChannelDrones\n";
        for (const auto& rec : g_p1LinkRecords) {
            csvFile << rec.epoch << "," << (int)rec.receiver << "," << (int)rec.sender << ","
                    << std::fixed << std::setprecision(2) << rec.distance << ","
                    << ((rec.category == REASON_SUCCESS) ? "SUCCESS" : "FAILED") << ","
                    << P1ReasonStrings[rec.category] << ","
                    << std::fixed << std::setprecision(2) << rec.prx_dbm << ","
                    << std::fixed << std::setprecision(2) << rec.interf_dbm << ","
                    << std::fixed << std::setprecision(2) << rec.sinr_db << ","
                    << rec.coChannelCount << "\n";
        }
        csvFile.close();
        std::cout << "✅ Exact Phase 1 ground truth link data exported to p1_exact_drop_reasons.csv\n";
        std::cout << "✅ Phase 1 ground truth summary report saved to p1_ground_truth_report.txt\n";
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
    ss << "Bracket   | Total | Success | P1 Miss | TX Deaf | RX Deaf | Ch Mismatch | CSMA Abort | Collision | Low SINR | Payload Drop\n";
    ss << "------------------------------------------------------------------------------------------------------------------------\n";
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
           << std::setw(11) << bCounts[P2_REASON_RECEIVER_CHANNEL_MISMATCH] << " | "
           << std::setw(10) << bCounts[P2_REASON_SENDER_CSMA_ABORT] << " | "
           << std::setw(9) << bCounts[P2_REASON_PREAMBLE_COLLISION_BUSY_RX] << " | "
           << std::setw(8) << bCounts[P2_REASON_PREAMBLE_LOW_SINR] << " | "
           << std::setw(12) << bCounts[P2_REASON_PAYLOAD_INTERFERENCE_DROP] << "\n";
    }
    ss << "========================================================================================================================\n\n";

    // Physical RF Signal Proofs
    double sumSinrSucc = 0, sumSinrDrop = 0, sumPrx = 0, sumInterf = 0;
    int cntSucc = 0, cntLowSinr = 0;
    for (const auto& rec : g_p2LinkRecords) {
        if (rec.category == P2_REASON_SUCCESS) {
            sumSinrSucc += rec.sinr_db;
            cntSucc++;
        } else if (rec.category == P2_REASON_PREAMBLE_LOW_SINR) {
            sumSinrDrop += rec.sinr_db;
            sumPrx += rec.prx_dbm;
            sumInterf += rec.interf_dbm;
            cntLowSinr++;
        }
    }
    double meanNeighbors = (g_countNeighborsIn50m > 0) ? (g_sumNeighborsIn50m / g_countNeighborsIn50m) : 0.0;
    double pctGe5 = (g_countNeighborsIn50m > 0) ? (100.0 * g_dronesWithGe5Neighbors / g_countNeighborsIn50m) : 0.0;
    ss << "📡 PHYSICAL RF SIGNAL PROOFS & SWARM DENSITY (Averages & Evidence):\n";
    ss << "  • Airspace Dimensions & Topology      : " << g_spaceSize << "m x " << g_spaceSize << "m x " << g_spaceZ << "m\n";
    ss << "  • Mean 50m Neighbors per UAV (Density): " << std::fixed << std::setprecision(2) << meanNeighbors << " UAVs\n";
    ss << "  • UAVs with >= 5 Neighbors in 50m     : " << std::fixed << std::setprecision(1) << pctGe5 << "%\n";
    ss << "  • Total Power Capture Events Triggered : " << g_totalCaptureEvents << " (rescued packets from closer neighbors)\n";
    if (cntSucc > 0) {
        ss << "  • Delivered Links Mean SINR           : " << std::fixed << std::setprecision(1) << (sumSinrSucc / cntSucc) << " dB (IEEE Threshold: > -5.0 dB)\n";
    }
    if (cntLowSinr > 0) {
        ss << "  • Low SINR Dropped Links Mean SINR    : " << std::fixed << std::setprecision(1) << (sumSinrDrop / cntLowSinr) << " dB (IEEE Threshold: <= -5.0 dB)\n";
        ss << "  • Low SINR Mean Received Power (Prx)  : " << std::fixed << std::setprecision(1) << (sumPrx / cntLowSinr) << " dBm\n";
        ss << "  • Low SINR Mean Interference Power (I): " << std::fixed << std::setprecision(1) << (sumInterf / cntLowSinr) << " dBm\n";
    }
    ss << "========================================================================================================================\n\n";

    std::cout << ss.str();

    // Write to report file
    std::ofstream rptFile("p2_ground_truth_report.txt");
    if (rptFile.is_open()) {
        rptFile << ss.str();
        rptFile.close();
    }

    // Write exact CSV with Ironclad Physical Evidence Columns
    std::ofstream csvFile("p2_exact_drop_reasons.csv");
    if (csvFile.is_open()) {
        csvFile << "Epoch,Receiver,Sender,Distance_m,Status,ExactReason,Prx_dBm,Interf_dBm,SINR_dB,CoChannelDrones\n";
        for (const auto& rec : g_p2LinkRecords) {
            csvFile << rec.epoch << "," << (int)rec.receiver << "," << (int)rec.sender << ","
                    << std::fixed << std::setprecision(2) << rec.distance << ","
                    << ((rec.category == P2_REASON_SUCCESS) ? "SUCCESS" : "FAILED") << ","
                    << P2ReasonStrings[rec.category] << ","
                    << std::fixed << std::setprecision(2) << rec.prx_dbm << ","
                    << std::fixed << std::setprecision(2) << rec.interf_dbm << ","
                    << std::fixed << std::setprecision(2) << rec.sinr_db << ","
                    << rec.coChannelCount << "\n";
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

    int numNodes = 75;
    double nodeSpeed = 10.0; // UAV mobility speed in m/s (default: 10 m/s ~ 36 km/h, 0 for static hover)
    bool autoPush = false;

    CommandLine cmd;
    cmd.AddValue("p2TxPower", "Phase 2 TX Power in dBm (e.g., -9, -4, 0)", g_p2TxPower);
    cmd.AddValue("p1TxPower", "Phase 1 TX Power in dBm (e.g., 0, 1, 3)", g_p1TxPower);
    cmd.AddValue("p1CcaThresholdDbm", "Phase 1 CSMA CCA Energy Detection Threshold in dBm (-106.58 to -80.0, default -96.58)", g_p1CcaThresholdDbm);
    cmd.AddValue("p1Duration", "Phase 1 duration in ms (e.g., 10 to 40)", g_p1DurationMs);
    cmd.AddValue("simTime", "Total simulation duration in seconds (default 10.0)", g_simTime);
    cmd.AddValue("enableP1Sidelink", "Enable Sidelink-inspired Semi-Persistent Scheduling for Phase 1 (default false)", g_enableP1Sidelink);
    cmd.AddValue("p1SlotUs", "Phase 1 Sidelink slot duration in microseconds (default 500.0)", g_p1SlotUs);
    cmd.AddValue("p1AvoidDist", "RX Deafness defense distance in meters", g_p1AvoidDist);
    cmd.AddValue("p1AvoidRssi", "Defense RSSI threshold in dBm (-106 to -90)", g_p1AvoidRssi);
    cmd.AddValue("enableDefense", "Enable spatial slot defense (default true)", g_enableDefense);
    cmd.AddValue("numChannels", "Number of Phase 2 data channels (e.g., 0 to 10)", g_numDataChannels);
    cmd.AddValue("numSlots", "Number of Phase 2 data slots (e.g., 5 to 20)", g_numDataSlots);
    cmd.AddValue("numNodes", "Number of UAV nodes in swarm (e.g., 50, 100)", numNodes);
    cmd.AddValue("nodeSpeed", "Speed of UAVs in m/s (default 10.0 m/s, 0 for static hover)", nodeSpeed);
    cmd.AddValue("spaceSize", "Side length of 3D box (X and Y) in meters", g_spaceSize);
    cmd.AddValue("spaceZ", "Height of 3D box in meters", g_spaceZ);
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
    
    // 3D Random Box Topology (g_spaceSize x g_spaceSize x g_spaceZ)
    Ptr<RandomBoxPositionAllocator> alloc = CreateObject<RandomBoxPositionAllocator>();
    Ptr<UniformRandomVariable> xVar = CreateObject<UniformRandomVariable>();
    xVar->SetAttribute("Min", DoubleValue(0.0));
    xVar->SetAttribute("Max", DoubleValue(g_spaceSize));
    alloc->SetX(xVar);
    
    Ptr<UniformRandomVariable> yVar = CreateObject<UniformRandomVariable>();
    yVar->SetAttribute("Min", DoubleValue(0.0));
    yVar->SetAttribute("Max", DoubleValue(g_spaceSize));
    alloc->SetY(yVar);
    
    Ptr<UniformRandomVariable> zVar = CreateObject<UniformRandomVariable>();
    zVar->SetAttribute("Min", DoubleValue(10.0));
    zVar->SetAttribute("Max", DoubleValue(10.0 + g_spaceZ)); // height difference
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
        app->SetStopTime(Seconds(g_simTime)); 
    }

    std::cout << "Starting Simulation for " << g_simTime << "s..." << std::endl;
    Simulator::Stop(Seconds(g_simTime));
    Simulator::Run();
    
    double globalDiscRatio = (g_p1TotalTargetLinks > 0) ? (double)g_p1ReasonCounts[REASON_SUCCESS] / g_p1TotalTargetLinks : 0.0;
    double globalBcnRatio = (g_p2TotalTargetLinks > 0) ? (double)g_p2ReasonCounts[P2_REASON_SUCCESS] / g_p2TotalTargetLinks : 0.0;
    double globalAvgDiscIat = (g_dynCountDiscoveryIat > 0) ? (g_dynSumDiscoveryIat / g_dynCountDiscoveryIat) : 0.0;
    double globalMeanAoI = (g_dynCountAoI > 0) ? (g_dynSumAoI / g_dynCountAoI) : 0.0;
    
    std::stringstream ss;
    ss << "\n=================================================\n";
    ss << "       GLOBAL NETWORK METRICS (0.0s ~ " << std::fixed << std::setprecision(1) << g_simTime << "s)       \n";
    ss << "    (Dynamic Real-Time Top-5 Neighbors Average)   \n";
    ss << "=================================================\n";
    ss << "Discovery Message Reception Ratio: " << std::fixed << std::setprecision(1) << globalDiscRatio * 100 << "%\n";
    ss << "Beacon Packet Reception Ratio   : " << std::fixed << std::setprecision(1) << globalBcnRatio * 100 << "%\n";
    ss << "Avg Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << globalAvgDiscIat << " ms\n";
    ss << "Max Discovery Msg IAT (Top-K)   : " << std::fixed << std::setprecision(1) << g_dynMaxDiscoveryIat << " ms\n";
    ss << "Mean Beacon Packet AoI (Top-K)  : " << std::fixed << std::setprecision(1) << globalMeanAoI << " ms\n";
    ss << "Max Beacon Packet AoI (Top-K)   : " << std::fixed << std::setprecision(1) << g_dynMaxAoI << " ms\n";
    ss << "-------------------------------------------------\n";
    ss << "=== PHASE 2 CONTENTION & DEAFNESS METRICS ===\n";
    ss << "Total Scheduled Top-K Neighbor Beacons: " << g_totalExpectedRx << "\n";
    ss << "TX Deafness (Same slot as TX)         : " << g_txDeafnessCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_txDeafnessCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "RX Deafness (Slot conflict)           : " << g_rxDeafnessCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_rxDeafnessCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "Resource Collision (Same S+C)         : " << g_resourceCollisionCount << " (" << std::fixed << std::setprecision(1) << (g_totalExpectedRx > 0 ? (double)g_resourceCollisionCount/g_totalExpectedRx*100 : 0) << "%)\n";
    ss << "=================================================\n\n";

    std::ofstream mFile("metrics.txt");
    if (mFile.is_open()) {
        mFile << ss.str();
        mFile.close();
    }

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
