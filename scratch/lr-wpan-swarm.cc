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
const uint32_t MINI_BEACON_SIZE = 4;
const uint32_t DATA_PACKET_SIZE = 50;

const double CYCLE_MS = 10.0;
const int NUM_MICRO_SLOTS = 6;  // 給 6 架飛機每人一個微時槽
const double MICRO_SLOT_US = 750.0; 
const double GAP_US = 100.0; 
// 50B 的 MAC+PHY 負載約需 2.15ms，加上 guard time 抓 2.3ms
const int NUM_DATA_SLOTS = 3;
const double DATA_SLOT_US = 2300.0; 

const uint8_t BROADCAST_CHANNEL = 11;
const uint8_t NUM_DATA_CHANNELS = 15; // Ch 12 ~ 26

// 鄰機資訊結構體
struct NeighborInfo {
    uint8_t id;
    int8_t rssi;
    uint32_t epoch;
};

// 時槽排程結構體
struct ScheduleSlot {
    enum Action { IDLE, TX, RX } action;
    uint8_t channel;
    uint8_t targetId;
};

class SwarmSchedulerApp : public Application {
public:
    SwarmSchedulerApp() : m_epoch(0) {}

    void Setup(Ptr<LrWpanNetDevice> dev, uint8_t id) {
        m_device = dev;
        m_id = id;
        
        // 繞過 CSMA-CA，實現純 TDMA 發射
        Ptr<LrWpanMac> mac = m_device->GetMac();
        Ptr<LrWpanCsmaCa> csma = CreateObject<LrWpanCsmaCa>();
        csma->SetMacMinBE(0);
        csma->SetMacMaxCSMABackoffs(0);
        mac->SetCsmaCa(csma);
        csma->SetMac(mac); // 必須把 MAC 的指標也設給 CSMA，否則底層發送會出現 null pointer crash
        // 設定統一的 PAN ID，避免預設 0xFFFF 被當成未初始化而濾除
        mac->SetPanId(1);
        
        // 必須開啟閒置時接收，否則 PHY 預設會處於 TRX_OFF 狀態，完全聽不到封包！
        mac->SetRxOnWhenIdle(true);

        // 掛載接收回呼，獲取 RSSI
        mac->SetMcpsDataIndicationCallback(MakeCallback(&SwarmSchedulerApp::ReceivePacket, this));
    }

    void StartApplication() override {
        ScheduleCycle();
    }
    
    void StopApplication() override {}

private:
    Ptr<LrWpanNetDevice> m_device;
    uint8_t m_id;
    uint32_t m_epoch;
    std::vector<NeighborInfo> m_monitorList;
    ScheduleSlot m_schedule[NUM_DATA_SLOTS];

    void SwitchChannel(uint8_t ch) {
        Ptr<PhyPibAttributes> attrs = Create<PhyPibAttributes>();
        attrs->phyCurrentChannel = ch;
        m_device->GetPhy()->PlmeSetAttributeRequest(phyCurrentChannel, attrs);
    }

    void SendPacket(uint32_t size) {
        Ptr<Packet> p = Create<Packet>(size);
        McpsDataRequestParams params;
        params.m_srcAddrMode = SHORT_ADDR;
        params.m_dstAddrMode = SHORT_ADDR;
        params.m_dstPanId = 1; // 必須與接收端相同
        // 使用 Broadcast Address，確保所有人都能收到，免去 Promiscuous 模式設定
        params.m_dstAddr = Mac16Address("FF:FF"); 
        params.m_msduHandle = 0;
        params.m_txOptions = TX_OPTION_NONE; // 不需 ACK

        m_device->GetMac()->McpsDataRequest(params, p);
    }

    void ScheduleCycle() {
        m_epoch++;
        m_monitorList.clear();

        // 階段一：切換至廣播頻道
        SwitchChannel(BROADCAST_CHANNEL);
        
        uint8_t myMicroSlot = m_id % NUM_MICRO_SLOTS;
        
        for (int i = 0; i < NUM_MICRO_SLOTS; i++) {
            if (i == myMicroSlot) {
                Simulator::Schedule(MicroSeconds(i * MICRO_SLOT_US), &SwarmSchedulerApp::SendPacket, this, MINI_BEACON_SIZE);
            }
        }

        // 安排運算間隔
        Simulator::Schedule(MicroSeconds(NUM_MICRO_SLOTS * MICRO_SLOT_US + GAP_US), &SwarmSchedulerApp::ComputeSchedule, this);
        
        // 安排下一次循環
        Simulator::Schedule(MilliSeconds(CYCLE_MS), &SwarmSchedulerApp::ScheduleCycle, this);
    }

    void ComputeSchedule() {
        // Top-K 能量排序 (RSSI 降序)
        std::sort(m_monitorList.begin(), m_monitorList.end(), [](const NeighborInfo& a, const NeighborInfo& b) {
            return a.rssi > b.rssi;
        });

        // 初始化階段二時槽
        for (int i = 0; i < NUM_DATA_SLOTS; i++) {
            m_schedule[i].action = ScheduleSlot::IDLE;
        }

        // 標記本機發射 (TX)
        int mySlot = m_id % NUM_DATA_SLOTS;
        int myCh = (m_id * 7 + m_epoch) % NUM_DATA_CHANNELS + 12;
        m_schedule[mySlot].action = ScheduleSlot::TX;
        m_schedule[mySlot].channel = myCh;

        // 貪婪排程，優先聽近的鄰機 (RX)
        int assigned = 0;
        for (auto& n : m_monitorList) {
            if (assigned >= NUM_DATA_SLOTS - 1) break; // 最多聽 N-1 個
            int nSlot = n.id % NUM_DATA_SLOTS;
            int nCh = (n.id * 7 + m_epoch) % NUM_DATA_CHANNELS + 12;

            if (nSlot == mySlot) continue; // 時槽與本機發射重疊，無法分身
            if (m_schedule[nSlot].action != ScheduleSlot::IDLE) continue; // 已被更近的鄰機佔用

            m_schedule[nSlot].action = ScheduleSlot::RX;
            m_schedule[nSlot].channel = nCh;
            m_schedule[nSlot].targetId = n.id;
            assigned++;
        }

        // 排程階段二的各個 Data Slot 動作
        double phase2StartUs = NUM_MICRO_SLOTS * MICRO_SLOT_US + GAP_US;
        for (int i = 0; i < NUM_DATA_SLOTS; i++) {
            Simulator::Schedule(MicroSeconds(phase2StartUs + i * DATA_SLOT_US), &SwarmSchedulerApp::ExecuteDataSlot, this, i);
        }
    }

    void ExecuteDataSlot(int slotIndex) {
        ScheduleSlot s = m_schedule[slotIndex];
        if (s.action == ScheduleSlot::TX) {
            SwitchChannel(s.channel);
            SendPacket(DATA_PACKET_SIZE);
        } else if (s.action == ScheduleSlot::RX) {
            SwitchChannel(s.channel);
        }
    }

    void ReceivePacket(McpsDataIndicationParams params, Ptr<Packet> p) {
        // 從 Short Address 解析出 Drone ID (例如 00:03 -> ID 3)
        uint8_t addrBuffer[2];
        params.m_srcAddr.CopyTo(addrBuffer);
        uint8_t srcId = addrBuffer[1];
        int8_t rssi = params.m_rssi;

        if (p->GetSize() == MINI_BEACON_SIZE) {
            m_monitorList.push_back({srcId, rssi, m_epoch});
        } else if (p->GetSize() == DATA_PACKET_SIZE) {
            std::cout << "[Epoch " << std::setw(3) << m_epoch << " | " 
                      << std::fixed << std::setprecision(2) << Simulator::Now().GetMilliSeconds() << " ms] "
                      << "Drone " << (int)m_id << " 成功收到 Drone " << (int)srcId 
                      << " 的 50B 狀態封包 (RSSI: " << (int)rssi << " dBm)" << std::endl;
        }
    }
};

int main(int argc, char *argv[]) {
    CommandLine cmd;
    cmd.Parse(argc, argv);

    int numNodes = 6; // 建立 6 架無人機進行驗證

    NodeContainer nodes;
    nodes.Create(numNodes);

    // 建立 lr-wpan 頻譜通道與物理層模型
    Ptr<SingleModelSpectrumChannel> channel = CreateObject<SingleModelSpectrumChannel>();
    Ptr<LogDistancePropagationLossModel> propModel = CreateObject<LogDistancePropagationLossModel>();
    Ptr<ConstantSpeedPropagationDelayModel> delayModel = CreateObject<ConstantSpeedPropagationDelayModel>();
    channel->AddPropagationLossModel(propModel);
    channel->SetPropagationDelayModel(delayModel);

    LrWpanHelper lrWpanHelper;
    lrWpanHelper.SetChannel(channel);
    NetDeviceContainer devices = lrWpanHelper.Install(nodes);

    // 設定無人機的 3D 位置 (拉開距離以呈現 RSSI 差異)
    MobilityHelper mobility;
    Ptr<ListPositionAllocator> pos = CreateObject<ListPositionAllocator>();
    pos->Add(Vector(0.0, 0.0, 10.0));    // ID 0
    pos->Add(Vector(10.0, 0.0, 10.0));   // ID 1 (距離 10m)
    pos->Add(Vector(20.0, 0.0, 10.0));   // ID 2 (距離 20m)
    pos->Add(Vector(80.0, 0.0, 10.0));   // ID 3 (距離 80m, 很遠)
    pos->Add(Vector(90.0, 0.0, 10.0));   // ID 4 (距離 90m)
    pos->Add(Vector(100.0, 0.0, 10.0));  // ID 5 (距離 100m)
    mobility.SetPositionAllocator(pos);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    // 為每架無人機設定 MAC 位址並啟動 App
    for (int i = 0; i < numNodes; i++) {
        Ptr<LrWpanNetDevice> dev = DynamicCast<LrWpanNetDevice>(devices.Get(i));
        
        // 設定 Short Address (例如 "00:00", "00:01", "00:02"...)
        char macStr[16];
        snprintf(macStr, sizeof(macStr), "00:%02x", i);
        dev->GetMac()->SetShortAddress(Mac16Address(macStr));

        Ptr<SwarmSchedulerApp> app = CreateObject<SwarmSchedulerApp>();
        app->Setup(dev, i);
        nodes.Get(i)->AddApplication(app);
        app->SetStartTime(Seconds(0.0));
        app->SetStopTime(Seconds(0.1)); // 模擬 10 個循環 (100ms)
    }

    std::cout << "Starting Simulation for 100ms (10 cycles of 10ms)..." << std::endl;
    Simulator::Stop(Seconds(0.1));
    Simulator::Run();
    Simulator::Destroy();

    return 0;
}
