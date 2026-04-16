#include <iostream>
#include <iomanip>
#include <fstream>
#include <sstream>
#include <vector>
#include <cstdint>
#include <unordered_map>
#include <string>

const uint32_t CACHE_SIZE = 16384;
const uint32_t BLOCK_SIZE = 16;
const uint32_t NUM_BLOCKS = CACHE_SIZE / BLOCK_SIZE;

enum class CacheState { IDLE, COMPARE_TAG, WRITE_BACK, ALLOCATE };

struct CacheBlock {
    bool valid = false, dirty = false;
    uint32_t tag = 0, data[4] = {0,0,0,0};
};

struct CpuToCacheSignals {
    bool valid, isWrite;
    uint32_t addr, data;
};

struct MemToCacheSignals {
    bool ready;
    uint32_t data[4];
};

// --- Main Memory ---
class MainMemory {
private:
    int latency_counter = 0;
    bool processing = false;
    uint32_t target_latency;
    std::unordered_map<uint32_t, uint32_t> storage;

public:
    MainMemory(uint32_t latency = 3) : target_latency(latency) {}

    MemToCacheSignals tick(bool mem_valid, bool mem_isWrite, uint32_t addr, uint32_t write_data[4]) {
        MemToCacheSignals response = {false, {0,0,0,0}};
        if (mem_valid && !processing) {
            processing = true;
            latency_counter = target_latency;
            std::cout << "    [MEM] Started " << (mem_isWrite ? "Write" : "Read")
                      << " @ 0x" << std::hex << addr << std::dec
                      << " (Latency: " << target_latency << " cycles)\n";
        }
        if (processing) {
            if (--latency_counter == 0) {
                processing = false;
                response.ready = true;
                if (mem_isWrite) {
                    for(int i = 0; i < 4; ++i) storage[addr + (i * 4)] = write_data[i];
                } else {
                    for(int i = 0; i < 4; ++i) response.data[i] = storage[addr + (i * 4)];
                }
                std::cout << "    [MEM] Transaction Complete. Ready signal High.\n";
            }
        }
        return response;
    }
};

// --- Cache Controller ---
class CacheController {
private:
    CacheState state = CacheState::IDLE;
    CacheBlock cache[NUM_BLOCKS];
    bool cpu_ready = false;

    uint32_t global_cycles = 0;
    uint32_t cpu_data_out = 0, hits = 0, misses = 0, write_backs = 0;

    bool mem_valid = false, mem_isWrite = false;
    uint32_t mem_addr = 0, mem_data_out[4] = {0};

public:
    bool isCpuReady() const { return cpu_ready; }
    uint32_t getCpuDataOut() const { return cpu_data_out; }
    bool getMemValid() const { return mem_valid; }
    bool getMemIsWrite() const { return mem_isWrite; }
    uint32_t getMemAddr() const { return mem_addr; }
    uint32_t* getMemDataOut() { return mem_data_out; }
    uint32_t getGlobalCycles() const { return global_cycles; }

    std::string getStateName() const {
        switch(state) {
            case CacheState::IDLE: return "IDLE";
            case CacheState::COMPARE_TAG: return "COMPARE_TAG";
            case CacheState::WRITE_BACK: return "WRITE_BACK";
            case CacheState::ALLOCATE: return "ALLOCATE";
        }
        return "UNKNOWN";
    }

    void tick(CpuToCacheSignals cpu_in, MemToCacheSignals mem_in) {
        global_cycles++;

        uint32_t offset = cpu_in.addr & 0xF;
        uint32_t word_idx = (offset >> 2) & 0x3;
        uint32_t index = (cpu_in.addr >> 4) & 0x3FF;
        uint32_t tag = cpu_in.addr >> 14;
        CacheBlock& block = cache[index];

        switch(state) {
            case CacheState::IDLE:
                cpu_ready = false;
                if (cpu_in.valid) {
                    std::cout << "    [CPU] New Request -> Tag: 0x" << std::hex << tag
                              << ", Index: " << std::dec << index << ", Word: " << word_idx << "\n";
                    state = CacheState::COMPARE_TAG;
                }
                break;

            case CacheState::COMPARE_TAG:
                if (block.valid && block.tag == tag) {
                    hits++; cpu_ready = true;
                    if (cpu_in.isWrite) {
                        block.data[word_idx] = cpu_in.data; block.dirty = true;
                        std::cout << "    [CACHE] Write Hit! Data stored in block, Dirty bit set.\n";
                    } else {
                        cpu_data_out = block.data[word_idx];
                        std::cout << "    [CACHE] Read Hit! Data retrieved from block.\n";
                    }
                    state = CacheState::IDLE;
                } else {
                    misses++; cpu_ready = false;
                    std::cout << "    [CACHE] Miss! Checking eviction strategy...\n";
                    if (block.valid && block.dirty) {
                        std::cout << "    [CACHE] Dirty Block Detected. Forcing WRITE-BACK.\n";
                        state = CacheState::WRITE_BACK; mem_valid = true; mem_isWrite = true;
                        mem_addr = (block.tag << 14) | (index << 4);
                        for(int i=0; i<4; ++i) mem_data_out[i] = block.data[i];
                    } else {
                        std::cout << "    [CACHE] Index is clean/empty. Proceeding to ALLOCATE.\n";
                        state = CacheState::ALLOCATE; mem_valid = true; mem_isWrite = false;
                        mem_addr = cpu_in.addr & 0xFFFFFFF0;
                    }
                }
                break;

            case CacheState::WRITE_BACK:
                if (mem_in.ready) {
                    write_backs++;
                    std::cout << "    [CACHE] Write-Back Finished. Now loading new block (ALLOCATE).\n";
                    state = CacheState::ALLOCATE;
                    mem_valid = true; mem_isWrite = false;
                    mem_addr = cpu_in.addr & 0xFFFFFFF0;
                }
                break;

            case CacheState::ALLOCATE:
                if (mem_in.ready) {
                    std::cout << "    [CACHE] Block fetched from memory. Updating Tag and Data.\n";
                    for(int i=0; i<4; ++i) block.data[i] = mem_in.data[i];
                    block.valid = true; block.dirty = false; block.tag = tag;
                    mem_valid = false; state = CacheState::COMPARE_TAG;
                }
                break;
        }
    }

    void display() {
        std::cout << "\n    --- Current Cache Content (Valid Blocks Only) ---\n";
        bool empty = true;
        for (int i = 0; i < NUM_BLOCKS; ++i) {
            if (cache[i].valid) {
                empty = false;
                std::cout << "    Idx [" << std::setw(4) << std::right << i << "] | "
                          << "Tag: 0x" << std::hex << std::setw(5) << std::left << cache[i].tag << std::dec << " | "
                          << "Dirty: " << cache[i].dirty << " | Data: [";
                for(int j=0; j<4; ++j) {
                    std::cout << cache[i].data[j] << (j < 3 ? ", " : "");
                }
                std::cout << "]\n";
            }
        }
        if (empty) std::cout << "    (Cache is completely empty)\n";
        std::cout << "    -------------------------------------------------\n";
    }

    void printStats() const {
        uint32_t total = hits + misses;
        std::cout << "\n========================================\n"
                  << "|            Cache Statistics          |\n"
                  << "========================================\n"
                  << "| Hits         : " << std::setw(10) << hits << "            |\n"
                  << "| Misses       : " << std::setw(10) << misses << "            |\n"
                  << "| Write-Backs  : " << std::setw(10) << write_backs << "            |\n"
                  << "| Total Cycles : " << std::setw(10) << global_cycles << "            |\n"
                  << "| Hit Rate     : " << std::fixed << std::setprecision(2)
                  << (total ? (100.0 * hits / total) : 0.0) << "%" << "                |\n"
                  << "========================================\n";
    }
};

// --- Engine to run individual requests ---
void runRequest(CpuToCacheSignals& req, CacheController& cache, MainMemory& memory) {
    uint32_t start_cycles = cache.getGlobalCycles();
    int local_timeout = 0;

    do {
        std::cout << "Cycle " << std::setw(4) << cache.getGlobalCycles() + 1 << " | FSM: " << cache.getStateName() << "\n";

        MemToCacheSignals m_res = memory.tick(cache.getMemValid(), cache.getMemIsWrite(), cache.getMemAddr(), cache.getMemDataOut());
        cache.tick(req, m_res);
        local_timeout++;

    } while (!cache.isCpuReady() && local_timeout < 100);

    uint32_t cost = cache.getGlobalCycles() - start_cycles;

    std::cout << ">> [CPU] Operation fulfilled! Cost: " << cost << " CC (Total Uptime: " << cache.getGlobalCycles() << " CC)\n";

    cache.display();
}

int main() {
    CacheController cache;
    MainMemory memory(3);
    std::string line, cmd;

    std::cout << "--- Cache FSM Simulator ---\n";
    std::cout << "Commands: 'r <addr>' (read) or 'w <addr> <data>' (write). Type 'sim' for a quick simulation. Type 'exit' to quit.\n";

    while (std::cout << "\n> " && std::getline(std::cin, line)) {
        if (line == "exit") break;
        std::stringstream ss(line);
        ss >> cmd;

        if (cmd == "sim") {
            std::string filename;
            if (!(ss >> filename)) filename = "sim_input.txt";

            std::ifstream script(filename);
            if (!script) { std::cout << "!! Error: Could not find file: " << filename << "\n"; continue; }

            std::cout << ">>> LOADING BATCH SCRIPT: " << filename << "\n";
            std::string s_line;
            while (std::getline(script, s_line)) {
                if (s_line.empty()) continue;
                std::stringstream s_ss(s_line);
                std::string s_cmd; uint32_t s_addr, s_data = 0;
                s_ss >> s_cmd >> std::hex >> s_addr >> std::dec;
                if (s_cmd == "w") s_ss >> s_data;

                std::cout << "\n> " << s_line << "\n";
                CpuToCacheSignals req = {(s_cmd=="r"||s_cmd=="w"), (s_cmd=="w"), s_addr, s_data};
                runRequest(req, cache, memory);
            }
            std::cout << "\n>>> BATCH PROCESSING COMPLETE\n";
        }
        else if (cmd == "r" || cmd == "w") {
            uint32_t addr, data = 0;
            ss >> std::hex >> addr >> std::dec;
            if (cmd == "w") ss >> data;
            CpuToCacheSignals req = {true, (cmd == "w"), addr, data};
            runRequest(req, cache, memory);
        }
    }
    cache.printStats();
    return 0;
}
