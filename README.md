# FDS2ASCII Batch SLCF Exporter

Batch-export FDS/PyroSim **SLCF slice** data to CSV by automating the interactive `fds2ascii` prompts.  
The script runs **serially (single-thread)** and produces **one CSV per time point**, where each CSV contains **time-averaged** results over a configurable window (default: `[t-1, t+1]` clamped to the global time range).

## Features

- Automates `fds2ascii` interactive inputs (CHID, file type, sampling factor, domain option, time averaging range, variable indices, output file name).
- Exports **one CSV per second/time point** (inclusive range).
- Supports **variable groups**:
  - Example: `vars_per_group = 9`
  - Group 1 → indices `1..9`, group 2 → `10..18`, etc.
- **Serial execution**: runs `t=0` → writes output → then `t=1` → ... (no parallelism).
- Output naming: `t.csv` (e.g., `0.csv`, `1.csv`, ...).

## How it Works

For each time point `t` in `[TSTART, TEND]` (inclusive), the script runs `fds2ascii` once and inputs:

- `CHID` (Job ID string)
- File type: `2` (SLCF)
- Sampling factor: `1`
- Domain: `n` (not limited)
- Averaging time range:  
  `tmin = max(TSTART, t-1)`  
  `tmax = min(TEND,   t+1)`
- Number of variables to read: `N` (user-defined, e.g. 9)
- Variable indices: `1..N` for group 1, `N+1..2N` for group 2, etc.
- Output file name: `{t}.csv`

> Note: `fds2ascii` outputs **time-averaged** data over the specified interval. This tool does **not** export raw instantaneous slice values in a single run; it performs repeated averaged exports per time point.

## Requirements

- Windows (tested with `fds2ascii.exe` from FDS/PyroSim toolchain)
- Python 3.9+ recommended
- `fds2ascii.exe` available locally
- FDS result files present in the results directory (e.g., `.sf`, `.smv`, etc.)

## Usage

Run the script and follow prompts, for example:

- `fds2ascii.exe path`: `E:\2-software\pyrosim\fds\fds2ascii.exe`
- `Results folder`: `E:\pyrosimmodel\hanxue\building`
- `Output root folder`: `E:\pyrosimmodel\hanxue\data\1F`
- `CHID`: `building`
- `Time range`: `0-200`
- `How many variables to read`: `9`
- `Groups to extract`: `1` (or `1-5`, `1,3,10`, etc.)

The script will produce:

- `0.csv ... 200.csv` (201 files total)
- Each file is the averaged result over `[t-1, t+1]` (clamped at boundaries)

### Example

Time range `0-10` produces **11 CSV files**: `0.csv ... 10.csv`.

For `t=5`:
- averaging input to `fds2ascii` is `4 6`
- output file is `5.csv`

## Notes / Troubleshooting

### `forrtl: severe (602): file not found`
Common causes:
- Output directory does not exist (ensure the script creates it or create it manually).
- Working directory is not the results folder (script should run `fds2ascii` with `cwd=results_dir`).
- Passing an invalid output file path to `fds2ascii` (prefer simple file names like `5.csv`).

### `fds2ascii.exe not found`
Make sure you provide the **full path to the executable**, not just a folder, e.g.:
- ✅ `E:\...\fds2ascii.exe`
- ❌ `E:\...\fds\`

## License

Choose a license before publishing (MIT is common for small utilities).  
If you are unsure, start with MIT.

## Acknowledgements

- NIST Fire Dynamics Simulator (FDS) / `fds2ascii` utility
- PyroSim workflows that rely on SLCF slice output
