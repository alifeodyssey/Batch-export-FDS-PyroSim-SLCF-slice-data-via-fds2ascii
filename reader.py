import argparse
import re
import shutil
import subprocess
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  Hardcoded fds2ascii interaction parameters
# ═══════════════════════════════════════════════════════════════
FILE_TYPE = "2"            # SLCF
SAMPLING_FACTOR = "1"      # all data
DOMAIN_LIMIT = "n"         # no domain limit


# ───────────────────────────────────────────────────────────────
#  Input parsing helpers
# ───────────────────────────────────────────────────────────────

def parse_int_range(s: str) -> tuple[int, int]:
    """
    Parse a simple integer range string.
    Accepts: "0-200", "0 200", "0,200", "0~200"
    Returns: (start, end) inclusive.
    """
    tokens = [t for t in re.split(r"[\s,\-~]+", s.strip()) if t]
    if len(tokens) != 2:
        raise ValueError(f"Cannot parse range: {s!r}. Example: 0-200")
    start, end = int(float(tokens[0])), int(float(tokens[1]))
    if end < start:
        raise ValueError(f"End must >= start. Got {start}..{end}")
    return start, end


def parse_groups(s: str) -> list[int]:
    """
    Parse group specification (no upper-bound validation).
    Accepts: "1", "1-5", "1,3,5", "1-3,7,10-12"
    Returns: sorted list of 1-based group numbers.
    """
    s = s.strip()
    groups: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            groups.update(range(int(a), int(b) + 1))
        else:
            groups.add(int(part))

    result = sorted(groups)
    for g in result:
        if g < 1:
            raise ValueError(f"Group number must >= 1, got {g}")
    return result


# ───────────────────────────────────────────────────────────────
#  fds2ascii interaction
# ───────────────────────────────────────────────────────────────

def build_stdin(
    chid: str,
    tmin: float,
    tmax: float,
    var_count: int,
    var_indices: list[int],
    output_filename: str,
) -> str:
    """
    Build the complete stdin text for one fds2ascii invocation.

    Prompt order (confirmed from fds2ascii source code):
      1. CHID
      2. File type       -> 2 (SLCF)
      3. Sampling factor -> 1
      4. Domain limit    -> n
      5. Time range      -> "tmin tmax"
      6. Var count
      7. Var indices     -> one per line
      8. Output filename
    """
    lines: list[str] = [
        chid,
        FILE_TYPE,
        SAMPLING_FACTOR,
        DOMAIN_LIMIT,
        f"{tmin:.1f} {tmax:.1f}",
        str(var_count),
    ]
    lines.extend(str(i) for i in var_indices)
    lines.append(output_filename)
    return "\n".join(lines) + "\n"


def run_fds2ascii(
    fds2ascii_path: Path,
    results_dir: Path,
    out_dir: Path,
    chid: str,
    t: int,
    start_t: int,
    end_t: int,
    var_count: int,
    var_indices: list[int],
) -> None:
    """
    Run fds2ascii once for time point *t*.

    Averaging window: [t-1, t+1], clamped to [start_t, end_t].
    Output: out_dir/{t}.csv
    """
    # ── averaging window ──
    tmin = max(start_t, t - 1)
    tmax = min(end_t, t + 1)

    # ── skip if already exists ──
    final_path = out_dir / f"{t}.csv"
    if final_path.exists():
        print(f"[SKIP] {final_path.name} already exists")
        return

    # ── temp file in results_dir (avoids Fortran long-path issues) ──
    tmp_name = f"__tmp_{chid}_t{t}.csv"
    tmp_path = results_dir / tmp_name
    if tmp_path.exists():
        tmp_path.unlink()

    stdin_text = build_stdin(
        chid=chid,
        tmin=float(tmin),
        tmax=float(tmax),
        var_count=var_count,
        var_indices=var_indices,
        output_filename=tmp_name,
    )

    print(f"t={t}  avg=[{tmin}, {tmax}]  -> {final_path.name}")

    # ── execute ──
    proc = subprocess.run(
        [str(fds2ascii_path)],
        input=stdin_text,
        text=True,
        cwd=str(results_dir),
        capture_output=True,
    )

    if proc.returncode != 0:
        print("\n=== fds2ascii STDOUT (tail) ===")
        print("\n".join(proc.stdout.splitlines()[-80:]))
        print("=== fds2ascii STDERR ===")
        print(proc.stderr)
        raise RuntimeError(
            f"fds2ascii failed at t={t} (returncode={proc.returncode})"
        )

    if not tmp_path.exists():
        print("\n=== fds2ascii STDOUT (tail) ===")
        print("\n".join(proc.stdout.splitlines()[-120:]))
        print("=== fds2ascii STDERR ===")
        print(proc.stderr)
        raise FileNotFoundError(f"Expected output not created: {tmp_path}")

    # ── move to final location ──
    shutil.move(str(tmp_path), str(final_path))


# ───────────────────────────────────────────────────────────────
#  CLI argument parsing
# ───────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser. All arguments are optional and
    fall back to interactive input() when not provided."""
    p = argparse.ArgumentParser(
        description="fds2ascii Batch Exporter — extract SLCF time-series CSVs",
    )
    p.add_argument("--fds2ascii", type=str, default=None,
                    help="Path to fds2ascii.exe")
    p.add_argument("--results", type=str, default=None,
                    help="Results folder (where .sf/.smv live)")
    p.add_argument("--out", type=str, default=None,
                    help="Output root folder")
    p.add_argument("--chid", type=str, default=None,
                    help="Job ID string (CHID)")
    p.add_argument("--time", type=str, default=None,
                    help="Time range, e.g. '0-200'")
    p.add_argument("--vars", type=int, default=None,
                    help="How many variables to read (e.g. 9)")
    p.add_argument("--groups", type=str, default=None,
                    help="Groups to extract, e.g. '1' or '1-5' or '1,3,10'")
    return p


def _ask_if_missing(value: str | None, prompt: str) -> str:
    """Return *value* if provided, otherwise fall back to interactive input."""
    if value is not None:
        return value
    return input(prompt).strip().strip('"')


# ───────────────────────────────────────────────────────────────
#  Main
# ───────────────────────────────────────────────────────────────

def main() -> None:
    print("=== fds2ascii Batch Exporter (serial) ===\n")

    args = build_arg_parser().parse_args()

    # ── resolve inputs (CLI first, interactive fallback) ──
    fds2ascii = Path(
        _ask_if_missing(args.fds2ascii, "fds2ascii.exe path: ")
    ).expanduser().resolve()

    results_dir = Path(
        _ask_if_missing(args.results, "Results folder (where .sf/.smv live): ")
    ).expanduser().resolve()

    out_root = Path(
        _ask_if_missing(args.out, "Output root folder: ")
    ).expanduser().resolve()

    chid = _ask_if_missing(args.chid, "CHID: ").strip()

    start_t, end_t = parse_int_range(
        _ask_if_missing(args.time, "Time range (e.g. 0-200): ")
    )

    var_count = args.vars if args.vars is not None else \
        int(input("How many variables to read: ").strip())
    if var_count < 1:
        raise ValueError(f"var_count must >= 1, got {var_count}")

    groups = parse_groups(
        _ask_if_missing(args.groups, "Groups to extract (e.g. '1' or '1-5' or '1,3,10'): ")
    )

    # ── validation ──
    if not fds2ascii.is_file():
        raise FileNotFoundError(f"fds2ascii not found: {fds2ascii}")
    if not results_dir.is_dir():
        raise FileNotFoundError(f"Results folder not found: {results_dir}")

    time_points = list(range(start_t, end_t + 1))
    total_runs = len(groups) * len(time_points)

    # ── summary ──
    print(f"\n{'─' * 50}")
    print(f"  Time points : {start_t} .. {end_t}  ({len(time_points)} points)")
    print(f"  Groups      : {groups}  ({len(groups)} groups)")
    print(f"  Vars / group: {var_count}")
    print(f"  Total runs  : {total_runs}")
    for g in groups:
        idx_s = (g - 1) * var_count + 1
        idx_e = idx_s + var_count - 1
        print(f"    group {g} -> var indices {idx_s}..{idx_e}")
    print(f"{'─' * 50}\n")

    # ── serial: group by group, time point by time point ──
    counter = 0
    for group in groups:
        idx_start = (group - 1) * var_count + 1
        var_indices = list(range(idx_start, idx_start + var_count))

        group_dir = out_root / f"group_{group}"
        group_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n══ Group {group}  (var indices {var_indices[0]}..{var_indices[-1]}) ══")

        for t in time_points:
            counter += 1
            print(f"  [{counter}/{total_runs}] ", end="")
            run_fds2ascii(
                fds2ascii_path=fds2ascii,
                results_dir=results_dir,
                out_dir=group_dir,
                chid=chid,
                t=t,
                start_t=start_t,
                end_t=end_t,
                var_count=var_count,
                var_indices=var_indices,
            )

    print(f"\n=== DONE — {total_runs} files generated ===")


if __name__ == "__main__":
    main()
