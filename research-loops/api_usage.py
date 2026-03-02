#!/usr/bin/env python3
"""
Real API Usage Tracking for Loop Farm Dashboard

Scans OpenClaw session transcripts and makes lightweight API status checks.
Replaces hardcoded mock data with actual usage and status information.
"""

import json
import os
import time
import requests
import glob
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yfinance
import sys

# Cache file for API status checks (5 minute TTL)
CACHE_FILE = Path(__file__).parent / "state" / "api_cache.json"
CACHE_TTL_SECONDS = 300  # 5 minutes

def get_current_cycle_start():
    """Get the start of current billing cycle (1st of current month)."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)

def scan_session_transcripts():
    """
    Scan all OpenClaw session transcripts for cost data.
    Returns spend by provider for current cycle.
    """
    # SOURCE: OpenClaw session transcripts (*.jsonl) — message.usage.cost.total
    
    transcripts_path = "/Users/garrett/.openclaw/agents/main/sessions/"
    if not os.path.exists(transcripts_path):
        return {"error": "Cannot read transcripts", "spend": {}}
    
    cycle_start = get_current_cycle_start()
    spend_by_provider = {}
    total_messages = 0
    cost_messages = 0
    
    try:
        # Scan all JSONL files in sessions directory
        pattern = os.path.join(transcripts_path, "*.jsonl")
        transcript_files = glob.glob(pattern)
        
        for file_path in transcript_files:
            try:
                with open(file_path, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        try:
                            if line.strip():
                                data = json.loads(line)
                                total_messages += 1
                                
                                # Check if this is a message with cost data
                                if (data.get("type") == "message" and 
                                    "message" in data and 
                                    "usage" in data["message"] and
                                    "cost" in data["message"]["usage"]):
                                    
                                    # Parse timestamp and filter by cycle
                                    timestamp_str = data.get("timestamp", "")
                                    if timestamp_str:
                                        try:
                                            # Handle various timestamp formats
                                            if timestamp_str.endswith('Z'):
                                                timestamp_str = timestamp_str[:-1] + '+00:00'
                                            elif '+' not in timestamp_str and 'Z' not in timestamp_str:
                                                timestamp_str += '+00:00'
                                            
                                            message_time = datetime.fromisoformat(timestamp_str)
                                            if message_time >= cycle_start:
                                                cost_messages += 1
                                                provider = data["message"].get("provider", "unknown")
                                                cost = data["message"]["usage"]["cost"].get("total", 0)
                                                
                                                if provider not in spend_by_provider:
                                                    spend_by_provider[provider] = 0.0
                                                spend_by_provider[provider] += cost
                                        except ValueError as e:
                                            # Skip malformed timestamps
                                            continue
                                            
                        except json.JSONDecodeError:
                            # Skip malformed JSON lines
                            continue
                            
            except (OSError, IOError):
                # Skip files that can't be read
                continue
                
        return {
            "spend": spend_by_provider,
            "meta": {
                "total_messages": total_messages,
                "cost_messages": cost_messages,
                "cycle_start": cycle_start.isoformat(),
                "transcript_files": len(transcript_files)
            }
        }
        
    except Exception as e:
        return {"error": f"Failed to scan transcripts: {str(e)}", "spend": {}}

def load_api_credentials():
    """Load API credentials from various config files."""
    creds = {}
    
    try:
        # Anthropic API key from auth profiles
        auth_profiles_path = "/Users/garrett/.openclaw/agents/main/agent/auth-profiles.json"
        if os.path.exists(auth_profiles_path):
            with open(auth_profiles_path) as f:
                auth_data = json.load(f)
                profiles = auth_data.get("profiles", {})
                anthropic_profile = profiles.get("anthropic:default", {})
                anthropic_token = anthropic_profile.get("token")
                if anthropic_token:
                    creds["anthropic"] = anthropic_token
    except:
        pass
    
    try:
        # OpenClaw config for various API keys
        openclaw_config_path = "/Users/garrett/.openclaw/openclaw.json"
        if os.path.exists(openclaw_config_path):
            with open(openclaw_config_path) as f:
                config_data = json.load(f)
                env_vars = config_data.get("env", {})
                
                if "XAI_API_KEY" in env_vars:
                    creds["xai"] = env_vars["XAI_API_KEY"]
                if "BRAVE_API_KEY" in env_vars:
                    creds["brave"] = env_vars["BRAVE_API_KEY"]
    except:
        pass
    
    try:
        # Tradier credentials
        tradier_path = "/Users/garrett/.openclaw/workspace/.tradier_credentials.json"
        if os.path.exists(tradier_path):
            with open(tradier_path) as f:
                tradier_data = json.load(f)
                # Use production token
                api_key = tradier_data.get("production", {}).get("token")
                if api_key:
                    creds["tradier"] = api_key
    except:
        pass
    
    return creds

def check_api_status_live(no_cache=False):
    """
    Make actual API status checks with caching.
    Returns real latency and status, not hardcoded values.
    """
    # SOURCE: Live API call — measured latency
    
    # Check cache first unless no_cache is True
    if not no_cache and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                cache_data = json.load(f)
                cache_time = cache_data.get("timestamp", 0)
                if time.time() - cache_time < CACHE_TTL_SECONDS:
                    return cache_data.get("status", {})
        except:
            pass
    
    creds = load_api_credentials()
    status = {}
    
    # Anthropic API - Reachability check (no auth needed)
    # NOTE: Our key is an OAuth token (oat01) managed by OpenClaw, not usable for direct API calls.
    # We check if the API endpoint is reachable. 401 = API is up. Timeout = API is down.
    try:
        start_time = time.time()
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={},  # No auth → should get 401 if API is reachable
            timeout=10
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code in (401, 400):
            # 401 = API reachable (no auth sent), 400 = API reachable (bad request)
            status["anthropic"] = {"status": "operational", "latency": f"{latency_ms}ms"}
        else:
            status["anthropic"] = {"status": "degraded", "latency": f"{latency_ms}ms", "note": f"HTTP {response.status_code}"}
            
    except requests.RequestException as e:
        status["anthropic"] = {"status": "error", "latency": "timeout", "error": str(e)[:50]}
    
    # xAI API
    if "xai" in creds:
        try:
            start_time = time.time()
            response = requests.get(
                "https://api.x.ai/v1/models",
                headers={
                    "Authorization": f"Bearer {creds['xai']}",
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                status["xai_grok"] = {"status": "operational", "latency": f"{latency_ms}ms"}
            else:
                status["xai_grok"] = {"status": "error", "latency": f"{latency_ms}ms", "error": f"HTTP {response.status_code}"}
                
        except requests.RequestException as e:
            status["xai_grok"] = {"status": "error", "latency": "timeout", "error": str(e)[:50]}
    else:
        status["xai_grok"] = {"status": "no_key", "latency": "N/A"}
    
    # Tradier API
    if "tradier" in creds:
        try:
            start_time = time.time()
            response = requests.get(
                "https://api.tradier.com/v1/user/profile",
                headers={
                    "Authorization": f"Bearer {creds['tradier']}",
                    "Accept": "application/json"
                },
                timeout=10
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                status["tradier"] = {"status": "operational", "latency": f"{latency_ms}ms"}
            else:
                status["tradier"] = {"status": "error", "latency": f"{latency_ms}ms", "error": f"HTTP {response.status_code}"}
                
        except requests.RequestException as e:
            status["tradier"] = {"status": "error", "latency": "timeout", "error": str(e)[:50]}
    else:
        status["tradier"] = {"status": "no_key", "latency": "N/A"}
    
    # yfinance check
    try:
        start_time = time.time()
        # Use the finance environment if available
        env_path = "/Users/garrett/.openclaw/workspace/projects/finance-env/"
        if os.path.exists(env_path):
            # Try importing yfinance and making a simple call
            import subprocess
            result = subprocess.run([
                f"{env_path}/bin/python", "-c",
                "import yfinance; ticker = yfinance.Ticker('SPY'); _ = ticker.info['symbol']"
            ], capture_output=True, timeout=10, text=True)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if result.returncode == 0:
                status["yfinance"] = {"status": "operational", "latency": f"{latency_ms}ms"}
            else:
                error_msg = result.stderr[:50] if result.stderr else "unknown error"
                status["yfinance"] = {"status": "error", "latency": f"{latency_ms}ms", "error": error_msg}
        else:
            status["yfinance"] = {"status": "no_env", "latency": "N/A"}
            
    except Exception as e:
        status["yfinance"] = {"status": "error", "latency": "timeout", "error": str(e)[:50]}
    
    # Brave Search API
    if "brave" in creds:
        try:
            start_time = time.time()
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": "test", "count": "1"},
                headers={
                    "X-Subscription-Token": creds["brave"]
                },
                timeout=10
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                status["brave_search"] = {"status": "operational", "latency": f"{latency_ms}ms"}
            else:
                status["brave_search"] = {"status": "error", "latency": f"{latency_ms}ms", "error": f"HTTP {response.status_code}"}
                
        except requests.RequestException as e:
            status["brave_search"] = {"status": "error", "latency": "timeout", "error": str(e)[:50]}
    else:
        status["brave_search"] = {"status": "no_key", "latency": "N/A"}
    
    # Cache the results
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "timestamp": time.time(),
            "status": status
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except:
        pass  # Cache write failure is non-critical
    
    return status

def get_budget_vs_spend():
    """
    Compare configured budgets against real spending from transcripts.
    Returns budget status with real data, no hardcoded values.
    """
    # SOURCE: state/loops.json — user-configured budget
    
    # Load budgets from loops.json
    loops_db_path = Path(__file__).parent / "state" / "loops.json"
    budgets = {}
    
    try:
        if loops_db_path.exists():
            with open(loops_db_path) as f:
                db_data = json.load(f)
                budgets = db_data.get("budgets", {})
    except Exception as e:
        return {"error": f"Cannot read budget config: {str(e)}"}
    
    # Get real spending from transcripts
    transcript_data = scan_session_transcripts()
    real_spend = transcript_data.get("spend", {})
    
    if "error" in transcript_data:
        return {"error": transcript_data["error"], "budgets": budgets}
    
    # Calculate budget status
    budget_status = {}
    
    for provider, config in budgets.items():
        if provider == "local":  # Special case for local compute
            budget_status[provider] = {
                "status": config.get("status", "offline"),
                "spend": 0.0,
                "budget": 0.0,
                "remaining": 0.0,
                "percent": 0.0
            }
            continue
        
        current_spend = real_spend.get(provider, 0.0)
        monthly_budget = config.get("monthly_budget_usd", 0.0)
        
        if monthly_budget > 0:
            remaining = monthly_budget - current_spend
            percent = (current_spend / monthly_budget) * 100
        else:
            remaining = 0.0
            percent = 0.0 if current_spend == 0 else 100.0
        
        budget_status[provider] = {
            "spend": current_spend,
            "budget": monthly_budget,
            "remaining": remaining,
            "percent": percent
        }
    
    return {
        "budgets": budget_status,
        "meta": transcript_data.get("meta", {}),
        "providers_found": list(real_spend.keys()),
        "total_real_spend": sum(real_spend.values())
    }

def main():
    """CLI interface for testing the module."""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw API Usage Tracker")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh API status checks")
    parser.add_argument("--transcripts", action="store_true", help="Show transcript scan results")
    parser.add_argument("--status", action="store_true", help="Show API status")
    parser.add_argument("--budget", action="store_true", help="Show budget vs spending")
    
    args = parser.parse_args()
    
    if args.transcripts or not any([args.status, args.budget]):
        print("=== Transcript Scan Results ===")
        result = scan_session_transcripts()
        print(json.dumps(result, indent=2))
        print()
    
    if args.status or not any([args.transcripts, args.budget]):
        print("=== API Status ===")
        status = check_api_status_live(no_cache=args.no_cache)
        print(json.dumps(status, indent=2))
        print()
    
    if args.budget or not any([args.transcripts, args.status]):
        print("=== Budget vs Spending ===")
        budget_data = get_budget_vs_spend()
        print(json.dumps(budget_data, indent=2))

if __name__ == "__main__":
    main()