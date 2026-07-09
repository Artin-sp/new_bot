# Telegram Userbot Dashboard

## Overview
Multi-account Telegram userbot (Telethon) with a FastAPI web dashboard and a
Telegram inline-button admin panel. Automates account actions: banner
forwarding, scheduled sends, auto-clicker, auto-reply, AI-assisted commands.

## Running
- Workflow "Start application" runs `python main.py`, serving the dashboard on port 5000.
- Secrets used: `API_ID`, `API_HASH`, `BOT_TOKEN` (admin panel bot), `GITHUB_TOKEN` (push-to-GitHub dashboard feature). Optional: `GROQ_API_KEY` / `OPENAI_API_KEY` for AI commands.
- Per-account Telegram sessions live in `sessions/*.session`; add new accounts via the dashboard's "Add Account" flow (needs the account's phone + login code).

## User preferences
None recorded yet.

## Notes
- The previously-committed `cred.env.txt` (plaintext credentials) was removed; its values were moved into Replit Secrets.
- The three imported account sessions show "Disconnected" — Telegram invalidated them due to concurrent use elsewhere (`AuthKeyDuplicatedError`). Re-login via "Add Account" is required to reconnect them.
