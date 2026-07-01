# Telegram Userbot — Claude Instructions

> Read this file first before touching any code. It covers the full idea, architecture, and all the non-obvious decisions.

---

## What This Project Is

A **multi-account Telegram userbot** — it logs in as real Telegram user accounts (not bots) and automates actions for their owners. Think of it as a programmable Telegram client: the user types a dot-command like `.ai سوال` or `.ویس سلام` inside any chat, and the bot handles it silently.

It has two interfaces:
1. **Telegram dot-commands** — typed directly in any Telegram chat by the account owner
2. **Web dashboard** — FastAPI app on port 5000, for managing accounts and viewing tasks

---

## Stack

| Layer | Tech |
|-------|------|
| Telegram MTProto | Telethon (Python) |
| Telegram helper bot | Telethon bot mode (BOT_TOKEN) — needed for inline buttons |
| Web API | FastAPI + uvicorn, port 5000 |
| Database | SQLite (WAL mode) — `userbot.db` |
| AI chat | Groq API — `llama-3.3-70b-versatile` |
| Speech-to-text | Groq API — `whisper-large-v3` |
| Text-to-speech | Microsoft edge-tts (free, no key, Persian + English + Arabic) |
| Translation | Google Translate (unauthenticated GTX endpoint) |
| Crypto prices | Nobitex exchange REST API (GET, no auth) |
| Language | Python 3.11 |

---

## File Map

```
main.py           Entry point — starts helper bot, loads accounts, starts web server
manager.py        Core — owns Acc objects, login flow, banner/send async loops
commands.py       All dot-commands registered per user account (735 lines)
autoclicker.py    Watches incoming messages, clicks inline buttons automatically
panel.py          Telegram inline-button panel (opened via .panel command)
web.py            FastAPI REST API + serves dashboard.html
db.py             SQLite schema + get/put/toggle/conn helpers
dashboard.html    Single-page web dashboard (vanilla JS)
CODEBASE.md       Technical reference (architecture, schemas, endpoints)
CLAUDE.md         This file — concept + instructions for Claude
requirements.txt  pip dependencies
sessions/         Telethon session files (one per account + helperbot)
```

---

## Core Concepts

### Accounts (Acc objects)
Each Telegram user account that logs in becomes an `Acc` object in `manager.py`. It holds:
- The Telethon client, the phone number (primary key everywhere), name, user_id
- A dict of running asyncio tasks (banner loops, send loops)
- Per-session state (dm_last cooldown dict, fmt_skip loop guard set)

Phone numbers are the universal primary key. Every DB table has a `phone` column.

### Two Telegram clients per session
1. **The userbot client** (`acc.client`) — logged in as the real user, sends/receives messages as them
2. **The helper bot** (`panel.bot`) — a real @BotFather bot that sends inline keyboard panels. Userbots can't send inline keyboards, so the helper bot does it.

### Persistence via SQLite settings table
The `settings` table stores `(phone, key, value)` rows. This is used for:
- Feature toggles: `ar_on`, `sec_on`, `autoseen`, `fmt_bold`, etc.
- AI memory: `ai_name` (user's saved name), `ai_history` (JSON array of last 12 messages)
- TTS preferences: `tts_lang` (fa/en/en-gb/en-au/ar/auto), `tts_gender` (f/m)

**Each account has completely separate settings — they never mix.**

### Async rule
**Never use blocking I/O directly in async handlers.** Everything that blocks (HTTP requests, file I/O, gtts) must go in `asyncio.get_event_loop().run_in_executor(None, fn)`. edge-tts is natively async and doesn't need this. Violation of this rule freezes the entire bot for all accounts.

---

## All Dot-Commands

The owner types these in any Telegram chat. Both Persian and English aliases work.

### Core
| Command | Effect |
|---------|--------|
| `.پنل` / `.panel` | Open inline button panel via helper bot |
| `.راهنما` / `.help` | Full help sent to Saved Messages |
| `.وضعیت` / `.status` | Status summary of all active features |

### Scheduled Send (ارسال زمان‌بندی)
| Command | Effect |
|---------|--------|
| `.ارسال [متن] [ثانیه]` / `.send` | Send a message repeatedly every N seconds. Persists across restarts. |
| `.stop` / `.توقف` / `.پایان ارسال` | Stop send in current chat |
| `.stopall` / `.توقف کل` | Stop all sends and banners |

### Banner / تیچی
Must **reply** to a message first, then type the command.
| Command | Effect |
|---------|--------|
| `.تنظیم بنر [ثانیه]` / `.setbanner` | Copy that message to the chat every N seconds |
| `.تنظیم بنر [ثانیه] فور` | Forward (instead of copy) |
| `.لیست بنر` | List active banners |
| `.پاکسازی بنر` | Stop banners in current chat |
| `.پاکسازی کل بنر` | Stop all banners |

### Auto-Reply
| Command | Effect |
|---------|--------|
| `.افزودن پاسخ kw = reply` | Add auto-reply: when incoming msg contains `kw`, reply with `reply` |
| `.حذف پاسخ kw` | Remove keyword |
| `.لیست پاسخ` | List all keywords |
| `.پاکسازی پاسخ` | Delete all keywords |

### Secretary (منشی)
Auto-replies to private DMs with a configurable message and cooldown.
| Command | Effect |
|---------|--------|
| `.متن منشی [متن]` / `.sectext` | Set the auto-reply text |
| `.تایم منشی [ثانیه]` / `.sectime` | Set cooldown between replies to same person |

### Spam
| Command | Effect |
|---------|--------|
| `.اسپم [n] [متن]` / `.spam` | Send n times (max 100), 0.8s delay |
| `.اسپم سریع [n] [متن]` | 0.3s delay |
| `.اسپم آرام [n] [متن]` | 2.5s delay |
| `.پایان اسپم` / `.stopspam` | Stop immediately |

### Voice / TTS (edge-tts — no API key needed)
| Command | Effect |
|---------|--------|
| `.ویس [متن]` / `.voice` | Convert text to voice note. Auto-detects Persian vs English. |
| `.ویس` (reply to text msg) | Convert that message to voice |
| `.ویس‌صدا fa f` | Set Persian female voice (Dilara) |
| `.ویس‌صدا fa m` | Set Persian male voice (Farid) |
| `.ویس‌صدا en f` | English US female (Jenny) |
| `.ویس‌صدا en m` | English US male (Guy) |
| `.ویس‌صدا en-gb f` | British female (Sonia) |
| `.ویس‌صدا en-au m` | Australian male (William) |
| `.ویس‌صدا ar f` | Arabic female (Zariyah) |
| `.ویس‌صدا auto` | Auto-detect language per message |

### Speech-to-Text (Groq Whisper)
| Command | Effect |
|---------|--------|
| `.متن` / `.totext` (reply to voice) | Transcribe voice note to text. Needs GROQ_API_KEY. |

### AI Chat (Groq Llama 3.3 70B — with per-account memory)
| Command | Effect |
|---------|--------|
| `.هوش [سوال]` / `.ai` | Ask a question. Remembers last 6 exchanges per account. |
| `.هوش نام [اسمت]` | Save your name — AI will address you by it |
| `.هوش ریست` | Clear conversation history |

**Memory is per-account**: `ai_name` and `ai_history` are stored under each account's phone number in the `settings` table. Two accounts never share or see each other's memory.

### Translation
| Command | Effect |
|---------|--------|
| `.ترجمه [متن]` / `.translate` | Translate any text to Persian (Google GTX, no key) |

### Crypto Prices
| Command | Effect |
|---------|--------|
| `.قیمت` / `.price` | USDT, BTC, ETH, BNB, TRX, DOGE, LTC prices in Toman (Nobitex API, GET) |

### Time & Date
| Command | Effect |
|---------|--------|
| `.ساعت` / `.تاریخ` | Current time + Jalali (Shamsi) date in Tehran timezone |

### Utilities
| Command | Effect |
|---------|--------|
| `.پینگ` / `.ping` | Round-trip latency to Telegram |
| `.حساب [expr]` / `.calc` | Evaluate math expression safely |
| `.پسورد [n]` / `.password` | Generate random n-char password → sent to Saved Messages |
| `.کوتاه [url]` / `.short` | Shorten URL via is.gd |
| `.شانس` / `.luck` | Random luck message |

### Games (dice with target value)
| Command | Effect |
|---------|--------|
| `.تاس [1-6]` / `.dice` | Send dice, retry until value matches |
| `.دارت [1-6]` / `.dart` | Same for dart |
| `.بسکتبال [1-5]` / `.basketball` | Same for basketball |
| `.فوتبال [1-5]` / `.football` | Same for football |
| `.بولینگ [1-6]` / `.bowling` | 6 = strike |
| `.اسلات [1-64]` / `.slot` | 64 or `777` = jackpot |

Telegram randomizes dice values server-side, so the only way to hit a target is: send → check value → delete if wrong → repeat.

### Auto-Clicker
| Command | Effect |
|---------|--------|
| `.دیباگ‌دکمه` (reply to msg with buttons) | Print exact button text for all buttons |
| `.افزودن‌کلیک @bot 0 \| Claim` | Add rule: click button containing "Claim" in any msg from @bot (0 = unlimited) |
| `.لیست‌کلیک` | List active rules |
| `.حذف‌کلیک [id]` | Delete a rule |

### Text Format Mode
When a format flag is on, every outgoing message from that account gets that formatting applied automatically.
Toggle via the `.پنل` → حالت‌متن screen, or: `fmt_bold`, `fmt_italic`, `fmt_underline`, `fmt_strike`, `fmt_mono`, `fmt_spoiler`, `fmt_quote` in settings.

---

## Database Schema

```sql
accounts(phone PK, name, username, active)
auto_replies(id, phone, keyword, reply, enabled)
banners(id, phone, chat_id, source_chat, msg_id, interval_sec, mode, active)
sends(id, phone, chat_id, message, interval_sec, active)
settings(phone, key, value)           ← per-account key-value store
config(key PK, value)                 ← global config (reserved)
click_rules(id, phone, bot_username, pattern, remaining, delay_sec, active)
```

Settings keys used:
- `ar_on`, `ar_type` — auto-reply toggle + match type
- `sec_on`, `sec_msg`, `sec_time` — secretary mode
- `autoseen` — auto-read-mark
- `fmt_bold/italic/underline/strike/mono/spoiler/quote` — text formatting
- `tts_lang`, `tts_gender` — voice settings (fa/en/en-gb/en-au/ar/auto, f/m)
- `ai_name` — user's saved name for AI
- `ai_history` — JSON array of last 12 chat messages

---

## API Endpoints (web.py)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Dashboard HTML |
| GET | `/api/accounts` | List accounts with stats |
| POST | `/api/login/code` | Send SMS code |
| POST | `/api/login/verify` | Verify code (returns `need2fa`) |
| POST | `/api/login/2fa` | Complete 2FA |
| DELETE | `/api/accounts/{phone}` | Remove account (`+` → `-` in path) |
| GET | `/api/tasks` | Active scheduled sends |
| DELETE | `/api/tasks/{phone}/{chat_id}` | Stop a send |
| GET | `/api/banners` | Active banners |
| DELETE | `/api/banners/{id}` | Stop a banner |
| GET | `/api/replies` | Auto-reply rules |
| DELETE | `/api/replies/{id}` | Delete a rule |
| GET | `/api/clicks` | Auto-clicker rules |
| DELETE | `/api/clicks/{id}` | Deactivate a rule |
| POST | `/api/git/push` | Commit + push to GitHub |

Phone numbers in URL paths use `-` instead of `+`.

---

## Required Secrets

Set in Replit Secrets (never hardcode):

| Secret | Required | Purpose |
|--------|----------|---------|
| `API_ID` | ✅ | From my.telegram.org |
| `API_HASH` | ✅ | From my.telegram.org |
| `BOT_TOKEN` | ✅ | Helper bot token from @BotFather |
| `GROQ_API_KEY` | Optional | AI chat + STT. Free at console.groq.com |
| `GITHUB_TOKEN` | Optional | GitHub push from dashboard |

---

## Key Pitfalls to Know

1. **`database is locked`** — SQLite journals left from crashes. Fixed by deleting `sessions/*.session-journal` at startup (in `main.py`).

2. **Blocking in async** — `urllib.request`, `gTTS`, `requests`, file I/O — all must use `run_in_executor`. `edge-tts` is natively async, no executor needed.

3. **Phone `+` in URLs** — Replace `+` with `-` in URL paths, then `.replace("-", "+")` server-side.

4. **Panel security** — `acc.user_id` is set from `get_me()` at login. Every callback checks `event.sender_id == acc.user_id`. This stops anyone else (e.g. in a group) from controlling another person's panel.

5. **`fmt_skip` set** — Text-format mode intercepts outgoing messages, deletes them, re-sends with HTML. Without `fmt_skip`, the re-sent message triggers the handler again → infinite loop. Add the message ID to `acc.fmt_skip` before re-sending; remove it after.

6. **Banner/send persistence** — DB row is written before the task starts. `manager.load()` → `_restore_banners` / `_restore_sends` reads active rows on startup and restarts the loops.

7. **Multi-account isolation** — `commands.register(client, acc, manager)` is called once per account. Each handler closure captures its own `client` and `acc`. Account A's handlers never fire for account B.

8. **Phone encoding in Telegram callback data** — `+` → `P` via `_enc`/`_dec` in `panel.py`.

9. **AI memory isolation** — `ai_history` and `ai_name` are stored with the phone number as key in `settings`. Each account has its own row — they never cross.

---

## How to Add a New Feature

### New dot-command
1. Open `commands.py`, inside `register(client, acc, manager)`
2. Add a handler:
```python
@client.on(events.NewMessage(outgoing=True, pattern=r'^\.mycommand (.+)$'))
async def _my_cmd(event):
    arg = event.pattern_match.group(1).strip()
    await event.delete()
    # Your logic here
    await client.send_message(event.chat_id, f"Result: {arg}")
```
3. Add to the help text in `_help`
4. Add to `CODEBASE.md` and `CLAUDE.md`

### New panel subscreen
1. Add `_sub_myfeature(phone)` function to `panel.py` returning `(text, keyboard)`
2. Add a button to `kb_menu(phone)`
3. Add `elif action == "sub_myfeature": t, kb = _sub_myfeature(phone); await show(t, kb)` in the callback handler

### New API endpoint
1. Add route to `web.py`
2. If it needs a UI button, add it to `dashboard.html`

### New per-account setting
1. Use `db.put(phone, "my_key", value)` and `db.get(phone, "my_key", default)`
2. No schema changes needed — `settings` table handles arbitrary keys

---

## Voice System Details

TTS uses **Microsoft edge-tts** (free, no API key, proper Persian support):

| Code | Language | Female | Male |
|------|----------|--------|------|
| `fa` | فارسی | DilaraNeural | FaridNeural |
| `en` | English US | JennyNeural | GuyNeural |
| `en-gb` | English UK | SoniaNeural | RyanNeural |
| `en-au` | English AU | NatashaNeural | WilliamNeural |
| `ar` | عربی | ZariyahNeural | HamedNeural |

Settings stored per account: `tts_lang` + `tts_gender`. Default: auto-detect language (Persian chars → `fa`, else `en`), female voice.

---

## AI System Details

Model: **Llama 3.3 70B** via Groq (free tier, fast).

Per-account memory stored in SQLite `settings` table:
- `ai_name` — user's preferred name (set via `.هوش نام [اسمت]`)
- `ai_history` — JSON array of `{role, content}` objects, max 12 entries (6 exchanges)

System prompt dynamically includes the user's name if set. History is prepended to every API call so the model has context. Memory is completely isolated per account (different phone numbers = different rows).

The AI can understand Persian and English and always replies in the same language the user writes in.
