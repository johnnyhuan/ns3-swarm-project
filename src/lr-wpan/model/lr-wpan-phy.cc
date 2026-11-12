/*
 * Copyright (c) 2011 The Boeing Company
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Author:
 *  Gary Pei <guangyu.pei@boeing.com>
 *  Sascha Alexander Jopen <jopen@cs.uni-bonn.de>
 */
#include "lr-wpan-phy.h"

#include "lr-wpan-constants.h"
#include "lr-wpan-error-model.h"
#include "lr-wpan-lqi-tag.h"
#include "lr-wpan-net-device.h"
#include "lr-wpan-spectrum-signal-parameters.h"
#include "lr-wpan-spectrum-value-helper.h"

#include "ns3/abort.h"
#include "ns3/antenna-model.h"
#include "ns3/double.h"
#include "ns3/error-model.h"
#include "ns3/log.h"
#include "ns3/mobility-model.h"
#include "ns3/net-device.h"
#include "ns3/node.h"
#include "ns3/packet-burst.h"
#include "ns3/packet.h"
#include "ns3/pointer.h"
#include "ns3/random-variable-stream.h"
#include "ns3/simulator.h"
#include "ns3/spectrum-channel.h"
#include "ns3/spectrum-value.h"

#include <array>

namespace ns3
{
namespace lrwpan
{

NS_LOG_COMPONENT_DEFINE("LrWpanPhy");
NS_OBJECT_ENSURE_REGISTERED(LrWpanPhy);

/**
 * The data and symbol rates for the different PHY options.
 * See Table 1 in section 6.1.1 IEEE 802.15.4-2006, IEEE 802.15.4c-2009, IEEE 802.15.4d-2009.
 * You can check also Table 66 of 802.15.4-2011.
 * Bit rate is in kbit/s.  Symbol rate is in ksymbol/s.
 * The index follows LrWpanPhyOption (kb/s and ksymbol/s)
 */
constexpr std::array<PhyDataAndSymbolRates, 10> dataSymbolRates{{
    {20.0, 20.0},  // IEEE_802_15_4_868MHZ_BPSK
    {40.0, 40.0},  // IEEE_802_15_4_915MHZ_BPSK
    {20.0, 20.0},  // IEEE_802_15_4_950MHZ_BPSK
    {250.0, 12.5}, // IEEE_802_15_4_868MHZ_ASK
    {250.0, 50.0}, // IEEE_802_15_4_915MHZ_ASK
    {250.0, 62.5}, // IEEE_802_15_4_780MHZ_OQPSK
    {100.0, 25.0}, // IEEE_802_15_4_868MHZ_OQPSK
    {250.0, 62.5}, // IEEE_802_15_4_915MHZ_OQPSK
    {2000.0, 62.5}, // IEEE_802_15_4_2_4GHZ_OQPSK: 2 Mbps bit rate, standard 62.5 ksym/s for stable CSMA CCA
    {0, 0},        // IEEE_802_15_4_INVALID_PHY_OPTION
}};

/**
 * The preamble, SFD, and PHR lengths in symbols for the different PHY options.
 * See Table 19 and Table 20 in section 6.3 IEEE 802.15.4-2006, IEEE 802.15.4c-2009, IEEE
 * 802.15.4d-2009.
 * The PHR is 1 octet and it follows phySymbolsPerOctet in Table 23.
 * The index follows LrWpanPhyOption.
 */
constexpr std::array<PhyPpduHeaderSymbolNumber, 10> ppduHeaderSymbolNumbers{{
    {32.0, 8.0, 8.0}, // IEEE_802_15_4_868MHZ_BPSK
    {32.0, 8.0, 8.0}, // IEEE_802_15_4_915MHZ_BPSK
    {32.0, 8.0, 8.0}, // IEEE_802_15_4_950MHZ_BPSK
    {2.0, 1.0, 0.4},  // IEEE_802_15_4_868MHZ_ASK
    {6.0, 1.0, 1.6},  // IEEE_802_15_4_915MHZ_ASK
    {8.0, 2.0, 2.0},  // IEEE_802_15_4_780MHZ_OQPSK
    {8.0, 2.0, 2.0},  // IEEE_802_15_4_868MHZ_OQPSK
    {8.0, 2.0, 2.0},  // IEEE_802_15_4_915MHZ_OQPSK
    {8.0, 2.0, 2.0},  // IEEE_802_15_4_2_4GHZ_OQPSK
    {0, 0, 0},        // IEEE_802_15_4_INVALID_PHY_OPTION
}};

/*
 * BLE 5.4 LE 2M (uncoded, 2 Mbps = 0.5 us/bit) frame timing used instead of the
 * 802.15.4 SHR/PHR symbol timing for the on-air frame.
 *   Preamble 2 B (8 us) + Access Address 4 B (16 us) = 24 us sync window
 *   PDU header 2 B = 8 us
 *   CRC-24 (3 B) replaces the 802.15.4 FCS-16 (2 B, already counted in the PSDU): +1 B = 4 us
 * CCA / backoff timing (symbol based) is unchanged.
 */
constexpr double kBleSyncUs = 24.0;
constexpr double kBlePduHeaderUs = 8.0;
constexpr double kBleCrcExtraUs = 4.0;

/*
 * BLE listen-before-talk (custom MAC; BLE itself has no CSMA):
 * CCA observation time 20 us (ETSI EN 300 328 LBT minimum, instead of 8 symbols = 128 us).
 */
constexpr double kBleCcaUs = 20.0;

/*
 * BLE 5.4 LE 2M receiver sensitivity (typical SoC, e.g. nRF52/nRF53 class: -92..-96 dBm).
 * The noise floor is derived from it: noise = sensitivity - preamble lock threshold (C/I).
 */
constexpr double kBleDefaultSensitivityDbm = -95.0;

std::ostream&
operator<<(std::ostream& os, const PhyEnumeration& state)
{
    switch (state)
    {
    case PhyEnumeration::IEEE_802_15_4_PHY_BUSY:
        os << "BUSY";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_BUSY_RX:
        os << "BUSY_RX";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_BUSY_TX:
        os << "BUSY_TX";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_FORCE_TRX_OFF:
        os << "FORCE_TRX_OFF";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_IDLE:
        os << "IDLE";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_INVALID_PARAMETER:
        os << "INVALID_PARAMETER";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_RX_ON:
        os << "RX_ON";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_SUCCESS:
        os << "SUCCESS";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_TRX_OFF:
        os << "TRX_OFF";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_TX_ON:
        os << "TX_ON";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_UNSUPPORTED_ATTRIBUTE:
        os << "UNSUPPORTED";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_READ_ONLY:
        os << "READ_ONLY";
        break;
    case PhyEnumeration::IEEE_802_15_4_PHY_UNSPECIFIED:
        os << "UNSPECIFIED";
        break;
    }
    return os;
}

std::ostream&
operator<<(std::ostream& os, const TracedValue<PhyEnumeration>& state)
{
    PhyEnumeration s = state;
    return os << s;
}

TypeId
LrWpanPhy::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::lrwpan::LrWpanPhy")
            .AddDeprecatedName("ns3::LrWpanPhy")
            .SetParent<SpectrumPhy>()
            .SetGroupName("LrWpan")
            .AddConstructor<LrWpanPhy>()
            .AddAttribute("PostReceptionErrorModel",
                          "An optional packet error model can be added to the receive "
                          "packet process after any propagation-based (SNR-based) error "
                          "models have been applied. Typically this is used to force "
                          "specific packet drops, for testing purposes.",
                          PointerValue(),
                          MakePointerAccessor(&LrWpanPhy::m_postReceptionErrorModel),
                          MakePointerChecker<ErrorModel>())
            .AddTraceSource("TrxStateValue",
                            "The state of the transceiver",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_trxState),
                            "ns3::TracedValueCallback::LrWpanPhyEnumeration")
            .AddTraceSource("TrxState",
                            "The state of the transceiver",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_trxStateLogger),
                            "ns3::lrwpan::LrWpanPhy::StateTracedCallback")
            .AddTraceSource("PhyTxBegin",
                            "Trace source indicating a packet has "
                            "begun transmitting over the channel medium",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_phyTxBeginTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxEnd",
                            "Trace source indicating a packet has been "
                            "completely transmitted over the channel.",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_phyTxEndTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxDrop",
                            "Trace source indicating a packet has been "
                            "dropped by the device during transmission",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_phyTxDropTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyRxBegin",
                            "Trace source indicating a packet has begun "
                            "being received from the channel medium by the device",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_phyRxBeginTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyRxEnd",
                            "Trace source indicating a packet has been "
                            "completely received from the channel medium "
                            "by the device",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_phyRxEndTrace),
                            "ns3::Packet::SinrTracedCallback")
            .AddTraceSource("PhyRxDrop",
                            "Trace source indicating a packet has been "
                            "dropped by the device during reception",
                            MakeTraceSourceAccessor(&LrWpanPhy::m_phyRxDropTrace),
                            "ns3::Packet::TracedCallback")
            .AddAttribute("PreambleLockThreshold",
                          "SINR in dB required at the end of the preamble to lock onto a "
                          "signal (BLE 5.4 LE 2M co-channel C/I).",
                          DoubleValue(6.0),
                          MakeDoubleAccessor(&LrWpanPhy::m_preambleLockThresholdDb),
                          MakeDoubleChecker<double>());
    return tid;
}

LrWpanPhy::LrWpanPhy()
    : m_edRequest(),
      m_setTRXState(),
      m_preambleLockThresholdDb(6.0)
{
    m_trxState = IEEE_802_15_4_PHY_TRX_OFF;
    m_trxStatePending = IEEE_802_15_4_PHY_IDLE;

    // default PHY PIB attributes
    m_phyPIBAttributes.phyTransmitPower = 0;
    m_phyPIBAttributes.phyCCAMode = 1;

    SetPhyOption(IEEE_802_15_4_2_4GHZ_OQPSK);

    m_random = CreateObject<UniformRandomVariable>();
    m_random->SetAttribute("Min", DoubleValue(0.0));
    m_random->SetAttribute("Max", DoubleValue(1.0));

    m_isRxCanceled = false;
    ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
}

LrWpanPhy::~LrWpanPhy()
{
}

void
LrWpanPhy::DoInitialize()
{
    NS_LOG_FUNCTION(this);

    // This method ensures that the local mobility model pointer holds
    // a pointer to the Node's aggregated mobility model (if one exists)
    // in the case that the user has not directly called SetMobility()
    // on this LrWpanPhy during simulation setup.  If the mobility model
    // needs to be added or changed during simulation runtime, users must
    // call SetMobility() on this object.

    if (!m_mobility)
    {
        NS_ABORT_MSG_UNLESS(m_device && m_device->GetNode(),
                            "Either install a MobilityModel on this object or ensure that this "
                            "object is part of a Node and NetDevice");
        m_mobility = m_device->GetNode()->GetObject<MobilityModel>();
        if (!m_mobility)
        {
            NS_LOG_WARN("Mobility not found, propagation models might not work properly");
        }
    }
}

void
LrWpanPhy::DoDispose()
{
    NS_LOG_FUNCTION(this);

    // Cancel pending transceiver state change, if one is in progress.
    m_setTRXState.Cancel();
    m_trxState = IEEE_802_15_4_PHY_TRX_OFF;
    m_trxStatePending = IEEE_802_15_4_PHY_IDLE;

    m_mobility = nullptr;
    m_device = nullptr;
    m_channel = nullptr;
    m_antenna = nullptr;
    m_txPsd = nullptr;
    m_noise = nullptr;
    m_signal = nullptr;
    m_errorModel = nullptr;
    m_currentRxPacket.first = nullptr;
    m_currentTxPacket.first = nullptr;
    m_postReceptionErrorModel = nullptr;

    m_ccaRequest.Cancel();
    m_edRequest.Cancel();
    m_setTRXState.Cancel();
    m_pdDataRequest.Cancel();

    m_random = nullptr;
    m_pdDataIndicationCallback = MakeNullCallback<void, uint32_t, Ptr<Packet>, uint8_t, int8_t>();
    m_pdDataConfirmCallback = MakeNullCallback<void, PhyEnumeration>();
    m_plmeCcaConfirmCallback = MakeNullCallback<void, PhyEnumeration>();
    m_plmeEdConfirmCallback = MakeNullCallback<void, PhyEnumeration, uint8_t>();
    m_plmeGetAttributeConfirmCallback =
        MakeNullCallback<void, PhyEnumeration, PhyPibAttributeIdentifier, Ptr<PhyPibAttributes>>();
    m_plmeSetTRXStateConfirmCallback = MakeNullCallback<void, PhyEnumeration>();
    m_plmeSetAttributeConfirmCallback =
        MakeNullCallback<void, PhyEnumeration, PhyPibAttributeIdentifier>();

    SpectrumPhy::DoDispose();
}

Ptr<NetDevice>
LrWpanPhy::GetDevice() const
{
    return m_device;
}

Ptr<MobilityModel>
LrWpanPhy::GetMobility() const
{
    return m_mobility;
}

void
LrWpanPhy::SetDevice(Ptr<NetDevice> d)
{
    NS_LOG_FUNCTION(this << d);
    m_device = d;
}

void
LrWpanPhy::SetMobility(Ptr<MobilityModel> m)
{
    NS_LOG_FUNCTION(this << m);
    m_mobility = m;
}

void
LrWpanPhy::SetChannel(Ptr<SpectrumChannel> c)
{
    NS_LOG_FUNCTION(this << c);
    m_channel = c;
}

Ptr<SpectrumChannel>
LrWpanPhy::GetChannel()
{
    NS_LOG_FUNCTION(this);
    return m_channel;
}

Ptr<const SpectrumModel>
LrWpanPhy::GetRxSpectrumModel() const
{
    NS_LOG_FUNCTION(this);
    if (m_txPsd)
    {
        return m_txPsd->GetSpectrumModel();
    }
    else
    {
        return nullptr;
    }
}

Ptr<Object>
LrWpanPhy::GetAntenna() const
{
    return m_antenna;
}

void
LrWpanPhy::SetAntenna(Ptr<AntennaModel> a)
{
    NS_LOG_FUNCTION(this << a);
    m_antenna = a;
}

void
LrWpanPhy::StartRx(Ptr<SpectrumSignalParameters> spectrumRxParams)
{
    NS_LOG_FUNCTION(this << spectrumRxParams);

    // 0- If a packet is being received, evaluate the chunk received so far with the
    // interference that existed *before* this new signal starts.
    if (m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
    {
        CheckInterference();
    }

    // 1- Add the signal to the spectrum to keep track of the transmission regardless
    // of the origin or the state of the receiving radio.
    m_signal->AddSignal(spectrumRxParams->psd);

    // 2- Update peak power if CCA or ED if it is in progress.
    UpdateEnergyTracking();

    // 3- Check the radio is on the right state to receive (RX_ON) and that the signal
    // is a lr-wpan signal, otherwise proceed to the end of the packet to be removed from
    // the accumulated signals in the spectrum tracker.
    Ptr<LrWpanSpectrumSignalParameters> lrWpanRxParams =
        DynamicCast<LrWpanSpectrumSignalParameters>(spectrumRxParams);

    if (!lrWpanRxParams)
    {
        NS_LOG_DEBUG("Non-Lr-wpan signal, do not process");
        Simulator::Schedule(spectrumRxParams->duration, &LrWpanPhy::EndRx, this, spectrumRxParams);
        return;
    }

    if (m_trxState == IEEE_802_15_4_PHY_RX_ON)
    {
        // The reception of the lr-wpan preamble start here
        NS_LOG_INFO("Lr-wpan signal detected, processing preamble for a duration of "
                    << lrWpanRxParams->preambleDuration.GetSeconds() << " seconds");

        Simulator::Schedule(lrWpanRxParams->preambleDuration,
                            &LrWpanPhy::EndPreamble,
                            this,
                            lrWpanRxParams);
        return;
    }

    if (m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
    {
        // Already locked onto a packet: like a real BLE receiver, never re-synchronize.
        // The new packet is dropped and only acts as interference on the locked one
        // (its chunk up to now was already evaluated in step 0 above).
        Ptr<Packet> p = lrWpanRxParams->packetBurst->GetPackets().front();
        m_phyRxDropTrace(p);
        Simulator::Schedule(spectrumRxParams->duration, &LrWpanPhy::EndRx, this, spectrumRxParams);
        return;
    }

    // Radio is not in RX_ON or BUSY_RX (e.g. TX_ON, BUSY_TX, TRX_OFF)
    NS_LOG_DEBUG(this << " Radio not in RX state, currently in " << m_trxState << ", dropping packet");
    Ptr<Packet> p = lrWpanRxParams->packetBurst->GetPackets().front();
    m_phyRxDropTrace(p);
    Simulator::Schedule(spectrumRxParams->duration, &LrWpanPhy::EndRx, this, spectrumRxParams);
}

void
LrWpanPhy::EndPreamble(Ptr<LrWpanSpectrumSignalParameters> lrWpanRxParams)
{
    NS_LOG_FUNCTION(this << lrWpanRxParams);

    // If in progress, update CCA peak power or ED measurement.
    UpdateEnergyTracking();

    Ptr<Packet> p = (lrWpanRxParams->packetBurst->GetPackets()).front();
    NS_ASSERT(p);

    // Prevent PHY from receiving another packet while switching the transceiver state.
    if (m_trxState == IEEE_802_15_4_PHY_RX_ON && !m_setTRXState.IsPending())
    {
        Ptr<SpectrumValue> interferenceAndNoise = m_signal->GetSignalPsd();
        *interferenceAndNoise -= *lrWpanRxParams->psd;
        *interferenceAndNoise += *m_noise;
        double sinr =
            LrWpanSpectrumValueHelper::TotalAvgPower(lrWpanRxParams->psd,
                                                     m_phyPIBAttributes.phyCurrentChannel) /
            LrWpanSpectrumValueHelper::TotalAvgPower(interferenceAndNoise,
                                                     m_phyPIBAttributes.phyCurrentChannel);

        // Figure out if packet is decodable based on SINR.
        // Preamble & Sync Word lock: SINR must exceed the BLE 5.4 LE 2M co-channel C/I
        // (default +6 dB). A weaker signal can no longer lock while a stronger one overlaps.
        if (10 * log10(sinr) > m_preambleLockThresholdDb)
        {
            ChangeTrxState(IEEE_802_15_4_PHY_BUSY_RX);

            NS_LOG_INFO("Preamble processing completed,"
                        << " initiating the reception of the rests of the packet");

            // Start tracking the packet interference
            m_currentRxPacket = std::make_pair(lrWpanRxParams, false);
            m_phyRxBeginTrace(p);

            m_rxLastUpdate = Simulator::Now();

            // Calculate RSSI
            // In theory, the RSSI calculation should be done in the PHR, not at the end
            // of the preamble. However since there is not much difference in ns-3, it
            // is done here for simplicity (We avoid doing an extra endSFD event)
            m_rssi = static_cast<int8_t>(10 * log10(LrWpanSpectrumValueHelper::TotalAvgPower(
                                                  m_signal->GetSignalPsd(),
                                                  m_phyPIBAttributes.phyCurrentChannel)) +
                                         30);
        }
        else
        {
            // The packet is *undecodable* drop it.
            m_currentRxPacket = std::make_pair(lrWpanRxParams, true);
            m_phyRxDropTrace(p);
            NS_LOG_INFO(this << " packet undecodable due to low SINR: " << 10 * log10(sinr)
                             << " dB");
        }
    }
    else if (m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
    {
        // Another packet locked first (its preamble ended earlier). No re-synchronization:
        // drop this one; it keeps acting as interference on the locked packet.
        NS_LOG_INFO(this << " Packet collision detected, dropping packet");
        m_phyRxDropTrace(p);
        CheckInterference();
    }
    else
    {
        // Transceiver not in RX_ON or BUSY_RX
        NS_LOG_DEBUG(this << " transceiver not in RX state, currently in " << m_trxState
                          << " state, dropping packet");
        m_phyRxDropTrace(p);
    }

    Time endRx = (lrWpanRxParams->duration - lrWpanRxParams->preambleDuration);
    Simulator::Schedule(endRx, &LrWpanPhy::EndRx, this, lrWpanRxParams);
}

void
LrWpanPhy::CheckInterference()
{
    // Calculate whether packet was lost.
    LrWpanSpectrumValueHelper psdHelper;
    Ptr<LrWpanSpectrumSignalParameters> currentRxParams = m_currentRxPacket.first;

    // We are currently receiving a packet.
    if (m_trxState == IEEE_802_15_4_PHY_BUSY_RX && currentRxParams)
    {
        // NS_ASSERT (currentRxParams && !m_currentRxPacket.second);

        Ptr<Packet> currentPacket = currentRxParams->packetBurst->GetPackets().front();

        // BLE 5.4 LE 2M GFSK has no spreading gain: if the SINR during any part of the
        // packet falls below the co-channel C/I (same threshold as the preamble lock),
        // bits are corrupted and the CRC-24 check fails -> the whole packet is lost.
        if (Simulator::Now() > m_rxLastUpdate)
        {
            Ptr<SpectrumValue> interferenceAndNoise = m_signal->GetSignalPsd();
            *interferenceAndNoise -= *currentRxParams->psd;
            *interferenceAndNoise += *m_noise;
            double sinr =
                LrWpanSpectrumValueHelper::TotalAvgPower(currentRxParams->psd,
                                                         m_phyPIBAttributes.phyCurrentChannel) /
                LrWpanSpectrumValueHelper::TotalAvgPower(interferenceAndNoise,
                                                         m_phyPIBAttributes.phyCurrentChannel);

            LrWpanLqiTag tag(std::numeric_limits<uint8_t>::max());
            currentPacket->PeekPacketTag(tag);
            if (10.0 * log10(sinr) < m_preambleLockThresholdDb)
            {
                // The packet was destroyed, drop the packet after reception.
                m_currentRxPacket.second = true;
                tag.Set(0);
            }
            currentPacket->ReplacePacketTag(tag);
        }
    }
    m_rxLastUpdate = Simulator::Now();
}

void
LrWpanPhy::UpdateEnergyTracking()
{
    // Update CCA peak power
    if (!m_ccaRequest.IsExpired())
    {
        double power =
            LrWpanSpectrumValueHelper::TotalAvgPower(m_signal->GetSignalPsd(),
                                                     m_phyPIBAttributes.phyCurrentChannel);
        if (m_ccaPeakPower < power)
        {
            m_ccaPeakPower = power;
            NS_LOG_DEBUG("Updating CCA peak power " << WToDbm(power) << " dBm");
        }
    }

    if (!m_edRequest.IsExpired())
    {
        // Update the average receive power during ED.
        Time now = Simulator::Now();
        m_edPower.averagePower +=
            LrWpanSpectrumValueHelper::TotalAvgPower(m_signal->GetSignalPsd(),
                                                     m_phyPIBAttributes.phyCurrentChannel) *
            (now - m_edPower.lastUpdate).GetTimeStep() / m_edPower.measurementLength.GetTimeStep();
        m_edPower.lastUpdate = now;
    }
}

void
LrWpanPhy::EndRx(Ptr<SpectrumSignalParameters> par)
{
    NS_LOG_FUNCTION(this << "End of packet signal after a duration: " << par->duration.GetSeconds()
                         << " seconds");

    Ptr<LrWpanSpectrumSignalParameters> params = DynamicCast<LrWpanSpectrumSignalParameters>(par);

    // Update peak power if CCA or ED if it is in progress.
    UpdateEnergyTracking();

    Ptr<LrWpanSpectrumSignalParameters> currentRxParams = m_currentRxPacket.first;
    // Evaluate the locked packet up to now before any signal leaves the channel, so that an
    // interferer ending mid-packet is accounted for over exactly the time it was present.
    CheckInterference();

    // The packet reception has ended, remove it from the accumulated signals
    // in the receptor tracker
    m_signal->RemoveSignal(par->psd);

    if (!params)
    {
        NS_LOG_LOGIC("Node: " << m_device->GetAddress()
                              << " Removing interferent: " << *(par->psd));
        return;
    }

    // If this is the end of the currently received packet, check if reception was successful.
    if (currentRxParams == params)
    {
        Ptr<Packet> currentPacket = currentRxParams->packetBurst->GetPackets().front();
        NS_ASSERT(currentPacket);

        if (m_postReceptionErrorModel &&
            m_postReceptionErrorModel->IsCorrupt(currentPacket->Copy()))
        {
            NS_LOG_DEBUG("Reception failed due to post-rx error model");
            m_currentRxPacket.second = true;
        }

        // If there is no error model attached to the PHY, we always report the maximum LQI value.
        LrWpanLqiTag tag(std::numeric_limits<uint8_t>::max());
        currentPacket->PeekPacketTag(tag);
        m_phyRxEndTrace(currentPacket, tag.Get());

        if (!m_currentRxPacket.second)
        {
            m_currentRxPacket = std::make_pair(nullptr, true);
            ChangeTrxState(IEEE_802_15_4_PHY_RX_ON);

            NS_LOG_INFO(" Packet successfully received,"
                        << "passing received packet to upper layer");

            // The packet was successfully received, push it up the stack.
            if (!m_pdDataIndicationCallback.IsNull())
            {
                m_pdDataIndicationCallback(currentPacket->GetSize(),
                                           currentPacket,
                                           tag.Get(),
                                           m_rssi);
            }
        }
        else
        {
            // The packet was destroyed due to interference, post-rx corruption or
            // cancelled, therefore drop it.
            m_phyRxDropTrace(currentPacket);
            m_currentRxPacket = std::make_pair(nullptr, true);

            if (!m_isRxCanceled)
            {
                ChangeTrxState(IEEE_802_15_4_PHY_RX_ON);
            }
            else
            {
                // The state of The PHY was already changed when the packet was canceled
                // due to a forced operation.
                m_isRxCanceled = false;
            }
        }
    }
}

void
LrWpanPhy::PdDataRequest(const uint32_t psduLength, Ptr<Packet> p)
{
    NS_LOG_FUNCTION(this << psduLength << p);

    if (psduLength > lrwpan::aMaxPhyPacketSize)
    {
        if (!m_pdDataConfirmCallback.IsNull())
        {
            m_pdDataConfirmCallback(IEEE_802_15_4_PHY_UNSPECIFIED);
        }
        NS_LOG_DEBUG("Drop packet because psduLength too long: " << psduLength);
        return;
    }

    // Prevent PHY from sending a packet while switching the transceiver state.
    if (!m_setTRXState.IsPending())
    {
        if (m_trxState == IEEE_802_15_4_PHY_TX_ON)
        {
            // send down
            NS_ASSERT(m_channel);

            // Remove a possible LQI tag from a previous transmission of the packet.
            LrWpanLqiTag lqiTag;
            p->RemovePacketTag(lqiTag);

            m_phyTxBeginTrace(p);
            m_currentTxPacket.first = p;
            m_currentTxPacket.second = false;

            Ptr<LrWpanSpectrumSignalParameters> txParams = Create<LrWpanSpectrumSignalParameters>();
            txParams->duration = CalculateTxTime(p);

            // BLE 5.4 LE 2M: preamble + Access Address sync window (24 us)
            txParams->preambleDuration = GetSyncDuration();

            txParams->txPhy = GetObject<SpectrumPhy>();
            txParams->psd = m_txPsd;
            txParams->txAntenna = m_antenna;
            Ptr<PacketBurst> pb = CreateObject<PacketBurst>();
            pb->AddPacket(p);
            txParams->packetBurst = pb;
            m_channel->StartTx(txParams);
            m_pdDataRequest = Simulator::Schedule(txParams->duration, &LrWpanPhy::EndTx, this);
            ChangeTrxState(IEEE_802_15_4_PHY_BUSY_TX);
            return;
        }
        else if ((m_trxState == IEEE_802_15_4_PHY_RX_ON) ||
                 (m_trxState == IEEE_802_15_4_PHY_TRX_OFF) ||
                 (m_trxState == IEEE_802_15_4_PHY_BUSY_TX))
        {
            if (!m_pdDataConfirmCallback.IsNull())
            {
                m_pdDataConfirmCallback(m_trxState);
            }
            // Drop packet, hit PhyTxDrop trace
            m_phyTxDropTrace(p);
            return;
        }
        else
        {
            NS_FATAL_ERROR("This should be unreachable, or else state "
                           << m_trxState << " should be added as a case");
        }
    }
    else
    {
        // TODO: This error code is not covered by the standard.
        // What is the correct behavior in this case?
        if (!m_pdDataConfirmCallback.IsNull())
        {
            m_pdDataConfirmCallback(IEEE_802_15_4_PHY_UNSPECIFIED);
        }
        // Drop packet, hit PhyTxDrop trace
        m_phyTxDropTrace(p);
        return;
    }
}

void
LrWpanPhy::PlmeCcaRequest()
{
    NS_LOG_FUNCTION(this);

    if (m_trxState == IEEE_802_15_4_PHY_RX_ON || m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
    {
        m_ccaPeakPower = 0.0;
        Time ccaTime = GetCcaDuration(); // BLE LBT: 20 us
        m_ccaRequest = Simulator::Schedule(ccaTime, &LrWpanPhy::EndCca, this);
    }
    else
    {
        if (!m_plmeCcaConfirmCallback.IsNull())
        {
            if (m_trxState == IEEE_802_15_4_PHY_TRX_OFF)
            {
                m_plmeCcaConfirmCallback(IEEE_802_15_4_PHY_TRX_OFF);
            }
            else
            {
                m_plmeCcaConfirmCallback(IEEE_802_15_4_PHY_BUSY);
            }
        }
    }
}

void
LrWpanPhy::CcaCancel()
{
    NS_LOG_FUNCTION(this);
    m_ccaRequest.Cancel();
}

void
LrWpanPhy::PlmeEdRequest()
{
    NS_LOG_FUNCTION(this);
    if (m_trxState == IEEE_802_15_4_PHY_RX_ON || m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
    {
        // Average over the powers of all signals received until EndEd()
        m_edPower.averagePower = 0;
        m_edPower.lastUpdate = Simulator::Now();
        m_edPower.measurementLength = Seconds(8.0 / GetDataOrSymbolRate(false));
        m_edRequest = Simulator::Schedule(m_edPower.measurementLength, &LrWpanPhy::EndEd, this);
    }
    else
    {
        PhyEnumeration result = m_trxState;
        if (m_trxState == IEEE_802_15_4_PHY_BUSY_TX)
        {
            result = IEEE_802_15_4_PHY_TX_ON;
        }

        if (!m_plmeEdConfirmCallback.IsNull())
        {
            m_plmeEdConfirmCallback(result, 0);
        }
    }
}

void
LrWpanPhy::PlmeGetAttributeRequest(PhyPibAttributeIdentifier id)
{
    NS_LOG_FUNCTION(this << id);
    PhyEnumeration status = IEEE_802_15_4_PHY_SUCCESS;
    Ptr<PhyPibAttributes> attributes = Create<PhyPibAttributes>();

    switch (id)
    {
    case phyCurrentChannel:
        attributes->phyCurrentChannel = m_phyPIBAttributes.phyCurrentChannel;
        break;
    case phyCurrentPage:
        attributes->phyCurrentPage = m_phyPIBAttributes.phyCurrentPage;
        break;
    case phySHRDuration:
        attributes->phySHRDuration = GetPhySHRDuration();
        break;
    case phySymbolsPerOctet:
        attributes->phySymbolsPerOctet = GetPhySymbolsPerOctet();
        break;
    default:
        status = IEEE_802_15_4_PHY_UNSUPPORTED_ATTRIBUTE;
        break;
    }

    if (!m_plmeGetAttributeConfirmCallback.IsNull())
    {
        m_plmeGetAttributeConfirmCallback(status, id, attributes);
    }
}

// Section 6.2.2.7.3
void
LrWpanPhy::PlmeSetTRXStateRequest(PhyEnumeration state)
{
    NS_LOG_FUNCTION(this << state);

    // Check valid states (Table 14)
    NS_ABORT_IF((state != IEEE_802_15_4_PHY_RX_ON) && (state != IEEE_802_15_4_PHY_TRX_OFF) &&
                (state != IEEE_802_15_4_PHY_FORCE_TRX_OFF) && (state != IEEE_802_15_4_PHY_TX_ON));

    NS_LOG_LOGIC("Trying to set m_trxState from " << m_trxState << " to " << state);

    // this method always overrides previous state setting attempts
    if (!m_setTRXState.IsExpired())
    {
        if (m_trxStatePending == state)
        {
            // Simply wait for the ongoing state switch.
            return;
        }
        else
        {
            NS_LOG_DEBUG("Cancel m_setTRXState");
            // Keep the transceiver state as the old state before the switching attempt.
            m_setTRXState.Cancel();
        }
    }
    if (m_trxStatePending != IEEE_802_15_4_PHY_IDLE)
    {
        m_trxStatePending = IEEE_802_15_4_PHY_IDLE;
    }

    if (state == m_trxState)
    {
        if (!m_plmeSetTRXStateConfirmCallback.IsNull())
        {
            m_plmeSetTRXStateConfirmCallback(state);
        }
        return;
    }

    if (((state == IEEE_802_15_4_PHY_RX_ON) || (state == IEEE_802_15_4_PHY_TRX_OFF)) &&
        (m_trxState == IEEE_802_15_4_PHY_BUSY_TX))
    {
        NS_LOG_DEBUG("Phy is busy; setting state pending to " << state);
        m_trxStatePending = state;
        return; // Send PlmeSetTRXStateConfirm later
    }

    // specification talks about being in RX_ON and having received
    // a valid SFD.  Here, we are not modelling at that level of
    // granularity, so we just test for BUSY_RX state (any part of
    // a packet being actively received)
    if (state == IEEE_802_15_4_PHY_TRX_OFF)
    {
        if ((m_trxState == IEEE_802_15_4_PHY_BUSY_RX) && (m_currentRxPacket.first) &&
            (!m_currentRxPacket.second))
        {
            NS_LOG_DEBUG("Receiver has valid SFD; defer state change");
            m_trxStatePending = state;
            return; // Send PlmeSetTRXStateConfirm later
        }
        else if (m_trxState == IEEE_802_15_4_PHY_RX_ON || m_trxState == IEEE_802_15_4_PHY_TX_ON)
        {
            CancelEd(state);
            ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
            if (!m_plmeSetTRXStateConfirmCallback.IsNull())
            {
                m_plmeSetTRXStateConfirmCallback(state);
            }
            return;
        }
    }

    if (state == IEEE_802_15_4_PHY_TX_ON)
    {
        CancelEd(state);

        NS_LOG_DEBUG("turn on PHY_TX_ON");
        if ((m_trxState == IEEE_802_15_4_PHY_BUSY_RX) || (m_trxState == IEEE_802_15_4_PHY_RX_ON))
        {
            if (m_currentRxPacket.first)
            {
                // TX_ON is being forced during a reception (For example, when a ACK or Beacon is
                // issued) The current RX frame is marked as incomplete and the reception as
                // canceled EndRx () will handle the rest accordingly
                NS_LOG_DEBUG("force TX_ON, terminate reception");
                m_currentRxPacket.second = true;
                m_isRxCanceled = true;
            }

            // If CCA is in progress, cancel CCA and return BUSY.
            if (!m_ccaRequest.IsExpired())
            {
                m_ccaRequest.Cancel();
                if (!m_plmeCcaConfirmCallback.IsNull())
                {
                    m_plmeCcaConfirmCallback(IEEE_802_15_4_PHY_BUSY);
                }
            }

            m_trxStatePending = IEEE_802_15_4_PHY_TX_ON;

            // Delay for turnaround time (BUSY_RX|RX_ON ---> TX_ON)
            // Tuned to BLE 5.4: 40 us fast PLL turnaround time (down from 192 us in 802.15.4)
            Time setTime = MicroSeconds(40);
            m_setTRXState = Simulator::Schedule(setTime, &LrWpanPhy::EndSetTRXState, this);
            return;
        }
        else if (m_trxState == IEEE_802_15_4_PHY_BUSY_TX || m_trxState == IEEE_802_15_4_PHY_TX_ON)
        {
            // We do NOT change the transceiver state here. We only report that
            // the transceiver is already in TX_ON state.
            if (!m_plmeSetTRXStateConfirmCallback.IsNull())
            {
                m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_TX_ON);
            }
            return;
        }
        else if (m_trxState == IEEE_802_15_4_PHY_TRX_OFF)
        {
            ChangeTrxState(IEEE_802_15_4_PHY_TX_ON);
            if (!m_plmeSetTRXStateConfirmCallback.IsNull())
            {
                m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_TX_ON);
            }
            return;
        }
    }

    if (state == IEEE_802_15_4_PHY_FORCE_TRX_OFF)
    {
        if (m_trxState == IEEE_802_15_4_PHY_TRX_OFF)
        {
            NS_LOG_DEBUG("force TRX_OFF, was already off");
        }
        else
        {
            NS_LOG_DEBUG("force TRX_OFF, SUCCESS");
            if (m_currentRxPacket.first)
            {
                // Terminate reception
                // Mark the packet as incomplete and reception as canceled.
                NS_LOG_DEBUG("force TRX_OFF, terminate reception");
                m_currentRxPacket.second = true;
                m_isRxCanceled = true;
            }
            bool txTerminated = false;
            if (m_trxState == IEEE_802_15_4_PHY_BUSY_TX)
            {
                NS_LOG_DEBUG("force TRX_OFF, terminate transmission");
                m_currentTxPacket.second = true;
                m_pdDataRequest.Cancel();
                m_currentTxPacket.first = nullptr;
                txTerminated = true;
            }
            ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
            // Clear any other state
            m_trxStatePending = IEEE_802_15_4_PHY_IDLE;
            if (txTerminated)
            {
                // The MAC learns about the aborted frame through PdDataConfirm and returns to
                // MAC_IDLE by itself. Do NOT also send a SUCCESS TRX confirm: the MAC is still in
                // MAC_SENDING with its packet already released and would hit NS_ASSERT(m_txPkt).
                if (!m_pdDataConfirmCallback.IsNull())
                {
                    m_pdDataConfirmCallback(IEEE_802_15_4_PHY_UNSPECIFIED);
                }
                return;
            }
        }
        if (!m_plmeSetTRXStateConfirmCallback.IsNull())
        {
            m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_SUCCESS);
        }
        return;
    }

    if (state == IEEE_802_15_4_PHY_RX_ON)
    {
        if (m_trxState == IEEE_802_15_4_PHY_TX_ON || m_trxState == IEEE_802_15_4_PHY_TRX_OFF)
        {
            // Turnaround delay
            // TODO: Does it really take aTurnaroundTime to switch the transceiver state,
            //       even when the transmitter is not busy? (6.9.1)
            m_trxStatePending = IEEE_802_15_4_PHY_RX_ON;

            // Turnaround delay: Tuned to BLE 5.4 fast PLL turnaround (40 us)
            Time setTime = MicroSeconds(40);
            m_setTRXState = Simulator::Schedule(setTime, &LrWpanPhy::EndSetTRXState, this);
            return;
        }
        else if (m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
        {
            if (!m_plmeSetTRXStateConfirmCallback.IsNull())
            {
                m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_RX_ON);
            }
            return;
        }
    }

    NS_FATAL_ERROR("Unexpected transition from state " << m_trxState << " to state " << state);
}

bool
LrWpanPhy::ChannelSupported(uint8_t channel)
{
    NS_LOG_FUNCTION(this << channel);
    bool retValue = false;

    // Bits 0-26 (27 LSB)
    if ((m_phyPIBAttributes.phyChannelsSupported[m_phyPIBAttributes.phyCurrentPage] &
         (1 << channel)) != 0)
    {
        return retValue = true;
    }
    else
    {
        return retValue;
    }
}

bool
LrWpanPhy::PageSupported(uint8_t page)
{
    NS_LOG_FUNCTION(this << +page);
    bool retValue = false;

    // TODO: Only O-QPSK 2.4GHz is supported in the LrWpanSpectrumModel
    //       we must limit the page until support for other modulation is added to the spectrum
    //       model.
    //
    NS_ABORT_MSG_UNLESS(page == 0, " Only Page 0 (2.4Ghz O-QPSK supported).");

    // IEEE 802.15.4-2006, Table 23 phyChannelsSupported   Bits 27-31  (5 MSB)
    uint8_t supportedPage = (m_phyPIBAttributes.phyChannelsSupported[page] >> 27) & (0x1F);

    if (page == supportedPage)
    {
        retValue = true;
    }

    return retValue;
}

void
LrWpanPhy::PlmeSetAttributeRequest(PhyPibAttributeIdentifier id, Ptr<PhyPibAttributes> attribute)
{
    NS_LOG_FUNCTION(this << id << attribute);
    NS_ASSERT(attribute);
    PhyEnumeration status = IEEE_802_15_4_PHY_SUCCESS;

    switch (id)
    {
    case phyCurrentPage: {
        if (!PageSupported(attribute->phyCurrentPage))
        {
            status = IEEE_802_15_4_PHY_INVALID_PARAMETER;
        }
        else if (m_phyPIBAttributes.phyCurrentPage != attribute->phyCurrentPage)
        {
            // Cancel a pending transceiver state change.
            // Switch off the transceiver.
            // TODO: Is switching off the transceiver the right choice?
            ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
            if (m_trxStatePending != IEEE_802_15_4_PHY_IDLE)
            {
                m_trxStatePending = IEEE_802_15_4_PHY_IDLE;
                m_setTRXState.Cancel();
                if (!m_plmeSetTRXStateConfirmCallback.IsNull())
                {
                    m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_TRX_OFF);
                }
            }

            // Any packet in transmission or reception will be corrupted.
            if (m_currentRxPacket.first)
            {
                m_currentRxPacket.second = true;
            }
            if (PhyIsBusy())
            {
                m_currentTxPacket.second = true;
                m_pdDataRequest.Cancel();
                m_currentTxPacket.first = nullptr;
                if (!m_pdDataConfirmCallback.IsNull())
                {
                    m_pdDataConfirmCallback(IEEE_802_15_4_PHY_UNSPECIFIED);
                }
            }

            // Changing the Page can change they current PHY in use
            // Set the correct PHY according to the Page
            if (attribute->phyCurrentPage == 0)
            {
                if (m_phyPIBAttributes.phyCurrentChannel == 0)
                {
                    // 868 MHz BPSK
                    m_phyOption = IEEE_802_15_4_868MHZ_BPSK;
                    NS_LOG_INFO("Page 0, 868 MHz BPSK PHY SET");
                }
                else if (m_phyPIBAttributes.phyCurrentChannel <= 10)
                {
                    // 915 MHz BPSK
                    m_phyOption = IEEE_802_15_4_915MHZ_BPSK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ",915 MHz BPSK PHY SET");
                }
                else if (m_phyPIBAttributes.phyCurrentChannel <= 26)
                {
                    // 2.4 GHz MHz O-QPSK
                    m_phyOption = IEEE_802_15_4_2_4GHZ_OQPSK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 2.4 Ghz O-QPSK PHY SET");
                }
            }
            else if (attribute->phyCurrentPage == 1)
            {
                if (m_phyPIBAttributes.phyCurrentChannel == 0)
                {
                    // 868 MHz ASK
                    m_phyOption = IEEE_802_15_4_868MHZ_ASK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 868 MHz ASK PHY SET");
                }
                else if (m_phyPIBAttributes.phyCurrentChannel <= 10)
                {
                    // 915 MHz ASK
                    m_phyOption = IEEE_802_15_4_915MHZ_ASK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 915 MHz ASK PHY SET");
                }
                else
                {
                    // No longer valid channel
                    m_phyOption = IEEE_802_15_4_868MHZ_ASK;
                    m_phyPIBAttributes.phyCurrentChannel = 0;
                    NS_LOG_INFO("Channel no longer valid in new page "
                                << (uint32_t)attribute->phyCurrentPage
                                << ", setting new default channel "
                                << (uint32_t)m_phyPIBAttributes.phyCurrentChannel);
                    NS_LOG_INFO("868 MHz ASK PHY SET");
                }
            }
            else if (attribute->phyCurrentPage == 2)
            {
                if (m_phyPIBAttributes.phyCurrentChannel == 0)
                {
                    // 868 MHz O-QPSK
                    m_phyOption = IEEE_802_15_4_868MHZ_OQPSK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 868 MHz O-QPSK PHY SET");
                }
                else if (m_phyPIBAttributes.phyCurrentChannel <= 10)
                {
                    // 915 MHz O-QPSK
                    m_phyOption = IEEE_802_15_4_915MHZ_OQPSK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 915 MHz O-QPSK PHY SET");
                }
                else
                {
                    // No longer valid channel
                    m_phyOption = IEEE_802_15_4_868MHZ_OQPSK;
                    m_phyPIBAttributes.phyCurrentChannel = 0;
                    NS_LOG_INFO("Channel no longer valid in new page "
                                << (uint32_t)attribute->phyCurrentPage
                                << ", setting new default channel "
                                << (uint32_t)m_phyPIBAttributes.phyCurrentChannel);
                    NS_LOG_INFO("868 MHz O-QPSK PHY SET");
                }
            }
            else if (attribute->phyCurrentPage == 5)
            {
                if (m_phyPIBAttributes.phyCurrentChannel <= 3)
                {
                    // 780 MHz O-QPSK
                    m_phyOption = IEEE_802_15_4_780MHZ_OQPSK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 915 MHz O-QPSK PHY SET");
                }
                else
                {
                    // No longer valid channel
                    m_phyOption = IEEE_802_15_4_780MHZ_OQPSK;
                    m_phyPIBAttributes.phyCurrentChannel = 0;
                    NS_LOG_INFO("Channel no longer valid in new page "
                                << (uint32_t)attribute->phyCurrentPage
                                << ", setting new default channel "
                                << (uint32_t)m_phyPIBAttributes.phyCurrentChannel);
                    NS_LOG_INFO("780 MHz O-QPSK PHY SET");
                }
            }
            else if (attribute->phyCurrentPage == 6)
            {
                if (m_phyPIBAttributes.phyCurrentChannel <= 9)
                {
                    // 950 MHz BPSK
                    m_phyOption = IEEE_802_15_4_950MHZ_BPSK;
                    NS_LOG_INFO("Page " << (uint32_t)attribute->phyCurrentPage
                                        << ", 950 MHz BPSK PHY SET");
                }
                else
                {
                    m_phyOption = IEEE_802_15_4_950MHZ_BPSK;
                    m_phyPIBAttributes.phyCurrentChannel = 0;
                    NS_LOG_INFO("Channel no longer valid in new page "
                                << (uint32_t)attribute->phyCurrentPage
                                << ", setting new default channel "
                                << (uint32_t)m_phyPIBAttributes.phyCurrentChannel);
                    NS_LOG_INFO("950 MHz BPSK PHY SET");
                }
            }

            m_phyPIBAttributes.phyCurrentPage = attribute->phyCurrentPage;

            // BLE 5.4 LE 2M default receiver sensitivity
            SetRxSensitivity(kBleDefaultSensitivityDbm);
        }
        break;
    }
    case phyCurrentChannel: {
        if (!ChannelSupported(attribute->phyCurrentChannel))
        {
            status = IEEE_802_15_4_PHY_INVALID_PARAMETER;
        }
        if (m_phyPIBAttributes.phyCurrentChannel != attribute->phyCurrentChannel)
        {
            // Cancel a pending transceiver state change.
            // Switch off the transceiver.
            // TODO: Is switching off the transceiver the right choice?
            ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
            if (m_trxStatePending != IEEE_802_15_4_PHY_IDLE)
            {
                m_trxStatePending = IEEE_802_15_4_PHY_IDLE;
                m_setTRXState.Cancel();
                if (!m_plmeSetTRXStateConfirmCallback.IsNull())
                {
                    m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_TRX_OFF);
                }
            }

            // Any packet in transmission or reception will be corrupted.
            if (m_currentRxPacket.first)
            {
                m_currentRxPacket.second = true;
            }
            if (PhyIsBusy())
            {
                m_currentTxPacket.second = true;
                m_pdDataRequest.Cancel();
                m_currentTxPacket.first = nullptr;
                if (!m_pdDataConfirmCallback.IsNull())
                {
                    m_pdDataConfirmCallback(IEEE_802_15_4_PHY_UNSPECIFIED);
                }
            }

            m_phyPIBAttributes.phyCurrentChannel = attribute->phyCurrentChannel;

            // use the prev configured sensitivity before changing the channel
            SetRxSensitivity(WToDbm(m_rxSensitivity));
        }
        break;
    }
    case phyChannelsSupported: { // only the first element is considered in the array
        if ((attribute->phyChannelsSupported[0] & 0xf8000000) != 0)
        { // 5 MSBs reserved
            status = IEEE_802_15_4_PHY_INVALID_PARAMETER;
        }
        else
        {
            m_phyPIBAttributes.phyChannelsSupported[0] = attribute->phyChannelsSupported[0];
        }
        break;
    }
    case phyTransmitPower: {
        if (attribute->phyTransmitPower & 0xC0)
        {
            NS_LOG_LOGIC("LrWpanPhy::PlmeSetAttributeRequest error - can not change read-only "
                         "attribute bits.");
            status = IEEE_802_15_4_PHY_INVALID_PARAMETER;
        }
        else
        {
            m_phyPIBAttributes.phyTransmitPower = attribute->phyTransmitPower;
            LrWpanSpectrumValueHelper psdHelper;
            m_txPsd = psdHelper.CreateTxPowerSpectralDensity(
                GetNominalTxPowerFromPib(m_phyPIBAttributes.phyTransmitPower),
                m_phyPIBAttributes.phyCurrentChannel);
        }
        break;
    }
    case phyCCAMode: {
        if ((attribute->phyCCAMode < 1) || (attribute->phyCCAMode > 3))
        {
            status = IEEE_802_15_4_PHY_INVALID_PARAMETER;
        }
        else
        {
            m_phyPIBAttributes.phyCCAMode = attribute->phyCCAMode;
        }
        break;
    }
    default: {
        status = IEEE_802_15_4_PHY_UNSUPPORTED_ATTRIBUTE;
        break;
    }
    }

    if (!m_plmeSetAttributeConfirmCallback.IsNull())
    {
        m_plmeSetAttributeConfirmCallback(status, id);
    }
}

void
LrWpanPhy::SetPdDataIndicationCallback(PdDataIndicationCallback c)
{
    NS_LOG_FUNCTION(this);
    m_pdDataIndicationCallback = c;
}

void
LrWpanPhy::SetPdDataConfirmCallback(PdDataConfirmCallback c)
{
    NS_LOG_FUNCTION(this);
    m_pdDataConfirmCallback = c;
}

void
LrWpanPhy::SetPlmeCcaConfirmCallback(PlmeCcaConfirmCallback c)
{
    NS_LOG_FUNCTION(this);
    m_plmeCcaConfirmCallback = c;
}

void
LrWpanPhy::SetPlmeEdConfirmCallback(PlmeEdConfirmCallback c)
{
    NS_LOG_FUNCTION(this);
    m_plmeEdConfirmCallback = c;
}

void
LrWpanPhy::SetPlmeGetAttributeConfirmCallback(PlmeGetAttributeConfirmCallback c)
{
    NS_LOG_FUNCTION(this);
    m_plmeGetAttributeConfirmCallback = c;
}

void
LrWpanPhy::SetPlmeSetTRXStateConfirmCallback(PlmeSetTRXStateConfirmCallback c)
{
    NS_LOG_FUNCTION(this);
    m_plmeSetTRXStateConfirmCallback = c;
}

void
LrWpanPhy::SetPlmeSetAttributeConfirmCallback(PlmeSetAttributeConfirmCallback c)
{
    NS_LOG_FUNCTION(this);
    m_plmeSetAttributeConfirmCallback = c;
}

void
LrWpanPhy::ChangeTrxState(PhyEnumeration newState)
{
    NS_LOG_LOGIC(this << " state: " << m_trxState << " -> " << newState);

    m_trxStateLogger(Simulator::Now(), m_trxState, newState);
    m_trxState = newState;

    if (newState == PhyEnumeration::IEEE_802_15_4_PHY_RX_ON &&
        m_trxStatePending == PhyEnumeration::IEEE_802_15_4_PHY_TRX_OFF)
    {
        // The MAC is set on RxOnWhenIdle = false, therefore when need to turn off
        // the radio
        NS_LOG_DEBUG("Turning off radio, appliying pending state");
        ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
    }
}

bool
LrWpanPhy::PhyIsBusy() const
{
    NS_LOG_FUNCTION(this << m_trxState);
    return ((m_trxState == IEEE_802_15_4_PHY_BUSY_TX) ||
            (m_trxState == IEEE_802_15_4_PHY_BUSY_RX) || (m_trxState == IEEE_802_15_4_PHY_BUSY));
}

void
LrWpanPhy::CancelEd(PhyEnumeration state)
{
    NS_LOG_FUNCTION(this);
    NS_ASSERT(state == IEEE_802_15_4_PHY_TRX_OFF || state == IEEE_802_15_4_PHY_TX_ON);

    if (!m_edRequest.IsExpired())
    {
        m_edRequest.Cancel();
        if (!m_plmeEdConfirmCallback.IsNull())
        {
            m_plmeEdConfirmCallback(state, 0);
        }
    }
}

void
LrWpanPhy::EndEd()
{
    NS_LOG_FUNCTION(this);

    m_edPower.averagePower +=
        LrWpanSpectrumValueHelper::TotalAvgPower(m_signal->GetSignalPsd(),
                                                 m_phyPIBAttributes.phyCurrentChannel) *
        (Simulator::Now() - m_edPower.lastUpdate).GetTimeStep() /
        m_edPower.measurementLength.GetTimeStep();

    uint8_t energyLevel;

    // Per IEEE802.15.4-2006 sec 6.9.7
    double ratio = m_edPower.averagePower / m_rxSensitivity;
    ratio = 10.0 * log10(ratio);
    if (ratio <= 10.0)
    { // less than 10 dB
        energyLevel = 0;
    }
    else if (ratio >= 40.0)
    { // less than 40 dB
        energyLevel = 255;
    }
    else
    {
        // in-between with linear increase per sec 6.9.7
        energyLevel = static_cast<uint8_t>(((ratio - 10.0) / 30.0) * 255.0);
    }

    if (!m_plmeEdConfirmCallback.IsNull())
    {
        m_plmeEdConfirmCallback(IEEE_802_15_4_PHY_SUCCESS, energyLevel);
    }
}

void
LrWpanPhy::EndCca()
{
    NS_LOG_FUNCTION(this);
    PhyEnumeration sensedChannelState = IEEE_802_15_4_PHY_UNSPECIFIED;

    // Update peak power.
    double power = LrWpanSpectrumValueHelper::TotalAvgPower(m_signal->GetSignalPsd(),
                                                            m_phyPIBAttributes.phyCurrentChannel);
    if (m_ccaPeakPower < power)
    {
        m_ccaPeakPower = power;
    }

    if (PhyIsBusy())
    {
        sensedChannelState = IEEE_802_15_4_PHY_BUSY;
    }
    else if (m_phyPIBAttributes.phyCCAMode == 1)
    { // sec 6.9.9 ED detection
        // -- ED threshold at most 10 dB above receiver sensitivity.
        if (10 * log10(m_ccaPeakPower / m_rxSensitivity) >= 10.0)
        {
            sensedChannelState = IEEE_802_15_4_PHY_BUSY;
        }
        else
        {
            sensedChannelState = IEEE_802_15_4_PHY_IDLE;
        }
    }
    else if (m_phyPIBAttributes.phyCCAMode == 2)
    {
        // sec 6.9.9 carrier sense only
        if (m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
        {
            // We currently do not model PPDU reception in detail. Instead we model
            // packet reception starting with the first bit of the preamble.
            // Therefore, this code will never be reached, as PhyIsBusy() would
            // already lead to a channel busy condition.
            // TODO: Change this, if we also model preamble and SFD detection.
            sensedChannelState = IEEE_802_15_4_PHY_BUSY;
        }
        else
        {
            sensedChannelState = IEEE_802_15_4_PHY_IDLE;
        }
    }
    else if (m_phyPIBAttributes.phyCCAMode == 3)
    { // sect 6.9.9 both
        if ((10 * log10(m_ccaPeakPower / m_rxSensitivity) >= 10.0) &&
            m_trxState == IEEE_802_15_4_PHY_BUSY_RX)
        {
            // Again, this code will never be reached, if we are already receiving
            // a packet, as PhyIsBusy() would already lead to a channel busy condition.
            // TODO: Change this, if we also model preamble and SFD detection.
            sensedChannelState = IEEE_802_15_4_PHY_BUSY;
        }
        else
        {
            sensedChannelState = IEEE_802_15_4_PHY_IDLE;
        }
    }
    else
    {
        NS_ASSERT_MSG(false, "Invalid CCA mode");
    }

    NS_LOG_LOGIC(this << "channel sensed state: " << sensedChannelState);

    if (!m_plmeCcaConfirmCallback.IsNull())
    {
        m_plmeCcaConfirmCallback(sensedChannelState);
    }
}

void
LrWpanPhy::EndSetTRXState()
{
    NS_LOG_FUNCTION(this);

    NS_ABORT_IF((m_trxStatePending != IEEE_802_15_4_PHY_RX_ON) &&
                (m_trxStatePending != IEEE_802_15_4_PHY_TX_ON));
    ChangeTrxState(m_trxStatePending);
    m_trxStatePending = IEEE_802_15_4_PHY_IDLE;

    if (!m_plmeSetTRXStateConfirmCallback.IsNull())
    {
        m_plmeSetTRXStateConfirmCallback(m_trxState);
    }
}

void
LrWpanPhy::EndTx()
{
    NS_LOG_FUNCTION(this);

    NS_ABORT_IF((m_trxState != IEEE_802_15_4_PHY_BUSY_TX) &&
                (m_trxState != IEEE_802_15_4_PHY_TRX_OFF));

    if (!m_currentTxPacket.second)
    {
        NS_LOG_DEBUG("Packet successfully transmitted");
        m_phyTxEndTrace(m_currentTxPacket.first);
        if (!m_pdDataConfirmCallback.IsNull())
        {
            m_pdDataConfirmCallback(IEEE_802_15_4_PHY_SUCCESS);
        }
    }
    else
    {
        NS_LOG_DEBUG("Packet transmission aborted");
        m_phyTxDropTrace(m_currentTxPacket.first);
        if (!m_pdDataConfirmCallback.IsNull())
        {
            // See if this is ever entered in another state
            NS_ASSERT(m_trxState == IEEE_802_15_4_PHY_TRX_OFF);
            m_pdDataConfirmCallback(m_trxState);
        }
    }
    m_currentTxPacket.first = nullptr;
    m_currentTxPacket.second = false;

    // We may be waiting to apply a pending state change.
    if (m_trxStatePending != IEEE_802_15_4_PHY_IDLE)
    {
        // Only change the state immediately, if the transceiver is not already
        // switching the state.
        if (!m_setTRXState.IsPending())
        {
            NS_LOG_LOGIC("Apply pending state change to " << m_trxStatePending);
            ChangeTrxState(m_trxStatePending);
            m_trxStatePending = IEEE_802_15_4_PHY_IDLE;
            if (!m_plmeSetTRXStateConfirmCallback.IsNull())
            {
                m_plmeSetTRXStateConfirmCallback(IEEE_802_15_4_PHY_SUCCESS);
            }
        }
    }
    else
    {
        if (m_trxState != IEEE_802_15_4_PHY_TRX_OFF)
        {
            ChangeTrxState(IEEE_802_15_4_PHY_TX_ON);
        }
    }
}

void
LrWpanPhy::AbortTx()
{
    NS_LOG_FUNCTION(this);
    if (m_trxState == IEEE_802_15_4_PHY_BUSY_TX)
    {
        NS_LOG_DEBUG("Forced slot cutoff: aborting active transmission");
        m_currentTxPacket.second = true;
        m_pdDataRequest.Cancel();
        m_currentTxPacket.first = nullptr;
        ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
        if (!m_pdDataConfirmCallback.IsNull())
        {
            m_pdDataConfirmCallback(IEEE_802_15_4_PHY_UNSPECIFIED);
        }
    }
    else if (m_trxState == IEEE_802_15_4_PHY_TX_ON)
    {
        ChangeTrxState(IEEE_802_15_4_PHY_TRX_OFF);
    }
}

PhyEnumeration
LrWpanPhy::GetTrxState() const
{
    return m_trxState;
}

Time
LrWpanPhy::CalculateTxTime(Ptr<const Packet> packet)
{
    NS_LOG_FUNCTION(this << packet);

    bool isData = true;
    Time txTime = GetPpduHeaderTxTime();

    txTime += Seconds(packet->GetSize() * 8.0 / GetDataOrSymbolRate(isData));
    txTime += MicroSeconds(kBleCrcExtraUs); // CRC-24 instead of FCS-16

    return txTime;
}

uint8_t
LrWpanPhy::GetCurrentPage() const
{
    return m_phyPIBAttributes.phyCurrentPage;
}

uint8_t
LrWpanPhy::GetCurrentChannelNum() const
{
    return m_phyPIBAttributes.phyCurrentChannel;
}

double
LrWpanPhy::GetDataOrSymbolRate(bool isData)
{
    double rate = 0.0;

    NS_ASSERT(m_phyOption < IEEE_802_15_4_INVALID_PHY_OPTION);

    if (isData)
    {
        rate = dataSymbolRates[m_phyOption].bitRate;
    }
    else
    {
        rate = dataSymbolRates[m_phyOption].symbolRate;
    }

    return (rate * 1000.0);
}

Time
LrWpanPhy::GetPpduHeaderTxTime()
{
    NS_LOG_FUNCTION(this);
    // BLE 5.4 LE 2M: preamble + Access Address (24 us) + PDU header (8 us)
    return MicroSeconds(kBleSyncUs + kBlePduHeaderUs);
}

Time
LrWpanPhy::GetSyncDuration() const
{
    return MicroSeconds(kBleSyncUs);
}

Time
LrWpanPhy::GetCcaDuration() const
{
    return MicroSeconds(kBleCcaUs);
}

void
LrWpanPhy::SetPhyOption(PhyOption phyOption)
{
    NS_LOG_FUNCTION(this);

    m_phyOption = IEEE_802_15_4_INVALID_PHY_OPTION;

    // TODO: Only O-QPSK 2.4GHz is supported in the LrWpanSpectrumModel
    //       we must limit the page until support for other modulations is added to the spectrum
    //       model.
    NS_ABORT_MSG_UNLESS(phyOption == IEEE_802_15_4_2_4GHZ_OQPSK, " Only 2.4Ghz O-QPSK supported.");

    // Set default Channel and Page
    // IEEE 802.15.4-2006 Table 2, section 6.1.1
    // IEEE 802.15.4c-2009 Table 2, section 6.1.2.2
    // IEEE 802.15.4d-2009 Table 2, section 6.1.2.2
    switch (phyOption)
    {
    case IEEE_802_15_4_868MHZ_BPSK:
        // IEEE 802.15.4-2006 868 MHz BPSK (Page 0, Channel 0)
        m_phyPIBAttributes.phyCurrentPage = 0;
        m_phyPIBAttributes.phyCurrentChannel = 0;
        break;
    case IEEE_802_15_4_915MHZ_BPSK:
        // IEEE 802.15.4-2006 915 MHz BPSK (Page 0, Channels 1 to 10)
        m_phyPIBAttributes.phyCurrentPage = 0;
        m_phyPIBAttributes.phyCurrentChannel = 1;
        break;
    case IEEE_802_15_4_950MHZ_BPSK:
        // IEEE 802.15.4d-2009 950 MHz BPSK (Page 6, Channels 0 to 9)
        m_phyPIBAttributes.phyCurrentPage = 6;
        m_phyPIBAttributes.phyCurrentChannel = 0;
        break;
    case IEEE_802_15_4_868MHZ_ASK:
        // IEEE 802.15.4-2006 868 MHz ASK (Page 1, Channel 0)
        m_phyPIBAttributes.phyCurrentPage = 1;
        m_phyPIBAttributes.phyCurrentChannel = 0;
        break;
    case IEEE_802_15_4_915MHZ_ASK:
        // IEEE 802.15.4-2006 915 MHz ASK (Page 1, Channel 1 to 10)
        m_phyPIBAttributes.phyCurrentPage = 1;
        m_phyPIBAttributes.phyCurrentChannel = 1;
        break;
    case IEEE_802_15_4_780MHZ_OQPSK:
        // IEEE 802.15.4c-2009 780 MHz O-QPSK (Page 5, Channel 0 to 3)
        m_phyPIBAttributes.phyCurrentPage = 5;
        m_phyPIBAttributes.phyCurrentChannel = 0;
        break;
    case IEEE_802_15_4_868MHZ_OQPSK:
        // IEEE 802.15.4-2006 868 MHz O-QPSK (Page 2, Channel 0)
        m_phyPIBAttributes.phyCurrentPage = 2;
        m_phyPIBAttributes.phyCurrentChannel = 0;
        break;
    case IEEE_802_15_4_915MHZ_OQPSK:
        // IEEE 802.15.4-2006 915 MHz O-QPSK (Page 2, Channels 1 to 10)
        m_phyPIBAttributes.phyCurrentPage = 2;
        m_phyPIBAttributes.phyCurrentChannel = 1;
        break;
    case IEEE_802_15_4_2_4GHZ_OQPSK:
        // IEEE 802.15.4-2009 2.4 GHz O-QPSK (Page 0, Channels 11 to 26)
        m_phyPIBAttributes.phyCurrentPage = 0;
        m_phyPIBAttributes.phyCurrentChannel = 11;
        break;
    case IEEE_802_15_4_INVALID_PHY_OPTION:
        // IEEE 802.15.4-2006 Use Non-Registered Page and channel
        m_phyPIBAttributes.phyCurrentPage = 31;
        m_phyPIBAttributes.phyCurrentChannel = 26;
        break;
    }

    NS_ASSERT(phyOption != IEEE_802_15_4_INVALID_PHY_OPTION);

    m_phyOption = phyOption;
    // TODO: Fix/Update list when more modulations are supported.
    // IEEE 802.15.4-2006, Table 23
    // 5 MSB = Page number, 27 LSB = Supported Channels (1= supported, 0 Not supported)
    // Currently only page 0, channels 11-26 supported.
    m_phyPIBAttributes.phyChannelsSupported[0] =
        0x7FFF800; // Page 0 should support, Channels 0 to 26 (0x07FFFFFF)

    for (int i = 1; i <= 31; i++)
    {
        // Page 1 to 31, No support (Page set to 31, all channels 0)
        m_phyPIBAttributes.phyChannelsSupported[i] = 0xF8000000;
    }

    m_edPower.averagePower = 0.0;
    m_edPower.lastUpdate = Seconds(0);
    m_edPower.measurementLength = Seconds(0);

    // BLE 5.4 LE 2M default receiver sensitivity
    SetRxSensitivity(kBleDefaultSensitivityDbm);

    m_rxLastUpdate = Seconds(0);
    m_currentRxPacket = std::make_pair(nullptr, true);
    m_currentTxPacket = std::make_pair(nullptr, true);
    m_errorModel = nullptr;
}

void
LrWpanPhy::SetRxSensitivity(double dbmSensitivity)
{
    NS_LOG_FUNCTION(this << dbmSensitivity << "dBm");

    // See IEEE 802.15.4-2011 Sections 10.3.4, 11.3.4, 13.3.4, 13.3.4, 14.3.4, 15.3.4
    if (m_phyOption == IEEE_802_15_4_915MHZ_BPSK || m_phyOption == IEEE_802_15_4_950MHZ_BPSK)
    {
        if (dbmSensitivity > -92)
        {
            NS_ABORT_MSG("The minimum Rx sensitivity for this band should be at least -92 dBm");
        }
    }
    else
    {
        if (dbmSensitivity > -85)
        {
            NS_ABORT_MSG("The minimum Rx sensitivity for this band should be at least -85 dBm");
        }
    }

    // BLE 5.4 LE 2M model: the sensitivity is the weakest signal that still reaches the
    // GFSK lock/C/I threshold over thermal noise, so
    //   noise floor = sensitivity - preamble lock threshold
    // e.g. -95 dBm sensitivity, 6 dB threshold -> -101 dBm noise floor.
    // Thermal noise (F = 1) over the 5 x 1 MHz bins of the channel: kT * 5 MHz = -107 dBm.
    double thermalNoiseW = 1.3803e-23 * 290.0 * 5.0e6;
    double noiseFloorDbm = dbmSensitivity - m_preambleLockThresholdDb;

    LrWpanSpectrumValueHelper psdHelper;
    m_txPsd = psdHelper.CreateTxPowerSpectralDensity(
        GetNominalTxPowerFromPib(m_phyPIBAttributes.phyTransmitPower),
        m_phyPIBAttributes.phyCurrentChannel);
    // Update thermal noise + noise factor added.
    long double noiseFactor = DbmToW(noiseFloorDbm) / thermalNoiseW;
    psdHelper.SetNoiseFactor(noiseFactor);
    m_noise = psdHelper.CreateNoisePowerSpectralDensity(m_phyPIBAttributes.phyCurrentChannel);

    m_signal = Create<LrWpanInterferenceHelper>(m_noise->GetSpectrumModel());
    // Change receiver sensitivity from dBm to Watts
    m_rxSensitivity = DbmToW(dbmSensitivity);
}

double
LrWpanPhy::GetRxSensitivity()
{
    NS_LOG_FUNCTION(this);
    // Change receiver sensitivity from Watt to dBm
    return WToDbm(m_rxSensitivity);
}

PhyOption
LrWpanPhy::GetMyPhyOption()
{
    NS_LOG_FUNCTION(this);
    return m_phyOption;
}

void
LrWpanPhy::SetTxPowerSpectralDensity(Ptr<SpectrumValue> txPsd)
{
    NS_LOG_FUNCTION(this << txPsd);
    NS_ASSERT(txPsd);
    m_txPsd = txPsd;
    NS_LOG_INFO("\t computed tx_psd: " << *txPsd << "\t stored tx_psd: " << *m_txPsd);
}

void
LrWpanPhy::SetNoisePowerSpectralDensity(Ptr<const SpectrumValue> noisePsd)
{
    NS_LOG_FUNCTION(this << noisePsd);
    NS_LOG_INFO("\t computed noise_psd: " << *noisePsd);
    NS_ASSERT(noisePsd);
    m_noise = noisePsd;
}

Ptr<const SpectrumValue>
LrWpanPhy::GetNoisePowerSpectralDensity()
{
    NS_LOG_FUNCTION(this);
    return m_noise;
}

void
LrWpanPhy::SetErrorModel(Ptr<LrWpanErrorModel> e)
{
    NS_LOG_FUNCTION(this << e);
    NS_ASSERT(e);
    m_errorModel = e;
}

Ptr<LrWpanErrorModel>
LrWpanPhy::GetErrorModel() const
{
    NS_LOG_FUNCTION(this);
    return m_errorModel;
}

uint64_t
LrWpanPhy::GetPhySHRDuration() const
{
    NS_LOG_FUNCTION(this);
    NS_ASSERT(m_phyOption < IEEE_802_15_4_INVALID_PHY_OPTION);

    return ppduHeaderSymbolNumbers[m_phyOption].shrPreamble +
           ppduHeaderSymbolNumbers[m_phyOption].shrSfd;
}

double
LrWpanPhy::GetPhySymbolsPerOctet() const
{
    NS_LOG_FUNCTION(this);
    NS_ASSERT(m_phyOption < IEEE_802_15_4_INVALID_PHY_OPTION);

    return dataSymbolRates[m_phyOption].symbolRate / (dataSymbolRates[m_phyOption].bitRate / 8);
}

double
LrWpanPhy::GetCurrentSignalPsd()
{
    double powerWatts =
        LrWpanSpectrumValueHelper::TotalAvgPower(m_signal->GetSignalPsd(),
                                                 m_phyPIBAttributes.phyCurrentChannel);
    return WToDbm(powerWatts);
}

int8_t
LrWpanPhy::GetNominalTxPowerFromPib(uint8_t phyTransmitPower)
{
    NS_LOG_FUNCTION(this << +phyTransmitPower);

    // The nominal Tx power is stored in the PIB as a 6-bit
    // twos-complement, signed number.

    // The 5 LSBs can be copied - as their representation
    // is the same for unsigned and signed integers.
    int8_t nominalTxPower = phyTransmitPower & 0x1F;

    // Now check the 6th LSB (the "sign" bit).
    // It's a twos-complement format, so the "sign"
    // bit represents -2^5 = -32.
    if (phyTransmitPower & 0x20)
    {
        nominalTxPower -= 32;
    }
    return nominalTxPower;
}

double
LrWpanPhy::WToDbm(double watt)
{
    return (10 * log10(1000 * watt));
}

double
LrWpanPhy::DbmToW(double dbm)
{
    return (pow(10.0, dbm / 10.0) / 1000.0);
}

int64_t
LrWpanPhy::AssignStreams(int64_t stream)
{
    NS_LOG_FUNCTION(this);
    m_random->SetStream(stream);
    return 1;
}

void
LrWpanPhy::SetPostReceptionErrorModel(const Ptr<ErrorModel> em)
{
    NS_LOG_FUNCTION(this << em);
    m_postReceptionErrorModel = em;
}

void
LrWpanPhy::SetPreambleLockThreshold(double thresholdDb)
{
    m_preambleLockThresholdDb = thresholdDb;
    // The noise floor is derived from sensitivity and threshold: re-apply it.
    SetRxSensitivity(WToDbm(m_rxSensitivity));
}

double
LrWpanPhy::GetPreambleLockThreshold() const
{
    return m_preambleLockThresholdDb;
}

} // namespace lrwpan
} // namespace ns3
