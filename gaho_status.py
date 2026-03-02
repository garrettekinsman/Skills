#!/usr/bin/env python3
"""
Gaho Status Block — live system status with APIs, compute, energy, loops.
Usage: python3 gaho_status.py
"""
import sys, os, time, json, subprocess, glob
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(__file__)
LOOPS_DB = os.path.join(ROOT, "state", "loops.json")
FRAMEWORK_HOST = os.environ.get("FRAMEWORK1_SSH_HOST", "")   # e.g. 100.x.x.x (Tailscale IP)
FRAMEWORK_USER = os.environ.get("FRAMEWORK1_SSH_USER", "")   # SSH username
FRAMEWORK_KEY  = os.path.expanduser(os.environ.get("FRAMEWORK1_SSH_KEY", "~/.ssh/framework_key"))
LITELLM_URL    = os.environ.get("LITELLM_URL", "")  # e.g. https://your-litellm-host.com

# ── Helpers ──────────────────────────────────────────────────────────────────

def ping(url, timeout=4):
    try:
        t = time.time()
        r = requests.get(url, timeout=timeout)
        ms = int((time.time() - t) * 1000)
        return True, ms
    except:
        return False, None

def bar(used, total, width=20):
    """Progress bar. Returns (bar_str, pct)."""
    if total <= 0:
        return "░" * width, 0
    pct = min(used / total, 1.0)
    filled = int(pct * width)
    b = "█" * filled + "░" * (width - filled)
    return b, int(pct * 100)

def status_icon(ok):
    return "🟢" if ok else "🔴"

def ssh_run(cmd):
    try:
        r = subprocess.run(
            ["ssh", "-i", FRAMEWORK_KEY, "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=5", f"{FRAMEWORK_USER}@{FRAMEWORK_HOST}", cmd],
            capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip()
    except:
        return ""

# ── API Status ────────────────────────────────────────────────────────────────

def check_apis():
    apis = {}

    # Anthropic — flat rate $100/mo
    ok, ms = ping("https://api.anthropic.com")
    try:
        import api_usage
        tx = api_usage.scan_session_transcripts()
        spend = tx.get("spend", {}).get("anthropic", 0)
        msgs  = tx.get("meta", {}).get("total_messages", 0)
    except:
        spend, msgs = 0, 0
    b, pct = bar(spend, 100, 20)
    warn = " ⚠️ 80%+" if pct >= 80 else ""
    apis["anthropic"] = {
        "icon": status_icon(ok), "ms": ms,
        "line": f"{status_icon(ok)} Anthropic      [{b}] ${spend:.2f} est / $100{warn}  ({msgs} msgs)",
        "pct": pct
    }

    # Brave — free tier 2000 queries/mo
    ok, ms = ping("https://api.search.brave.com")
    brave_used = 0  # no usage tracking yet
    b2, pct2 = bar(brave_used, 2000, 20)
    apis["brave"] = {
        "icon": status_icon(ok), "ms": ms,
        "line": f"{status_icon(ok)} Brave Search   [{b2}] {brave_used}/2000 queries  ~$0.001/ea",
        "pct": pct2
    }

    # xAI
    ok, ms = ping("https://api.x.ai")
    apis["xai"] = {
        "icon": status_icon(ok), "ms": ms,
        "line": f"{status_icon(ok)} xAI / Grok     free quota  {ms}ms" if ms else f"🔴 xAI / Grok     offline"
    }

    # Tradier
    ok, ms = ping("https://api.tradier.com")
    apis["tradier"] = {
        "icon": status_icon(ok),
        "line": f"{status_icon(ok)} Tradier         free tier  {ms}ms" if ms else "🔴 Tradier         offline"
    }

    # yFinance
    ok, ms = ping("https://query1.finance.yahoo.com/v8/finance/chart/AAPL")
    apis["yfinance"] = {
        "icon": status_icon(ok),
        "line": f"{status_icon(ok)} yFinance        free  {ms}ms" if ms else "🔴 yFinance         offline"
    }

    # Telegram
    ok, ms = ping("https://api.telegram.org")
    apis["telegram"] = {
        "icon": status_icon(ok),
        "line": f"{status_icon(ok)} Telegram        free  {ms}ms" if ms else "🔴 Telegram         offline"
    }

    return apis

# ── Local Compute ─────────────────────────────────────────────────────────────

def check_compute():
    nodes = {}

    # Mac Mini (localhost)
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        ram_used = ram.used // 1024**3
        ram_total = ram.total // 1024**3
        nodes["mac_mini"] = {
            "ok": True,
            "cpu": cpu,
            "ram_used": ram_used,
            "ram_total": ram_total,
            "power_w": 10,  # estimated idle
        }
    except:
        nodes["mac_mini"] = {"ok": True, "power_w": 10}

    # Framework1 via SSH
    fw_out = ssh_run("""python3 << 'PYEOF'
import os, glob, time, json, urllib.request

# CPU load
with open('/proc/loadavg') as f:
    load = f.read().split()[0]

# RAM
with open('/proc/meminfo') as f:
    lines = {}
    for l in f:
        if ':' in l:
            k,v = l.split(':')
            lines[k.strip()] = int(v.split()[0])
used_gb = (lines['MemTotal']-lines['MemAvailable'])//1024//1024
total_gb = lines['MemTotal']//1024//1024

# Power estimate from load (Ryzen AI MAX+ 395: ~65W idle, ~180W full)
load_f = float(load)
cores = 32
load_pct = min(load_f / cores, 1.0)
est_watts = int(65 + (180-65)*load_pct)

# Ollama models
models = []
try:
    r = urllib.request.urlopen('http://localhost:11434/api/ps', timeout=3)
    d = json.loads(r.read())
    for m in d.get('models',[]):
        models.append(m.get('name','?').split(':')[0])
except: pass

print(f'{load}|{used_gb}|{total_gb}|{est_watts}|{",".join(models)}')
PYEOF""")

    if fw_out and '|' in fw_out:
        parts = fw_out.split('|')
        load = parts[0] if len(parts) > 0 else '?'
        ram_u = int(parts[1]) if len(parts) > 1 else 0
        ram_t = int(parts[2]) if len(parts) > 2 else 0
        est_w = int(parts[3]) if len(parts) > 3 else 65
        models = parts[4].split(',') if len(parts) > 4 and parts[4] else []
        nodes["framework1"] = {
            "ok": True,
            "load": load,
            "ram_used": ram_u,
            "ram_total": ram_t,
            "power_w": est_w,
            "models": models,
        }
    else:
        nodes["framework1"] = {"ok": False, "power_w": 0}

    # LiteLLM
    ok, ms = ping(LITELLM_URL)
    nodes["litellm"] = {"ok": ok, "ms": ms}

    return nodes

# ── Loops ─────────────────────────────────────────────────────────────────────

def check_loops():
    try:
        with open(LOOPS_DB) as f:
            db = json.load(f)
        loops = db.get("loops", [])
        active    = [l for l in loops if l.get("status") == "active"]
        completed = [l for l in loops if l.get("status") == "completed"]
        total_findings = sum(l.get("findings", l.get("findings_count", 0)) for l in loops)
        total_cost = sum(l.get("cost_usd", 0) for l in loops)
        return active, completed, total_findings, total_cost
    except:
        return [], [], 0, 0

# ── Render ────────────────────────────────────────────────────────────────────

def render():
    now = datetime.now().strftime("%a %b %d %H:%M PST")

    apis    = check_apis()
    compute = check_compute()
    active_loops, completed_loops, total_findings, total_cost = check_loops()

    # Energy totals
    total_w = sum(n.get("power_w", 0) for n in compute.values() if isinstance(n, dict))
    kwh_day = total_w * 24 / 1000
    cost_day = kwh_day * 0.22  # ~$0.22/kWh Long Beach

    # Build output
    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🪨  **Gaho Status**  —  {now}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # APIs
    lines.append("**🌐 API Status & Usage**")
    for k, v in apis.items():
        lines.append(f"  {v['line']}")
    lines.append("")

    # Compute
    lines.append("**🖥️ Local Compute**")

    mini = compute.get("mac_mini", {})
    if mini.get("ok"):
        cpu_s = f"CPU {mini.get('cpu',0):.0f}%  " if mini.get('cpu') else ""
        ram_s = f"RAM {mini.get('ram_used',0)}/{mini.get('ram_total',0)}GB  " if mini.get('ram_total') else ""
        lines.append(f"  🟢 Mac Mini       {cpu_s}{ram_s}~{mini.get('power_w',10)}W")
    else:
        lines.append("  🔴 Mac Mini       offline")

    fw = compute.get("framework1", {})
    if fw.get("ok"):
        models_str = ", ".join(fw.get("models", [])) or "no models loaded"
        ram_b, ram_pct = bar(fw.get("ram_used",0), fw.get("ram_total",122), 16)
        lines.append(f"  🟢 Framework1     load {fw.get('load','?')}  RAM [{ram_b}] {fw.get('ram_used',0)}/{fw.get('ram_total',0)}GB  ~{fw.get('power_w',65)}W")
        lines.append(f"     └ {models_str}")
    else:
        lines.append("  🔴 Framework1     offline")

    ltm = compute.get("litellm", {})
    litellm_host = LITELLM_URL.replace("https://", "").replace("http://", "").split("/")[0] or "unconfigured"
    lines.append(f"  {'🟢' if ltm.get('ok') else '🔴'} LiteLLM (tunnel)  {litellm_host}  {ltm.get('ms','?')}ms")
    lines.append(f"  🔴 Mac Studio     awaiting delivery")
    lines.append("")

    # Energy
    lines.append("**⚡ Energy**")
    lines.append(f"  Current draw:  ~{total_w}W")
    lines.append(f"  Daily est:     ~{kwh_day:.2f} kWh  ≈ ${cost_day:.2f}/day (@$0.22/kWh LB)")
    lines.append("")

    # Loops
    lines.append("**🔁 Research Loops**")
    if active_loops:
        lines.append(f"  🟢 **{len(active_loops)} active**")
        for l in active_loops:
            lines.append(f"     └ {l.get('id','?')} — {l.get('name','?')[:40]}  sprint {l.get('current_sprint',0)}/{l.get('max_sprints',0)}")
    else:
        lines.append("  ⚪ 0 active")

    lines.append(f"  {len(completed_loops)} completed  ·  {total_findings} findings  ·  ${total_cost:.2f} total est")

    if completed_loops:
        lines.append("  **Recent:**")
        for l in list(reversed(completed_loops))[:5]:
            name = l.get("topic", l.get("name","?"))[:38]
            cost = l.get("cost_usd", 0)
            findings = l.get("findings", l.get("findings_count", 0))
            sprints = f"{l.get('sprints_completed',0)}/{l.get('max_sprints',0)}"
            lines.append(f"     ✅ {l.get('id','?')}  {name:<38}  {sprints} sprints  {findings} findings  ${cost:.2f}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)

if __name__ == "__main__":
    print(render())
