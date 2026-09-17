#include <ns3/core-module.h>
#include <ns3/network-module.h>
#include <ns3/mobility-module.h>
#include <ns3/spectrum-module.h>
#include <ns3/lr-wpan-module.h>
#include <iostream>
#include <vector>
#include <algorithm>
#include <iomanip>

using namespace ns3;
using namespace ns3::lrwpan;

NS_LOG_COMPONENT_DEFINE("LrWpanSwarm");

// --- 系統常數設定 ---
const uint32_t MINI_BEACON_SIZE = 2; // 壓縮為 2 Bytes
const uint32_t DATA_PACKET_SIZE = 50;

const double CYCLE_MS = 33.5;
const double PHASE1_DURATION_US = 15000.0; // 給 beacon 隨機競爭 15ms
const double GAP_US = 1000.0; 
const int NUM_DATA_SLOTS = 7;
const int NUM_DATA_CHANNELS = 3; // 對應 Ch 12, 13, 14
const double DATA_SLOT_US = 2500.0; 

const uint8_t BROADCAST_CHANNEL = 11;

// 鄰機資訊結構體
struct NeighborInfo {
    uint8_t id;
    int8_t rssi;
    uint32_t epoch;
    uint8_t claimedSlot;
    uint8_t claimedChannel;
};

// 時槽排程結構體
struct ScheduleSlot {
    enum Action { IDLE, TX, RX } action;
    uint8_t channel;
    uint8_t targetId;
};

class SwarmSchedulerApp : public Application {
public:
    SwarmSchedulerApp() : m_epoch(0), m_myClaimedSlot(0), m_myClaimedChannel(0) {}

    void Setup(Ptr<LrWpanNetDevice> dev, uint8_t id) {
        m_device = dev;
        m_id = id;
        
        Ptr<LrWpanMac> mac = m_device->GetMac();
        Ptr<LrWpanCsmaCa> csma = CreateObject<LrWpanCsmaCa>();
        csma->SetMacMinBE(0); // 降低退避延遲
        csma->SetMacMaxCSMABackoffs(4); // 恢復 CSMA 退避以支援隨機競爭
        mac->SetCsmaCa(csma);
        csma->SetMac(mac);
        
        csma->SetLrWpanMacStateCallback(MakeCallback(&LrWpanMac::SetLrWpanMacState, mac));
        m_device->GetPhy()->SetPlmeCcaConfirmCallback(MakeCallback(&LrWpanCsmaCa::PlmeCcaConfirm, csma));

        mac->SetPanId(1);
        mac->SetRxOnWhenIdle(true);

        mac->SetMcpsDataIndicationCallback(MakeCallback(&SwarmSchedulerApp::ReceivePacket, this));
        mac->SetMcpsDataConfirmCallback(MakeCallback(&SwarmSchedulerApp::DataConfirm, this));
    }

    void StartApplication() override {
        std::cout << "Drone " << (int)m_id << " StartApplication called!" << std::endl;
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

        // 階段一：切換至廣播頻道
        SwitchChannel(BROADCAST_CHANNEL);
        
        // 隨機抽選 0 ~ (15ms - 2ms) 作為發送時間
        Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
        double randomDelayUs = uv->GetValue(0, PHASE1_DURATION_US - 2000.0);
        
        Simulator::Schedule(MicroSeconds(randomDelayUs), &SwarmSchedulerApp::PickResourceAndSendBeacon, this);
        
        // 安排運算間隔
        Simulator::Schedule(MicroSeconds(PHASE1_DURATION_US + GAP_US), &SwarmSchedulerApp::ComputeSchedule, this);
        
        // 安排下一次循環
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

        // 位元封裝 (Bit-packing) 到 2 Bytes
        uint16_t payload = (m_id & 0x1F) | ((m_myClaimedSlot & 0x07) << 5) | ((m_myClaimedChannel & 0x03) << 8);
        uint8_t buffer[2];
        buffer[0] = payload & 0xFF;
        buffer[1] = (payload >> 8) & 0xFF;
        
        Ptr<Packet> p = Create<Packet>(buffer, 2);
        
        std::cout << "[Epoch " << std::setw(3) << m_epoch << " | "
                  << std::fixed << std::setprecision(2) << Simulator::Now().GetMilliSeconds() 
                  << "ms] Drone " << (int)m_id << " 宣告 Slot: " << (int)m_myClaimedSlot 
                  << ", Ch: " << (int)(m_myClaimedChannel + 12) << " (Cost: " << minCost << ")" << std::endl;
                  
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
        for (auto& n : m_monitorList) {
            if (assigned >= 5) break; 
            if (n.claimedSlot == m_myClaimedSlot) continue; 
            if (m_schedule[n.claimedSlot].action != ScheduleSlot::IDLE) continue; 

            m_schedule[n.claimedSlot].action = ScheduleSlot::RX;
            m_schedule[n.claimedSlot].channel = n.claimedChannel + 12;
            m_schedule[n.claimedSlot].targetId = n.id;
            assigned++;
        }

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
        if (params.m_status != MacStatus::SUCCESS) {
            std::cout << "[Epoch " << std::setw(3) << m_epoch << " | " 
                      << std::fixed << std::setprecision(2) << Simulator::Now().GetMilliSeconds() << " ms] "
                      << "Drone " << (int)m_id << " TX Failed! Status: " << (int)params.m_status << std::endl;
        }
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
        } else if (p->GetSize() == DATA_PACKET_SIZE) {
            uint8_t addrBuffer[2];
            params.m_srcAddr.CopyTo(addrBuffer);
            uint8_t srcId = addrBuffer[1];
            
            std::cout << "[Epoch " << std::setw(3) << m_epoch << " | " 
                      << std::fixed << std::setprecision(2) << Simulator::Now().GetMilliSeconds() << " ms] "
                      << "Drone " << (int)m_id << " 成功收到 Drone " << (int)srcId 
                      << " 的 50B 資料 (RSSI: " << (int)rssi << " dBm)" << std::endl;
        }
    }
};

int main(int argc, char *argv[]) {
    CommandLine cmd;
    cmd.Parse(argc, argv);

    // 關閉過於冗長的底層 Log，只留下自己的 Log 方便觀察
    // LogComponentEnable("LrWpanMac", LOG_LEVEL_ALL);
    // LogComponentEnable("LrWpanPhy", LOG_LEVEL_ALL);

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
        app->SetStopTime(Seconds(0.1)); // 模擬約 3 個週期 (100ms)
    }

    std::cout << "Starting Simulation for 100ms..." << std::endl;
    Simulator::Stop(Seconds(0.1));
    Simulator::Run();
    Simulator::Destroy();

    return 0;
}
