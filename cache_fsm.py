"""
Simple Cache Controller FSM Simulator
Based on the standard direct-mapped write-back cache controller FSM
(Patterson & Hennessy style, Computer Organization and Design)

States:
  IDLE       - Waiting for CPU request
  COMPARE    - Comparing tag of requested address with cache tag
  ALLOCATE   - Cache miss: reading block from memory into cache (write-allocate)
  WRITE_BACK - Cache miss on dirty line: writing dirty block back to memory first

Signals (inputs):
  cpu_req     - CPU issues a read or write request (1/0)
  cpu_write   - 1=write, 0=read
  cpu_addr    - 32-bit address from CPU
  cpu_wdata   - data to write
  mem_ready   - memory signals it has completed read/write operation

Signals (outputs):
  cache_hit   - 1 if access is a hit
  cache_ready - 1 when cache is ready for next CPU request
  stall       - CPU must stall
  mem_read    - assert memory read
  mem_write   - assert memory write
  mem_addr    - address sent to memory
  rdata       - data returned to CPU on a read
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum, auto

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CACHE_SETS      = 4      # number of cache lines (direct-mapped)
BLOCK_SIZE      = 4      # words per block
ADDR_BITS       = 8      # total address bits (simplified)
OFFSET_BITS     = 2      # log2(BLOCK_SIZE)
INDEX_BITS      = 2      # log2(CACHE_SETS)
TAG_BITS        = ADDR_BITS - OFFSET_BITS - INDEX_BITS  # 4 bits
MEMORY_SIZE     = 256    # words
MEM_LATENCY     = 3      # cycles for memory read/write

# ---------------------------------------------------------------------------
# FSM States
# ---------------------------------------------------------------------------
class State(Enum):
    IDLE       = auto()
    COMPARE    = auto()
    ALLOCATE   = auto()
    WRITE_BACK = auto()

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
@dataclass
class CacheLine:
    valid: bool  = False
    dirty: bool  = False
    tag:   int   = 0
    data:  List[int] = field(default_factory=lambda: [0]*BLOCK_SIZE)

@dataclass
class CPURequest:
    write:  bool
    addr:   int
    wdata:  int = 0

@dataclass
class Signals:
    """Snapshot of all interface signals for one cycle."""
    cycle:       int
    state:       State
    cpu_req:     bool
    cpu_write:   bool
    cpu_addr:    Optional[int]
    cache_hit:   bool
    cache_ready: bool
    stall:       bool
    mem_read:    bool
    mem_write:   bool
    mem_addr:    Optional[int]
    rdata:       Optional[int]
    note:        str = ""

    def pretty(self) -> str:
        def b(v): return '1' if v else '0'
        addr_s  = f"0x{self.cpu_addr:02X}"  if self.cpu_addr  is not None else "---"
        maddr_s = f"0x{self.mem_addr:02X}"  if self.mem_addr  is not None else "---"
        rd_s    = f"0x{self.rdata:04X}"     if self.rdata     is not None else "----"
        return (
            f"Cy{self.cycle:3d} | {self.state.name:<10s} | "
            f"cpu_req={b(self.cpu_req)} wr={b(self.cpu_write)} addr={addr_s} | "
            f"hit={b(self.cache_hit)} rdy={b(self.cache_ready)} stall={b(self.stall)} | "
            f"mem_rd={b(self.mem_read)} mem_wr={b(self.mem_write)} maddr={maddr_s} | "
            f"rdata={rd_s}  {self.note}"
        )

# ---------------------------------------------------------------------------
# Cache Controller FSM
# ---------------------------------------------------------------------------
class CacheController:
    def __init__(self):
        self.state    = State.IDLE
        self.lines    = [CacheLine() for _ in range(CACHE_SETS)]
        self.memory   = [i & 0xFF for i in range(MEMORY_SIZE)]  # pre-fill memory
        self.mem_counter = 0    # countdown for memory latency
        self.cur_req: Optional[CPURequest] = None
        self.cycle    = 0
        self.log: List[Signals] = []

    # ---- address decode -----------------------------------------------
    def _decode(self, addr: int):
        offset = addr & ((1 << OFFSET_BITS) - 1)
        index  = (addr >> OFFSET_BITS) & ((1 << INDEX_BITS) - 1)
        tag    = (addr >> (OFFSET_BITS + INDEX_BITS)) & ((1 << TAG_BITS) - 1)
        return tag, index, offset

    # ---- memory helpers -----------------------------------------------
    def _mem_block_addr(self, tag, index) -> int:
        """Return the base word address in memory for a tag/index."""
        return ((tag << INDEX_BITS) | index) << OFFSET_BITS

    def _read_block_from_mem(self, tag, index) -> List[int]:
        base = self._mem_block_addr(tag, index)
        return [self.memory[base + i] for i in range(BLOCK_SIZE)]

    def _write_block_to_mem(self, tag, index, data: List[int]):
        base = self._mem_block_addr(tag, index)
        for i, v in enumerate(data):
            self.memory[base + i] = v

    # ---- one clock step -----------------------------------------------
    def step(self, req: Optional[CPURequest] = None) -> Signals:
        self.cycle += 1
        # defaults
        cache_hit = cache_ready = mem_read = mem_write = stall = False
        mem_addr: Optional[int] = None
        rdata:    Optional[int] = None
        note = ""

        if self.state == State.IDLE:
            cache_ready = True
            stall = False
            if req is not None:
                self.cur_req = req
                self.state = State.COMPARE
                note = "CPU issued request → COMPARE"
            else:
                note = "Waiting for CPU request"

        elif self.state == State.COMPARE:
            req_in = self.cur_req
            tag, index, offset = self._decode(req_in.addr)
            line = self.lines[index]

            if line.valid and line.tag == tag:
                # HIT
                cache_hit  = True
                cache_ready = True
                stall = False
                if req_in.write:
                    line.data[offset] = req_in.wdata
                    line.dirty = True
                    note = f"WRITE HIT  tag={tag} idx={index} off={offset} data=0x{req_in.wdata:02X}"
                else:
                    rdata = line.data[offset]
                    note = f"READ HIT   tag={tag} idx={index} off={offset} rdata=0x{rdata:02X}"
                self.state = State.IDLE
                self.cur_req = None
            else:
                # MISS
                cache_hit = False
                stall = True
                if line.valid and line.dirty:
                    # must write back first
                    self.state = State.WRITE_BACK
                    self.mem_counter = MEM_LATENCY
                    mem_write = True
                    mem_addr  = self._mem_block_addr(line.tag, index)
                    note = f"MISS + dirty line → WRITE_BACK  wb_addr=0x{mem_addr:02X}"
                else:
                    self.state = State.ALLOCATE
                    self.mem_counter = MEM_LATENCY
                    mem_read = True
                    mem_addr = self._mem_block_addr(tag, index)
                    note = f"MISS (clean) → ALLOCATE  fetch_addr=0x{mem_addr:02X}"

        elif self.state == State.WRITE_BACK:
            tag, index, offset = self._decode(self.cur_req.addr)
            line = self.lines[index]
            stall = True
            mem_write = True
            mem_addr  = self._mem_block_addr(line.tag, index)
            self.mem_counter -= 1
            note = f"Writing back dirty block, mem_counter={self.mem_counter}"

            if self.mem_counter == 0:
                # actually write to simulated memory
                self._write_block_to_mem(line.tag, index, line.data)
                line.dirty = False
                # now allocate
                self.state = State.ALLOCATE
                self.mem_counter = MEM_LATENCY
                note += " → done, switching to ALLOCATE"

        elif self.state == State.ALLOCATE:
            tag, index, offset = self._decode(self.cur_req.addr)
            line = self.lines[index]
            stall = True
            mem_read = True
            mem_addr = self._mem_block_addr(tag, index)
            self.mem_counter -= 1
            note = f"Fetching block from memory, mem_counter={self.mem_counter}"

            if self.mem_counter == 0:
                # fill cache line
                line.data  = self._read_block_from_mem(tag, index)
                line.valid = True
                line.dirty = False
                line.tag   = tag
                # satisfy original request
                req_in = self.cur_req
                if req_in.write:
                    line.data[offset] = req_in.wdata
                    line.dirty = True
                    note += f" → ALLOC done, WRITE 0x{req_in.wdata:02X} to off={offset}"
                else:
                    rdata = line.data[offset]
                    note += f" → ALLOC done, READ  0x{rdata:02X} from off={offset}"
                cache_hit  = True
                cache_ready = True
                stall = False
                self.state = State.IDLE
                self.cur_req = None

        sig = Signals(
            cycle       = self.cycle,
            state       = self.state if self.cur_req is not None or self.state == State.IDLE else State.IDLE,
            cpu_req     = self.cur_req is not None,
            cpu_write   = self.cur_req.write if self.cur_req else False,
            cpu_addr    = self.cur_req.addr if self.cur_req else (req.addr if req else None),
            cache_hit   = cache_hit,
            cache_ready = cache_ready,
            stall       = stall,
            mem_read    = mem_read,
            mem_write   = mem_write,
            mem_addr    = mem_addr,
            rdata       = rdata,
            note        = note,
        )
        # Fix: use state before transition for logging
        sig.state = self.state
        self.log.append(sig)
        return sig


# ---------------------------------------------------------------------------
# CPU (feeds requests from a queue)
# ---------------------------------------------------------------------------
class CPU:
    def __init__(self, requests: List[CPURequest]):
        self.queue    = list(requests)
        self.pending  = False   # waiting for cache to finish
        self.cur: Optional[CPURequest] = None

    def tick(self, cache_ready: bool):
        """Returns the request to give the cache this cycle (or None)."""
        if not self.pending:
            if self.queue:
                self.cur     = self.queue.pop(0)
                self.pending = True
                return self.cur
            return None
        else:
            # still waiting
            if cache_ready:
                self.pending = False
            return None


# ---------------------------------------------------------------------------
# Full simulation runner
# ---------------------------------------------------------------------------
def run_simulation(requests: List[CPURequest], label="Simulation") -> List[Signals]:
    print(f"\n{'='*110}")
    print(f"  {label}")
    print(f"{'='*110}")
    hdr = (f"{'Cycle':>5}  {'State':<10}  "
           f"{'cpu_req':>7} {'wr':>2} {'addr':>6}  "
           f"{'hit':>3} {'rdy':>3} {'stall':>5}  "
           f"{'mem_rd':>6} {'mem_wr':>6} {'maddr':>7}  "
           f"{'rdata':>6}  Note")
    print(hdr)
    print('-'*110)

    cache = CacheController()
    cpu   = CPU(requests)
    cycle = 0
    max_cycles = 200

    while cycle < max_cycles:
        cache_ready = (cache.state == State.IDLE and cache.cur_req is None)
        req = cpu.tick(cache_ready)
        sig = cache.step(req)
        print(sig.pretty())
        cycle += 1
        if not cpu.pending and not cpu.queue and cache.state == State.IDLE:
            break

    return cache.log


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------
def addr(tag, index, offset):
    """Build an address from components."""
    return (tag << (INDEX_BITS + OFFSET_BITS)) | (index << OFFSET_BITS) | offset

if __name__ == "__main__":

    print("\n" + "#"*110)
    print("  CACHE CONTROLLER FSM SIMULATOR")
    print(f"  Config: {CACHE_SETS} sets, {BLOCK_SIZE} words/block, {ADDR_BITS}-bit addr "
          f"[tag={TAG_BITS}b | index={INDEX_BITS}b | offset={OFFSET_BITS}b]")
    print("#"*110)

    # ------------------------------------------------------------------
    # Scenario 1: Cold-start reads (all misses → ALLOCATE)
    # ------------------------------------------------------------------
    reqs1 = [
        CPURequest(write=False, addr=addr(0,0,0)),  # miss
        CPURequest(write=False, addr=addr(0,0,1)),  # hit (same block)
        CPURequest(write=False, addr=addr(1,1,2)),  # miss
        CPURequest(write=False, addr=addr(1,1,3)),  # hit
    ]
    run_simulation(reqs1, "SCENARIO 1 — Cold-start reads (compulsory misses then hits)")

    # ------------------------------------------------------------------
    # Scenario 2: Write hit and dirty bit
    # ------------------------------------------------------------------
    reqs2 = [
        CPURequest(write=False, addr=addr(0,0,0)),   # miss → allocate
        CPURequest(write=True,  addr=addr(0,0,0), wdata=0xAB),  # write HIT → dirty
        CPURequest(write=False, addr=addr(0,0,0)),   # read HIT (dirty line)
    ]
    run_simulation(reqs2, "SCENARIO 2 — Write hit sets dirty bit")

    # ------------------------------------------------------------------
    # Scenario 3: Write-back on eviction
    # ------------------------------------------------------------------
    reqs3 = [
        CPURequest(write=True,  addr=addr(0,0,0), wdata=0xDE),  # miss→alloc→write (dirty)
        CPURequest(write=False, addr=addr(1,0,0)),  # conflict miss: evict dirty → WRITE_BACK → ALLOCATE
        CPURequest(write=False, addr=addr(0,0,0)),  # evicted again, re-read
    ]
    run_simulation(reqs3, "SCENARIO 3 — Eviction of dirty block (WRITE_BACK path)")

    # ------------------------------------------------------------------
    # Scenario 4: Multiple write-back + re-allocate
    # ------------------------------------------------------------------
    reqs4 = [
        CPURequest(write=True,  addr=addr(0,2,1), wdata=0x11),
        CPURequest(write=True,  addr=addr(1,2,1), wdata=0x22),  # evict 0x11 block (dirty)
        CPURequest(write=True,  addr=addr(2,2,1), wdata=0x33),  # evict 0x22 block (dirty)
        CPURequest(write=False, addr=addr(0,2,1)),               # re-fetch evicted block
    ]
    run_simulation(reqs4, "SCENARIO 4 — Repeated write-back cycle (same index)")

    # ------------------------------------------------------------------
    # Scenario 5: Mixed reads/writes — comprehensive coverage
    # ------------------------------------------------------------------
    reqs5 = [
        CPURequest(write=False, addr=addr(0,0,0)),               # R miss
        CPURequest(write=True,  addr=addr(0,0,2), wdata=0xFF),   # W hit (same block)
        CPURequest(write=False, addr=addr(0,1,0)),               # R miss (diff index)
        CPURequest(write=True,  addr=addr(2,1,0), wdata=0x42),   # W miss on idx 1 (no dirty yet)
        CPURequest(write=True,  addr=addr(3,1,0), wdata=0x77),   # W miss idx 1, evict dirty→WB→alloc
        CPURequest(write=False, addr=addr(3,1,1)),               # R hit (just allocated)
        CPURequest(write=False, addr=addr(0,0,0)),               # R hit (still in cache)
    ]
    run_simulation(reqs5, "SCENARIO 5 — Comprehensive mixed read/write")

