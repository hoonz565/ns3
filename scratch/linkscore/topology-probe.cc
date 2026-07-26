/*
 * P1 — do hinh hoc ma dataset se duoc thu trong do.
 *
 * 30 node, Gauss-Markov 3D, 300 s. KHONG giao thuc dinh tuyen, KHONG traffic
 * ung dung, KHONG unicast probe. Chi beacon broadcast dinh ky va ghi log.
 *
 * Cau hoi phai tra loi:
 *   1. DEGREE that la bao nhieu. Cong thuc khong tra loi duoc: chieu cao hop
 *      (500 m) xap xi bang tam phu, nen cong thuc 2D va 3D lech nhau gan gap
 *      doi va cau phu song bi bien cat.
 *   2. Node co don vao bien khong. GaussMarkovMobilityModel::DoWalk phan xa
 *      (dao dau van toc VA lat m_meanDirection / m_meanPitch), nen khong ky
 *      vong dan tran -- nhung phai do chu khong doan.
 *
 * Beacon la broadcast nen khong co ARQ: khong retry, khong nhan. Day la
 * scenario DO HINH HOC, khong sinh feature hay nhan. Do la viec cua P2.
 *
 * Chay:
 *   ./ns3 run "scratch/linkscore/topology-probe
 *      --config=sim-config/fanet-tier2.conf
 *      --config=sim-config/p1-topology.conf --seed=1 --out=data/smoke/p1-topology"
 */

#include "sim-config.h"

#include "ns3/core-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/propagation-module.h"
#include "ns3/wifi-module.h"

#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("TopologyProbeP1");

namespace
{

uint32_t g_numNodes = 0;
double g_window = 5.0;
NodeContainer g_nodes;
std::vector<Ptr<MobilityModel>> g_mob;
std::map<Mac48Address, uint32_t> g_macToNode;

/// Thoi diem tung node phat beacon, chi giu trong cua so [t-W, t).
std::vector<std::deque<double>> g_sendTimes;
/// Thoi diem j nhan duoc beacon cua i, khoa la i*N+j.
std::vector<std::deque<double>> g_recvTimes;

uint64_t g_beaconsSent = 0;
uint64_t g_beaconsRecv = 0;

std::ofstream g_neighborCsv;
std::ofstream g_positionCsv;

double
NowSec()
{
    return Simulator::Now().GetSeconds();
}

void
Prune(std::deque<double>& d, double cutoff)
{
    while (!d.empty() && d.front() < cutoff)
    {
        d.pop_front();
    }
}

/// Beacon broadcast. Ethertype khac probe cua P0 (0x88b5) de phan biet duoc.
void
SendBeacon(Ptr<NetDevice> dev, uint32_t nodeId, uint32_t bytes, double interval, double stopAt)
{
    if (NowSec() >= stopAt)
    {
        return;
    }
    dev->Send(Create<Packet>(bytes), Mac48Address::GetBroadcast(), 0x88b6);
    g_sendTimes[nodeId].push_back(NowSec());
    g_beaconsSent++;

    // Jitter tung lan phat, khong chi lech pha ban dau: 30 node phat dung cung
    // moc thoi gian se tu tao collision he thong, va no se hien ra thanh "link
    // xau" trong ty le nhan beacon.
    static Ptr<UniformRandomVariable> jitter = CreateObject<UniformRandomVariable>();
    const double next = interval * (1.0 + jitter->GetValue(-0.05, 0.05));
    Simulator::Schedule(Seconds(next), &SendBeacon, dev, nodeId, bytes, interval, stopAt);
}

bool
RecvBeacon(Ptr<NetDevice> dev, Ptr<const Packet> /*pkt*/, uint16_t /*proto*/, const Address& from)
{
    const auto it = g_macToNode.find(Mac48Address::ConvertFrom(from));
    if (it == g_macToNode.end())
    {
        return true; // khong the xay ra; bo qua thay vi dung ca run
    }
    const uint32_t i = it->second;                  // nguoi phat
    const uint32_t j = dev->GetNode()->GetId();     // nguoi nhan
    g_recvTimes[i * g_numNodes + j].push_back(NowSec());
    g_beaconsRecv++;
    return true;
}

/// Moi cap co huong mot dong, KE CA cap khong nhan duoc gi.
///
/// Ghi ca cap ty le 0 la co y: neu chi ghi cap nghe thay nhau thi phan tich
/// khong phan biet duoc "khong co dong" voi "ty le 0", va degree se bi tinh
/// tren mot mau da bi loc san.
void
SampleNeighbors(double interval, double stopAt)
{
    const double t = NowSec();
    if (t >= stopAt)
    {
        return;
    }
    const double cutoff = t - g_window;

    for (uint32_t i = 0; i < g_numNodes; ++i)
    {
        Prune(g_sendTimes[i], cutoff);
    }
    for (uint32_t i = 0; i < g_numNodes; ++i)
    {
        const size_t sent = g_sendTimes[i].size();
        if (sent == 0)
        {
            continue;
        }
        for (uint32_t j = 0; j < g_numNodes; ++j)
        {
            if (i == j)
            {
                continue;
            }
            auto& recv = g_recvTimes[i * g_numNodes + j];
            Prune(recv, cutoff);
            g_neighborCsv << t << ',' << i << ',' << j << ','
                          << g_mob[i]->GetDistanceFrom(g_mob[j]) << ',' << sent << ','
                          << recv.size() << '\n';
        }
    }
    Simulator::Schedule(Seconds(interval), &SampleNeighbors, interval, stopAt);
}

void
SamplePositions(double interval, double stopAt)
{
    const double t = NowSec();
    if (t >= stopAt)
    {
        return;
    }
    for (uint32_t i = 0; i < g_numNodes; ++i)
    {
        const Vector p = g_mob[i]->GetPosition();
        g_positionCsv << t << ',' << i << ',' << p.x << ',' << p.y << ',' << p.z << '\n';
    }
    Simulator::Schedule(Seconds(interval), &SamplePositions, interval, stopAt);
}

std::string
Uniform(double min, double max)
{
    std::ostringstream s;
    s << "ns3::UniformRandomVariable[Min=" << min << "|Max=" << max << ']';
    return s.str();
}

std::string
Normal(double variance, double bound)
{
    std::ostringstream s;
    s << "ns3::NormalRandomVariable[Mean=0.0|Variance=" << variance << "|Bound=" << bound << ']';
    return s.str();
}

} // namespace

int
main(int argc, char* argv[])
{
    uint32_t seed = 1;
    std::string outDir = "data/smoke/p1-topology";
    std::string configHelp;
    bool allowUnknown = false;

    uint32_t numNodes = 30;
    double simTime = 300.0;
    double areaX = 2000.0;
    double areaY = 2000.0;
    double altMin = 100.0;
    double altMax = 600.0;

    double gmAlpha = 0.85;
    double gmTimeStep = 0.5;
    double gmVelMin = 15.0;
    double gmVelMax = 30.0;
    double gmDirMin = 0.0;
    double gmDirMax = 6.283185307;
    double gmPitchMin = -0.05;
    double gmPitchMax = 0.05;
    double gmNormVelVar = 2.0;
    double gmNormVelBound = 4.0;
    double gmNormDirVar = 0.2;
    double gmNormDirBound = 0.4;
    double gmNormPitchVar = 0.02;
    double gmNormPitchBound = 0.04;

    double txPowerDbm = 20.0;
    double exponent = 2.2;
    double minRssiDbm = -82.0;
    uint32_t channelNumber = 36;
    std::string dataMode = "OfdmRate6Mbps";
    double m0 = 8.0;
    double m1 = 5.0;
    double m2 = 3.0;
    double nakD1 = 100.0;
    double nakD2 = 300.0;

    double beaconInterval = 0.1;
    uint32_t beaconBytes = 32;
    double neighborWindow = 5.0;
    double sampleInterval = 1.0;
    double positionInterval = 5.0;

    linkscore::SimConfig cfg;
    cfg.Load(linkscore::ConfigPathsFromArgv(argc, argv),
             linkscore::FlagInArgv(argc, argv, "--allowUnknownKeys"));

    CommandLine cmd(__FILE__);
    cmd.AddValue("seed", "RngRun", seed);
    cmd.AddValue("out", "Thu muc ghi neighbors.csv / positions.csv / meta.json", outDir);
    cmd.AddValue("config", "File sim-config (lap lai duoc, file sau ghi de)", configHelp);
    cmd.AddValue("allowUnknownKeys", "Chi canh bao thay vi dung khi config co key la", allowUnknown);

    cfg.Add(cmd, "numNodes", "So node", numNodes);
    cfg.Add(cmd, "simTime", "Thoi gian mo phong (s)", simTime);
    cfg.Add(cmd, "areaX", "Chieu X cua hop (m)", areaX);
    cfg.Add(cmd, "areaY", "Chieu Y cua hop (m)", areaY);
    cfg.Add(cmd, "altMin", "Do cao min (m)", altMin);
    cfg.Add(cmd, "altMax", "Do cao max (m)", altMax);
    cfg.Add(cmd, "gmAlpha", "Gauss-Markov Alpha", gmAlpha);
    cfg.Add(cmd, "gmTimeStep", "Gauss-Markov TimeStep (s)", gmTimeStep);
    cfg.Add(cmd, "gmVelMin", "MeanVelocity min (m/s)", gmVelMin);
    cfg.Add(cmd, "gmVelMax", "MeanVelocity max (m/s)", gmVelMax);
    cfg.Add(cmd, "gmDirMin", "MeanDirection min (rad)", gmDirMin);
    cfg.Add(cmd, "gmDirMax", "MeanDirection max (rad)", gmDirMax);
    cfg.Add(cmd, "gmPitchMin", "MeanPitch min (rad)", gmPitchMin);
    cfg.Add(cmd, "gmPitchMax", "MeanPitch max (rad)", gmPitchMax);
    cfg.Add(cmd, "gmNormVelVar", "NormalVelocity variance", gmNormVelVar);
    cfg.Add(cmd, "gmNormVelBound", "NormalVelocity bound", gmNormVelBound);
    cfg.Add(cmd, "gmNormDirVar", "NormalDirection variance", gmNormDirVar);
    cfg.Add(cmd, "gmNormDirBound", "NormalDirection bound", gmNormDirBound);
    cfg.Add(cmd, "gmNormPitchVar", "NormalPitch variance", gmNormPitchVar);
    cfg.Add(cmd, "gmNormPitchBound", "NormalPitch bound", gmNormPitchBound);
    cfg.Add(cmd, "txPowerDbm", "Cong suat phat (dBm)", txPowerDbm);
    cfg.Add(cmd, "exponent", "So mu path loss", exponent);
    cfg.Add(cmd, "minRssiDbm", "ThresholdPreambleDetectionModel::MinimumRssi (dBm)", minRssiDbm);
    cfg.Add(cmd, "channelNumber", "So kenh 5 GHz", channelNumber);
    cfg.Add(cmd, "dataMode", "WifiMode", dataMode);
    cfg.Add(cmd, "nakagamiM0", "Nakagami m0", m0);
    cfg.Add(cmd, "nakagamiM1", "Nakagami m1", m1);
    cfg.Add(cmd, "nakagamiM2", "Nakagami m2", m2);
    cfg.Add(cmd, "nakagamiD1", "Nakagami Distance1 (m)", nakD1);
    cfg.Add(cmd, "nakagamiD2", "Nakagami Distance2 (m)", nakD2);
    cfg.Add(cmd, "topoBeaconInterval", "Chu ky beacon (s)", beaconInterval);
    cfg.Add(cmd, "topoBeaconBytes", "Payload beacon (B)", beaconBytes);
    cfg.Add(cmd, "topoNeighborWindow", "Cua so tinh ty le nhan beacon (s)", neighborWindow);
    cfg.Add(cmd, "topoSampleInterval", "Chu ky ghi neighbors.csv (s)", sampleInterval);
    cfg.Add(cmd, "topoPositionInterval", "Chu ky ghi positions.csv (s)", positionInterval);
    cmd.Parse(argc, argv);
    cfg.Finish();

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(seed);

    g_numNodes = numNodes;
    g_window = neighborWindow;
    g_sendTimes.resize(numNodes);
    g_recvTimes.resize(static_cast<size_t>(numNodes) * numNodes);

    const double freqMhz = 5000.0 + 5.0 * channelNumber;
    const double lambda = 299792458.0 / (freqMhz * 1e6);
    const double refLossDb = 20.0 * std::log10(4.0 * M_PI / lambda);

    g_nodes.Create(numNodes);

    YansWifiChannelHelper channelHelper;
    channelHelper.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channelHelper.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                                     "Exponent",
                                     DoubleValue(exponent),
                                     "ReferenceDistance",
                                     DoubleValue(1.0),
                                     "ReferenceLoss",
                                     DoubleValue(refLossDb));
    channelHelper.AddPropagationLoss("ns3::NakagamiPropagationLossModel",
                                     "m0",
                                     DoubleValue(m0),
                                     "m1",
                                     DoubleValue(m1),
                                     "m2",
                                     DoubleValue(m2),
                                     "Distance1",
                                     DoubleValue(nakD1),
                                     "Distance2",
                                     DoubleValue(nakD2));

    YansWifiPhyHelper phy;
    phy.SetChannel(channelHelper.Create());
    phy.Set("TxPowerStart", DoubleValue(txPowerDbm));
    phy.Set("TxPowerEnd", DoubleValue(txPowerDbm));
    phy.Set("TxPowerLevels", UintegerValue(1));
    phy.Set("ChannelSettings",
            StringValue("{" + std::to_string(channelNumber) + ", 20, BAND_5GHZ, 0}"));
    phy.SetPreambleDetectionModel("ns3::ThresholdPreambleDetectionModel",
                                  "MinimumRssi",
                                  DoubleValue(minRssiDbm));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211a);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                "DataMode",
                                StringValue(dataMode),
                                "ControlMode",
                                StringValue(dataMode));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, g_nodes);

    MobilityHelper mobility;
    mobility.SetPositionAllocator("ns3::RandomBoxPositionAllocator",
                                  "X",
                                  StringValue(Uniform(0.0, areaX)),
                                  "Y",
                                  StringValue(Uniform(0.0, areaY)),
                                  "Z",
                                  StringValue(Uniform(altMin, altMax)));
    mobility.SetMobilityModel("ns3::GaussMarkovMobilityModel",
                              "Bounds",
                              BoxValue(Box(0.0, areaX, 0.0, areaY, altMin, altMax)),
                              "TimeStep",
                              TimeValue(Seconds(gmTimeStep)),
                              "Alpha",
                              DoubleValue(gmAlpha),
                              "MeanVelocity",
                              StringValue(Uniform(gmVelMin, gmVelMax)),
                              "MeanDirection",
                              StringValue(Uniform(gmDirMin, gmDirMax)),
                              "MeanPitch",
                              StringValue(Uniform(gmPitchMin, gmPitchMax)),
                              "NormalVelocity",
                              StringValue(Normal(gmNormVelVar, gmNormVelBound)),
                              "NormalDirection",
                              StringValue(Normal(gmNormDirVar, gmNormDirBound)),
                              "NormalPitch",
                              StringValue(Normal(gmNormPitchVar, gmNormPitchBound)));
    mobility.Install(g_nodes);

    for (uint32_t i = 0; i < numNodes; ++i)
    {
        g_mob.push_back(g_nodes.Get(i)->GetObject<MobilityModel>());
        g_macToNode[Mac48Address::ConvertFrom(devices.Get(i)->GetAddress())] = i;
        devices.Get(i)->SetReceiveCallback(MakeCallback(&RecvBeacon));
    }

    std::filesystem::create_directories(outDir);
    g_neighborCsv.open(outDir + "/neighbors.csv");
    g_positionCsv.open(outDir + "/positions.csv");
    g_neighborCsv << std::fixed << std::setprecision(3);
    g_positionCsv << std::fixed << std::setprecision(3);
    g_neighborCsv << "t_s,src,dst,dist_m,sent,recv\n";
    g_positionCsv << "t_s,node,x,y,z\n";

    // Lech pha ban dau rai deu tren mot chu ky beacon.
    Ptr<UniformRandomVariable> phase = CreateObject<UniformRandomVariable>();
    for (uint32_t i = 0; i < numNodes; ++i)
    {
        Simulator::Schedule(Seconds(phase->GetValue(0.0, beaconInterval)),
                            &SendBeacon,
                            devices.Get(i),
                            i,
                            beaconBytes,
                            beaconInterval,
                            simTime);
    }
    // Bat dau lay mau khi cua so da day, khong thi ty le dau run bi tinh tren
    // mot cua so chua du beacon.
    Simulator::Schedule(Seconds(neighborWindow), &SampleNeighbors, sampleInterval, simTime);
    Simulator::Schedule(Seconds(0.0), &SamplePositions, positionInterval, simTime);

    Simulator::Stop(Seconds(simTime) + Seconds(1.0));
    Simulator::Run();
    Simulator::Destroy();

    g_neighborCsv.close();
    g_positionCsv.close();

    std::ofstream meta(outDir + "/meta.json");
    meta << std::fixed << std::setprecision(6) << "{\n"
         << "  \"scenario\": \"topology-probe\",\n"
         << "  \"phase\": \"P1\",\n"
         << "  \"seed\": " << seed << ",\n"
         << "  \"config_files\": [";
    for (size_t i = 0; i < cfg.Files().size(); ++i)
    {
        meta << (i ? ", " : "") << '"' << cfg.Files()[i] << '"';
    }
    meta << "],\n"
         << "  \"num_nodes\": " << numNodes << ",\n"
         << "  \"sim_time_s\": " << simTime << ",\n"
         << "  \"area_x_m\": " << areaX << ",\n"
         << "  \"area_y_m\": " << areaY << ",\n"
         << "  \"alt_min_m\": " << altMin << ",\n"
         << "  \"alt_max_m\": " << altMax << ",\n"
         << "  \"tx_power_dbm\": " << txPowerDbm << ",\n"
         << "  \"exponent\": " << exponent << ",\n"
         << "  \"min_rssi_dbm\": " << minRssiDbm << ",\n"
         << "  \"freq_mhz\": " << freqMhz << ",\n"
         << "  \"ref_loss_db\": " << refLossDb << ",\n"
         << "  \"nakagami_m0\": " << m0 << ",\n"
         << "  \"nakagami_m1\": " << m1 << ",\n"
         << "  \"nakagami_m2\": " << m2 << ",\n"
         << "  \"nakagami_distance1_m\": " << nakD1 << ",\n"
         << "  \"nakagami_distance2_m\": " << nakD2 << ",\n"
         << "  \"beacon_interval_s\": " << beaconInterval << ",\n"
         << "  \"beacon_bytes\": " << beaconBytes << ",\n"
         << "  \"neighbor_window_s\": " << neighborWindow << ",\n"
         << "  \"sample_interval_s\": " << sampleInterval << ",\n"
         << "  \"position_interval_s\": " << positionInterval << ",\n"
         << "  \"beacons_sent\": " << g_beaconsSent << ",\n"
         << "  \"beacons_received\": " << g_beaconsRecv << "\n"
         << "}\n";
    meta.close();

    std::cout << "--- topology-probe P1 ---\n"
              << "  node             : " << numNodes << ", " << simTime << " s\n"
              << "  hop              : " << areaX << " x " << areaY << " x [" << altMin << ", "
              << altMax << "] m\n"
              << "  txPower          : " << txPowerDbm << " dBm, san detect " << minRssiDbm
              << " dBm\n"
              << "  beacon phat      : " << g_beaconsSent << '\n'
              << "  beacon nhan      : " << g_beaconsRecv << "  (trung binh "
              << (g_beaconsSent ? static_cast<double>(g_beaconsRecv) / g_beaconsSent : 0.0)
              << " nguoi nhan / beacon)\n"
              << "  ghi vao          : " << outDir << "/{neighbors.csv,positions.csv,meta.json}\n";

    return 0;
}
