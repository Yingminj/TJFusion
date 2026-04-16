#pragma once

#include <array>
#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

// TPM license enforcement using tpm2-tools, equivalent to tpm_check.py.
//
// Contract:
// - Reads sealed blobs from MYAPP_TPM_DIR (if set) or /etc/myapp/tpm
//   - Requires files: sealed.pub, sealed.priv
// - Executes: tpm2_createprimary, tpm2_load, tpm2_unseal
// - Returns the unsealed 32-byte key (if requested) and success=true on success
// - On failure returns success=false and fills error message
//
// Usage example:
//   std::string err;
//   if (!EnforceTpmLicense(err)) {
//       std::cerr << "Not licensed for this machine: " << err << std::endl;
//       return 1;
//   }
//   std::cout << "License OK" << std::endl;
//
namespace myapp {

namespace fs = std::filesystem;

inline std::string GetEnvOr(const char* key, std::string_view defv) {
    const char* v = std::getenv(key);
    return v && *v ? std::string(v) : std::string(defv);
}

inline bool IsExecutable(const fs::path& p) {
    std::error_code ec;
    auto st = fs::status(p, ec);
    if (ec) return false;
    if (!fs::is_regular_file(st)) return false;
#ifdef _WIN32
    return true; // Not relevant on Windows for tpm2-tools
#else
    return (access(p.c_str(), X_OK) == 0);
#endif
}

inline bool FindInPath(const std::string& exe, fs::path& out) {
    const char* path = std::getenv("PATH");
    if (!path) return false;
    std::string p(path);
    size_t start = 0;
    while (start <= p.size()) {
        size_t end = p.find(':', start);
        if (end == std::string::npos) end = p.size();
        fs::path dir = p.substr(start, end - start);
        fs::path cand = dir / exe;
        if (IsExecutable(cand)) { out = cand; return true; }
        start = end + 1;
    }
    return false;
}

inline int RunSilently(const std::string& cmdline) {
#ifdef _WIN32
    // Not supported on Windows in this helper.
    (void)cmdline;
    return -1;
#else
    // Redirect stdout/stderr to /dev/null for cleanliness
    std::string full = cmdline + " > /dev/null 2>&1";
    int rc = std::system(full.c_str());
    if (rc == -1) return -1;
    // system() returns exit status in the upper bits; normalize like sh
    if (WIFEXITED(rc)) return WEXITSTATUS(rc);
    return -1;
#endif
}

inline bool ReadAll(const fs::path& p, std::vector<uint8_t>& out, std::string& err) {
    std::ifstream ifs(p, std::ios::binary);
    if (!ifs.is_open()) { err = std::string("Failed to open ") + p.string(); return false; }
    out.assign(std::istreambuf_iterator<char>(ifs), std::istreambuf_iterator<char>());
    return true;
}

inline bool TpmUnseal(std::vector<uint8_t>& key_out, std::string& error_out) {
    try {
        const std::string tpm_dir = GetEnvOr("MYAPP_TPM_DIR", "/etc/myapp/tpm");
        const fs::path pub = fs::path(tpm_dir) / "sealed.pub";
        const fs::path priv = fs::path(tpm_dir) / "sealed.priv";

        // Check directory presence and permissions
        std::error_code ec;
        if (!fs::is_directory(tpm_dir, ec)) {
            if (ec == std::errc::permission_denied) {
                error_out = std::string("Permission denied to access ") + tpm_dir + ". Run as root or adjust permissions (group & perms).";
                return false;
            }
            error_out = std::string("TPM directory not found: ") + tpm_dir;
            return false;
        }

        // Check files exist
        if (!fs::exists(pub) || !fs::exists(priv)) {
            error_out = std::string("TPM sealed object missing files in ") + tpm_dir;
            return false;
        }

        // Ensure required commands
        for (const char* exe : {"tpm2_createprimary", "tpm2_load", "tpm2_unseal"}) {
            fs::path found;
            if (!FindInPath(exe, found)) {
                error_out = std::string("Missing command: ") + exe + ". Please install tpm2-tools.";
                return false;
            }
        }

        // Temp dir
        std::array<char, 64> tmpl{};
        std::snprintf(tmpl.data(), tmpl.size(), "/tmp/tpmcxx_%ld_XXXXXX", static_cast<long>(::getpid()));
        char* tdir = ::mkdtemp(tmpl.data());
        if (!tdir) { error_out = "Failed to create temp dir"; return false; }
        fs::path d(tdir);
        auto prim = d / "primary.ctx";
        auto seal = d / "seal.ctx";
        auto outb = d / "out.bin";

        // Run: create primary
        {
            std::string cmd = std::string("tpm2_createprimary -C o -G ecc -g sha256 -c ") + prim.string();
            int rc = RunSilently(cmd);
            if (rc != 0) { error_out = "TPM operation failed at tpm2_createprimary. Check /dev/tpmrm0 and user permission (group 'tss')."; return false; }
        }
        // Run: load sealed object
        {
            std::string cmd = std::string("tpm2_load -C ") + prim.string() + " -u " + pub.string() + " -r " + priv.string() + " -c " + seal.string();
            int rc = RunSilently(cmd);
            if (rc != 0) { error_out = "TPM operation failed at tpm2_load. Sealed blobs may not belong to this TPM."; return false; }
        }
        // Run: unseal
        {
            std::string cmd = std::string("tpm2_unseal -c ") + seal.string() + " -o " + outb.string();
            int rc = RunSilently(cmd);
            if (rc != 0) { error_out = "TPM operation failed at tpm2_unseal. Check permissions and TPM availability."; return false; }
        }

        std::vector<uint8_t> key;
        if (!ReadAll(outb, key, error_out)) return false;
        key_out = std::move(key);
        return true;
    } catch (const fs::filesystem_error& e) {
        if (e.code() == std::errc::permission_denied) {
            error_out = std::string("Permission denied: ") + e.path1().string();
        } else {
            error_out = std::string("Filesystem error: ") + e.what();
        }
        return false;
    } catch (const std::exception& e) {
        error_out = e.what();
        return false;
    }
}

inline bool EnforceTpmLicense(std::string& error_out, std::vector<uint8_t>* key_opt = nullptr) {
    std::vector<uint8_t> key;
    if (!TpmUnseal(key, error_out)) return false;
    if (key.size() != 32) { error_out = "Bad key length"; return false; }
    if (key_opt) *key_opt = key; // optional return of the raw key
    return true;
}

} // namespace myapp


// usage
// #include <iostream>
// #include "tpm/tpm_check.hpp"

// int main() {
//     std::string err;
//     if (!myapp::EnforceTpmLicense(err)) {
//         std::cerr << "Not licensed for this machine: " << err << std::endl;
//         return 1;
//     }
//     std::cout << "License OK" << std::endl;
//     return 0;
// }