# Cache Controller FSM Simulator

A C++ simulator for a **direct-mapped, write-back, write-allocate cache controller** modeled as a **finite state machine (FSM)**. The program simulates the interaction between a CPU, cache, and main memory cycle by cycle, and shows how cache hits, misses, allocation, and write-back operations occur.

This project is useful for understanding cache controller behavior in **Computer Architecture / COA** courses, especially topics such as cache mapping, dirty-bit handling, memory latency, and FSM-based control logic.

## Features

- Direct-mapped cache simulation
- Write-back policy with dirty-bit tracking
- Write-allocate on write misses
- 4 FSM states:
  - `IDLE`
  - `COMPARE_TAG`
  - `WRITE_BACK`
  - `ALLOCATE`
- Configurable main memory latency
- Interactive terminal-based command input
- Batch simulation from a script file
- Cycle-by-cycle execution trace
- Final cache performance statistics:
  - Hits
  - Misses
  - Write-backs
  - Total cycles
  - Hit rate

## Cache Configuration

The simulator uses the following cache settings:

| Parameter | Value |
|---|---:|
| Cache Size | 16 KB |
| Block Size | 16 bytes |
| Number of Blocks | 1024 |
| Mapping | Direct-Mapped |
| Write Policy | Write-Back |
| Allocation Policy | Write-Allocate |
| Default Memory Latency | 3 cycles |
| Address Size | 32-bit |

From the code:
- `CACHE_SIZE = 16384`
- `BLOCK_SIZE = 16`
- `NUM_BLOCKS = CACHE_SIZE / BLOCK_SIZE` fileciteturn1file0L8-L10

## Address Breakdown

For a 32-bit address:

- **Offset** = lower 4 bits
- **Word index** = bits inside the 16-byte block
- **Index** = selects one of the 1024 cache blocks
- **Tag** = upper bits used for comparison

The simulator computes them as follows:

```cpp
uint32_t offset = cpu_in.addr & 0xF;
uint32_t word_idx = (offset >> 2) & 0x3;
uint32_t index = (cpu_in.addr >> 4) & 0x3FF;
uint32_t tag = cpu_in.addr >> 14;
```

These calculations are implemented directly in the controller tick logic fileciteturn1file0L94-L98.

## FSM States

The controller operates using four states:

### 1. `IDLE`
Waits for a CPU request.

### 2. `COMPARE_TAG`
Checks whether the requested block is present in cache.
- If tag matches and block is valid → **hit**
- Otherwise → **miss**

### 3. `WRITE_BACK`
If the victim block is dirty, it is first written back to memory.

### 4. `ALLOCATE`
Fetches the requested block from main memory and loads it into cache.

These states are declared in the enum:

```cpp
enum class CacheState { IDLE, COMPARE_TAG, WRITE_BACK, ALLOCATE };
```

fileciteturn1file0L12-L12

## Main Components

### `CacheBlock`
Represents a cache line with:
- `valid`
- `dirty`
- `tag`
- `data[4]`

Defined in the code here fileciteturn1file0L14-L17.

### `MainMemory`
Simulates memory with a configurable latency and sparse storage using `unordered_map`. It starts a transaction when `mem_valid` is asserted and finishes after the latency expires fileciteturn1file0L29-L55.

### `CacheController`
Implements the FSM, cache storage, signal handling, cycle counting, and statistics collection fileciteturn1file0L58-L190.

### `runRequest(...)`
Executes one CPU request cycle by cycle until the operation is fulfilled, printing the FSM state and final cost in clock cycles fileciteturn1file0L193-L210.

## How to Compile

Compile with any C++ compiler that supports modern C++.

### Using g++

```bash
g++ -std=c++17 -O2 -o cache_fsm main.cpp
```

If your source file has a different name, replace `main.cpp` with the correct filename.

### On Windows (MinGW g++)

```bash
g++ -std=c++17 -O2 -o cache_fsm.exe main.cpp
cache_fsm.exe
```

### On Linux / macOS

```bash
g++ -std=c++17 -O2 -o cache_fsm main.cpp
./cache_fsm
```

## How to Run

When the program starts, it shows a simple terminal interface with supported commands:

```text
r <addr>          read from address
w <addr> <data>   write data to address
sim [filename]    run a batch simulation file
exit              quit and print statistics
```

The command prompt and command handling are implemented in `main()` fileciteturn1file0L213-L247.

## Supported Commands

### Read

```text
r 0x0000
```

Reads from the given hexadecimal address.

### Write

```text
w 0x0000 25
```

Writes decimal data to the given hexadecimal address.

### Batch Simulation

```text
sim sim_input.txt
```

Loads commands from a script file. If no filename is given, the simulator uses `sim_input.txt` by default fileciteturn1file0L223-L226.

### Exit

```text
exit
```

Prints final statistics and terminates the program.

## Simulation File Format

A batch input file should contain one command per line.

Example:

```text
r 0x0000
w 0x0004 10
r 0x0010
w 0x4000 99
r 0x0000
```

Rules:
- Use hexadecimal addresses
- Use decimal values for write data
- One command per line
- Empty lines are ignored

## Example Test Cases

### 1. Read Miss Then Hit
```text
r 0x0000
r 0x0004
```
- First access loads the block
- Second access may hit if it maps to the same block and valid word position

### 2. Write Hit
```text
w 0x0000 55
w 0x0000 99
```
- The block becomes dirty
- A second write to the same cached location should hit

### 3. Dirty Eviction
```text
w 0x0000 77
w 0x4000 88
```
- If both addresses map to the same cache index but different tags, the first block may need to be written back before allocation

## Program Output

For each request, the simulator prints:
- current cycle number
- current FSM state
- cache or memory actions
- total cycle cost for the request
- current valid cache contents

At the end, it prints cache statistics using `printStats()` fileciteturn1file0L174-L190.

## Learning Outcomes

This project demonstrates:
- how direct-mapped caches work
- how tags, indices, and offsets are derived
- the difference between hits and misses
- dirty block eviction and write-back behavior
- how FSMs are used in hardware-style control design
- how memory latency affects total cycle cost

## Project Structure

A simple repository layout could look like this:

```text
cache-controller-fsm/
├── main.cpp
├── sim_input.txt
├── README.md
└── screenshots/
```

You can rename `main.cpp` if your source file uses another name.

## Possible Improvements

- Add support for set-associative caches
- Add LRU or FIFO replacement policies
- Add write-through mode
- Add random test generation
- Export trace logs to file
- Add a GUI or waveform-style visualization


## Author

 nazmus sakib-230041118
 abid-230041144
 abida awwal ava-230041158
 course-cse 4307 computer organization and architecture


