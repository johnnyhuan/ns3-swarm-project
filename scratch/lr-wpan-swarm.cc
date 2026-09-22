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

using namespace ns3;
using namespace ns3::lrwpan;

NS_LOG_COMPONENT_DEFINE("LrWpanSwarm");

// --- 系統常數設定 ---
const uint32_t MINI_BEACON_SIZE = 2; 
const uint32_t DATA_PACKET_SIZE = 50;

const double CYCLE_MS = 33.5;
const double PHASE1_DURATION_US = 15000.0; 
const double GAP_US = 1000.0; 
const int NUM_DATA_SLOTS = 7;
const int NUM_DATA_CHANNELS = 3; 
const double DATA_SLOT_US = 2500.0; 

const uint8_t BROADCAST_CHANNEL = 11;

// 全域 SRF 統計
static int g_totalDataPacketsReceived = 0;

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
    SwarmSchedulerApp() : m_epoch(0), m_myClaimedSlot(0), m_myClaimedChannel(0), m_topologyMatchCount(0), m_topologyCheckCount(0) {}

    void Setup(Ptr<LrWpanNetDevice> dev, uint8_t id) {
        m_device = dev;
        m_id = id;
        
        Ptr<LrWpanMac> mac = m_device->GetMac();
        Ptr<LrWpanCsmaCa> csma = CreateObject<LrWpanCsmaCa>();
        csma->SetMacMinBE(0); 
        csma->SetMacMaxCSMABackoffs(4); 
        mac->SetCsmaCa(csma);
        csma->SetMac(mac);
        
        csma->SetLrWpanMacStateCallback(MakeCallback(&LrWpanMac::SetLrWpanMacState, mac));
        m_device->GetPhy()->SetPlmeCcaConfirmCallback(MakeCallback(&LrWpanCsmaCa::PlmeCcaConfirm, csma));

        mac->SetPanId(1);
        mac->SetRxOnWhenIdle(true);

        mac->SetMcpsDataIndicationCallback(MakeCallback(&SwarmSchedulerApp::ReceivePacket, this));
        mac->SetMcpsDataConfirmCallback(MakeCallback(&SwarmSchedulerApp::DataConfirm, this));
        
        // 安排在模擬結束前一刻印出報表
        Simulator::Schedule(Seconds(0.999), &SwarmSchedulerApp::PrintMetrics, this);
    }

    void StartApplication() override {
        // 減少 Log 輸出，避免洗版
        if (m_id == 0) std::cout << "All Drones StartApplication called! Running for 1.0s..." << std::endl;
        ScheduleCycle();
    }
    
    void StopApplication() override {}

private:
    Ptr<LrWpanNetDevice> m_device;
    uint8_t m_id;
    uint32_t m_epoch;
    uint8_t m_myClaimedSlot;
    uint8_t m_myClaimedChannel;
    std::vector<NeighborInfo> m_monitorList;
    ScheduleSlot m_schedule[NUM_DATA_SLOTS];

    // 數據統計變數
    std::map<uint8_t, int> m_beaconReceivedCount;
    std::map<uint8_t, int> m_dataReceivedCount;
    std::map<uint8_t, double> m_lastDataTime;
    std::map<uint8_t, double> m_sumIat;
    std::map<uint8_t, int> m_countIat;
    std::map<uint8_t, double> m_maxIat;
    
    std::vector<uint8_t> m_lastScheduledRx;
    int m_topologyMatchCount;
    int m_topologyCheckCount;

    void SwitchChannel(uint8_t ch) {
        Ptr<PhyPibAttributes> attrs = Create<PhyPibAttributes>();
        attrs->phyCurrentChannel = ch;
        m_device->GetPhy()->PlmeSetAttributeRequest(phyCurrentChannel, attrs);
    }

    void SendPacket(uint32_t size, Ptr<Packet> p) {
        McpsDataRequestParams params;
        params.m_srcAddrMode = SHORT_ADDR;
        params.m_dstAddrMode = SHORT_ADDR;
        params.m_dstPanId = 1;
        params.m_dstAddr = Mac16Address("FF:FF"); 
        params.m_msduHandle = 0;
        params.m_txOptions = TX_OPTION_NONE;

        m_device->GetMac()->McpsDataRequest(params, p);
    }

    void ScheduleCycle() {
        m_epoch++;
        m_monitorList.clear();

        SwitchChannel(BROADCAST_CHANNEL);
        
        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
        double randomDelayUs = uv->GetValue(0, PHASE1_DURATION_US - 2000.0);
        
        Simulator::Schedule(MicroSeconds(randomDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        Simulator::Schedule(MicroSeconds(PHASE1_DURATION_US + GAP_US), &SwarmSchedulerApp::ComputeSchedule, this);
        Simulator::Schedule(MilliSeconds(CYCLE_MS), &SwarmSchedulerApp::ScheduleCycle, this);
    }

    void PickResourceAndSendBeacon() {
        int cost[NUM_DATA_SLOTS][NUM_DATA_CHANNELS] = {0};
        
        for (const auto& n : m_monitorList) {
            cost[n.claimedSlot][n.claimedChannel] += 10000;
            if (n.rssi > -85) {
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

        uint16_t payload = (m_id & 0x1F) | ((m_myClaimedSlot & 0x07) << 5) | ((m_myClaimedChannel & 0x03) << 8);
        uint8_t buffer[2] = { (uint8_t)(payload & 0xFF), (uint8_t)((payload >> 8) & 0xFF) };
        Ptr<Packet> p = Create<Packet>(buffer, 2);
                  
        SendPacket(MINI_BEACON_SIZE, p);
    }

    void ComputeSchedule() {
        std::sort(m_monitorList.begin(), m_monitorList.end(), [](const NeighborInfo& a, const NeighborInfo& b) {
            return a.rssi > b.rssi;
        });

        for (int i = 0; i < NUM_DATA_SLOTS; i++) {
            m_schedule[i].action = ScheduleSlot::IDLE;
        }

        m_schedule[m_myClaimedSlot].action = ScheduleSlot::TX;
        m_schedule[m_myClaimedSlot].channel = m_myClaimedChannel + 12;

        int assigned = 0;
        m_lastScheduledRx.clear();
        for (auto& n : m_monitorList) {
            if (assigned >= 5) break; 
            if (n.claimedSlot == m_myClaimedSlot) continue; 
            if (m_schedule[n.claimedSlot].action != ScheduleSlot::IDLE) continue; 

            m_schedule[n.claimedSlot].action = ScheduleSlot::RX;
            m_schedule[n.claimedSlot].channel = n.claimedChannel + 12;
            m_schedule[n.claimedSlot].targetId = n.id;
            m_lastScheduledRx.push_back(n.id);
            assigned++;
        }

        // 上帝視角：計算拓樸準確度
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
        std::vector<std::pair<uint8_t, double>> godDistances;
        for (uint32_t i = 0; i < NodeList::GetNodeNum(); i++) {
            if (i == m_id) continue;
            Ptr<MobilityModel> otherMobility = NodeList::GetNode(i)->GetObject<MobilityModel>();
            double dist = myMobility->GetDistanceFrom(otherMobility);
            godDistances.push_back({i, dist});
        }
        std::sort(godDistances.begin(), godDistances.end(), [](const auto& a, const auto& b) {
            return a.second < b.second;
        });

        int match = 0;
        int expectedTop = std::min(5, (int)godDistances.size());
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
            SwitchChannel(s.channel);
            Ptr<Packet> p = Create<Packet>(DATA_PACKET_SIZE);
            SendPacket(DATA_PACKET_SIZE, p);
        } else if (s.action == ScheduleSlot::RX) {
            SwitchChannel(s.channel);
        }
    }

    void DataConfirm(McpsDataConfirmParams params) {
        // 隱藏錯誤 Log，保持報表整潔
    }

    void ReceivePacket(McpsDataIndicationParams params, Ptr<Packet> p) {
        int8_t rssi = params.m_rssi;

        if (p->GetSize() == MINI_BEACON_SIZE) {
            uint8_t buffer[2];
            p->CopyData(buffer, 2);
            uint16_t payload = buffer[0] | (buffer[1] << 8);
            
            uint8_t senderId = payload & 0x1F;
            uint8_t claimedSlot = (payload >> 5) & 0x07;
            uint8_t claimedChannel = (payload >> 8) & 0x03;
            
            m_monitorList.push_back({senderId, rssi, m_epoch, claimedSlot, claimedChannel});
            m_beaconReceivedCount[senderId]++;
        } else if (p->GetSize() == DATA_PACKET_SIZE) {
            uint8_t addrBuffer[2];
            params.m_srcAddr.CopyTo(addrBuffer);
            uint8_t srcId = addrBuffer[1];
            
            m_dataReceivedCount[srcId]++;
            g_totalDataPacketsReceived++;
            
            double now = Simulator::Now().GetMilliSeconds();
            if (m_lastDataTime.find(srcId) != m_lastDataTime.end()) {
                double iat = now - m_lastDataTime[srcId];
                m_sumIat[srcId] += iat;
                m_countIat[srcId]++;
                if (m_maxIat.find(srcId) == m_maxIat.end() || iat > m_maxIat[srcId]) {
                    m_maxIat[srcId] = iat;
                }
            }
            m_lastDataTime[srcId] = now;
        }
    }

    void PrintMetrics() {
        Ptr<MobilityModel> myMobility = m_device->GetNode()->GetObject<MobilityModel>();
        std::vector<std::pair<uint8_t, double>> godDistances;
        for (uint32_t i = 0; i < NodeList::GetNodeNum(); i++) {
            if (i == m_id) continue;
            Ptr<MobilityModel> otherMobility = NodeList::GetNode(i)->GetObject<MobilityModel>();
            double dist = myMobility->GetDistanceFrom(otherMobility);
            godDistances.push_back({i, dist});
        }
        std::sort(godDistances.begin(), godDistances.end(), [](const auto& a, const auto& b) {
            return a.second < b.second;
        });

        std::cout << "\n=== Drone " << std::setw(2) << (int)m_id << " Metrics Report ===" << std::endl;
        std::cout << "Target (True Dist) | BDR (%) | DDR (%) | Avg IAT(ms) | Max IAT(ms)" << std::endl;
        std::cout << "------------------------------------------------------------------" << std::endl;
        
        for (int i = 0; i < std::min(5, (int)godDistances.size()); i++) {
            uint8_t target = godDistances[i].first;
            double dist = godDistances[i].second;
            
            double bdr = (double)m_beaconReceivedCount[target] / m_epoch;
            double ddr = (double)m_dataReceivedCount[target] / m_epoch;
            double avgIat = (m_countIat[target] > 0) ? (m_sumIat[target] / m_countIat[target]) : 0;
            double maxIat = (m_maxIat.find(target) != m_maxIat.end()) ? m_maxIat[target] : 0;
            
            std::cout << "Drone " << std::setw(2) << (int)target << " (" << std::setw(4) << dist << "m) | "
                      << std::fixed << std::setprecision(1) << std::setw(6) << bdr * 100 << " | "
                      << std::fixed << std::setprecision(1) << std::setw(6) << ddr * 100 << " | "
                      << std::fixed << std::setprecision(1) << std::setw(11) << avgIat << " | "
                      << std::fixed << std::setprecision(1) << std::setw(11) << maxIat << std::endl;
        }
        
        double topAcc = (m_topologyCheckCount > 0) ? ((double)m_topologyMatchCount / m_topologyCheckCount) : 0;
        std::cout << "--> Topology Accuracy (Top-5 Match Rate): " << std::fixed << std::setprecision(1) << topAcc * 100 << "%" << std::endl;
    }
};

int main(int argc, char *argv[]) {
    CommandLine cmd;
    cmd.Parse(argc, argv);

    int numNodes = 12; // 測試 12 台無人機
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
    Ptr<ListPositionAllocator> pos = CreateObject<ListPositionAllocator>();
    // 將 12 台無人機分佈在不同距離 (每隔 20m)
    for (int i = 0; i < numNodes; i++) {
        pos->Add(Vector(i * 20.0, 0.0, 10.0)); 
    }
    mobility.SetPositionAllocator(pos);
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
        app->SetStopTime(Seconds(1.0)); // 模擬延長至 1.0 秒
    }

    std::cout << "Starting Simulation for 1.0s..." << std::endl;
    Simulator::Stop(Seconds(1.0));
    Simulator::Run();
    
    // 結算全域 SRF (空間復用率)
    int totalEpochs = 1000 / CYCLE_MS; // 1.0秒約 29 回合
    int totalSlots = totalEpochs * NUM_DATA_SLOTS;
    double srf = (double)g_totalDataPacketsReceived / totalSlots;
    
    std::cout << "\n=================================================" << std::endl;
    std::cout << "          GLOBAL NETWORK METRICS (1.0s)          " << std::endl;
    std::cout << "=================================================" << std::endl;
    std::cout << "Total Data Packets Delivered : " << g_totalDataPacketsReceived << std::endl;
    std::cout << "Total Network Slots Elapsed  : " << totalSlots << " slots" << std::endl;
    std::cout << "Spatial Reuse Factor (SRF)   : " << std::fixed << std::setprecision(2) << srf << " packets/slot" << std::endl;
    std::cout << "=================================================\n" << std::endl;

    Simulator::Destroy();

    return 0;
}
