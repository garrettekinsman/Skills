#!/usr/bin/env python3
"""
local_research.py — Call a local LLM via LiteLLM API for research sprints.

This is the TOOL that the Opus orchestrator sub-agent calls to delegate
heavy research work to the local GPU model. The Opus agent:
  1. Builds a focused sprint prompt
  2. Calls this script to send it to the local model
  3. Reads the sanitized output
  4. Decides what to research next

This keeps cloud token usage minimal — Opus orchestrates (~500 tokens/sprint),
local model does the actual research/analysis (~2000-4000 tokens/sprint).

Usage:
    python3 scripts/local_research.py \
        --model qwen3-coder \
        --prompt "Analyze NVIDIA's competitive moat in AI inference..." \
        --max-tokens 4000 \
        --temperature 0.7

    # With sanitization (default: on)
    python3 scripts/local_research.py --model qwen3-coder --prompt "..." --sanitize

    # Raw output (skip sanitizer — ONLY for debugging)
    python3 scripts/local_research.py --model qwen3-coder --prompt "..." --no-sanitize

Environment:
    LITELLM_URL      — e.g. http://100.112.143.23:4000
    LITELLM_API_KEY  — API key for LiteLLM

Output (JSON to stdout):
    {
        "ok": true,
        "content": "sanitized model output...",
        "raw_length": 3421,
        "sanitized_length": 3380,
        "tokens_used": 892,
        "latency_ms": 12340,
        "model": "qwen3-coder",
        "sanitizer": {
            "safe": true,
            "blocked": false,
            "flags": [],
            "strips": 2
        }
    }

    On error:
    {
        "ok": false,
        "error": "description",
        "error_type": "timeout|connection|auth|sanitizer_block|model_error"
    }
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR))

from model_output_sanitizer import sanitize_model_output


def call_local_model(
    prompt: str,
    model: str = "qwen3-coder",
    max_tokens: int = 4000,
    temperature: float = 0.7,
    system_prompt: str = None,
    timeout_sec: int = 120,
) -> dict:
    """
    Call a local model via LiteLLM API and return sanitized output.
    
    Returns dict with ok, content, tokens_used, latency_ms, sanitizer info.
    """
    import urllib.request
    import urllib.error
    
    litellm_url = os.environ.get("LITELLM_URL")
    api_key = os.environ.get("LITELLM_API_KEY")
    
    if not litellm_url:
        return {"ok": False, "error": "LITELLM_URL not set", "error_type": "config"}
    if not api_key:
        return {"ok": False, "error": "LITELLM_API_KEY not set", "error_type": "config"}
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    url = litellm_url.rstrip("/") + "/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}: {body}", "error_type": "model_error"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Connection failed: {e.reason}", "error_type": "connection"}
    except TimeoutError:
        return {"ok": False, "error": f"Timed out after {timeout_sec}s", "error_type": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e), "error_type": "unknown"}
    
    latency_ms = int((time.time() - t0) * 1000)
    
    choices = data.get("choices", [])
    if not choices:
        return {"ok": False, "error": "Empty choices in response", "error_type": "model_error"}
    
    raw_content = choices[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    tokens_used = usage.get("total_tokens", 0)
    
    if not raw_content.strip():
        return {"ok": False, "error": "Model returned empty content", "error_type": "model_error"}
    
    return {
        "ok": True,
        "raw_content": raw_content,
        "tokens_used": tokens_used,
        "latency_ms": latency_ms,
        "model": model,
        "raw_length": len(raw_content),
    }


def research_sprint(
    prompt: str,
    model: str = "qwen3-coder",
    max_tokens: int = 4000,
    temperature: float = 0.7,
    system_prompt: str = None,
    sanitize: bool = True,
    timeout_sec: int = 120,
) -> dict:
    """
    Full research sprint: call model → sanitize → return safe output.
    """
    result = call_local_model(
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
        timeout_sec=timeout_sec,
    )
    
    if not result["ok"]:
        return result
    
    raw = result["raw_content"]
    
    if sanitize:
        san = sanitize_model_output(raw, source_model=model, task="research_sprint")
        result["sanitizer"] = {
            "safe": san.get("safe", False),
            "blocked": san.get("blocked", False),
            "flags": san.get("flags", []),
            "strips": san.get("strips", 0),
        }
        
        if san.get("blocked"):
            return {
                "ok": False,
                "error": f"Sanitizer blocked output: {san.get('flags', [])}",
                "error_type": "sanitizer_block",
                "raw_length": len(raw),
                "sanitizer": result["sanitizer"],
            }
        
        result["content"] = san.get("text", raw)
        result["sanitized_length"] = len(result["content"])
    else:
        result["content"] = raw
        result["sanitized_length"] = len(raw)
        result["sanitizer"] = {"safe": None, "blocked": False, "flags": [], "strips": 0}
    
    # Remove raw_content from output (only return sanitized)
    del result["raw_content"]
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Call local LLM for research sprint")
    parser.add_argument("--model", default="qwen3-coder", help="LiteLLM model ID")
    parser.add_argument("--prompt", required=True, help="Research prompt")
    parser.add_argument("--system", default=None, help="System prompt")
    parser.add_argument("--max-tokens", type=int, default=4000, help="Max output tokens")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    parser.add_argument("--sanitize", action="store_true", default=True, help="Sanitize output (default)")
    parser.add_argument("--no-sanitize", action="store_true", help="Skip sanitization (debug only)")
    args = parser.parse_args()
    
    result = research_sprint(
        prompt=args.prompt,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        system_prompt=args.system,
        sanitize=not args.no_sanitize,
        timeout_sec=args.timeout,
    )
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
