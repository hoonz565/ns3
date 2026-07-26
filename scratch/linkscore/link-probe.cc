/*
 * P0 — Kiểm chứng thiết bị đo (PLAN.md muc P0).
 *
 * Hai node: node 0 dung yen tai goc, node 1 bay thang ra xa voi toc do khong
 * doi. Mot lan chay quet toan dai RSSI, tu sat canh den qua diem link chet, nen
 * doi chieu duoc voi path loss tinh tay tren giay.
 *
 * KHONG co giao thuc dinh tuyen, KHONG co IP stack. Probe la unicast L2 goi
 * truc tiep bang NetDevice::Send (CLAUDE.md quy tac 12): mot probe di qua IP co
 * the bi forward sang next hop khac hoac bi drop vi thieu route, ca hai deu pha
 * viec quy frame ve dung link.
 *
 * Ba thu do duoc, ung voi ba cong nghiem thu cua P0:
 *   1. RSSI moi frame nhan duoc tai node 1  -> rx.csv   (bam duong ly thuyet?)
 *   2. So lan MAC retry tai node 0          -> tx.csv   (khac 0, khong toan bo?)
 *   3. Residual RSSI khi bat fading         -> tinh trong Python (sigma ~ 2 dB?)
 *
 * Scenario nay chi de kiem chung callback, khong sinh dataset. Feature
 * (rssi_level / rssi_slope / retry_rate) duoc dinh nghia o P2.
 *
 * Chay:
 *   ./ns3 run "scratch/linkscore/link-probe -- --fading=false --out=data/smoke/p0-nofading"
 *   ./ns3 run "scratch/linkscore/link-probe -- --fading=true  --out=data/smoke/p0-fading"
 */

#include "ns3/core-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/propagation-module.h"
#include "ns3/wifi-module.h"

#include <filesystem>
#include <fstream>
#include <iomanip>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("LinkProbeP0");

namespace
{

/// Toan bo so dem cua mot lan chay. In ra cuoi run va ghi vao meta.json.
struct Counters
{
    uint64_t sends = 0;      ///< so lan goi NetDevice::Send (tang tren)
    uint64_t attempts = 0;   ///< so PPDU data node 0 thuc su phat (ke ca retx)
    uint64_t retries = 0;    ///< MacTxDataFailed: mot lan thu that bai
    uint64_t finalFails = 0; ///< MacTxFinalDataFailed: het so lan thu, drop
    uint64_t delivered = 0;  ///< frame len duoc tang tren tai node 1
    uint64_t sniffRx = 0;    ///< frame PHY node 1 giai ma thanh cong
};

Counters g_count;
Ptr<MobilityModel> g_mobA; ///< node 0 (phat, dung yen)
Ptr<MobilityModel> g_mobB; ///< node 1 (nhan, dang bay)
std::ofstream g_rxCsv;
std::ofstream g_txCsv;

/// Kich thuoc toi thieu de tinh la frame data. ACK/RTS/CTS ~14-20 B.
/// Loc theo kich thuoc de mau so cua retry_rate khong lan frame control.
constexpr uint32_t MIN_DATA_BYTES = 100;

double
Distance()
{
    return g_mobA->GetDistanceFrom(g_mobB);
}

double
NowSec()
{
    return Simulator::Now().GetSeconds();
}

/// RSSI tai node 1. signalNoise.signal la cong suat tin hieu (dBm) do
/// InterferenceHelper tinh — day chinh la truong can doc; doc nham sang noise
/// hay sang txVector se lech hang chuc dB va cong nghiem thu 1 bat duoc ngay.
void
RxSniffer(std::string /*context*/,
          Ptr<const Packet> packet,
          uint16_t channelFreqMhz,
          WifiTxVector /*txVector*/,
          MpduInfo /*aMpdu*/,
          SignalNoiseDbm signalNoise,
          uint16_t /*staId*/)
{
    if (packet->GetSize() < MIN_DATA_BYTES)
    {
        return; // frame control, khong phai probe
    }
    g_count.sniffRx++;
    g_rxCsv << NowSec() << ',' << Distance() << ',' << signalNoise.signal << ','
            << signalNoise.noise << ',' << packet->GetSize() << ',' << channelFreqMhz << '\n';
}

/// Moi PPDU data node 0 dat len song, ke ca lan phat lai. Day la MAU SO cua
/// retry_rate = retries / attempts, lay o tang MAC chu khong suy ra tu so lan
/// goi Send() (queue co the drop truoc khi phat, va lan phat lai khong co lan
/// goi Send tuong ung).
void
TxSniffer(std::string /*context*/,
          Ptr<const Packet> packet,
          uint16_t /*channelFreqMhz*/,
          WifiTxVector /*txVector*/,
          MpduInfo /*aMpdu*/,
          uint16_t /*staId*/)
{
    if (packet->GetSize() < MIN_DATA_BYTES)
    {
        return;
    }
    g_count.attempts++;
    g_txCsv << NowSec() << ',' << Distance() << ",attempt\n";
}

void
MacTxDataFailed(std::string /*context*/, Mac48Address /*addr*/)
{
    g_count.retries++;
    g_txCsv << NowSec() << ',' << Distance() << ",retry\n";
}

void
MacTxFinalDataFailed(std::string /*context*/, Mac48Address /*addr*/)
{
    g_count.finalFails++;
    g_txCsv << NowSec() << ',' << Distance() << ",final_fail\n";
}

bool
RxUpper(Ptr<NetDevice> /*dev*/, Ptr<const Packet> /*p*/, uint16_t /*proto*/, const Address& /*from*/)
{
    g_count.delivered++;
    return true;
}

void
SendProbe(Ptr<NetDevice> dev, Address dst, uint32_t bytes, Time interval, Time stopAt)
{
    if (Simulator::Now() >= stopAt)
    {
        return;
    }
    // Ethertype thi nghiem noi bo (IEEE 802 local experimental). Khong co IP,
    // khong co ARP — dst la dia chi MAC lay truc tiep tu NetDevice ben kia.
    dev->Send(Create<Packet>(bytes), dst, 0x88b5);
    g_count.sends++;
    g_txCsv << NowSec() << ',' << Distance() << ",send\n";
    Simulator::Schedule(interval, &SendProbe, dev, dst, bytes, interval, stopAt);
}

} // namespace

int
main(int argc, char* argv[])
{
    // Mac dinh = cau hinh nominal cua CLAUDE.md, tru duong bay (rieng cua P0).
    uint32_t seed = 1;
    bool fading = true;
    double txPowerDbm = 10.0;
    double exponent = 2.2;
    uint32_t channelNumber = 36; // 5 GHz -> 5180 MHz
    std::string dataMode = "OfdmRate6Mbps";
    double m0 = 8.0;
    double m1 = 5.0;
    double m2 = 3.0;
    double nakDistance1 = 100.0;
    double nakDistance2 = 300.0;
    // Mac dinh -82 dBm la mac dinh cua ns-3 (ThresholdPreambleDetectionModel).
    // Do la mot SAN CUNG tren RSSI: frame yeu hon khong bao gio duoc detect, bat
    // ke SNR, va nam cao hon gioi han do nhieu 7 dB. Ha xuong -101 (bang
    // RxSensitivity) thi rang buoc chuyen sang Threshold (4 dB SNR), tuc dua tren
    // SNR chu khong phai mot hang so tuyet doi. De mac dinh o day; P1 chot.
    double minRssiDbm = -82.0;
    double altitude = 100.0;
    double startDist = 10.0;
    double speed = 10.0; // cham hon nominal 15-30 m/s: day mau tren truc khoang cach
    double simTime = 60.0;
    double probeIntervalMs = 10.0;
    uint32_t probeBytes = 512;
    std::string outDir = "data/smoke/p0";

    CommandLine cmd(__FILE__);
    cmd.AddValue("seed", "RngRun", seed);
    cmd.AddValue("fading", "Bat NakagamiPropagationLossModel", fading);
    cmd.AddValue("txPower", "Cong suat phat (dBm)", txPowerDbm);
    cmd.AddValue("exponent", "So mu path loss cua LogDistance", exponent);
    cmd.AddValue("channel", "So kenh 5 GHz (36 -> 5180 MHz)", channelNumber);
    cmd.AddValue("dataMode", "WifiMode cho ConstantRateWifiManager", dataMode);
    cmd.AddValue("m0", "Nakagami m khi d < distance1", m0);
    cmd.AddValue("m1", "Nakagami m khi distance1 <= d < distance2", m1);
    cmd.AddValue("m2", "Nakagami m khi d >= distance2", m2);
    cmd.AddValue("nakDistance1", "Nakagami Distance1 (m)", nakDistance1);
    cmd.AddValue("nakDistance2", "Nakagami Distance2 (m)", nakDistance2);
    cmd.AddValue("minRssi",
                 "ThresholdPreambleDetectionModel::MinimumRssi (dBm), san cung tren RSSI",
                 minRssiDbm);
    cmd.AddValue("altitude", "Do cao ca hai node (m)", altitude);
    cmd.AddValue("startDist", "Khoang cach ban dau (m)", startDist);
    cmd.AddValue("speed", "Toc do node 1 bay ra xa (m/s)", speed);
    cmd.AddValue("simTime", "Thoi gian mo phong (s)", simTime);
    cmd.AddValue("probeIntervalMs", "Chu ky probe (ms)", probeIntervalMs);
    cmd.AddValue("probeBytes", "Payload probe (B)", probeBytes);
    cmd.AddValue("out", "Thu muc ghi rx.csv / tx.csv / meta.json", outDir);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(seed);

    const double freqMhz = 5000.0 + 5.0 * channelNumber;
    // Friis tai d0 = 1 m cho dung song mang dang dung. Mac dinh cua ns-3 la
    // 46.6777 dB (tinh cho 5.15 GHz) — lech nho nhung khong co ly do de dung
    // sai tan so khi minh biet tan so that.
    const double c = 299792458.0;
    const double lambda = c / (freqMhz * 1e6);
    const double refLossDb = 20.0 * std::log10(4.0 * M_PI / lambda);

    NodeContainer nodes;
    nodes.Create(2);

    YansWifiChannelHelper channelHelper;
    channelHelper.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channelHelper.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                                     "Exponent",
                                     DoubleValue(exponent),
                                     "ReferenceDistance",
                                     DoubleValue(1.0),
                                     "ReferenceLoss",
                                     DoubleValue(refLossDb));
    if (fading)
    {
        // Thu tu quan trong: Nakagami boc ngoai LogDistance (chuoi loss model).
        channelHelper.AddPropagationLoss("ns3::NakagamiPropagationLossModel",
                                         "m0",
                                         DoubleValue(m0),
                                         "m1",
                                         DoubleValue(m1),
                                         "m2",
                                         DoubleValue(m2),
                                         "Distance1",
                                         DoubleValue(nakDistance1),
                                         "Distance2",
                                         DoubleValue(nakDistance2));
    }

    YansWifiPhyHelper phy;
    phy.SetChannel(channelHelper.Create());
    phy.Set("TxPowerStart", DoubleValue(txPowerDbm));
    phy.Set("TxPowerEnd", DoubleValue(txPowerDbm));
    phy.Set("TxPowerLevels", UintegerValue(1));
    phy.Set("ChannelSettings",
            StringValue("{" + std::to_string(channelNumber) + ", 20, BAND_5GHZ, 0}"));
    // Ghi de tuong minh, ke ca khi bang mac dinh: de gia tri nay luon xuat hien
    // trong meta.json va khong bao gio phai suy tu mac dinh cua phien ban ns-3.
    phy.SetPreambleDetectionModel("ns3::ThresholdPreambleDetectionModel",
                                  "MinimumRssi",
                                  DoubleValue(minRssiDbm));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211a);
    // CLAUDE.md quy tac 10: khong bao gio dung rate adaptation.
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue(dataMode),
                                 "ControlMode",
                                 StringValue(dataMode));

    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);

    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes.Get(0));
    mobility.SetMobilityModel("ns3::ConstantVelocityMobilityModel");
    mobility.Install(nodes.Get(1));

    g_mobA = nodes.Get(0)->GetObject<MobilityModel>();
    g_mobB = nodes.Get(1)->GetObject<MobilityModel>();
    g_mobA->SetPosition(Vector(0.0, 0.0, altitude));
    g_mobB->SetPosition(Vector(startDist, 0.0, altitude));
    nodes.Get(1)->GetObject<ConstantVelocityMobilityModel>()->SetVelocity(
        Vector(speed, 0.0, 0.0));

    std::filesystem::create_directories(outDir);
    g_rxCsv.open(outDir + "/rx.csv");
    g_txCsv.open(outDir + "/tx.csv");
    g_rxCsv << std::fixed << std::setprecision(6);
    g_txCsv << std::fixed << std::setprecision(6);
    g_rxCsv << "t_s,dist_m,rssi_dbm,noise_dbm,size_b,freq_mhz\n";
    g_txCsv << "t_s,dist_m,event\n";

    Config::Connect("/NodeList/1/DeviceList/0/$ns3::WifiNetDevice/Phy/MonitorSnifferRx",
                    MakeCallback(&RxSniffer));
    Config::Connect("/NodeList/0/DeviceList/0/$ns3::WifiNetDevice/Phy/MonitorSnifferTx",
                    MakeCallback(&TxSniffer));
    Config::Connect(
        "/NodeList/0/DeviceList/0/$ns3::WifiNetDevice/RemoteStationManager/MacTxDataFailed",
        MakeCallback(&MacTxDataFailed));
    Config::Connect(
        "/NodeList/0/DeviceList/0/$ns3::WifiNetDevice/RemoteStationManager/MacTxFinalDataFailed",
        MakeCallback(&MacTxFinalDataFailed));
    devices.Get(1)->SetReceiveCallback(MakeCallback(&RxUpper));

    const Time interval = MilliSeconds(probeIntervalMs);
    const Time stopAt = Seconds(simTime);
    Simulator::Schedule(Seconds(0.1),
                        &SendProbe,
                        devices.Get(0),
                        devices.Get(1)->GetAddress(),
                        probeBytes,
                        interval,
                        stopAt);

    Simulator::Stop(Seconds(simTime) + Seconds(1.0));
    Simulator::Run();
    const double endDist = Distance();
    Simulator::Destroy();

    g_rxCsv.close();
    g_txCsv.close();

    const double retryRate =
        g_count.attempts ? static_cast<double>(g_count.retries) / g_count.attempts : -1.0;
    const double pdr = g_count.sends ? static_cast<double>(g_count.delivered) / g_count.sends : -1.0;

    std::ofstream meta(outDir + "/meta.json");
    meta << std::fixed << std::setprecision(6) << "{\n"
         << "  \"scenario\": \"link-probe\",\n"
         << "  \"phase\": \"P0\",\n"
         << "  \"seed\": " << seed << ",\n"
         << "  \"fading\": " << (fading ? "true" : "false") << ",\n"
         << "  \"tx_power_dbm\": " << txPowerDbm << ",\n"
         << "  \"exponent\": " << exponent << ",\n"
         << "  \"ref_distance_m\": 1.0,\n"
         << "  \"ref_loss_db\": " << refLossDb << ",\n"
         << "  \"freq_mhz\": " << freqMhz << ",\n"
         << "  \"data_mode\": \"" << dataMode << "\",\n"
         << "  \"min_rssi_dbm\": " << minRssiDbm << ",\n"
         << "  \"nakagami_m0\": " << m0 << ",\n"
         << "  \"nakagami_m1\": " << m1 << ",\n"
         << "  \"nakagami_m2\": " << m2 << ",\n"
         << "  \"nakagami_distance1_m\": " << nakDistance1 << ",\n"
         << "  \"nakagami_distance2_m\": " << nakDistance2 << ",\n"
         << "  \"altitude_m\": " << altitude << ",\n"
         << "  \"start_dist_m\": " << startDist << ",\n"
         << "  \"speed_mps\": " << speed << ",\n"
         << "  \"end_dist_m\": " << endDist << ",\n"
         << "  \"sim_time_s\": " << simTime << ",\n"
         << "  \"probe_interval_ms\": " << probeIntervalMs << ",\n"
         << "  \"probe_bytes\": " << probeBytes << ",\n"
         << "  \"sends\": " << g_count.sends << ",\n"
         << "  \"mac_attempts\": " << g_count.attempts << ",\n"
         << "  \"mac_retries\": " << g_count.retries << ",\n"
         << "  \"mac_final_fails\": " << g_count.finalFails << ",\n"
         << "  \"delivered\": " << g_count.delivered << ",\n"
         << "  \"phy_rx_ok\": " << g_count.sniffRx << ",\n"
         << "  \"retry_rate\": " << retryRate << ",\n"
         << "  \"pdr\": " << pdr << "\n"
         << "}\n";
    meta.close();

    std::cout << "--- link-probe P0 (fading=" << (fading ? "on" : "off") << ") ---\n"
              << "  quang duong      : " << startDist << " -> " << endDist << " m\n"
              << "  sends            : " << g_count.sends << '\n'
              << "  MAC attempts     : " << g_count.attempts << '\n'
              << "  MAC retries      : " << g_count.retries << "  (retry_rate " << retryRate
              << ")\n"
              << "  MAC final fails  : " << g_count.finalFails << '\n'
              << "  delivered        : " << g_count.delivered << "  (pdr " << pdr << ")\n"
              << "  PHY rx ok        : " << g_count.sniffRx << '\n'
              << "  ghi vao          : " << outDir << "/{rx.csv,tx.csv,meta.json}\n";

    return 0;
}
