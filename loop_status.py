#!/usr/bin/env python3
"""
loop_status.py — Loop Farm Status Dashboard

Renders the exact format used in the Gaho loop status block:
  - Credits & Spending (This Cycle)  — scans session transcripts for real spend
  - Local Compute Status             — Framework1 SSH health + Ollama model list
  - API Status (live latency)        — pings each configured endpoint
  - Energy                           — Framework1 RAPL power readings via SSH
  - Loops (from SQLite database)

Usage:
    python3 loop_status.py           # full status
    python3 loop_status.py --json    # JSON output for automation
    python3 loop_status.py --loops   # loops section only
    python3 loop_status.py --discord # wrap output in Discord code block
    python3 loop_status.py --import-json  # migrate loops.json → SQLite

Sources configured in status_sources.json — add/remove APIs there.
API keys come from environment variables ONLY (never hardcoded).

Database: state/loops.db (SQLite)
"""

import sys, os, time, json, sqlite3, subprocess, argparse
from datetime import datetime, timezone
from pathlib import Path

# Optional deps — degrade gracefully
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "status_sources.json"
DB_FILE = ROOT / "state" / "loops.db"
SESSIONS_PATH = Path("/Users/garrett/.openclaw/agents/main/sessions/")

# Framework1 defaults — override in status_sources.json → compute.framework1
# or via env vars FRAMEWORK1_SSH_HOST / FRAMEWORK1_SSH_KEY
F1_DEFAULT = {
    "ssh_host": os.environ.get("FRAMEWORK1_SSH_HOST", ""),
    "ssh_key": os.environ.get("FRAMEWORK1_SSH_KEY", "~/.ssh/framework_key"),
    "label": "Framework1",
    "enabled": True,
    # Framework1 AMD Ryzen AI MAX+ 395 TDP: ~65W CPU + 45W GPU typical under load
    # SOURCE: spec sheet + measured; used only as fallback when RAPL read fails
    "idle_watts_fallback": 40,
}


# ─── Config ──────────────────────────────────────────────────────────────────

def load_config():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


# ─── Database ─────────────────────────────────────────────────────────────────

def get_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS loops (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'active',
            sprints_done INTEGER DEFAULT 0,
            sprints_max  INTEGER DEFAULT 20,
            findings     INTEGER DEFAULT 0,
            cost_usd     REAL DEFAULT 0.0,
            kwh          REAL DEFAULT 0.0,
            started_at   TEXT,
            finished_at  TEXT,
            notes        TEXT
        );

        CREATE TABLE IF NOT EXISTS loop_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            loop_id    TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail     TEXT,
            ts         TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_loop_events_loop_id ON loop_events(loop_id);
    """)
    conn.commit()


def import_from_json(conn):
    """One-time migration from loops.json → SQLite."""
    json_file = ROOT / "state" / "loops.json"
    if not json_file.exists():
        return 0
    with open(json_file) as f:
        data = json.load(f)
    loops = data.get("loops", [])
    imported = 0
    for l in loops:
        loop_id = l.get("id") or l.get("loop_id")
        if not loop_id:
            continue
        try:
            conn.execute("""
                INSERT OR IGNORE INTO loops
                (id, name, status, sprints_done, sprints_max, findings, cost_usd, kwh, started_at, finished_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                loop_id,
                l.get("topic") or l.get("name", "Untitled"),
                l.get("status", "completed"),
                l.get("sprints_completed") or l.get("current_sprint", 0),
                l.get("max_sprints") or l.get("sprints_max", 20),
                l.get("findings") or l.get("findings_count", 0),
                l.get("cost_usd", 0.0),
                l.get("kwh", 0.0),
                l.get("started_at"),
                l.get("finished_at"),
            ))
            imported += 1
        except Exception:
            pass
    conn.commit()
    return imported


def get_loops(conn):
    rows = conn.execute("SELECT * FROM loops ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def register_loop(conn, loop_id, name, sprints_max=20):
    """Called from loops.py when a new loop starts."""
    conn.execute("""
        INSERT OR IGNORE INTO loops (id, name, status, sprints_max, started_at)
        VALUES (?, ?, 'active', ?, datetime('now'))
    """, (loop_id, name, sprints_max))
    conn.commit()


def update_loop(conn, loop_id, **kwargs):
    """Update loop fields. Valid: status, sprints_done, findings, cost_usd, kwh, finished_at, notes"""
    allowed = {"status", "sprints_done", "findings", "cost_usd", "kwh", "finished_at", "notes", "name"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [loop_id]
    conn.execute(f"UPDATE loops SET {sets} WHERE id = ?", vals)
    conn.commit()


def log_event(conn, loop_id, event_type, detail=None):
    conn.execute(
        "INSERT INTO loop_events (loop_id, event_type, detail) VALUES (?,?,?)",
        (loop_id, event_type, detail)
    )
    conn.commit()


# ─── SSH helpers ──────────────────────────────────────────────────────────────

def ssh_run(host, key_path, cmd, timeout=6):
    """
    Run a command on a remote host via SSH.
    Returns (stdout, stderr, returncode) or ("", error_msg, 1) on failure.
    SOURCE: live SSH subprocess call
    """
    key = os.path.expanduser(key_path)
    try:
        result = subprocess.run(
            ["ssh", "-i", key,
             "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=4",
             "-o", "BatchMode=yes",
             host, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "SSH timeout", 1
    except Exception as e:
        return "", str(e), 1


# ─── Framework1 / Local Compute ───────────────────────────────────────────────

def get_framework1_status(config):
    """
    SOURCE: Live SSH connection to Framework1 (host from env FRAMEWORK1_SSH_HOST)
    Returns dict with keys: online, label, models, watts, error
    """
    f1 = {**F1_DEFAULT, **config.get("compute", {}).get("framework1", {})}
    if not f1.get("enabled", True):
        return {"online": False, "label": f1["label"], "models": [], "watts": None, "error": "disabled"}

    host = f1["ssh_host"]
    key = f1["ssh_key"]
    label = f1["label"]

    # 1. Reachability + installed models
    # SOURCE: `ollama list` on Framework1
    stdout, stderr, rc = ssh_run(host, key, "ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'")
    if rc != 0:
        return {"online": False, "label": label, "models": [], "active_models": [],
                "watts": None, "error": stderr or "unreachable"}

    models = [m for m in stdout.splitlines() if m.strip()]

    # 2. Active models (currently loaded in memory)
    # SOURCE: `ollama ps` — shows models hot in VRAM/RAM with processor + expiry
    ps_out, _, ps_rc = ssh_run(host, key, "ollama ps 2>/dev/null | tail -n +2")
    active_models = []
    if ps_rc == 0 and ps_out.strip():
        for line in ps_out.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0]
                # ollama ps columns: NAME ID SIZE PROCESSOR UNTIL
                # SIZE is "54 GB" (two tokens) so PROCESSOR starts at index 3 or 4
                # Find "CPU" or "GPU" token to locate processor column
                proc_idx = next((i for i, p in enumerate(parts) if "CPU" in p or "GPU" in p), None)
                if proc_idx and proc_idx >= 1:
                    # size = everything between index 2 and proc_idx-1
                    size = " ".join(parts[2:proc_idx-1]) if proc_idx > 3 else parts[2]
                    processor = " ".join(parts[proc_idx-1:proc_idx+1])  # e.g. "100% CPU"
                else:
                    size = parts[2]
                    processor = ""
                active_models.append({"name": name, "size": size, "processor": processor})
    

    # 2. Energy: read RAPL (Running Average Power Limit) via powercap sysfs
    # SOURCE: /sys/class/powercap/intel-rapl or amd_energy_XXX (kernel driver)
    # AMD Ryzen AI MAX+ 395 exposes rapl via amd_energy or powercap
    energy_cmd = (
        "cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj 2>/dev/null || "
        "cat /sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/energy_uj 2>/dev/null || "
        "echo UNAVAILABLE"
    )
    e1_out, _, _ = ssh_run(host, key, energy_cmd, timeout=4)
    time.sleep(1)
    e2_out, _, _ = ssh_run(host, key, energy_cmd, timeout=4)

    watts = None
    if e1_out not in ("", "UNAVAILABLE") and e2_out not in ("", "UNAVAILABLE"):
        try:
            e1 = int(e1_out.splitlines()[-1])
            e2 = int(e2_out.splitlines()[-1])
            delta_uj = e2 - e1
            if delta_uj > 0:
                watts = delta_uj / 1_000_000  # µJ/s = Watts (1s sample)
        except ValueError:
            pass

    if watts is None:
        # Fall back to AMD hwmon if RAPL not exposed
        # SOURCE: /sys/class/hwmon/hwmon*/power1_average (AMD hwmon driver)
        hwmon_cmd = "cat /sys/class/hwmon/hwmon*/power1_average 2>/dev/null | head -1"
        hwmon_out, _, hwmon_rc = ssh_run(host, key, hwmon_cmd, timeout=4)
        if hwmon_rc == 0 and hwmon_out.strip():
            try:
                watts = int(hwmon_out.strip()) / 1_000_000  # µW → W
            except ValueError:
                pass

    if watts is None:
        watts_display = f"~{f1['idle_watts_fallback']}W (est)"
        watts_value = f1["idle_watts_fallback"]
    else:
        watts_display = f"{watts:.1f}W"
        watts_value = watts

    return {
        "online": True,
        "label": label,
        "models": models,
        "active_models": active_models,
        "watts": watts_value,
        "watts_display": watts_display,
        "error": None,
    }


def render_compute(f1):
    """Render the local compute section."""
    lines = []
    if not f1["online"]:
        err = f1.get("error", "unknown")
        lines.append(f"🔴 Local ({f1['label']}): OFFLINE — {err}")
        return lines

    watts_str = f1.get("watts_display", f"{f1['watts']}W")
    lines.append(f"🟢 Local ({f1['label']}): online  {watts_str}")

    # Active models (hot in memory)
    active = f1.get("active_models", [])
    if active:
        lines.append("  Active (in memory):")
        for m in active:
            proc = m.get("processor", "")
            lines.append(f"    ▶ {m['name']:<32} {m['size']:<6}  {proc}")
    else:
        lines.append("  Active: none (models idle/unloaded)")

    # Installed models
    installed = f1.get("models", [])
    if installed:
        inst_str = ", ".join(installed)
        lines.append(f"  Installed: {inst_str}")

    return lines


# ─── Credits & Spending ───────────────────────────────────────────────────────

def bar(used, total, width=20):
    """SOURCE: derived from scan_transcripts() spend values and configured budgets."""
    if total <= 0:
        return "░" * width, 0
    pct = used / total
    filled = int(min(pct, 1.0) * width)
    b = "█" * filled + "░" * (width - filled)
    return b, pct * 100


def scan_transcripts():
    """
    SOURCE: OpenClaw session transcripts (*.jsonl) at SESSIONS_PATH
            Field: message.usage.cost.total — filtered to current billing cycle
    Returns: (spend_by_provider dict, record_count, file_count)
    """
    if not SESSIONS_PATH.exists():
        return {}, 0, 0

    now = datetime.now(timezone.utc)
    cycle_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    spend = {}
    records = 0
    files = set()

    for fpath in SESSIONS_PATH.glob("*.jsonl"):
        files.add(str(fpath))
        try:
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (d.get("type") == "message"
                            and "message" in d
                            and "usage" in d.get("message", {})
                            and "cost" in d["message"]["usage"]):
                        ts_raw = d.get("timestamp", "")
                        try:
                            if ts_raw.endswith("Z"):
                                ts_raw = ts_raw[:-1] + "+00:00"
                            elif "+" not in ts_raw and ts_raw:
                                ts_raw += "+00:00"
                            if ts_raw and datetime.fromisoformat(ts_raw) < cycle_start:
                                continue
                        except Exception:
                            pass
                        provider = d["message"].get("provider", "anthropic")
                        cost = d["message"]["usage"]["cost"].get("total", 0)
                        spend[provider] = spend.get(provider, 0) + cost
                        records += 1
        except Exception:
            pass

    return spend, records, len(files)


def render_credits(config, spend, records, files):
    lines = ["Credits & Spending (This Cycle)", ""]
    budgets = config.get("budgets", {})

    for key, binfo in budgets.items():
        label = binfo.get("label", key)
        budget = binfo.get("monthly_budget_usd", 0)
        used = spend.get(key, 0)
        remaining = budget - used
        b, pct = bar(used, budget, 20)
        icon = "🟢" if remaining >= 0 else "🔴"
        remaining_str = f"${remaining:.2f}" if remaining >= 0 else f"$-{abs(remaining):.2f}"
        lines.append(
            f"{icon} {label:<12}: ${used:>7.2f} / ${budget:<6.2f} [{b}] {pct:>3.0f}%  — {remaining_str} remaining"
        )

    lines.append("")
    lines.append(f"Data: {records:,} cost records from {files} session files")
    return lines


# ─── API Status ───────────────────────────────────────────────────────────────

def ping(url, timeout=5):
    """SOURCE: live requests.get() with wall-clock timing."""
    if not _HAS_REQUESTS:
        return None, None
    try:
        t = time.time()
        requests.get(url, timeout=timeout)
        return True, int((time.time() - t) * 1000)
    except Exception:
        return False, None


def render_api_status(config):
    sources = config.get("api_status", {})
    lines = ["API Status", ""]

    # Group 1: core AI/trading (rendered first, blank line, then data APIs)
    group1_keys = {"anthropic", "xai", "tradier"}

    def render_source(key, src):
        ok, ms = ping(src["url"])
        if ok is None:
            return f"⚪ {src.get('label', key):<16}: {'no requests lib'}"
        icon = "🟢" if ok else "🔴"
        label = src.get("label", key)
        status = "operational" if ok else "offline"
        ms_str = f"{ms}ms" if ms is not None else "—"
        return f"{icon} {label:<16}: {status:<20}{ms_str}"

    for key, src in sources.items():
        if not src.get("enabled", True):
            continue
        if key in group1_keys:
            lines.append(render_source(key, src))

    lines.append("")

    for key, src in sources.items():
        if not src.get("enabled", True):
            continue
        if key not in group1_keys:
            lines.append(render_source(key, src))

    return lines


# ─── Energy ───────────────────────────────────────────────────────────────────

def render_energy(config, f1_status, loops):
    """
    Energy section: Framework1 live power + estimated kWh burned by loops.
    SOURCE: Framework1 watts from get_framework1_status() (RAPL/hwmon or fallback)
            Loop kWh from loops SQLite table (tracked per-loop at run time)
    """
    lines = ["Energy", ""]

    # Live power reading
    if f1_status["online"] and f1_status.get("watts"):
        w = f1_status["watts"]
        lines.append(f"  Framework1 (live): {w:.1f}W")
        kwh_rate = config.get("energy", {}).get("kwh_rate_usd", 0.22)
        # Project daily cost at current draw
        daily_kwh = (w * 24) / 1000
        daily_usd = daily_kwh * kwh_rate
        lines.append(f"  Projected:         {daily_kwh:.2f} kWh/day  @ ${kwh_rate}/kWh = ${daily_usd:.3f}/day")
    else:
        lines.append("  Framework1 (live): OFFLINE — energy data unavailable")

    # Cumulative loop energy
    total_kwh = sum(l["kwh"] for l in loops)
    if total_kwh > 0:
        kwh_rate = config.get("energy", {}).get("kwh_rate_usd", 0.22)
        energy_usd = total_kwh * kwh_rate
        lines.append(f"  Loop total (all):  {total_kwh:.3f} kWh  (${energy_usd:.3f} electricity)")

    return lines


# ─── Loops ────────────────────────────────────────────────────────────────────

def render_loops(conn):
    loops = get_loops(conn)
    lines = ["Loops", ""]

    active    = [l for l in loops if l["status"] == "active"]
    completed = [l for l in loops if l["status"] != "active"]
    all_display = active + completed[:20]

    total_findings = sum(l["findings"] for l in loops)
    total_cost     = sum(l["cost_usd"] for l in loops)
    total_kwh      = sum(l["kwh"] for l in loops)

    for l in all_display:
        lid     = l["id"]
        name    = (l["name"] or "")[:36]
        done    = l["sprints_done"]
        maxs    = l["sprints_max"]
        findings = l["findings"]
        cost    = l["cost_usd"]
        kwh     = l["kwh"]
        mark    = ">" if l["status"] == "active" else "x"
        kwh_str = f"  {kwh:.3f}kWh" if kwh > 0 else ""
        lines.append(
            f"{lid} [{mark}] {name:<36} {done:>2}/{maxs:<2} {findings:>2} findings  ${cost:.2f}{kwh_str}"
        )

    lines.append("")
    lines.append(
        f"Totals: {len(loops)} loops | {total_findings} findings | ${total_cost:.2f} cloud | {total_kwh:.3f} kWh"
    )
    return loops, lines


# ─── Full Render ──────────────────────────────────────────────────────────────

def render_full(config, conn, discord=False):
    # Fetch all data
    spend, records, files   = scan_transcripts()
    f1_status               = get_framework1_status(config)
    loops, loop_lines       = render_loops(conn)

    sections = []
    sections += render_credits(config, spend, records, files)
    sections.append("")
    sections += render_compute(f1_status)
    sections.append("")
    sections += render_api_status(config)
    sections.append("")
    sections += render_energy(config, f1_status, loops)
    sections.append("")
    sections += loop_lines

    body = "\n".join(sections)
    if discord:
        return f"```\n{body}\n```"
    return body


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Loop Farm Status Dashboard")
    parser.add_argument("--json",        action="store_true", help="Output JSON")
    parser.add_argument("--loops",       action="store_true", help="Loops section only")
    parser.add_argument("--discord",     action="store_true", help="Wrap in Discord code block")
    parser.add_argument("--import-json", action="store_true", help="Migrate loops.json → SQLite")
    args = parser.parse_args()

    config = load_config()
    conn   = get_db()

    if args.import_json:
        n = import_from_json(conn)
        print(f"Imported {n} loops from loops.json → {DB_FILE}")
        return

    if args.loops:
        _, lines = render_loops(conn)
        print("\n".join(lines))
        return

    if args.json:
        spend, records, files = scan_transcripts()
        loops = get_loops(conn)
        f1 = get_framework1_status(config)
        print(json.dumps({
            "spend": spend,
            "records": records,
            "files": files,
            "framework1": f1,
            "loops": loops,
        }, indent=2))
        return

    print(render_full(config, conn, discord=args.discord))
    conn.close()


if __name__ == "__main__":
    main()
