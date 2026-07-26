/*
 * P2 — Harness thu du lieu Tier 2 (PLAN.md P2, CLAUDE.md "Three simulation tiers").
 *
 * 30 node Gauss-Markov, BON loai phat tren MOT radio moi node:
 *
 *   OLSR    chuan, HELLO 2 s. CHI tao tai + dinh tuyen CBR. Khong sua, khong
 *           do, khong bao cao. No dinh tuyen bang hop count nen mu ve
 *           LinkScore — khong co endogeneity.
 *   CBR     UDP da chang qua OLSR. Lam moi truong tranh chap giong Tier 3.
 *           Frame unicast cua no la trial tren link no di qua (cot *_cbr).
 *   BEACON  L2 broadcast 0x88b6, 10 Hz. Nguon DUY NHAT cua feature RSSI: mat
 *           do mau dong deu moi link, khong tuong quan voi routing/probing.
 *   PROBE   L2 unicast 0x88b5 (NetDevice::Send, khong IP) toi tung neighbor
 *           con nghe duoc beacon trong neighborTtl. Lap link off-path
 *           (cot *_probe). Cat theo beacon, KHONG theo unicast con song.
 *
 * Ke thua nguyen ven ba cach do da chot o P0 (reports/P0-instrumentation.md):
 *   1. RSSI tu MonitorSnifferRx, truong signalNoise.signal
 *   2. Mau so moi ti le MAC tu MonitorSnifferTx (PPDU len song), khong tu Send()
 *   3. Probe unicast L2 qua NetDevice::Send, Ethertype 0x88b5
 *
 * Nhan per-attempt, KHONG post-ARQ (CLAUDE.md quy tac 3):
 *   trials = so PPDU data unicast len song toi j trong cua so
 *   fails  = so MacTxDataFailed(j) trong cung cua so
 * Fail chi mang dia chi, khong mang packet, nen lop (probe/cbr) cua fail duoc
 * quy ve lop cua ATTEMPT GAN NHAT toi cung dia chi — MAC non-QoS serial hoa
 * tung frame (mot frame data in flight moi luc) nen phep quy nay chinh xac,
 * tru truot bien cua so ~ms (dem o fail_slipped, kep ve trials).
 *
 * Tach thoi gian cuong che bang CAU TRUC: dong chi duoc ghi tai t+tau, khi
 * cua so nhan da dong. Hien thuc bang xoay bucket moi labelWin giay — doi hoi
 * featureWin == labelWin, neu cau hinh khac se dung ngay (NS_FATAL_ERROR).
 *
 * Chay:
 *   ./ns3 run "scratch/linkscore/link-dataset-fanet
 *      --config=sim-config/fanet-tier2.conf --seed=1
 *      --out=data/smoke/p2-harness/seed-1"
 */

#include "sim-config.h"

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/olsr-module.h"
#include "ns3/propagation-module.h"
#include "ns3/traffic-control-module.h"
#include "ns3/wifi-module.h"

#include <algorithm>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("LinkDatasetFanetP2");

namespace
{

constexpr uint16_t ETHERTYPE_PROBE = 0x88b5;  // nhu P0
constexpr uint16_t ETHERTYPE_BEACON = 0x88b6; // nhu P1

// ---- tham so chia se cho callback (gan trong main sau khi parse config)
uint32_t g_N = 0;
double g_simTime = 300.0;
double g_labelWin = 4.0;
double g_warmup = 30.0;
double g_neighborTtl = 2.0;
double g_probeInterval = 0.5;
uint32_t g_probeBytes = 540;
uint32_t g_minRssiSamples = 3;
uint32_t g_minTrials = 2;
uint32_t g_seed = 1;

NodeContainer g_nodes;
NetDeviceContainer g_devices;
std::vector<Ptr<MobilityModel>> g_mob;
std::vector<Mac48Address> g_macs;
std::map<Mac48Address, uint32_t> g_macToNode;
Ptr<UniformRandomVariable> g_jitter;

// ---- phan lop frame tren song, dung cho ca Tx (nhan + airtime) va Rx (RSSI)
enum FrameClass : uint8_t
{
    FC_BEACON = 0,
    FC_PROBE,
    FC_CBR,
    FC_OLSR, // IPv4 broadcast — chi OLSR phat loai nay
    FC_ARP,  // phai bang 0 nho ARP tinh; khac 0 la nhan bi ban
    FC_CTRL, // ACK
    FC_MGMT,
    FC_OTHER,
    FC_COUNT
};

const char* const kClassName[FC_COUNT] =
    {"beacon", "probe", "cbr", "olsr", "arp", "ctrl", "mgmt", "other"};

double g_airtimeS[FC_COUNT] = {};
uint64_t g_frames[FC_COUNT] = {};

// ---- RSSI: CHI tu beacon (quyet dinh C3). Mau cua link i->j do tai j.
struct RssiSample
{
    double t;
    double dbm;
};

std::vector<std::deque<RssiSample>> g_rssi;   // [i*N+j]
std::vector<std::deque<double>> g_beaconSent; // [i]

// ---- probe: [i*N+j] = lan cuoi i nghe beacon cua j / loop dang chay?
std::vector<double> g_lastHeard;
std::vector<uint8_t> g_probeLoopActive;

// ---- bucket dem attempt/fail moi cua so labelWin, ben phat la i
struct Bucket
{
    uint32_t attProbe = 0;
    uint32_t failProbe = 0;
    uint32_t attCbr = 0;
    uint32_t failCbr = 0;
};

std::vector<Bucket> g_curr; // cua so dang mo [B-W, B)
std::vector<Bucket> g_prev; // cua so truoc — nguon feature retry
std::vector<Vector> g_anchorPos; // vi tri tai anchor t = B - W
std::vector<uint8_t> g_lastClassTo; // lop cua attempt gan nhat i->j, 255 = chua co

struct Counters
{
    uint64_t beaconsSent = 0;
    uint64_t beaconsRecv = 0;
    uint64_t probesSent = 0;
    uint64_t attProbe = 0;
    uint64_t failProbe = 0;
    uint64_t finalFailProbe = 0;
    uint64_t attCbr = 0;
    uint64_t failCbr = 0;
    uint64_t finalFailCbr = 0;
    uint64_t failUnattributed = 0; // fail khong quy duoc lop — phai ~0
    uint64_t failSlipped = 0;      // fail > attempts trong mot cua so (truot bien ~ms)
    uint64_t queueExpired = 0;     // MaxDelay het han
    uint64_t queueDropBefore = 0;  // tran queue
    uint64_t queueDropAfter = 0;
    uint64_t queueDequeued = 0;
    uint64_t cbrAppTx = 0;
    uint64_t cbrAppRx = 0;
    uint64_t rows = 0;
    uint64_t rowsDropLowRssi = 0;   // du trial, thieu mau RSSI
    uint64_t rowsDropLowTrials = 0; // co trial nhung < minTrials
} g_count;

uint32_t g_psduProbe = 0; // PSDU byte dau tien quan sat duoc moi lop
uint32_t g_psduCbr = 0;
std::vector<float> g_queueDelayMs;

double g_degreeSum = 0;
uint64_t g_degreeSamples = 0;
uint64_t g_isolatedSamples = 0;

// --- phan bo hop cua duong CBR, tu bang dinh tuyen OLSR cua node nguon.
// Chi DOC (khong RNG, khong phat gi) nen khong doi ket qua mo phong —
// rows.csv phai byte-identical voi run khong do. Khoa -1 = khong co route.
std::vector<std::pair<uint32_t, Ipv4Address>> g_flowProbe; // (src, dst addr)
std::map<int32_t, uint64_t> g_cbrHops;

std::ofstream g_rowsCsv;
std::ofstream g_posCsv;

double
NowSec()
{
    return Simulator::Now().GetSeconds();
}

size_t
Key(uint32_t i, uint32_t j)
{
    return static_cast<size_t>(i) * g_N + j;
}

double
FrontTime(const RssiSample& s)
{
    return s.t;
}

double
FrontTime(double t)
{
    return t;
}

template <typename D>
void
PruneBefore(D& d, double cutoff)
{
    while (!d.empty() && FrontTime(d.front()) < cutoff)
    {
        d.pop_front();
    }
}

/// Boc WifiMacHeader + LLC/SNAP de phan lop frame tren song. Dung chung cho
/// Tx va Rx sniffer de hai dau khong bao gio lech dinh nghia.
FrameClass
Classify(Ptr<const Packet> pkt, WifiMacHeader& hdr, Mac48Address& dst)
{
    Ptr<Packet> p = pkt->Copy();
    p->RemoveHeader(hdr);
    dst = hdr.GetAddr1();
    if (hdr.IsCtl())
    {
        return FC_CTRL;
    }
    if (hdr.IsMgt())
    {
        return FC_MGMT;
    }
    if (!hdr.IsData())
    {
        return FC_OTHER;
    }
    LlcSnapHeader llc;
    if (p->GetSize() < llc.GetSerializedSize())
    {
        return FC_OTHER;
    }
    p->RemoveHeader(llc);
    switch (llc.GetType())
    {
    case ETHERTYPE_BEACON:
        return FC_BEACON;
    case ETHERTYPE_PROBE:
        return FC_PROBE;
    case 0x0806:
        return FC_ARP;
    case 0x0800:
        return dst.IsGroup() ? FC_OLSR : FC_CBR;
    default:
        return FC_OTHER;
    }
}

// ------------------------------------------------------------------ Tx side

/// Moi PPDU len song, moi node, ke ca phat lai: mau so cua nhan (P0 quyet
/// dinh 2) + hach toan airtime theo lop (con so quyet dinh muc tai C8).
void
TxSniffer(uint32_t i,
          Ptr<const Packet> pkt,
          uint16_t /*channelFreqMhz*/,
          WifiTxVector txVector,
          MpduInfo /*aMpdu*/,
          uint16_t /*staId*/)
{
    WifiMacHeader hdr;
    Mac48Address dst;
    const FrameClass fc = Classify(pkt, hdr, dst);
    g_frames[fc]++;
    g_airtimeS[fc] +=
        WifiPhy::CalculateTxDuration(pkt->GetSize(), txVector, WIFI_PHY_BAND_5GHZ).GetSeconds();

    if (fc != FC_PROBE && fc != FC_CBR)
    {
        return;
    }
    const auto it = g_macToNode.find(dst);
    if (it == g_macToNode.end())
    {
        return;
    }
    const size_t k = Key(i, it->second);
    Bucket& b = g_curr[k];
    if (fc == FC_PROBE)
    {
        b.attProbe++;
        g_count.attProbe++;
        if (g_psduProbe == 0)
        {
            g_psduProbe = pkt->GetSize();
        }
    }
    else
    {
        b.attCbr++;
        g_count.attCbr++;
        if (g_psduCbr == 0)
        {
            g_psduCbr = pkt->GetSize();
        }
    }
    // Quy tac 12: probe phai cung airtime voi data. Khong tin so hoc
    // probeBytes = cbrBytes + 28 — assert bang kich thuoc PPDU do duoc.
    if (g_psduProbe != 0 && g_psduCbr != 0 && g_psduProbe != g_psduCbr)
    {
        NS_FATAL_ERROR("PSDU probe " << g_psduProbe << " B != PSDU CBR " << g_psduCbr
                                     << " B — sua probeBytes cho khop (quy tac 12)");
    }
    g_lastClassTo[k] = fc;
}

/// MacTxDataFailed chi mang dia chi. Lop lay tu attempt gan nhat toi cung
/// dia chi (MAC non-QoS: mot frame data in flight moi luc).
void
MacFailed(uint32_t i, Mac48Address addr)
{
    const auto it = g_macToNode.find(addr);
    if (it == g_macToNode.end())
    {
        g_count.failUnattributed++;
        return;
    }
    const size_t k = Key(i, it->second);
    Bucket& b = g_curr[k];
    switch (g_lastClassTo[k])
    {
    case FC_PROBE:
        b.failProbe++;
        g_count.failProbe++;
        break;
    case FC_CBR:
        b.failCbr++;
        g_count.failCbr++;
        break;
    default:
        g_count.failUnattributed++;
        break;
    }
}

void
MacFinalFailed(uint32_t i, Mac48Address addr)
{
    const auto it = g_macToNode.find(addr);
    if (it == g_macToNode.end())
    {
        return;
    }
    switch (g_lastClassTo[Key(i, it->second)])
    {
    case FC_PROBE:
        g_count.finalFailProbe++;
        break;
    case FC_CBR:
        g_count.finalFailCbr++;
        break;
    default:
        break;
    }
}

// ------------------------------------------------------------------ Rx side

void ProbeLoop(uint32_t i, uint32_t j);

/// Moi frame PHY giai ma duoc tai j. Chi beacon duoc dung: RSSI cua link
/// i->j (quyet dinh C3 — mat do mau khong tuong quan routing/probing) va
/// dieu kien admission cho probe j->i ("con nghe beacon", quy tac 12).
void
RxSniffer(uint32_t j,
          Ptr<const Packet> pkt,
          uint16_t /*channelFreqMhz*/,
          WifiTxVector /*txVector*/,
          MpduInfo /*aMpdu*/,
          SignalNoiseDbm signalNoise,
          uint16_t /*staId*/)
{
    WifiMacHeader hdr;
    Mac48Address dst;
    if (Classify(pkt, hdr, dst) != FC_BEACON)
    {
        return;
    }
    const auto it = g_macToNode.find(hdr.GetAddr2());
    if (it == g_macToNode.end())
    {
        return;
    }
    const uint32_t i = it->second;
    if (i == j)
    {
        return;
    }
    g_count.beaconsRecv++;
    g_rssi[Key(i, j)].push_back({NowSec(), signalNoise.signal});

    const size_t k = Key(j, i); // chieu nguoc: j vua nghe i -> j probe i
    g_lastHeard[k] = NowSec();
    if (!g_probeLoopActive[k])
    {
        g_probeLoopActive[k] = 1;
        Simulator::Schedule(Seconds(g_jitter->GetValue(0.0, g_probeInterval)), &ProbeLoop, j, i);
    }
}

// ------------------------------------------------------------- may phat L2

void
SendBeacon(uint32_t i, uint32_t bytes, double interval)
{
    if (NowSec() >= g_simTime)
    {
        return;
    }
    g_devices.Get(i)->Send(Create<Packet>(bytes), Mac48Address::GetBroadcast(), ETHERTYPE_BEACON);
    g_beaconSent[i].push_back(NowSec());
    g_count.beaconsSent++;
    // Jitter tung lan phat (nhu P1): 30 node cung nhip se tu tao collision
    // he thong va no hien ra thanh "link xau" trong ti le nhan beacon.
    const double next = interval * (1.0 + g_jitter->GetValue(-0.05, 0.05));
    Simulator::Schedule(Seconds(next), &SendBeacon, i, bytes, interval);
}

/// Loop rieng cho tung cap (i, j), song chung nao i con nghe beacon cua j
/// trong neighborTtl. Cat theo unicast se mat dung phan neo day sigmoid.
void
ProbeLoop(uint32_t i, uint32_t j)
{
    const size_t k = Key(i, j);
    if (NowSec() >= g_simTime || NowSec() - g_lastHeard[k] > g_neighborTtl)
    {
        g_probeLoopActive[k] = 0; // RxSniffer se moi lai khi nghe thay lai
        return;
    }
    g_devices.Get(i)->Send(Create<Packet>(g_probeBytes), g_macs[j], ETHERTYPE_PROBE);
    g_count.probesSent++;
    const double next = g_probeInterval * (1.0 + g_jitter->GetValue(-0.05, 0.05));
    Simulator::Schedule(Seconds(next), &ProbeLoop, i, j);
}

// ------------------------------------------------------------------- queue

void
OnQueueDequeue(Ptr<const WifiMpdu> mpdu)
{
    g_count.queueDequeued++;
    g_queueDelayMs.push_back(
        static_cast<float>((Simulator::Now() - mpdu->GetTimestamp()).GetSeconds() * 1e3));
}

void
OnQueueExpired(Ptr<const WifiMpdu> /*mpdu*/)
{
    g_count.queueExpired++;
}

void
OnQueueDropBefore(Ptr<const WifiMpdu> /*mpdu*/)
{
    g_count.queueDropBefore++;
}

void
OnQueueDropAfter(Ptr<const WifiMpdu> /*mpdu*/)
{
    g_count.queueDropAfter++;
}

// -------------------------------------------------------------- app traces

void
OnCbrTx(Ptr<const Packet> /*p*/)
{
    g_count.cbrAppTx++;
}

void
OnCbrRx(Ptr<const Packet> /*p*/, const Address& /*from*/)
{
    g_count.cbrAppRx++;
}

// ---------------------------------------------------------------- do dac

/// Degree theo dung dinh nghia P1: ti le nhan beacon >= 0.5 trong 5 s.
/// So sanh truc tiep duoc voi 6.14 cua reports/P1-config.md.
void
SampleDegree()
{
    const double t = NowSec();
    if (t >= g_simTime)
    {
        return;
    }
    constexpr double W = 5.0;
    // Prune ve t-9: cua so feature can toi 2*labelWin = 8 s ve truoc,
    // degree can 5 s — 9 s phu ca hai.
    const double cutoff = t - 9.0;
    for (uint32_t i = 0; i < g_N; ++i)
    {
        PruneBefore(g_beaconSent[i], cutoff);
    }
    for (uint32_t i = 0; i < g_N; ++i)
    {
        for (uint32_t j = 0; j < g_N; ++j)
        {
            if (i != j)
            {
                PruneBefore(g_rssi[Key(i, j)], cutoff);
            }
        }
    }
    for (uint32_t j = 0; j < g_N; ++j)
    {
        uint32_t deg = 0;
        for (uint32_t i = 0; i < g_N; ++i)
        {
            if (i == j)
            {
                continue;
            }
            const auto& sent = g_beaconSent[i];
            const size_t nSent =
                sent.end() - std::lower_bound(sent.begin(), sent.end(), t - W);
            if (nSent == 0)
            {
                continue;
            }
            const auto& recv = g_rssi[Key(i, j)];
            const size_t nRecv =
                recv.end() - std::lower_bound(recv.begin(),
                                              recv.end(),
                                              t - W,
                                              [](const RssiSample& s, double v) { return s.t < v; });
            if (static_cast<double>(nRecv) >= 0.5 * static_cast<double>(nSent))
            {
                deg++;
            }
        }
        g_degreeSum += deg;
        g_degreeSamples++;
        if (deg == 0)
        {
            g_isolatedSamples++;
        }
    }
    Simulator::Schedule(Seconds(1.0), &SampleDegree);
}

/// Moi giay, moi flow: tra bang OLSR cua node nguon xem duong toi dich dai
/// bao nhieu hop. Tra loi "CBR co that su da chang khong" — neu phan lon
/// 1 hop thi lap luan 'CBR tao tranh chap chuyen tiep giong Tier 3' yeu di.
void
SampleCbrHops()
{
    const double t = NowSec();
    if (t >= g_simTime)
    {
        return;
    }
    for (const auto& [src, dstAddr] : g_flowProbe)
    {
        Ptr<olsr::RoutingProtocol> rp = DynamicCast<olsr::RoutingProtocol>(
            g_nodes.Get(src)->GetObject<Ipv4>()->GetRoutingProtocol());
        NS_ABORT_MSG_UNLESS(rp, "routing protocol cua node khong phai olsr::RoutingProtocol");
        int32_t hops = -1;
        for (const auto& entry : rp->GetRoutingTableEntries())
        {
            if (entry.destAddr == dstAddr)
            {
                hops = static_cast<int32_t>(entry.distance);
                break;
            }
        }
        g_cbrHops[hops]++;
    }
    Simulator::Schedule(Seconds(1.0), &SampleCbrHops);
}

void
SamplePositions(double interval)
{
    const double t = NowSec();
    if (t >= g_simTime)
    {
        return;
    }
    for (uint32_t i = 0; i < g_N; ++i)
    {
        const Vector p = g_mob[i]->GetPosition();
        g_posCsv << t << ',' << i << ',' << p.x << ',' << p.y << ',' << p.z << '\n';
    }
    Simulator::Schedule(Seconds(interval), &SamplePositions, interval);
}

/// Xoay bucket tai moi boc B = k*labelWin. Dong ghi tai day co anchor
/// t = B - labelWin: nhan tu bucket vua dong [t, B), feature tu bucket
/// truoc [t - labelWin, t) — dong chi ton tai KHI cua so nhan da dong,
/// khong the fit contemporaneous ke ca khi co y (CLAUDE.md quy tac 1).
void
Rotate()
{
    const double B = NowSec();
    const double t = B - g_labelWin;

    if (t >= g_warmup)
    {
        const double f0 = B - 2.0 * g_labelWin; // cua so feature [f0, f1)
        const double f1 = t;
        for (uint32_t i = 0; i < g_N; ++i)
        {
            for (uint32_t j = 0; j < g_N; ++j)
            {
                if (i == j)
                {
                    continue;
                }
                const size_t k = Key(i, j);
                const Bucket& lab = g_curr[k];
                const uint32_t trials = lab.attProbe + lab.attCbr;
                if (trials == 0)
                {
                    continue;
                }
                if (trials < g_minTrials)
                {
                    g_count.rowsDropLowTrials++;
                    continue;
                }

                // RSSI tho trong [f0, f1): mean + OLS slope (quy tac 8 —
                // khong EWMA, khong tien xu ly).
                double sumT = 0;
                double sumY = 0;
                uint32_t n = 0;
                for (const auto& s : g_rssi[k])
                {
                    if (s.t >= f0 && s.t < f1)
                    {
                        sumT += s.t;
                        sumY += s.dbm;
                        n++;
                    }
                }
                if (n < g_minRssiSamples)
                {
                    g_count.rowsDropLowRssi++;
                    continue;
                }
                const double meanT = sumT / n;
                const double meanY = sumY / n;
                double sxx = 0;
                double sxy = 0;
                for (const auto& s : g_rssi[k])
                {
                    if (s.t >= f0 && s.t < f1)
                    {
                        sxx += (s.t - meanT) * (s.t - meanT);
                        sxy += (s.t - meanT) * (s.dbm - meanY);
                    }
                }
                const double slope = (sxx > 0) ? sxy / sxx : 0.0;

                // Kep fail <= attempt tung lop: ack-timeout cua attempt cuoi
                // cua so co the roi sang bucket sau (truot ~ms tren cua so 4 s).
                uint32_t fp = std::min(lab.failProbe, lab.attProbe);
                uint32_t fc = std::min(lab.failCbr, lab.attCbr);
                if (fp != lab.failProbe || fc != lab.failCbr)
                {
                    g_count.failSlipped++;
                }
                const uint32_t fails = fp + fc;

                // Feature retry tu cua so truoc. Rong khac 0: khong attempt
                // thi de trong, KHONG ghi 0 (CLAUDE.md "known traps").
                const Bucket& fea = g_prev[k];
                const uint32_t attPast = fea.attProbe + fea.attCbr;
                const uint32_t failPast =
                    std::min(fea.failProbe, fea.attProbe) + std::min(fea.failCbr, fea.attCbr);

                const auto& sent = g_beaconSent[i];
                const size_t nSent = std::lower_bound(sent.begin(), sent.end(), f1) -
                                     std::lower_bound(sent.begin(), sent.end(), f0);

                const double dist = CalculateDistance(g_anchorPos[i], g_anchorPos[j]);

                g_rowsCsv << g_seed << ',' << t << ',' << i << ',' << j << ',' << dist << ','
                          << meanY << ',' << slope << ',' << n << ',';
                if (nSent > 0)
                {
                    g_rowsCsv << static_cast<double>(n) / static_cast<double>(nSent);
                }
                g_rowsCsv << ',';
                if (attPast > 0)
                {
                    g_rowsCsv << static_cast<double>(failPast) / attPast;
                }
                g_rowsCsv << ',' << attPast << ',' << lab.attProbe << ',' << fp << ','
                          << lab.attCbr << ',' << fc << ',' << trials << ',' << fails << ','
                          << 1.0 - static_cast<double>(fails) / trials << '\n';
                g_count.rows++;
            }
        }
    }

    std::swap(g_prev, g_curr);
    std::fill(g_curr.begin(), g_curr.end(), Bucket{});
    for (uint32_t i = 0; i < g_N; ++i)
    {
        g_anchorPos[i] = g_mob[i]->GetPosition();
    }
    if (B + g_labelWin <= g_simTime + 1e-9)
    {
        Simulator::Schedule(Seconds(g_labelWin), &Rotate);
    }
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

double
Percentile(std::vector<float>& v, double q)
{
    if (v.empty())
    {
        return -1.0;
    }
    const size_t idx = static_cast<size_t>(q * (v.size() - 1));
    std::nth_element(v.begin(), v.begin() + idx, v.end());
    return v[idx];
}

} // namespace

int
main(int argc, char* argv[])
{
    uint32_t seed = 1;
    std::string outDir = "data/smoke/p2-harness/seed-1";
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

    double txPowerDbm = 19.0;
    double exponent = 2.2;
    double minRssiDbm = -101.0;
    uint32_t channelNumber = 36;
    std::string dataMode = "OfdmRate6Mbps";
    uint32_t frameRetryLimit = 2;
    double m0 = 8.0;
    double m1 = 5.0;
    double m2 = 3.0;
    double nakD1 = 100.0;
    double nakD2 = 300.0;

    double beaconInterval = 0.1;
    uint32_t beaconBytes = 32;
    double probeInterval = 0.5;
    uint32_t probeBytes = 540;
    double neighborTtl = 2.0;

    uint32_t cbrFlows = 6;
    uint32_t cbrBytes = 512;
    uint32_t cbrPps = 8;
    uint32_t maxQueueDelayMs = 100;

    double featureWin = 4.0;
    double labelWin = 4.0;
    double warmupTime = 30.0;
    uint32_t minRssiSamples = 3;
    uint32_t minTrials = 2;

    linkscore::SimConfig cfg;
    cfg.Load(linkscore::ConfigPathsFromArgv(argc, argv),
             linkscore::FlagInArgv(argc, argv, "--allowUnknownKeys"));

    CommandLine cmd(__FILE__);
    cmd.AddValue("seed", "RngRun", seed);
    cmd.AddValue("out", "Thu muc ghi rows.csv / positions.csv / meta.json / summary.json", outDir);
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
    cfg.Add(cmd,
            "frameRetryLimit",
            "dot11ShortRetryLimit: so ATTEMPT toi da moi frame, toan he thong",
            frameRetryLimit);
    cfg.Add(cmd, "nakagamiM0", "Nakagami m0", m0);
    cfg.Add(cmd, "nakagamiM1", "Nakagami m1", m1);
    cfg.Add(cmd, "nakagamiM2", "Nakagami m2", m2);
    cfg.Add(cmd, "nakagamiD1", "Nakagami Distance1 (m)", nakD1);
    cfg.Add(cmd, "nakagamiD2", "Nakagami Distance2 (m)", nakD2);
    cfg.Add(cmd, "beaconInterval", "Chu ky beacon moi node (s)", beaconInterval);
    cfg.Add(cmd, "beaconBytes", "Payload beacon (B)", beaconBytes);
    cfg.Add(cmd, "probeInterval", "Chu ky probe MOI NEIGHBOR (s)", probeInterval);
    cfg.Add(cmd, "probeBytes", "Payload probe (B), = cbrBytes + 28 de PPDU bang nhau", probeBytes);
    cfg.Add(cmd, "neighborTtl", "Probe neighbor nghe thay trong bao lau (s)", neighborTtl);
    cfg.Add(cmd, "cbrFlows", "So luong CBR", cbrFlows);
    cfg.Add(cmd, "cbrBytes", "Payload UDP moi goi CBR (B)", cbrBytes);
    cfg.Add(cmd, "cbrPps", "Goi/s moi luong CBR", cbrPps);
    cfg.Add(cmd, "maxQueueDelayMs", "WifiMacQueue::MaxDelay (ms)", maxQueueDelayMs);
    cfg.Add(cmd, "featureWin", "Cua so feature Delta (s)", featureWin);
    cfg.Add(cmd, "labelWin", "Cua so nhan tau (s)", labelWin);
    cfg.Add(cmd, "warmupTime", "Bo dong co anchor t < gia tri nay (s)", warmupTime);
    cfg.Add(cmd, "minRssiSamples", "So mau RSSI toi thieu moi dong", minRssiSamples);
    cfg.Add(cmd, "minTrials", "So trial toi thieu moi dong", minTrials);
    cmd.Parse(argc, argv);
    cfg.Finish();

    if (featureWin != labelWin)
    {
        // Co che xoay bucket dung cua so truoc lam cua so feature. Muon
        // featureWin != labelWin thi phai viet lai bang ring buffer co dau
        // thoi gian — dung ngay thay vi im lang do sai cua so.
        NS_FATAL_ERROR("featureWin (" << featureWin << ") != labelWin (" << labelWin
                                      << "): xoay bucket gia dinh hai cua so bang nhau");
    }
    if (probeBytes != cbrBytes + 28)
    {
        std::cerr << "CANH BAO: probeBytes (" << probeBytes << ") != cbrBytes + 28 ("
                  << cbrBytes + 28 << ") — PPDU se lech va assert quy tac 12 se dung run\n";
    }

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(seed);

    g_N = numNodes;
    g_seed = seed;
    g_simTime = simTime;
    g_labelWin = labelWin;
    g_warmup = warmupTime;
    g_neighborTtl = neighborTtl;
    g_probeInterval = probeInterval;
    g_probeBytes = probeBytes;
    g_minRssiSamples = minRssiSamples;
    g_minTrials = minTrials;

    const size_t nn = static_cast<size_t>(numNodes) * numNodes;
    g_rssi.resize(nn);
    g_beaconSent.resize(numNodes);
    g_lastHeard.assign(nn, -1e9);
    g_probeLoopActive.assign(nn, 0);
    g_curr.assign(nn, Bucket{});
    g_prev.assign(nn, Bucket{});
    g_lastClassTo.assign(nn, 255);
    g_anchorPos.assign(numNodes, Vector());
    g_jitter = CreateObject<UniformRandomVariable>();

    const double freqMhz = 5000.0 + 5.0 * channelNumber;
    const double lambda = 299792458.0 / (freqMhz * 1e6);
    const double refLossDb = 20.0 * std::log10(4.0 * M_PI / lambda);

    g_nodes.Create(numNodes);

    // --- PHY / channel: y het topology-probe (P1), doc tu config dong bang
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

    // Chan backlog bang thoi gian song cua goi, khong bang gian nhip (da do
    // o P0: gian nhip khong chua duoc). Ap cho MOI queue — mot radio moi
    // node nen day la queue chung cua ca OLSR/CBR/probe/beacon, co chu y.
    Config::SetDefault("ns3::WifiMacQueue::MaxDelay", TimeValue(MilliSeconds(maxQueueDelayMs)));
    // Quyet dinh toan he thong (CLAUDE.md bang Simulation Setup): tran so
    // attempt moi frame. MaxSsrc/MaxSlrc cu la OBSOLETE trong ns-3.45; knob
    // con hoat dong la WifiMac::FrameRetryLimit (= dot11ShortRetryLimit).
    Config::SetDefault("ns3::WifiMac::FrameRetryLimit", UintegerValue(frameRetryLimit));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211a);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue(dataMode),
                                 "ControlMode",
                                 StringValue(dataMode));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    g_devices = wifi.Install(phy, mac, g_nodes);

    // --- Mobility: y het topology-probe
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

    // --- IP + OLSR (chuan, HELLO 2 s mac dinh — diem can thiep cua Tier 3,
    // o day co dinh) + dia chi
    OlsrHelper olsrHelper;
    InternetStackHelper internet;
    internet.SetRoutingHelper(olsrHelper);
    internet.Install(g_nodes);

    Ipv4AddressHelper addressHelper;
    addressHelper.SetBase("10.1.0.0", "255.255.0.0");
    Ipv4InterfaceContainer ifaces = addressHelper.Assign(g_devices);

    // ns-3.45 tu cai root qdisc (FqCoDel) len device khi gan dia chi. Go no:
    // CBR se xep hang hai tang (qdisc + WifiMacQueue) trong khi probe L2 di
    // thang NetDevice::Send chi mot tang — hai lop trial cua cung mot nhan
    // chiu hai che do dem khac nhau, va MaxDelay chi quan ly tang duoi.
    // Guard phia duoi giu nguyen de viec nay khong bao gio tai dien im lang.
    TrafficControlHelper tch;
    tch.Uninstall(g_devices);

    for (uint32_t i = 0; i < numNodes; ++i)
    {
        g_mob.push_back(g_nodes.Get(i)->GetObject<MobilityModel>());
        g_macs.push_back(Mac48Address::ConvertFrom(g_devices.Get(i)->GetAddress()));
        g_macToNode[g_macs[i]] = i;
        g_anchorPos[i] = g_mob[i]->GetPosition();
    }

    // --- ARP tinh. ARP reply la unicast ~64 B: no chui vao MacTxDataFailed
    // (trace chi co dia chi, khong loc duoc theo size) ma khong co attempt
    // tuong ung trong mau so da loc — thoi phong fails/attempts mot chieu.
    // Nap cache vinh vien, khai bao trong paper.
    Ptr<ArpCache> arpCache = CreateObject<ArpCache>();
    for (uint32_t i = 0; i < numNodes; ++i)
    {
        ArpCache::Entry* entry = arpCache->Add(ifaces.GetAddress(i));
        entry->SetMacAddress(g_macs[i]);
        entry->MarkPermanent();
    }
    for (uint32_t i = 0; i < numNodes; ++i)
    {
        Ptr<Ipv4L3Protocol> ip = g_nodes.Get(i)->GetObject<Ipv4L3Protocol>();
        const int32_t ifIndex = ip->GetInterfaceForDevice(g_devices.Get(i));
        NS_ABORT_MSG_IF(ifIndex < 0, "khong tim thay interface wifi");
        ip->GetInterface(ifIndex)->SetArpCache(arpCache);
    }

    // Xac nhan KHONG co qdisc TrafficControl tren wifi device: neu co, CBR
    // xep hang hai tang con probe L2 (NetDevice::Send) thi khong — hai lop
    // trial cua cung mot nhan se chiu hai che do dem khac nhau.
    {
        Ptr<TrafficControlLayer> tc = g_nodes.Get(0)->GetObject<TrafficControlLayer>();
        if (tc && tc->GetRootQueueDiscOnDevice(g_devices.Get(0)))
        {
            NS_FATAL_ERROR("Co root qdisc tren WifiNetDevice — go qdisc de queue duy nhat "
                           "la WifiMacQueue, khong thi probe va CBR dem khac nhau");
        }
    }

    // --- CBR: cap (src, dst) rut tu RNG cua run, co dinh suot run
    Ptr<UniformRandomVariable> pick = CreateObject<UniformRandomVariable>();
    std::set<std::pair<uint32_t, uint32_t>> flowPairs;
    std::vector<std::pair<uint32_t, uint32_t>> flows;
    while (flows.size() < cbrFlows)
    {
        const uint32_t s = pick->GetInteger(0, numNodes - 1);
        const uint32_t d = pick->GetInteger(0, numNodes - 1);
        if (s == d || flowPairs.count({s, d}))
        {
            continue;
        }
        flowPairs.insert({s, d});
        flows.emplace_back(s, d);
    }
    for (uint32_t f = 0; f < flows.size(); ++f)
    {
        const auto [s, d] = flows[f];
        const uint16_t port = 9000 + f;
        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(ifaces.GetAddress(d), port));
        onoff.SetConstantRate(DataRate(static_cast<uint64_t>(cbrBytes) * 8 * cbrPps), cbrBytes);
        ApplicationContainer src = onoff.Install(g_nodes.Get(s));
        // Bat dau sau khi OLSR co route (HELLO 2 s + TC ~5 s), truoc warmup 30 s.
        src.Start(Seconds(15.0 + 0.5 * f));
        src.Stop(Seconds(simTime));
        src.Get(0)->TraceConnectWithoutContext("Tx", MakeCallback(&OnCbrTx));

        PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                    InetSocketAddress(Ipv4Address::GetAny(), port));
        ApplicationContainer sink = sinkHelper.Install(g_nodes.Get(d));
        sink.Start(Seconds(0.0));
        sink.Stop(Seconds(simTime) + Seconds(1.0));
        sink.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&OnCbrRx));
        g_flowProbe.emplace_back(s, ifaces.GetAddress(d));
    }

    // --- trace: sniffer + fail theo node (bound callback, khong parse context)
    for (uint32_t i = 0; i < numNodes; ++i)
    {
        const std::string base =
            "/NodeList/" + std::to_string(i) + "/DeviceList/*/$ns3::WifiNetDevice/";
        Config::ConnectWithoutContext(base + "Phy/MonitorSnifferTx",
                                      MakeBoundCallback(&TxSniffer, i));
        Config::ConnectWithoutContext(base + "Phy/MonitorSnifferRx",
                                      MakeBoundCallback(&RxSniffer, i));
        Config::ConnectWithoutContext(base + "RemoteStationManager/MacTxDataFailed",
                                      MakeBoundCallback(&MacFailed, i));
        Config::ConnectWithoutContext(base + "RemoteStationManager/MacTxFinalDataFailed",
                                      MakeBoundCallback(&MacFinalFailed, i));
    }
    // Queue chung (non-QoS -> Mac/Txop/Queue): do tre + dem drop theo nguyen
    // nhan. Drop duoc DEM, khong bao gio vao nhan (quy tac 3).
    Config::ConnectWithoutContext("/NodeList/*/DeviceList/*/$ns3::WifiNetDevice/Mac/Txop/Queue/Dequeue",
                                  MakeCallback(&OnQueueDequeue));
    Config::ConnectWithoutContext("/NodeList/*/DeviceList/*/$ns3::WifiNetDevice/Mac/Txop/Queue/Expired",
                                  MakeCallback(&OnQueueExpired));
    Config::ConnectWithoutContext(
        "/NodeList/*/DeviceList/*/$ns3::WifiNetDevice/Mac/Txop/Queue/DropBeforeEnqueue",
        MakeCallback(&OnQueueDropBefore));
    Config::ConnectWithoutContext(
        "/NodeList/*/DeviceList/*/$ns3::WifiNetDevice/Mac/Txop/Queue/DropAfterDequeue",
        MakeCallback(&OnQueueDropAfter));

    // --- output
    std::filesystem::create_directories(outDir);
    g_rowsCsv.open(outDir + "/rows.csv");
    g_posCsv.open(outDir + "/positions.csv");
    g_rowsCsv << std::fixed << std::setprecision(4);
    g_posCsv << std::fixed << std::setprecision(3);
    g_rowsCsv << "seed,t,src,dst,dist_m,rssi_level,rssi_slope,rssi_n,beacon_ratio,"
                 "retry_rate,tx_attempts,trials_probe,fails_probe,trials_cbr,fails_cbr,"
                 "trials_future,fails_future,pdr_future\n";
    g_posCsv << "t_s,node,x,y,z\n";

    // --- lich
    for (uint32_t i = 0; i < numNodes; ++i)
    {
        Simulator::Schedule(Seconds(g_jitter->GetValue(0.0, beaconInterval)),
                            &SendBeacon,
                            i,
                            beaconBytes,
                            beaconInterval);
    }
    Simulator::Schedule(Seconds(5.0), &SampleDegree);
    Simulator::Schedule(Seconds(0.0), &SamplePositions, 5.0);
    Simulator::Schedule(Seconds(labelWin), &Rotate);
    Simulator::Schedule(Seconds(15.0), &SampleCbrHops); // tu luc flow dau bat dau

    Simulator::Stop(Seconds(simTime) + Seconds(1.0));
    Simulator::Run();
    Simulator::Destroy();

    g_rowsCsv.close();
    g_posCsv.close();

    // --- tong ket
    const uint64_t attempts = g_count.attProbe + g_count.attCbr;
    const uint64_t fails = g_count.failProbe + g_count.failCbr;
    const double macLoss = attempts ? static_cast<double>(fails) / attempts : -1.0;
    const double degreeMean =
        g_degreeSamples ? g_degreeSum / static_cast<double>(g_degreeSamples) : -1.0;
    const double isolatedFrac =
        g_degreeSamples ? static_cast<double>(g_isolatedSamples) / g_degreeSamples : -1.0;
    const double delayP50 = Percentile(g_queueDelayMs, 0.50);
    const double delayP90 = Percentile(g_queueDelayMs, 0.90);
    const double delayP99 = Percentile(g_queueDelayMs, 0.99);
    const double delayMax =
        g_queueDelayMs.empty() ? -1.0 : *std::max_element(g_queueDelayMs.begin(), g_queueDelayMs.end());

    std::ofstream meta(outDir + "/meta.json");
    meta << std::fixed << std::setprecision(6) << "{\n"
         << "  \"scenario\": \"link-dataset-fanet\",\n"
         << "  \"phase\": \"P2\",\n"
         << "  \"seed\": " << seed << ",\n"
         << "  \"config_files\": [";
    for (size_t i = 0; i < cfg.Files().size(); ++i)
    {
        meta << (i ? ", " : "") << '"' << cfg.Files()[i] << '"';
    }
    meta << "],\n"
         << "  \"num_nodes\": " << numNodes << ",\n"
         << "  \"sim_time_s\": " << simTime << ",\n"
         << "  \"warmup_s\": " << warmupTime << ",\n"
         << "  \"tx_power_dbm\": " << txPowerDbm << ",\n"
         << "  \"min_rssi_dbm\": " << minRssiDbm << ",\n"
         << "  \"freq_mhz\": " << freqMhz << ",\n"
         << "  \"ref_loss_db\": " << refLossDb << ",\n"
         << "  \"beacon_interval_s\": " << beaconInterval << ",\n"
         << "  \"probe_interval_s\": " << probeInterval << ",\n"
         << "  \"probe_bytes\": " << probeBytes << ",\n"
         << "  \"neighbor_ttl_s\": " << neighborTtl << ",\n"
         << "  \"cbr_flows\": " << cbrFlows << ",\n"
         << "  \"cbr_bytes\": " << cbrBytes << ",\n"
         << "  \"cbr_pps\": " << cbrPps << ",\n"
         << "  \"max_queue_delay_ms\": " << maxQueueDelayMs << ",\n"
         << "  \"feature_win_s\": " << featureWin << ",\n"
         << "  \"label_win_s\": " << labelWin << ",\n"
         << "  \"min_rssi_samples\": " << minRssiSamples << ",\n"
         << "  \"min_trials\": " << minTrials << ",\n"
         << "  \"flows\": [";
    for (size_t f = 0; f < flows.size(); ++f)
    {
        meta << (f ? ", " : "") << "[" << flows[f].first << ", " << flows[f].second << "]";
    }
    meta << "]\n}\n";
    meta.close();

    std::ofstream summary(outDir + "/summary.json");
    summary << std::fixed << std::setprecision(6) << "{\n"
            << "  \"seed\": " << seed << ",\n"
            << "  \"rows\": " << g_count.rows << ",\n"
            << "  \"rows_drop_low_rssi\": " << g_count.rowsDropLowRssi << ",\n"
            << "  \"rows_drop_low_trials\": " << g_count.rowsDropLowTrials << ",\n"
            << "  \"beacons_sent\": " << g_count.beaconsSent << ",\n"
            << "  \"beacons_recv\": " << g_count.beaconsRecv << ",\n"
            << "  \"probes_sent\": " << g_count.probesSent << ",\n"
            << "  \"attempts_probe\": " << g_count.attProbe << ",\n"
            << "  \"fails_probe\": " << g_count.failProbe << ",\n"
            << "  \"final_fails_probe\": " << g_count.finalFailProbe << ",\n"
            << "  \"attempts_cbr\": " << g_count.attCbr << ",\n"
            << "  \"fails_cbr\": " << g_count.failCbr << ",\n"
            << "  \"final_fails_cbr\": " << g_count.finalFailCbr << ",\n"
            << "  \"fails_unattributed\": " << g_count.failUnattributed << ",\n"
            << "  \"fails_slipped_windows\": " << g_count.failSlipped << ",\n"
            << "  \"mac_loss\": " << macLoss << ",\n"
            << "  \"psdu_bytes_probe\": " << g_psduProbe << ",\n"
            << "  \"psdu_bytes_cbr\": " << g_psduCbr << ",\n"
            << "  \"degree_mean\": " << degreeMean << ",\n"
            << "  \"degree_samples\": " << g_degreeSamples << ",\n"
            << "  \"isolated_frac\": " << isolatedFrac << ",\n"
            << "  \"queue_dequeued\": " << g_count.queueDequeued << ",\n"
            << "  \"queue_expired\": " << g_count.queueExpired << ",\n"
            << "  \"queue_drop_before_enqueue\": " << g_count.queueDropBefore << ",\n"
            << "  \"queue_drop_after_dequeue\": " << g_count.queueDropAfter << ",\n"
            << "  \"queue_delay_ms_p50\": " << delayP50 << ",\n"
            << "  \"queue_delay_ms_p90\": " << delayP90 << ",\n"
            << "  \"queue_delay_ms_p99\": " << delayP99 << ",\n"
            << "  \"queue_delay_ms_max\": " << delayMax << ",\n"
            << "  \"cbr_app_tx\": " << g_count.cbrAppTx << ",\n"
            << "  \"cbr_app_rx\": " << g_count.cbrAppRx << ",\n"
            << "  \"cbr_hops\": {";
    {
        bool first = true;
        for (const auto& [hops, count] : g_cbrHops)
        {
            summary << (first ? "" : ", ") << '"'
                    << (hops < 0 ? std::string("no_route") : std::to_string(hops)) << "\": "
                    << count;
            first = false;
        }
    }
    summary << "},\n"
            << "  \"airtime_s\": {";
    for (int c = 0; c < FC_COUNT; ++c)
    {
        summary << (c ? ", " : "") << '"' << kClassName[c] << "\": " << g_airtimeS[c];
    }
    summary << "},\n  \"airtime_frames\": {";
    for (int c = 0; c < FC_COUNT; ++c)
    {
        summary << (c ? ", " : "") << '"' << kClassName[c] << "\": " << g_frames[c];
    }
    summary << "}\n}\n";
    summary.close();

    std::cout << "--- link-dataset-fanet P2, seed " << seed << " ---\n"
              << "  rows             : " << g_count.rows << "  (bo " << g_count.rowsDropLowRssi
              << " thieu RSSI, " << g_count.rowsDropLowTrials << " thieu trial)\n"
              << "  degree (P1 def)  : " << degreeMean << "  (P1 do 6.14; co lap "
              << 100.0 * isolatedFrac << "% node-thoi-gian)\n"
              << "  beacon           : " << g_count.beaconsSent << " phat / " << g_count.beaconsRecv
              << " nhan\n"
              << "  probe attempts   : " << g_count.attProbe << "  fails " << g_count.failProbe
              << "\n"
              << "  cbr attempts     : " << g_count.attCbr << "  fails " << g_count.failCbr << "\n"
              << "  mac_loss (attempt): " << macLoss << "\n"
              << "  fails unattributed: " << g_count.failUnattributed
              << "  slipped windows: " << g_count.failSlipped << "\n"
              << "  PSDU probe/cbr   : " << g_psduProbe << " / " << g_psduCbr << " B\n"
              << "  queue            : dequeued " << g_count.queueDequeued << ", expired "
              << g_count.queueExpired << ", tran " << g_count.queueDropBefore << "\n"
              << "  queue delay ms   : p50 " << delayP50 << "  p90 " << delayP90 << "  p99 "
              << delayP99 << "  max " << delayMax << "\n"
              << "  cbr app          : tx " << g_count.cbrAppTx << "  rx " << g_count.cbrAppRx
              << "\n"
              << "  cbr hop (flow-giay): ";
    for (const auto& [hops, count] : g_cbrHops)
    {
        std::cout << (hops < 0 ? std::string("no_route") : std::to_string(hops) + " hop") << "="
                  << count << "  ";
    }
    std::cout << "\n"
              << "  --- airtime theo nguon (% cua " << simTime << " s, toan mang, chua chia "
                 "mien tranh chap) ---\n";
    for (int c = 0; c < FC_COUNT; ++c)
    {
        std::cout << "    " << std::left << std::setw(8) << kClassName[c] << std::right
                  << std::setw(10) << std::fixed << std::setprecision(2) << g_airtimeS[c]
                  << " s   " << std::setw(6) << 100.0 * g_airtimeS[c] / simTime << " %   ("
                  << g_frames[c] << " frame)\n";
    }
    std::cout << "  ghi vao          : " << outDir
              << "/{rows.csv,positions.csv,meta.json,summary.json}\n";

    return 0;
}
