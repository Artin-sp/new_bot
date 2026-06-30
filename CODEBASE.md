# Telegram Userbot — Codebase Reference

This document is written for an AI assistant (or human developer) who needs to understand, modify, or extend this project. Read it fully before touching any file.

---

## What This Project Is

A **multi-account Telegram userbot** ("self-bot") — it logs in as a real Telegram user account (not a bot account) and automates actions on their behalf. It has:

- A **web dashboard** (FastAPI + plain HTML/JS) for managing accounts and viewing active tasks
- A **Telegram inline-button panel** accessible by typing `.panel` in any chat
- A set of **dot-commands** (e.g. `.ai سوال`, `.ویس سلام`) the account owner types in Telegram
- **Automation loops**: banner forwarding, scheduled sends, auto-clicker, auto-reply, secretary mode

It is written in **Python 3.11**, uses **Telethon** for the MTProto API, **FastAPI + uvicorn** for the web layer, and **SQLite** for persistence.

---

## File Map

```
main.py          — entry point: wires everything together, starts bot + web server
manager.py       — core: manages Acc objects, login flow, banner/send loops
commands.py      — all dot-commands registered per user account
autoclicker.py   — watches incoming messages and clicks inline buttons
panel.py         — Telegram inline-button UI (.panel command)
web.py           — FastAPI app: REST API + serves dashboard.html
db.py            — SQLite schema + helper functions (get/put/toggle/conn)
dashboard.html   — single-page web dashboard (vanilla JS, no framework)
requirements.txt — pip dependencies
```

---

## Architecture

```
User types .panel or .ai in Telegram
        │
        ▼
commands.py / panel.py   ← registered via Telethon event handlers
        │                   one set of handlers per connected account
        ▼
manager.py (Manager)     ← owns all Acc objects and async task loops
        │
        ├── db.py (SQLite)   ← persistent state for all settings/tasks
        └── web.py (FastAPI) ← REST API consumed by dashboard.html
                 │
                 ▼
          dashboard.html     ← runs in browser, calls /api/* endpoints
```

**Key design rule:** `manager.py` is the single source of truth for running accounts. `web.py` reads `mgr` (set at startup in `main.py`) to serve API calls. `commands.py` and `autoclicker.py` are registered *per account* inside `manager.connect()`.

---

## main.py

Entry point. Runs three things concurrently inside a single asyncio event loop:

1. **Helper bot** — a real `@BotFather` bot (BOT_TOKEN) that serves the inline panel. Started with `panel.bot.start(bot_token=...)`.
2. **Account loader** — calls `mgr.load()` which reads the `accounts` table and reconnects each saved session.
3. **Web server** — `await web.start()` (uvicorn on port 5000, blocks until killed).

**Startup cleanup:** At the very top, `glob.glob("sessions/*.session-journal")` deletes any leftover SQLite journal files. These are created by Telethon when it crashes mid-write and cause `sqlite3.OperationalError: database is locked` on the next start. Deleting them is safe — SQLite recreates them if needed.

**Environment variables** are loaded from `.env` via `python-dotenv`. In production (Replit), they come from Secrets.

---

## manager.py

### `Acc` dataclass

Each connected Telegram account is represented as an `Acc`:

| Field | Type | Purpose |
|-------|------|---------|
| `phone` | str | E.164 phone number, used as primary key everywhere |
| `client` | TelegramClient | Telethon client for this account |
| `name` | str | First name from Telegram |
| `username` | str | @username (may be empty) |
| `user_id` | int | Telegram user ID (used for panel security check) |
| `tasks` | dict[str, Task] | Running asyncio tasks keyed by `"banner:ID"` or `"text:chat_id"` |
| `dm_last` | dict[int, float] | Secretary cooldown: last reply timestamp per chat |
| `fmt_skip` | set[int] | Loop-guard for text-format mode (prevents infinite re-send) |

### `Manager` class

**`connect(phone)`** — The core method. Creates a TelegramClient, checks the session is authorized, fetches `get_me()`, calls `commands.register()` and `autoclicker.register()` to attach event handlers, then restores any persisted banners/sends from the DB.

**Login flow** (used by the dashboard):
1. `begin_login(phone)` — sends the SMS code, stores pending client in `_pending`
2. `finish_login(phone, code, pw)` — signs in; if `SessionPasswordNeeded` raises `2FA_REQUIRED`
3. `finish_2fa(phone, pw)` — completes 2FA sign-in
4. All three are serialized with `_login_lock` to avoid race conditions

**Banner loop** (`_banner_loop`) — copies or forwards a specific message to a chat every N seconds. Stored in `banners` table; resumed on restart via `_restore_banners`.

**Send loop** (`_send_loop`) — sends a text message to a chat every N seconds. Stored in `sends` table; resumed on restart via `_restore_sends`.

---

## commands.py

All commands are registered inside `register(client, acc, manager)`. Each command is an outgoing message handler (`outgoing=True`) that matches a regex pattern. Commands fire only for the account owner (outgoing messages from their own client).

### Command Reference

| Command (Persian / English) | What it does |
|-----------------------------|-------------|
| `.پنل` / `.panel` | Opens the inline button panel via the helper bot |
| `.ارسال [s] [msg]` / `.send` | Start scheduled send every s seconds |
| `.پایان ارسال [chat]` / `.stopsend` | Stop scheduled send in a chat |
| `.پایان همه` / `.stopall` | Cancel all sends and banners |
| `.تنظیم بنر [s]` / `.setbanner` | Reply to a message → forward/copy it every s seconds |
| `.تنظیم بنر [s] فور` | Same but using forward (not copy) |
| `.لیست بنر` / `.bannerlist` | List active banners |
| `.پاکسازی بنر` / `.clearbanner` | Stop banners in current chat |
| `.پاکسازی کل بنر` / `.clearallbanners` | Stop all banners for this account |
| `.افزودن پاسخ kw = reply` / `.addreply` | Add auto-reply keyword |
| `.حذف پاسخ kw` / `.delreply` | Remove auto-reply keyword |
| `.لیست پاسخ` / `.replylist` | List auto-reply keywords |
| `.پاکسازی پاسخ` / `.clearreplies` | Delete all auto-reply rules |
| `.متن منشی [text]` / `.sectext` | Set secretary auto-reply text |
| `.تایم منشی [s]` / `.sectime` | Set secretary cooldown (seconds) |
| `.اسپم [n] [msg]` / `.spam` | Send message n times (max 100) |
| `.اسپم سریع [n] [msg]` | Spam with 0.3s delay |
| `.اسپم آرام [n] [msg]` | Spam with 3s delay |
| `.پایان اسپم` / `.stopspam` | Stop ongoing spam |
| `.ویس [text]` / `.voice` | Convert text to voice note (gTTS, auto-detects fa/en) |
| `.ویس` (reply) | Convert replied-to text message to voice |
| `.متن` / `.totext` / `.stt` | Transcribe replied-to voice note (Groq Whisper large-v3) |
| `.هوش [q]` / `.ai` | Ask AI a question (Groq Llama 3.3 70B) |
| `.ترجمه [text]` / `.translate` | Translate text to Persian (MyMemory free API) |
| `.قیمت` / `.price` | Crypto prices in Toman (Nobitex API) |
| `.ساعت` / `.تاریخ` / `.time` | Current time + Jalali (Shamsi) date in Tehran |
| `.پینگ` / `.ping` | Round-trip latency to Telegram |
| `.حساب [expr]` / `.calc` | Evaluate a math expression safely |
| `.پسورد [n]` / `.password` | Generate random n-char password (sent to Saved Messages) |
| `.کوتاه [url]` / `.short` | Shorten a URL via TinyURL |
| `.شانس` / `.luck` | Random luck message (just for fun) |
| `.تاس [n]` / `.dice` | Send dice, retry until value = n |
| `.دارت [n]` / `.dart` | Same for dart emoji |
| `.بسکتبال [n]` / `.basketball` | Same for basketball |
| `.فوتبال [n]` / `.football` | Same for football |
| `.بولینگ [n]` / `.bowling` | Same for bowling |
| `.اسلات [n]` / `.slot` | Same for slot machine |
| `.افزودن‌کلیک @bot n \| pattern` / `.addclick` | Add auto-clicker rule |
| `.لیست‌کلیک` / `.clicklist` | List auto-clicker rules |
| `.حذف‌کلیک [id]` / `.delclick` | Delete auto-clicker rule by ID |
| `.دیباگ‌دکمه` / `.debugbuttons` | Reply to a message to print exact button texts |
| `.راهنما` / `.help` | Full command list (sent to Saved Messages) |

### Auto-reply logic (incoming message handler)

When `ar_on == "1"` for an account, every incoming message is checked against `auto_replies` table. Match type is either `contains` (substring) or `exact`. On match it replies in the same chat.

### Secretary mode (`sec_on`)

When enabled, automatically replies to incoming **DMs** with a configurable message, with a per-sender cooldown to avoid spam.

### Auto-seen (`autoseen`)

When enabled, marks every incoming message as read via `client.send_read_acknowledge`.

### Text-format mode (`fmt_*`)

When any format flag is active (bold, italic, etc.), every outgoing message from that account is intercepted, deleted, and re-sent with the appropriate HTML formatting. Uses `fmt_skip` set as a loop guard so the re-sent message doesn't trigger the handler again.

---

## autoclicker.py

Watches **incoming** messages for inline buttons. When a message arrives from a bot whose username matches a `click_rules` entry, it waits `delay_sec` seconds then clicks the matching button.

**Pattern matching:** Case-insensitive Unicode-normalized substring match (`unicodedata.normalize("NFKC")`). Use `.دیباگ‌دکمه` to print the exact button text before creating a rule.

**`remaining` field:** `-1` = unlimited. Positive = countdown; rule deactivated when it hits 0.

---

## panel.py

The Telegram inline-button UI. Requires a helper bot (BOT_TOKEN) to send messages with buttons — Telethon userbot clients can't send inline keyboards.

**Security:** Every callback checks `event.sender_id == acc.user_id`. If anyone else clicks the panel buttons (e.g. in a group), they get silently rejected.

**Phone encoding:** `+` in phone numbers can't be in Telegram callback data, so `+` is encoded as `P` via `_enc`/`_dec`.

**Subpanels:** Each feature has its own `_sub_*` function that returns `(text, keyboard)`. Toggles call `db.toggle()` and immediately re-render the panel.

---

## web.py

FastAPI app served on `0.0.0.0:5000`.

### REST API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serves `dashboard.html` |
| GET | `/api/accounts` | List all accounts with stats |
| POST | `/api/login/code` | Send SMS verification code |
| POST | `/api/login/verify` | Verify code (returns `need2fa: true` if 2FA) |
| POST | `/api/login/2fa` | Complete 2FA login |
| DELETE | `/api/accounts/{phone}` | Remove account (phone uses `-` instead of `+`) |
| GET | `/api/tasks` | List active scheduled sends |
| DELETE | `/api/tasks/{phone}/{chat_id}` | Stop a scheduled send |
| GET | `/api/banners` | List active banners |
| DELETE | `/api/banners/{id}` | Stop a banner |
| GET | `/api/replies` | List auto-reply rules |
| DELETE | `/api/replies/{id}` | Delete an auto-reply rule |
| GET | `/api/clicks` | List auto-clicker rules |
| DELETE | `/api/clicks/{id}` | Deactivate auto-clicker rule |
| POST | `/api/git/push` | Commit all changes and push to GitHub |

**Note:** Phone numbers in URL paths replace `+` with `-` to avoid URL encoding issues.

---

## db.py

SQLite database at `userbot.db` (WAL mode enabled).

### Tables

**`accounts`** — one row per added Telegram account
- `phone` (PK), `name`, `username`, `active`

**`auto_replies`** — auto-reply keyword rules
- `id`, `phone`, `keyword`, `reply`, `enabled`

**`banners`** — recurring forward/copy tasks
- `id`, `phone`, `chat_id`, `source_chat`, `msg_id`, `interval_sec`, `mode` (copy/fwd), `active`

**`sends`** — recurring text sends
- `id`, `phone`, `chat_id`, `message`, `interval_sec`, `active`

**`settings`** — per-account key-value flags
- `(phone, key)` PK, `value` (always stored as string)
- Keys: `ar_on`, `ar_type`, `sec_on`, `sec_msg`, `sec_time`, `autoseen`, `fmt_bold`, `fmt_italic`, `fmt_underline`, `fmt_strike`, `fmt_mono`, `fmt_spoiler`, `fmt_quote`

**`config`** — global key-value store (currently unused, reserved)

**`click_rules`** — auto-clicker rules
- `id`, `phone`, `bot_username`, `pattern`, `remaining`, `delay_sec`, `active`

### Helper functions

- `conn()` — returns a new connection with `row_factory = sqlite3.Row` (access columns by name)
- `get(phone, key, default)` — read a setting
- `put(phone, key, value)` — write a setting
- `toggle(phone, key)` — flip "0"/"1", returns new value
- `get_config(key)` / `set_config(key, value)` — global config table

---

## dashboard.html

Single-file SPA (no framework, vanilla JS). Tabs: Accounts, Scheduled Sends, Banners, Auto-Replies, Auto-Clicker, Add Account.

- Polls `/api/accounts` every 15 seconds
- **Push to GitHub** button (top-right) calls `POST /api/git/push` — commits and force-pushes to `origin main`
- Add Account tab implements the 3-step login flow (phone → code → optional 2FA)

---

## Environment Variables / Secrets

All stored in Replit Secrets (never in code or `.env` committed to git).

| Secret | Required | Purpose |
|--------|----------|---------|
| `API_ID` | ✅ | Telegram app ID from my.telegram.org |
| `API_HASH` | ✅ | Telegram app hash from my.telegram.org |
| `BOT_TOKEN` | ✅ | @BotFather token for the helper bot (inline panel) |
| `GROQ_API_KEY` | Optional | Enables `.ai` (Llama 3.3 70B) and `.متن` (Whisper STT). Free at console.groq.com |
| `GITHUB_TOKEN` | Optional | GitHub PAT for the "Push to GitHub" dashboard button |

---

## Sessions

Telethon session files live in `sessions/` directory:
- `sessions/{phone_without_plus}.session` — one per user account
- `sessions/helperbot.session` — for the helper bot

**Do not delete `.session` files** — they contain the authenticated session. Deleting one forces re-login.

**`-journal` files** are SQLite crash artifacts. They are automatically deleted at startup (`main.py` top-level glob). If the bot crashes mid-write they can be safely deleted manually too.

---

## External APIs Used

| API | Used for | Auth |
|-----|----------|------|
| Telegram MTProto | All Telegram operations | API_ID + API_HASH + session |
| Telegram Bot API | Inline panel buttons | BOT_TOKEN |
| Groq | `.ai` chat + `.متن` speech-to-text | GROQ_API_KEY |
| gTTS (Google TTS) | `.ویس` text-to-voice | None (unauthenticated) |
| MyMemory | `.ترجمه` translation | None (free tier) |
| Nobitex | `.قیمت` crypto prices | None (public API) |
| TinyURL | `.کوتاه` URL shortener | None |
| GitHub | Dashboard push button | GITHUB_TOKEN |

---

## Common Pitfalls & Design Decisions

1. **`database is locked`** — Happens when Python is killed mid-write and leaves a `-journal` file. Fixed by deleting `sessions/*.session-journal` at startup. Never use threads to access SQLite — always use the async executor pattern.

2. **Blocking calls in async** — All HTTP calls and blocking I/O must be wrapped in `asyncio.get_event_loop().run_in_executor(None, fn)`. Failing to do this freezes the entire bot. gTTS, requests, subprocess calls all need this treatment.

3. **Port encoding in URLs** — Phone numbers have `+` which breaks URL paths. The convention everywhere is to replace `+` with `-` in URL paths and convert back server-side with `.replace("-", "+")`.

4. **Panel security** — `acc.user_id` is set at login time from `get_me()`. The callback handler verifies `event.sender_id == acc.user_id` before processing any button click. This prevents other users in groups from controlling someone else's account.

5. **Multi-account handler isolation** — `register(client, acc, manager)` is called once per account. Each handler closure captures its own `client` and `acc`, so handlers from account A never fire for account B.

6. **`fmt_skip` set** — Text-format mode works by intercepting outgoing messages, deleting them, and re-sending with HTML formatting. Without `fmt_skip`, the re-sent message would trigger the handler again → infinite loop. Before re-sending, add the message ID to `acc.fmt_skip`; the handler checks this set and skips if present, then removes the ID after.

7. **Banner/send persistence** — Both loops write to SQLite before starting the asyncio task. On restart, `manager.load()` calls `_restore_banners` and `_restore_sends` which read the active rows and recreate the tasks. The `active` flag is set to 0 when stopped, not deleted, to preserve history.

8. **Dice/game commands** — Telegram server randomizes dice values, so hitting a target number requires: send → check value → delete if wrong → repeat. This is the only reliable way.

---

## How to Add a New Command

1. Open `commands.py`, inside the `register(client, acc, manager)` function
2. Add a new handler:
```python
@client.on(events.NewMessage(outgoing=True, pattern=r'^\.mycommand(.*)$'))
async def _my_command(event):
    arg = event.pattern_match.group(1).strip()
    await event.delete()
    # your logic here
    await client.send_message(event.chat_id, f"Result: {arg}")
```
3. If it needs a new DB table or setting, add it to `db.py` `init()` and add `get`/`put` calls
4. If it needs a panel subscreen, add `_sub_myfeature(phone)` to `panel.py` and wire it into `kb_menu` and the callback handler

## How to Add a New API Endpoint

1. Open `web.py`
2. Add a route function using FastAPI decorators
3. If it needs a button in the dashboard, add it to `dashboard.html` with a `fetch('/api/your-endpoint')` call
