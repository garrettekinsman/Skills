#!/usr/bin/env python3
"""
Loop Farm — Multi-Domain Research Loop Database & Manager
Universal research framework supporting financial, technical, product, scientific, and intelligence domains.
Inspired by DML Print Farm pattern: preview before launch, track active, review recent.

Usage:
    python3 loops.py status [--no-cache] [--domain <domain>] # Show loops (optionally filtered by domain)
    python3 loops.py preview <config>                        # Preview a loop config before launching
    python3 loops.py log <id> <event>                        # Log an event to a loop
    python3 loops.py list                                    # List all loops (active + completed)
    python3 loops.py history [n]                             # Show last N completed loops (default 5)
    python3 loops.py detail <id>                             # Show full detail for a loop

Domains: financial, technical, product, scientific, intelligence

Examples:
    python3 loops.py status --domain financial              # Show only financial market research loops
    python3 loops.py status --domain technical --no-cache   # Show technical loops with fresh API status
    python3 generate_config.py financial "What are the key trends in renewable energy this quarter?"
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Import real usage tracking (replaces hardcoded mock data)
try:
    from api_usage import get_budget_vs_spend, check_api_status_live
except ImportError:
    print("ERROR: Cannot import api_usage module. Run from skills/research-loops/ directory.")
    sys.exit(1)

DB_PATH = Path(__file__).parent / "state" / "loops.json"
CONFIGS_PATH = Path(__file__).parent / "configs"


def load_db():
    if DB_PATH.exists():
        with open(DB_PATH) as f:
            db = json.load(f)
    else:
        db = {"loops": [], "next_id": 1}
    
    # Ensure budget structure exists
    if "budgets" not in db:
        db["budgets"] = {
            "local": {"status": "offline"},
            "anthropic": {"monthly_budget_usd": 50.0, "spent_this_cycle_usd": 0.0},
            "xai": {"monthly_budget_usd": 25.0, "spent_this_cycle_usd": 0.0},
            "brave": {"monthly_budget_usd": 10.0, "spent_this_cycle_usd": 0.0}
        }
        save_db(db)
    
    # Ensure models registry exists
    if "models" not in db:
        db["models"] = {
            "anthropic/claude-sonnet-4": {
                "provider": "anthropic",
                "cost_per_1k_input": 0.015,
                "cost_per_1k_output": 0.075
            },
            "anthropic/claude-opus-4-6": {
                "provider": "anthropic", 
                "cost_per_1k_input": 0.015,
                "cost_per_1k_output": 0.075
            },
            "xai/grok-4-fast-reasoning": {
                "provider": "xai",
                "cost_per_1k_input": 0.005,
                "cost_per_1k_output": 0.015
            }
        }
        save_db(db)
    
    return db


def save_db(db):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_loop(db, config):
    """Register a new loop from a config dict. Returns loop record."""
    loop_id = f"L{db['next_id']:04d}"
    db["next_id"] += 1

    loop = {
        "id": loop_id,
        "topic": config.get("topic", "Untitled"),
        "model": config.get("model", "default"),
        "min_sprints": config.get("min_sprints", 12),
        "max_sprints": config.get("max_sprints", 20),
        "timeout_minutes": config.get("timeout_minutes", 15),
        "token_budget": config.get("token_budget", 400000),
        "theses": config.get("theses", []),
        "data_sources": config.get("data_sources", []),
        "output_dir": config.get("output_dir", ""),
        "status": "preview",  # preview → queued → running → completed/failed/killed
        "created_at": now_iso(),
        "started_at": None,
        "completed_at": None,
        "session_key": None,
        "run_id": None,
        "sprints_completed": 0,
        "tokens_used": 0,
        "tokens_by_model": {},  # e.g. {"anthropic/claude-sonnet": 150000, "xai/grok-4-fast": 50000}
        "theses_tested": 0,
        "theses_killed": 0,
        "findings": 0,
        "cost_usd": 0.0,
        "wall_time_min": 0.0,
        "energy_wh": 0.0,
        "events": [],
        "briefing_path": None,
        "state_path": None,
    }

    db["loops"].append(loop)
    save_db(db)
    return loop


def update_loop(db, loop_id, updates):
    """Update fields on a loop."""
    for loop in db["loops"]:
        if loop["id"] == loop_id:
            loop.update(updates)
            save_db(db)
            return loop
    return None


def log_event(db, loop_id, event_text):
    """Append an event to a loop's history."""
    for loop in db["loops"]:
        if loop["id"] == loop_id:
            loop["events"].append({
                "timestamp": now_iso(),
                "event": event_text
            })
            save_db(db)
            return True
    return False


def get_active(db):
    return [l for l in db["loops"] if l["status"] in ("preview", "queued", "running")]


def get_recent(db, n=5):
    completed = [l for l in db["loops"] if l["status"] in ("completed", "failed", "killed")]
    return sorted(completed, key=lambda x: x.get("completed_at") or "", reverse=True)[:n]


def format_status_line(loop, indent=""):
    """Single-line status for a loop (ASCII box format)."""
    status_icons = {
        "preview": ".",
        "queued": "~",
        "running": ">",
        "completed": "x",
        "failed": "!",
        "killed": "-",
    }
    icon = status_icons.get(loop["status"], "?")
    sprints = f"{loop['sprints_completed']:>2}/{loop['max_sprints']:<2}"
    topic = loop["topic"][:35].ljust(35)

    # Mode/type indicator
    mode_info = ""
    if loop.get("mode") == "streaming":
        mode_info = "real-time"
    elif loop.get("mode") == "hybrid":
        mode_info = "hybrid   "
    elif loop.get("real_time", {}).get("enabled"):
        mode_info = "streaming"
    else:
        mode_info = "batch    "

    # TODO: Enable local energy tracking when Mac Studio is online
    # For now, only show energy for cloud loops (estimated from tokens)
    energy = loop.get("energy_wh", 0)
    energy_kwh = energy / 1000

    extras = ""
    if loop["status"] == "running" and loop["started_at"]:
        started = datetime.fromisoformat(loop["started_at"].replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60
        confidence = loop.get("confidence_score", 0)
        confidence_text = f" {confidence:.0f}% confidence" if confidence > 0 else ""
        extras = f"{mode_info} ${loop.get('cost_usd', 0):.2f}{confidence_text}"
    elif loop["status"] == "completed":
        extras = f"{loop['findings']:>2} findings  ${loop['cost_usd']:.2f}  {energy_kwh:.3f}kWh"

    line = f"{indent}  {loop['id']} [{icon}] {topic} {sprints} {extras}"
    return line


def format_preview(loop):
    """Detailed preview of a loop before launch."""
    lines = []
    lines.append(f"## Loop Preview: {loop['id']}")
    lines.append(f"**Topic:** {loop['topic']}")
    lines.append(f"**Model:** {loop['model']}")
    lines.append(f"**Sprints:** {loop['min_sprints']}-{loop['max_sprints']}")
    lines.append(f"**Timeout:** {loop['timeout_minutes']} min")
    lines.append(f"**Token Budget:** {loop['token_budget']:,}")
    lines.append("")

    if loop["theses"]:
        lines.append("**Starting Theses:**")
        for i, t in enumerate(loop["theses"], 1):
            lines.append(f"  T{i}: {t}")
        lines.append("")

    if loop["data_sources"]:
        lines.append("**Data Sources:**")
        for s in loop["data_sources"]:
            lines.append(f"  - {s}")
        lines.append("")

    if loop["output_dir"]:
        lines.append(f"**Output:** {loop['output_dir']}")

    lines.append("")
    lines.append(f"**Status:** {loop['status'].upper()} — ready to launch")
    lines.append("")
    lines.append("Reply **LAUNCH** to start, or edit the config and re-preview.")

    return "\n".join(lines)


def format_detail(loop):
    """Full detail view of a loop."""
    lines = []
    lines.append(f"## Loop Detail: {loop['id']}")
    lines.append(f"**Topic:** {loop['topic']}")
    lines.append(f"**Status:** {loop['status'].upper()}")
    lines.append(f"**Model:** {loop['model']}")
    lines.append(f"**Created:** {loop['created_at']}")
    if loop["started_at"]:
        lines.append(f"**Started:** {loop['started_at']}")
    if loop["completed_at"]:
        lines.append(f"**Completed:** {loop['completed_at']}")
    lines.append(f"**Sprints:** {loop['sprints_completed']}/{loop['max_sprints']}")
    lines.append(f"**Tokens:** {loop['tokens_used']:,}")
    if loop.get("tokens_by_model"):
        for model, toks in loop["tokens_by_model"].items():
            model_short = model.split("/")[-1]
            lines.append(f"  — {model_short}: {toks:,} tokens")
    lines.append(f"**Findings:** {loop['findings']}")
    lines.append(f"**Theses:** {loop['theses_tested']} tested, {loop['theses_killed']} killed")
    lines.append(f"**Cost:** ${loop['cost_usd']:.2f}")

    if loop["session_key"]:
        lines.append(f"**Session:** `{loop['session_key']}`")
    if loop["briefing_path"]:
        lines.append(f"**Briefing:** `{loop['briefing_path']}`")
    if loop["state_path"]:
        lines.append(f"**State:** `{loop['state_path']}`")

    if loop["events"]:
        lines.append("")
        lines.append("**Event Log:**")
        for e in loop["events"][-10:]:  # Last 10 events
            ts = e["timestamp"][:19].replace("T", " ")
            lines.append(f"  [{ts}] {e['event']}")

    return "\n".join(lines)


def calc_cycle_spend(db):
    """
    DEPRECATED: Calculate spend per provider from loop history for current cycle.
    This function is replaced by real transcript scanning in api_usage.py.
    Kept for backward compatibility but should not be used for real data.
    """
    budgets = db.get("budgets", {})
    models = db.get("models", {})
    spend_by_provider = {}

    for loop in db["loops"]:
        # If we have per-model token breakdown, use it for more accurate cost
        if loop.get("tokens_by_model"):
            for model_id, toks in loop["tokens_by_model"].items():
                model_info = models.get(model_id, {})
                provider = model_info.get("provider", "unknown")
                # Rough split: 60% input, 40% output tokens
                cost_in = (toks * 0.6 / 1000) * model_info.get("cost_per_1k_input", 0)
                cost_out = (toks * 0.4 / 1000) * model_info.get("cost_per_1k_output", 0)
                spend_by_provider[provider] = spend_by_provider.get(provider, 0.0) + cost_in + cost_out
        else:
            # Fallback: use loop's primary model + recorded cost
            model_info = models.get(loop["model"], {})
            provider = model_info.get("provider", "unknown")
            cost = loop.get("cost_usd", 0.0)
            spend_by_provider[provider] = spend_by_provider.get(provider, 0.0) + cost

    return spend_by_provider


def make_bar(pct, width=20):
    """ASCII progress bar."""
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def check_api_status(no_cache=False):
    """Check status of APIs using real API calls and measured latency."""
    # SOURCE: Live API call — measured latency
    try:
        return check_api_status_live(no_cache=no_cache)
    except Exception as e:
        # If real API checks fail, return error status (not fake data)
        return {
            "error": f"API status check failed: {str(e)}",
            "anthropic": {"status": "error", "latency": "N/A"},
            "xai_grok": {"status": "error", "latency": "N/A"},
            "yfinance": {"status": "error", "latency": "N/A"},
            "brave_search": {"status": "error", "latency": "N/A"}
        }

def format_api_status(no_cache=False):
    """Format API status for display using real API calls."""
    # SOURCE: Live API call — measured latency
    api_status = check_api_status(no_cache=no_cache)
    lines = []
    lines.append("  API Status")
    lines.append("")
    
    # Show error message if API checks failed completely
    if "error" in api_status:
        lines.append(f"  🔴 ERROR: {api_status['error']}")
        lines.append("")
    
    for service, data in api_status.items():
        if service == "error":  # Skip the error message key
            continue
            
        # Determine status icon based on actual status
        if data["status"] == "operational":
            status_icon = "🟢"
        elif data["status"] == "no_key":
            status_icon = "⚪"  # White circle for missing credentials
        elif data["status"] == "no_env":
            status_icon = "🟡"  # Yellow for missing environment
        else:
            status_icon = "🔴"  # Red for errors
        
        service_name = service.replace("_", " ").title()
        status_display = data["status"]
        latency_display = data["latency"]
        
        # Show error details if available
        if "error" in data and data["error"]:
            status_display = f"{status_display} ({data['error'][:20]}...)"
        
        lines.append(f"  {status_icon} {service_name:<15}: {status_display:<20} {latency_display:>8}")
    
    return lines

def format_header():
    """Top lines: progress bars with REAL spend from transcripts, no hardcoded values."""
    # SOURCE: OpenClaw session transcripts (*.jsonl) — message.usage.cost.total
    # SOURCE: state/loops.json — user-configured budget
    
    budget_data = get_budget_vs_spend()
    lines = []

    lines.append("  Credits & Spending (This Cycle)")
    lines.append("")

    # Show error if transcript scanning failed
    if "error" in budget_data:
        lines.append(f"  🔴 ERROR: {budget_data['error']}")
        lines.append("")
        return lines

    budgets = budget_data.get("budgets", {})
    
    # Local first
    local_budget = budgets.get("local", {})
    local_status = local_budget.get("status", "offline")
    if local_status == "online":
        lines.append("  🟢 Local (Mac Studio): $0.00 (free)")
    else:
        lines.append("  🔴 Local (Mac Studio): OFFLINE — awaiting delivery")

    # Process each provider with real data
    provider_order = ["anthropic", "xai", "brave"]
    provider_names = {
        "anthropic": "Anthropic",
        "xai": "xAI",
        "brave": "Brave Search"
    }
    
    for provider in provider_order:
        if provider not in budgets:
            continue
        
        # xAI: no reliable spend tracking yet (no billing API, no transcript cost data)
        # SOURCE: N/A — xAI does not provide a usage/billing API and OpenClaw transcript
        # cost data for xAI is not yet validated. Show null until we have real data.
        if provider == "xai":
            lines.append(f"  ⚪ {provider_names[provider]:<12}:   N/A  / $25.00 — no verified spend data available")
            continue
            
        budget_info = budgets[provider]
        spend = budget_info.get("spend", 0.0)
        budget = budget_info.get("budget", 0.0)
        remaining = budget_info.get("remaining", 0.0)
        percent = budget_info.get("percent", 0.0)
        
        # Handle cases where budget is not configured
        if budget <= 0:
            lines.append(f"  ⚪ {provider_names[provider]:<12}: ${spend:>6.2f} / NOT SET — configure budget with 'budget {provider} <amount>'")
            continue
        
        # Determine status icon
        if percent > 90:
            icon = "🔴"
        elif percent > 70:
            icon = "🟡"
        else:
            icon = "🟢"
        
        # Create progress bar
        bar = make_bar(percent)
        
        lines.append(f"  {icon} {provider_names[provider]:<12}: ${spend:>6.2f} / ${budget:.2f} [{bar}] {percent:>3.0f}%  — ${remaining:.2f} remaining")

    # Add metadata about data sources
    meta = budget_data.get("meta", {})
    if meta:
        lines.append("")
        lines.append(f"  Data: {meta.get('cost_messages', 0)} cost records from {meta.get('transcript_files', 0)} session files")
    
    return lines


def cmd_status(no_cache=False, domain_filter=None):
    db = load_db()
    active = get_active(db)
    recent = get_recent(db, 5)

    lines = []
    lines.append("```")

    # Header: credits & spending with REAL data from transcripts
    lines.extend(format_header())
    lines.append("")

    # API Status with real latency measurements
    lines.extend(format_api_status(no_cache=no_cache))
    lines.append("")

    # Loops section
    loops_title = "  Loops"
    if domain_filter:
        loops_title += f" (filtered by domain: {domain_filter})"
    lines.append(loops_title)
    lines.append("")

    all_loops = sorted(db["loops"], key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Apply domain filter if specified
    if domain_filter:
        all_loops = [l for l in all_loops if l.get("domain", "financial") == domain_filter]
    
    if all_loops:
        # Group by domain if not filtering
        if not domain_filter:
            # Group loops by domain
            domains = {}
            for loop in all_loops[:20]:  # Limit to recent 20
                domain = loop.get("domain", "financial")
                if domain not in domains:
                    domains[domain] = []
                domains[domain].append(loop)
            
            # Display each domain section
            for domain, domain_loops in domains.items():
                active_count = len([l for l in domain_loops if l["status"] == "running"])
                completed_count = len([l for l in domain_loops if l["status"] == "completed"])
                
                domain_title = domain.title()
                lines.append(f"  {domain_title} ({active_count} active, {completed_count} completed)")
                
                # Show latest 6 loops per domain
                for loop in domain_loops[:6]:
                    lines.append(format_status_line(loop, indent="  "))
                lines.append("")
        else:
            # Show filtered loops
            for loop in all_loops[:15]:
                lines.append(format_status_line(loop))
    else:
        if domain_filter:
            lines.append(f"  No loops found for domain: {domain_filter}")
        else:
            lines.append("  No loops yet.")

    # Totals - SOURCE: loop database records
    # Apply same filter to totals
    total_loops_for_calc = db["loops"]
    if domain_filter:
        total_loops_for_calc = [l for l in db["loops"] if l.get("domain", "financial") == domain_filter]
    
    total_cost = sum(l.get("cost_usd", 0) for l in total_loops_for_calc)
    total_findings = sum(l.get("findings", 0) for l in total_loops_for_calc)
    total_energy = sum(l.get("energy_wh", 0) for l in total_loops_for_calc)
    total_loops = len(total_loops_for_calc)
    total_kwh = total_energy / 1000
    
    lines.append("")
    filter_text = f" ({domain_filter})" if domain_filter else ""
    lines.append(f"  Totals{filter_text}: {total_loops} loops | {total_findings} findings | ${total_cost:.2f} cloud | {total_kwh:.3f} kWh")

    lines.append("```")

    print("\n".join(lines))


def cmd_preview(config_path):
    db = load_db()

    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
    else:
        print(f"Config not found: {config_path}")
        sys.exit(1)

    loop = create_loop(db, config)
    print(format_preview(loop))


def cmd_list():
    db = load_db()
    if not db["loops"]:
        print("No loops in database.")
        return
    for loop in db["loops"]:
        print(format_status_line(loop))


def cmd_history(n=5):
    db = load_db()
    recent = get_recent(db, n)
    if not recent:
        print("No completed loops yet.")
        return
    for loop in recent:
        print(format_status_line(loop))


def cmd_detail(loop_id):
    db = load_db()
    for loop in db["loops"]:
        if loop["id"] == loop_id:
            print(format_detail(loop))
            return
    print(f"Loop {loop_id} not found.")


def cmd_log(loop_id, event):
    db = load_db()
    if log_event(db, loop_id, event):
        print(f"Logged to {loop_id}: {event}")
    else:
        print(f"Loop {loop_id} not found.")


def cmd_spend(provider, amount):
    """Add manual spend to a provider's cycle total."""
    db = load_db()
    budgets = db.get("budgets", {})
    if provider not in budgets:
        print(f"Unknown provider: {provider}. Available: {', '.join(budgets.keys())}")
        return
    budgets[provider]["spent_this_cycle_usd"] += float(amount)
    save_db(db)
    total = budgets[provider]["spent_this_cycle_usd"]
    print(f"Added ${float(amount):.2f} to {provider}. Cycle total (manual): ${total:.2f}")


def cmd_budget(provider, amount):
    """Set monthly budget for a provider."""
    db = load_db()
    budgets = db.get("budgets", {})
    if provider not in budgets:
        print(f"Unknown provider: {provider}. Available: {', '.join(budgets.keys())}")
        return
    budgets[provider]["monthly_budget_usd"] = float(amount)
    save_db(db)
    print(f"Set {provider} monthly budget to ${float(amount):.2f}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAdditional commands:")
        print("    python3 loops.py spend <provider> <amount>  # Log manual spend")
        print("    python3 loops.py budget <provider> <amount> # Set monthly budget")
        sys.exit(1)

    cmd = sys.argv[1]

    # Handle flags for status command
    no_cache = False
    domain_filter = None
    if cmd == "status":
        if "--no-cache" in sys.argv:
            no_cache = True
        # Look for domain filter: --domain financial, --domain technical, etc.
        for i, arg in enumerate(sys.argv):
            if arg == "--domain" and i + 1 < len(sys.argv):
                domain_filter = sys.argv[i + 1]
                break

    if cmd == "status":
        cmd_status(no_cache=no_cache, domain_filter=domain_filter)
    elif cmd == "preview" and len(sys.argv) >= 3:
        cmd_preview(sys.argv[2])
    elif cmd == "list":
        cmd_list()
    elif cmd == "history":
        n = int(sys.argv[2]) if len(sys.argv) >= 3 else 5
        cmd_history(n)
    elif cmd == "detail" and len(sys.argv) >= 3:
        cmd_detail(sys.argv[2])
    elif cmd == "log" and len(sys.argv) >= 4:
        cmd_log(sys.argv[2], " ".join(sys.argv[3:]))
    elif cmd == "spend" and len(sys.argv) >= 4:
        cmd_spend(sys.argv[2], sys.argv[3])
    elif cmd == "budget" and len(sys.argv) >= 4:
        cmd_budget(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
