/*
 * Doc cac file .conf trong sim-config/. Dung chung cho moi scenario cua du an,
 * de dinh nghia
 * tham so khong the lech giua P0, P2 va P8 (PLAN.md muc 3: train va deploy
 * phai tinh feature giong het nhau).
 *
 * FORMAT      key = value, '#' bat dau comment, dong trong bo qua.
 *             Dung dinh dang ma sim-config/fanet-tier2.conf da tu khai bao.
 *
 * PRECEDENCE  built-in default < config file < command line flag
 *             Nhieu --config ghep duoc; file sau ghi de file truoc. Nho vay
 *             khoi physics dinh nghia MOT lan trong fanet-tier2.conf, con
 *             p0-link-probe.conf chi ghi nhung gi P0 lech di.
 *
 * KEY LA      hai tang, vi neu chi co mot tang thi config phan lop se gay:
 *             topology-probe khong biet key cua link-probe.
 *               - key khong co trong KnownKeys()  -> typo   -> NS_FATAL_ERROR
 *               - key co trong KnownKeys() nhung scenario nay khong doc
 *                                                -> canh bao to, liet ke ra
 *             Danh sach "biet nhung khong dung" in ra moi run la mot dang tu
 *             kiem: neu thay txPowerDbm trong do thi co gi rat sai.
 */

#ifndef LINKSCORE_SIM_CONFIG_H
#define LINKSCORE_SIM_CONFIG_H

#include "ns3/command-line.h"
#include "ns3/fatal-error.h"

#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace linkscore
{

/**
 * Moi key hop le cua TOAN du an, khong rieng scenario nao.
 *
 * Them key moi o P2/P8 thi phai them vao day — do la co che bat typo. Key chi
 * dung o phia Python (seedsTrain, gate*, topoDegreeThreshold) van phai co mat:
 * chung se hien trong danh sach "biet nhung khong dung" cua moi run C++, va
 * dieu do la dung.
 */
inline const std::set<std::string>&
KnownKeys()
{
    static const std::set<std::string> keys = {
        // --- Scenario / khong gian (fanet-tier2.conf)
        "numNodes",
        "simTime",
        "areaX",
        "areaY",
        "altMin",
        "altMax",
        "randomSetup",
        "numNodesMin",
        "numNodesMax",
        "areaMin",
        "areaMax",
        // --- Gauss-Markov
        "gmAlpha",
        "gmAlphaMin",
        "gmAlphaMax",
        "gmTimeStep",
        "gmVelMin",
        "gmVelMax",
        "gmDirMin",
        "gmDirMax",
        "gmPitchMin",
        "gmPitchMax",
        "gmNormVelVar",
        "gmNormVelBound",
        "gmNormDirVar",
        "gmNormDirBound",
        "gmNormPitchVar",
        "gmNormPitchBound",
        // --- PHY / propagation
        "txPowerDbm",
        "txPowerMin",
        "txPowerMax",
        "exponent",
        "minRssiDbm",
        "channelNumber",
        "dataMode",
        "frameRetryLimit",
        "nakagamiM0",
        "nakagamiM1",
        "nakagamiM2",
        "nakagamiD1",
        "nakagamiD2",
        // --- Harness do luong (P2)
        "beaconInterval",
        "beaconBytes",
        "probeInterval",
        "probeBytes",
        "neighborTtl",
        // --- Tai nen + queue (P2)
        "cbrFlows",
        "cbrBytes",
        "cbrPps",
        "cbrPpsMin",
        "cbrPpsMax",
        "maxQueueDelayMs",
        // --- Cua so feature / nhan (P2)
        "featureWin",
        "labelWin",
        "aggregateInterval",
        "minRssiSamples",
        "minTrials",
        // --- Cong nghiem thu (Python doc)
        "gateDegreeMin",
        "gateRetryMin",
        "gateMidMin",
        "gateLossMax",
        "gatePinnedMax",
        "rHalfM",
        "gateNearQMax",
        // --- Lo seed (Python doc)
        "seedsCalibration",
        "seedsTrain",
        "seedsTest",
        // --- P0 link-probe: hinh hoc 2 node bay thang, KHONG thuoc bang
        //     Simulation Setup cua paper
        "p0Fading",
        "p0Altitude",
        "p0StartDist",
        "p0Speed",
        "p0ProbeIntervalMs",
        // --- P1 topology-probe: dac thu phep do topology
        "topoBeaconInterval",
        "topoBeaconBytes",
        "topoNeighborWindow",
        "topoDegreeThreshold",
        "topoPositionInterval",
        "topoSampleInterval",
    };
    return keys;
}

/// Quet argv tim `--config=...` TRUOC CommandLine::Parse. Lap lai duoc.
inline std::vector<std::string>
ConfigPathsFromArgv(int argc, char** argv)
{
    std::vector<std::string> paths;
    const std::string prefix = "--config=";
    for (int i = 1; i < argc; ++i)
    {
        const std::string arg = argv[i];
        if (arg.rfind(prefix, 0) == 0)
        {
            paths.push_back(arg.substr(prefix.size()));
        }
    }
    return paths;
}

/// Co mat trong argv? Dung cho co phai xu ly truoc Parse.
inline bool
FlagInArgv(int argc, char** argv, const std::string& flag)
{
    for (int i = 1; i < argc; ++i)
    {
        const std::string arg = argv[i];
        if (arg == flag || arg.rfind(flag + "=", 0) == 0)
        {
            return true;
        }
    }
    return false;
}

class SimConfig
{
  public:
    /// Nap cac file theo thu tu; file sau ghi de file truoc.
    void Load(const std::vector<std::string>& paths, bool allowUnknownKeys = false)
    {
        for (const auto& path : paths)
        {
            std::ifstream in(path);
            if (!in)
            {
                NS_FATAL_ERROR("sim-config: khong mo duoc " << path);
            }
            m_files.push_back(path);

            std::string line;
            uint32_t lineNo = 0;
            while (std::getline(in, line))
            {
                ++lineNo;
                const auto hash = line.find('#');
                if (hash != std::string::npos)
                {
                    line = line.substr(0, hash);
                }
                const auto eq = line.find('=');
                if (eq == std::string::npos)
                {
                    if (!Trim(line).empty())
                    {
                        NS_FATAL_ERROR("sim-config: " << path << ':' << lineNo
                                                      << " khong phai 'key = value': " << line);
                    }
                    continue;
                }
                const std::string key = Trim(line.substr(0, eq));
                const std::string value = Trim(line.substr(eq + 1));
                if (key.empty())
                {
                    NS_FATAL_ERROR("sim-config: " << path << ':' << lineNo << " key rong");
                }
                if (KnownKeys().count(key) == 0)
                {
                    if (allowUnknownKeys)
                    {
                        std::cerr << "sim-config: CANH BAO key la '" << key << "' (" << path << ':'
                                  << lineNo << ") — bo qua vi --allowUnknownKeys\n";
                        continue;
                    }
                    NS_FATAL_ERROR("sim-config: key khong co trong registry: '"
                                   << key << "' (" << path << ':' << lineNo
                                   << ").\n  Day gan nhu chac chan la typo. Neu la key moi that "
                                      "thi them vao KnownKeys() trong scratch/linkscore/"
                                      "sim-config.h.\n  Bo qua tam bang --allowUnknownKeys.");
                }
                if (m_values.count(key) && m_values[key].file == path)
                {
                    std::cerr << "sim-config: CANH BAO '" << key << "' xuat hien hai lan trong "
                              << path << " (dong " << lineNo << "), lan sau thang\n";
                }
                m_values[key] = Entry{value, path, lineNo};
            }
        }
    }

    /**
     * Khai bao mot tham so: ap gia tri tu config (neu co) roi dang ky voi
     * CommandLine. Ten flag trung ten key — mot khai niem mot ten.
     *
     * Phai goi TRUOC cmd.Parse(). Provenance in ra o Finish().
     */
    template <typename T>
    void Add(ns3::CommandLine& cmd, const std::string& key, const std::string& help, T& var)
    {
        NS_ASSERT_MSG(KnownKeys().count(key) == 1,
                      "sim-config: scenario doc key '" << key << "' khong co trong KnownKeys()");
        m_consumed.insert(key);

        const T builtinDefault = var;
        bool fromConfig = false;
        std::string file;
        if (m_values.count(key))
        {
            const Entry& e = m_values.at(key);
            var = Convert<T>(e.value, key, e.file, e.lineNo);
            fromConfig = true;
            file = e.file;
        }
        const T configValue = var;

        cmd.AddValue(key, help, var);

        // Chup gia tri bang value, bien bang reference: doc lai sau Parse.
        m_printers.push_back([&var, key, builtinDefault, configValue, fromConfig, file]() {
            std::string source;
            if (fromConfig)
            {
                source = (var == configValue) ? file : ("cmdline (ghi de " + file + ")");
            }
            else
            {
                source = (var == builtinDefault) ? "default" : "cmdline";
            }
            std::ostringstream value;
            value << std::boolalpha << var;
            std::cout << "  " << std::left << std::setw(22) << key << std::setw(16) << value.str()
                      << source << '\n';
        });
    }

    /// Goi SAU cmd.Parse(). Tuy chon in provenance va canh bao key khong dung.
    void Finish(bool printValues = true, bool warnUnused = true) const
    {
        if (printValues)
        {
            std::cout << "--- cau hinh hieu dung (" << m_files.size() << " file config) ---\n";
            for (const auto& path : m_files)
            {
                std::cout << "  # " << path << '\n';
            }
            for (const auto& printer : m_printers)
            {
                printer();
            }
        }

        std::vector<std::string> unused;
        for (const auto& [key, entry] : m_values)
        {
            if (m_consumed.count(key) == 0)
            {
                unused.push_back(key);
            }
        }
        if (warnUnused && !unused.empty())
        {
            std::cerr << "sim-config: CANH BAO " << unused.size()
                      << " key co trong registry nhung scenario nay KHONG doc:\n   ";
            for (size_t i = 0; i < unused.size(); ++i)
            {
                std::cerr << unused[i] << (i + 1 < unused.size() ? ", " : "\n");
            }
            std::cerr << "   Binh thuong khi mot scenario nap ca file nominal (vi du seedsTrain,"
                         " gate* la cua Python).\n"
                         "   NHUNG neu mot tham so vat ly nam trong danh sach nay thi scenario"
                         " dang chay bang default, khong bang config.\n";
        }
    }

    const std::vector<std::string>& Files() const
    {
        return m_files;
    }

  private:
    struct Entry
    {
        std::string value;
        std::string file;
        uint32_t lineNo;
    };

    static std::string Trim(const std::string& s)
    {
        const auto begin = s.find_first_not_of(" \t\r\n");
        if (begin == std::string::npos)
        {
            return "";
        }
        const auto end = s.find_last_not_of(" \t\r\n");
        return s.substr(begin, end - begin + 1);
    }

    template <typename T>
    static T Convert(const std::string& raw,
                     const std::string& key,
                     const std::string& file,
                     uint32_t lineNo)
    {
        std::istringstream in(raw);
        T out{};
        in >> std::boolalpha >> out;
        if (in.fail())
        {
            NS_FATAL_ERROR("sim-config: " << file << ':' << lineNo << " khong doi duoc '" << raw
                                          << "' sang kieu cua '" << key << '\'');
        }
        return out;
    }

    std::map<std::string, Entry> m_values;
    std::vector<std::string> m_files;
    std::set<std::string> m_consumed;
    std::vector<std::function<void()>> m_printers;
};

/// bool: nhan ca true/false va 1/0 — viet 1 trong file config la phan xa tu nhien.
template <>
inline bool
SimConfig::Convert<bool>(const std::string& raw,
                         const std::string& key,
                         const std::string& file,
                         uint32_t lineNo)
{
    if (raw == "true" || raw == "1" || raw == "yes" || raw == "on")
    {
        return true;
    }
    if (raw == "false" || raw == "0" || raw == "no" || raw == "off")
    {
        return false;
    }
    NS_FATAL_ERROR("sim-config: " << file << ':' << lineNo << " '" << raw << "' khong phai bool cho '"
                                  << key << "' (dung true/false)");
    return false;
}

/// std::string doc ca dong (khong dung >> vi no cat o dau trang).
template <>
inline std::string
SimConfig::Convert<std::string>(const std::string& raw,
                                const std::string& /*key*/,
                                const std::string& /*file*/,
                                uint32_t /*lineNo*/)
{
    return raw;
}

} // namespace linkscore

#endif // LINKSCORE_SIM_CONFIG_H
