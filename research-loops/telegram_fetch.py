#!/usr/bin/env python3
"""
telegram_fetch.py — Secure Telegram OSINT entry point for sub-agents
=====================================================================

USAGE (sub-agents only):
    python3 telegram_fetch.py [--hours 4] [--channels priority|extended|all]

OUTPUT: JSON to stdout — structured, sanitized, safe to pass to LLM prompt.

NEVER call this from the main agent session.
NEVER pass raw .text fields directly into LLM prompts — use .prompt_prefix.
"""

import asyncio
import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Security layer — must be imported before anything else
from telegram_secure import (
    make_read_only,
    sanitize_message,
    format_safe_summary,
    # assert_subagent_context,  # Enable when OPENCLAW_SESSION_KIND env is set
)

try:
    from telethon import TelegramClient
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
except ImportError:
    print(json.dumps({"error": "telethon not installed: pip install telethon"}))
    sys.exit(1)


CONFIG_PATH = Path(__file__).parent / "telegram_config.json"

CHANNEL_LISTS = {
    "priority": [
        "@S2undergroundWire",
        "@OSINTdefender",
        "@warmonitors",
        "@liveuamap",
        "@s2_underground_project",
    ],
    "extended": [
        "@sashakots",
        "@IntelCrab",
        "@sentdefender",
        "@rybar_en",
        "@AircraftSpots",
    ],
}
CHANNEL_LISTS["all"] = CHANNEL_LISTS["priority"] + CHANNEL_LISTS["extended"]


async def fetch_channel(client, channel_handle: str, hours_back: int, msg_limit: int = 50) -> list:
    """Fetch messages from one channel, return list of sanitized dicts.

    RATE LIMIT SAFETY:
    - Default limit=50 per channel — do not raise without explicit reason
    - No per-message entity resolution (each get_entity() = extra API hit)
    - 2s sleep between channels
    - FloodWaitError: respect Telegram's backoff, propagate up cleanly
    - @gahonga is a new account — conservative posture prevents re-ban
    """
    raw_messages = []
    try:
        entity = await client.get_entity(channel_handle)
        since = datetime.now().replace(tzinfo=None) - timedelta(hours=hours_back)

        # iter_messages with no offset_date fetches newest-first.
        # We break manually when we pass the time window cutoff.
        # DO NOT resolve msg.from_id — that's an extra API call per message.
        async for msg in client.iter_messages(entity, limit=msg_limit):
            # Stop once we've gone past our time window
            if msg.date:
                msg_dt = msg.date.replace(tzinfo=None)
                if msg_dt < since:
                    break

            text = msg.message or msg.text or ""
            if not text.strip():
                continue

            media_type = None
            if msg.media:
                if isinstance(msg.media, MessageMediaPhoto):
                    media_type = "photo"
                elif isinstance(msg.media, MessageMediaDocument):
                    media_type = "document"
                else:
                    media_type = "other"

            raw_messages.append({
                "channel": channel_handle,
                "message_id": msg.id,
                "timestamp": msg.date.isoformat() if msg.date else "",
                "text": text,
                "sender": "",  # Intentionally blank — no entity resolution (extra API hit)
                "media_type": media_type,
                "views": getattr(msg, "views", None),
                "forwards": getattr(msg, "forwards", None),
                "reactions": None,
                "reply_to": msg.reply_to_msg_id,
            })

        # Polite pause between channels — 2s is enough to be safe
        await asyncio.sleep(2)

    except Exception as e:
        err_type = type(e).__name__
        # FloodWaitError means Telegram told us to back off — respect it
        flood_wait = getattr(e, "seconds", None)
        raw_messages.append({
            "channel": channel_handle,
            "error": f"fetch_failed: {err_type}" + (f" (flood_wait={flood_wait}s)" if flood_wait else ""),
            "message_id": 0,
            "timestamp": datetime.now().isoformat(),
            "text": "",
            "sender": "",
            "media_type": None,
            "views": None,
            "forwards": None,
            "reactions": None,
            "reply_to": None,
        })
        # If Telegram asked us to wait, do it before the next channel
        if flood_wait:
            import sys
            print(f"[telegram_fetch] FloodWait on {channel_handle}: sleeping {flood_wait}s", file=sys.stderr)
            await asyncio.sleep(flood_wait + 2)

    return [sanitize_message(m) for m in raw_messages]


async def main(hours_back: int = 4, channel_set: str = "priority", msg_limit: int = 50, store: bool = False):
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)["telegram_api"]

    client = TelegramClient(
        cfg["session_path"],
        int(cfg["api_id"]),
        cfg["api_hash"]
    )

    # Enforce read-only BEFORE connecting
    make_read_only(client)

    await client.connect()

    if not await client.is_user_authorized():
        print(json.dumps({
            "error": "not_authenticated",
            "message": "Run telegram_auth.py first to create a session."
        }))
        await client.disconnect()
        sys.exit(1)

    channels = CHANNEL_LISTS.get(channel_set, CHANNEL_LISTS["priority"])
    all_messages = []

    for handle in channels:
        msgs = await fetch_channel(client, handle, hours_back, msg_limit=msg_limit)
        all_messages.extend(msgs)

    await client.disconnect()

    # Filter out error-only entries for the summary
    valid_messages = [m for m in all_messages if not m.get("error")]
    error_channels = [m["channel"] for m in all_messages if m.get("error")]

    summary = format_safe_summary(valid_messages)
    summary["fetch_metadata"] = {
        "channels_requested": len(channels),
        "channels_failed": len(error_channels),
        "failed_channels": error_channels,
        "hours_back": hours_back,
        "fetched_at": datetime.now().isoformat(),
        "channel_set": channel_set,
    }

    # Optionally persist to SQLite before printing
    if store:
        try:
            from osint_store import store_messages as _store
            store_stats = _store(valid_messages)
            summary["fetch_metadata"]["stored"] = store_stats
        except Exception as e:
            import sys as _sys
            print(f"[store] warning: could not write to DB: {e}", file=_sys.stderr)
            summary["fetch_metadata"]["stored"] = {"error": str(e)}

    # Output clean JSON — sub-agent reads this from stdout
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram OSINT fetch (sub-agents only)")
    parser.add_argument("--hours", type=int, default=4, help="Hours of history to fetch")
    parser.add_argument("--channels", choices=["priority", "extended", "all"],
                        default="priority", help="Channel set to fetch")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max messages per channel (default 50 — do not raise without reason; "
                             "@gahonga is a new account and already got temporarily banned once; "
                             "50 is the conservative safe cap for regular runs)")
    parser.add_argument("--store", action="store_true", default=False,
                        help="Write fetched messages to osint_archive.db (deduped)")
    args = parser.parse_args()

    asyncio.run(main(hours_back=args.hours, channel_set=args.channels, msg_limit=args.limit, store=args.store))
