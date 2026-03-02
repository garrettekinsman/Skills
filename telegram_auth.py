#!/usr/bin/env python3
"""
One-time Telegram auth flow.
Run this ONCE interactively to create the session file.
After that, telegram_osint.py runs headless forever.

Usage:
    cd ~/.openclaw/workspace/skills/research-loops
    python3 telegram_auth.py
"""

import asyncio
import json
from pathlib import Path

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    print("Missing dependency. Run: pip3 install telethon")
    exit(1)

CONFIG_PATH = Path(__file__).parent / "telegram_config.json"

async def main():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)["telegram_api"]

    session_path = cfg["session_path"]
    print(f"Session will be saved to: {session_path}.session")

    client = TelegramClient(
        session_path,
        int(cfg["api_id"]),
        cfg["api_hash"]
    )

    await client.connect()

    if not await client.is_user_authorized():
        print(f"\nSending auth code to {cfg['phone']}...")
        await client.send_code_request(cfg["phone"])

        code = input("Enter the code Telegram sent to your phone: ").strip()

        try:
            await client.sign_in(cfg["phone"], code)
        except SessionPasswordNeededError:
            # 2FA enabled — try config first, then prompt
            password = cfg.get("password_2fa")
            if password:
                print("Two-factor auth enabled. Using password from config...")
            else:
                password = input("Two-factor auth enabled. Enter your password: ").strip()
            await client.sign_in(password=password)

    me = await client.get_me()
    print(f"\n✅ Authenticated as: {me.first_name} (@{me.username})")
    print(f"   Phone: {me.phone}")
    print(f"   Session saved: {session_path}.session")
    print("\nYou're good. telegram_osint.py will now work headless.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
