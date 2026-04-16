# Cache Controller FSM Simulator

> **COA Assignment 2** — Computer Organization and Architecture  
> Student ID: `230041118`

A cycle-accurate Python simulation of a **direct-mapped, write-back cache controller** implemented as a Finite State Machine (FSM). The simulator models the complete CPU ↔ Cache ↔ Memory pipeline, logging every interface signal every clock cycle.

---

## Table of Contents

- [Overview](#overview)
- [Cache Configuration](#cache-configuration)
- [FSM Design](#fsm-design)
  - [States](#states)
  - [State Diagram](#state-diagram)
  - [Interface Signals](#interface-signals)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Requirements](#requirements)
  - [Running the Simulation](#running-the-simulation)
- [Test Scenarios](#test-scenarios)
- [Sample Output](#sample-output)
- [Timing Summary](#timing-summary)
- [Report](#report)

---

## Overview

The simulator models three cooperating hardware components:

| Component | Role |
|-----------|------|
| **CPU** | Issues a queue of read/write requests; stalls while cache is busy |
| **Cache Controller FSM** | Direct-mapped, write-back, write-allocate cache; drives all interface signals |
| **Main Memory** | 256-word flat array; never misses; 3-cycle latency for block read/write |

The cache controller is implemented as a **four-state Mealy/Moore hybrid FSM** following the design in *Patterson & Hennessy, Computer Organization and Design (RISC-V Edition), Chapter 5*.

---

## Cache Configuration

| Parameter | Value |
|-----------|-------|
| Organisation | Direct-mapped |
| Number of sets | 4 |
| Block size | 4 words |
| Address width | 8 bits |
| Tag bits | 4 bits `[addr[7:4]]` |
| Index bits | 2 bits `[addr[3:2]]` |
| Block offset bits | 2 bits `[addr[1:0]]` |
| Write policy | Write-back, write-allocate |
| Memory size | 256 words |
| Memory latency | 3 clock cycles (configurable via `MEM_LATENCY`) |

**Address layout:**

```
 Bit 7    Bit 4  Bit 3  Bit 2  Bit 1  Bit 0
 [  TAG (4 bits)  ] [ IDX (2b)] [ OFFSET (2b) ]
```

Address construction: `addr = (tag << 4) | (index << 2) | offset`

---

## FSM Design

### States

```
IDLE        →  Waiting for CPU request. Asserts cache_ready=1.
COMPARE     →  Checks tag and valid bit. Determines HIT or MISS.
ALLOCATE    →  Fetches block from memory (MEM_LATENCY cycles). Satisfies request on completion.
WRITE_BACK  →  Writes dirty evicted block to memory before proceeding to ALLOCATE.
```

### State Diagram

```
               cpu_req=1
    ┌─────────────────────────────────────────────────────┐
    ▼                                                     │
 ┌──────┐   cpu_req=1   ┌─────────┐                      │
 │      │──────────────▶│         │──── HIT ─────────────┘
 │ IDLE │               │ COMPARE │                (cache_hit=1)
 │      │◀──────────────│         │
 └──────┘   done+hit    └─────────┘
    ▲                    │       │
    │                    │       │
    │            clean   │       │  dirty
    │            miss    │       │  miss
    │                    ▼       ▼
    │           ┌──────────┐  ┌────────────┐
    │           │          │  │            │
    └───done────│ ALLOCATE │◀─│ WRITE_BACK │
   (cache_hit=1)│mem_read=1│  │mem_write=1 │
                └──────────┘  └────────────┘
                    stall=1       stall=1
```

### Interface Signals

| Signal | Direction | Description |
|--------|-----------|-------------|
| `cpu_req` | IN | CPU presents a valid request |
| `cpu_write` | IN | 1=write, 0=read |
| `cpu_addr` | IN | 8-bit word address |
| `cpu_wdata` | IN | Write data (valid when `cpu_write=1`) |
| `cache_hit` | OUT | Request satisfied from cache (asserted 1 cycle) |
| `cache_ready` | OUT | Controller in IDLE, ready for next request |
| `stall` | OUT | CPU must stall — miss being handled |
| `mem_read` | OUT | Read block from memory (held throughout ALLOCATE) |
| `mem_write` | OUT | Write dirty block to memory (held throughout WRITE_BACK) |
| `mem_addr` | OUT | Base address for current memory operation |
| `rdata` | OUT | Data returned to CPU on completed read |

---

## Project Structure

```
cache-fsm-simulator/
├── cache_fsm.py          # Main simulator (FSM + CPU + Memory)
├── COA_A2_230041118.pdf  # Full assignment report (PDF)
└── README.md             # This file
```

### `cache_fsm.py` — Key Classes

```python
CacheLine       # dataclass: valid, dirty, tag, data[4]
CPURequest      # dataclass: write flag, addr, optional wdata
Signals         # dataclass: full signal snapshot for one cycle
CacheController # FSM engine — call .step(req) each clock cycle
CPU             # Request queue feeder with stall logic
run_simulation  # Orchestrator — ties CPU + Cache together
```

---

## Getting Started

### Requirements

- Python 3.7 or later
- No external libraries required

### Running the Simulation

```bash
# Clone the repository
git clone https://github.com/<your-username>/cache-fsm-simulator.git
cd cache-fsm-simulator

# Run all 5 test scenarios
python3 cache_fsm.py
```

Output is printed to stdout. Redirect to a file to save:

```bash
python3 cache_fsm.py > simulation_output.txt
```

### Customising the Configuration

Edit the constants at the top of `cache_fsm.py`:

```python
CACHE_SETS   = 4    # number of cache lines
BLOCK_SIZE   = 4    # words per block
ADDR_BITS    = 8    # total address bits
MEM_LATENCY  = 3    # cycles for memory read/write
MEMORY_SIZE  = 256  # words in main memory
```

### Writing Your Own Scenarios

```python
from cache_fsm import CPURequest, run_simulation, addr

# addr(tag, index, offset) builds the address
requests = [
    CPURequest(write=False, addr=addr(0, 0, 0)),          # read
    CPURequest(write=True,  addr=addr(0, 0, 1), wdata=0xAB),  # write
    CPURequest(write=False, addr=addr(1, 0, 0)),          # read (conflict miss)
]
run_simulation(requests, label="My custom scenario")
```

---

## Test Scenarios

| # | Name | Requests | States Exercised |
|---|------|----------|-----------------|
| 1 | Cold-start reads | 4 reads (2 miss, 2 hit) | IDLE, COMPARE, ALLOCATE |
| 2 | Write hit + dirty bit | Read miss → write hit → read hit | IDLE, COMPARE, ALLOCATE |
| 3 | Dirty eviction | Write (dirty) → conflict read → re-read | All 4 states |
| 4 | Repeated write-back | 3 writes same index, 1 re-read | All 4 states × 2 WB cycles |
| 5 | Mixed R/W | 7 mixed requests, all transitions | All 4 states, all 6 transitions |

**All 12 FSM behaviours are covered** (100% state and transition coverage):

- ✅ IDLE waiting  
- ✅ COMPARE → IDLE on read hit  
- ✅ COMPARE → IDLE on write hit (dirty bit set)  
- ✅ COMPARE → ALLOCATE on clean read miss  
- ✅ COMPARE → ALLOCATE on clean write miss  
- ✅ COMPARE → WRITE_BACK on dirty eviction  
- ✅ WRITE_BACK → ALLOCATE  
- ✅ ALLOCATE → IDLE on read completion  
- ✅ ALLOCATE → IDLE on write-allocate completion  
- ✅ Write-back data persisted in memory  
- ✅ Read-after-write consistency  
- ✅ Non-interfering independent cache sets  

---

## Sample Output

```
Cy  1 | COMPARE    | cpu_req=1 wr=0 addr=0x00 | hit=0 rdy=1 stall=0 | ...  CPU issued request → COMPARE
Cy  2 | ALLOCATE   | cpu_req=1 wr=0 addr=0x00 | hit=0 rdy=0 stall=1 | mem_rd=1 ...  MISS (clean) → ALLOCATE
Cy  3 | ALLOCATE   | ...                                              | mem_rd=1 ...  Fetching block, mem_counter=2
Cy  4 | ALLOCATE   | ...                                              | mem_rd=1 ...  Fetching block, mem_counter=1
Cy  5 | IDLE       | cpu_req=0 ...             | hit=1 rdy=1 stall=0 | ...  ALLOC done, READ 0x00 from off=0
Cy  7 | COMPARE    | cpu_req=1 wr=0 addr=0x01 | hit=0 rdy=1 stall=0 | ...  CPU issued request → COMPARE
Cy  8 | IDLE       | cpu_req=0 ...             | hit=1 rdy=1 stall=0 | ...  READ HIT tag=0 idx=0 off=1 rdata=0x01
```

---

## Timing Summary

| Access Type | Latency | State Path |
|-------------|---------|-----------|
| Read hit | 2 cycles | IDLE → COMPARE → IDLE |
| Write hit | 2 cycles | IDLE → COMPARE → IDLE (dirty bit set) |
| Clean miss (read or write) | 5 cycles | IDLE → COMPARE → ALLOCATE(×3) → IDLE |
| Miss + dirty eviction | 8 cycles | IDLE → COMPARE → WRITE_BACK(×3) → ALLOCATE(×3) → IDLE |

*MEM_LATENCY = 3 cycles. All latencies measured from request issue to `cache_ready` assertion.*

---

## Report

The full assignment report (`COA_A2_230041118.pdf`) covers:

1. Introduction & motivation  
2. System architecture and cache configuration  
3. FSM design — states, state diagram, signal table, transition table  
4. Implementation details — memory latency, write-allocate, dirty eviction  
5. All 5 simulation scenarios with cycle-accurate signal traces  
6. Correctness analysis and coverage matrix  
7. Complete source code listing  
8. Conclusions  

---

*Computer Organization and Architecture — Assignment 2*  
*Student ID: 230041118*
