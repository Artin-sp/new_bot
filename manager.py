import asyncio, os
from telethon import TelegramClient
from telethon.errors import FloodWaitError
import db

API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
os.makedirs("sessions", exist_ok=True)


class Acc:
    def __init__(self, phone, client):
        self.phone    = phone
        self.client   = client
        self.name     = ""
        self.username = ""
        self.user_id  = None
        self.tasks:    dict[str, asyncio.Task] = {}
        self.dm_last:  dict[int, float]        = {}
        self.fmt_skip: set[int]                = set()


class Manager:
    def __init__(self):
        self.accs:     dict[str, Acc] = {}
        self._pending: dict           = {}

    # ── Startup ──────────────────────────────────────────────────
    async def load(self):
        c = db.conn()
        rows = c.execute("SELECT phone FROM accounts WHERE active=1").fetchall()
        c.close()
        for r in rows:
            try:
                await self.connect(r["phone"])
                print(f"  ✅ {r['phone']}")
            except Exception as e:
                print(f"  ❌ {r['phone']}: {e}")

    async def connect(self, phone: str) -> Acc:
        if phone in self.accs:
            raise Exception("این حساب از قبل متصله")

        path   = f"sessions/{phone.replace('+', '')}"
        client = TelegramClient(path, API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise Exception("session نیست — باید دوباره لاگین کنی")

        me  = await client.get_me()
        acc = Acc(phone, client)
        acc.name     = me.first_name or ""
        acc.username = me.username   or ""
        acc.user_id  = me.id

        from commands import register
        register(client, acc, self)

        try:
            import autoclicker
            autoclicker.register(client, acc, self)
        except Exception as e:
            print(f"[autoclicker] {e}")

        asyncio.create_task(client.run_until_disconnected())

        await self._restore_banners(acc)
        await self._restore_sends(acc)
        await self._restore_ghost(acc)
        asyncio.create_task(self._spy_loop(acc))

        self.accs[phone] = acc

        c = db.conn()
        c.execute(
            "INSERT OR REPLACE INTO accounts(phone,name,username) VALUES(?,?,?)",
            (phone, acc.name, acc.username))
        c.commit(); c.close()
        return acc

    # ── Banners (تیچی) — fixed from_peer ─────────────────────────
    async def _restore_banners(self, acc: Acc):
        c = db.conn()
        rows = c.execute(
            "SELECT * FROM banners WHERE phone=? AND active=1", (acc.phone,)
        ).fetchall()
        c.close()
        for r in rows:
            t = asyncio.create_task(self._banner_loop(
                acc, r["chat_id"], r["source_chat"],
                r["msg_id"], r["interval_sec"], r["mode"]))
            acc.tasks[f"banner:{r['id']}"] = t

    async def _banner_loop(self, acc, chat_id, source_chat, msg_id, interval, mode):
        while True:
            try:
                if mode == "fwd":
                    await acc.client.forward_messages(
                        int(chat_id), msg_id,
                        from_peer=int(source_chat))          # ← FIXED keyword arg
                else:
                    msg = await acc.client.get_messages(int(source_chat), ids=msg_id)
                    if msg:
                        await acc.client.send_message(
                            int(chat_id), msg.text or "",
                            file=msg.media if msg.media else None)
            except Exception as e:
                print(f"[banner] {e}")
            await asyncio.sleep(interval)

    async def add_banner(self, acc, chat_id, source_chat, msg_id, interval, mode="copy"):
        c = db.conn()
        c.execute(
            "INSERT INTO banners(phone,chat_id,source_chat,msg_id,interval_sec,mode)"
            " VALUES(?,?,?,?,?,?)",
            (acc.phone, str(chat_id), str(source_chat), msg_id, interval, mode))
        row_id = c.lastrowid; c.commit(); c.close()
        t = asyncio.create_task(
            self._banner_loop(acc, str(chat_id), str(source_chat), msg_id, interval, mode))
        acc.tasks[f"banner:{row_id}"] = t

    async def edit_banner(self, acc, bid: int, chat_id, source_chat, msg_id, interval, mode):
        key = f"banner:{bid}"
        if key in acc.tasks:
            acc.tasks[key].cancel(); del acc.tasks[key]
        c = db.conn()
        c.execute(
            "UPDATE banners SET chat_id=?, source_chat=?, msg_id=?, interval_sec=?, mode=? WHERE id=?",
            (str(chat_id), str(source_chat), msg_id, interval, mode, bid))
        c.commit(); c.close()
        t = asyncio.create_task(
            self._banner_loop(acc, str(chat_id), str(source_chat), msg_id, interval, mode))
        acc.tasks[key] = t

    async def clear_banners(self, acc, chat_id=None):
        c = db.conn()
        if chat_id:
            rows = c.execute(
                "SELECT id FROM banners WHERE phone=? AND chat_id=? AND active=1",
                (acc.phone, str(chat_id))).fetchall()
            c.execute("UPDATE banners SET active=0 WHERE phone=? AND chat_id=?",
                      (acc.phone, str(chat_id)))
        else:
            rows = c.execute(
                "SELECT id FROM banners WHERE phone=? AND active=1", (acc.phone,)
            ).fetchall()
            c.execute("UPDATE banners SET active=0 WHERE phone=?", (acc.phone,))
        c.commit(); c.close()
        for r in rows:
            key = f"banner:{r['id']}"
            if key in acc.tasks:
                acc.tasks[key].cancel(); del acc.tasks[key]

    # ── Sends — unique key per send (multiple per chat) ───────────
    async def _restore_sends(self, acc: Acc):
        c = db.conn()
        rows = c.execute(
            "SELECT * FROM sends WHERE phone=? AND active=1", (acc.phone,)
        ).fetchall()
        c.close()
        for r in rows:
            t = asyncio.create_task(
                self._send_loop(acc, r["id"], r["chat_id"], r["message"], r["interval_sec"]))
            acc.tasks[f"text:{r['chat_id']}:{r['id']}"] = t   # unique key

    async def _send_loop(self, acc, db_id, chat_id, text, secs):
        while True:
            c = db.conn()
            row = c.execute("SELECT active FROM sends WHERE id=?", (db_id,)).fetchone()
            c.close()
            if not row or not row["active"]:
                break
            try:
                await acc.client.send_message(int(chat_id), text)
            except Exception as e:
                print(f"[send] {e}")
            await asyncio.sleep(secs)

    async def start_send(self, acc, chat_id: str, text: str, secs: int) -> int:
        c = db.conn()
        c.execute(
            "INSERT INTO sends(phone,chat_id,message,interval_sec) VALUES(?,?,?,?)",
            (acc.phone, str(chat_id), text, secs))
        row_id = c.lastrowid; c.commit(); c.close()
        t = asyncio.create_task(self._send_loop(acc, row_id, str(chat_id), text, secs))
        acc.tasks[f"text:{chat_id}:{row_id}"] = t
        return row_id

    async def edit_send(self, acc, send_id: int, chat_id: str, text: str, secs: int):
        c = db.conn()
        row = c.execute(
            "SELECT id FROM sends WHERE id=? AND phone=? AND active=1", (send_id, acc.phone)
        ).fetchone()
        if not row:
            c.close()
            raise Exception("Send not found for this account")
        old_keys = [k for k in list(acc.tasks) if k.endswith(f":{send_id}") and k.startswith("text:")]
        for k in old_keys:
            acc.tasks[k].cancel(); del acc.tasks[k]
        c.execute(
            "UPDATE sends SET chat_id=?, message=?, interval_sec=? WHERE id=? AND phone=?",
            (str(chat_id), text, secs, send_id, acc.phone))
        c.commit(); c.close()
        t = asyncio.create_task(self._send_loop(acc, send_id, str(chat_id), text, secs))
        acc.tasks[f"text:{chat_id}:{send_id}"] = t

    async def stop_send(self, acc, chat_id: str):
        keys = [k for k in list(acc.tasks) if k.startswith(f"text:{chat_id}:")]
        for k in keys:
            acc.tasks[k].cancel(); del acc.tasks[k]
        c = db.conn()
        c.execute("UPDATE sends SET active=0 WHERE phone=? AND chat_id=?",
                  (acc.phone, str(chat_id)))
        c.commit(); c.close()

    async def stop_all(self, acc):
        for t in acc.tasks.values():
            t.cancel()
        acc.tasks.clear()
        c = db.conn()
        c.execute("UPDATE sends SET active=0 WHERE phone=?", (acc.phone,))
        c.commit(); c.close()

    # ── Ghost mode — FIXED: 3s interval, import before loop ───────
    async def _restore_ghost(self, acc: Acc):
        if db.get(acc.phone, "ghost") == "1":
            acc.tasks["ghost"] = asyncio.create_task(self._ghost_loop(acc))

    async def _ghost_loop(self, acc: Acc):
        # Import ONCE before the loop — not inside it
        from telethon.tl.functions.account import UpdateStatusRequest
        while True:
            if db.get(acc.phone, "ghost") != "1":
                break
            try:
                await acc.client(UpdateStatusRequest(offline=True))
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 30))
            except Exception as e:
                print(f"[ghost] {e}")
            await asyncio.sleep(3)   # 3s instead of 5s

    async def start_ghost(self, acc: Acc):
        db.put(acc.phone, "ghost", "1")
        if "ghost" in acc.tasks:
            acc.tasks["ghost"].cancel()
        acc.tasks["ghost"] = asyncio.create_task(self._ghost_loop(acc))

    async def stop_ghost(self, acc: Acc):
        db.put(acc.phone, "ghost", "0")
        if "ghost" in acc.tasks:
            acc.tasks["ghost"].cancel()
            del acc.tasks["ghost"]
        try:
            from telethon.tl.functions.account import UpdateStatusRequest
            await acc.client(UpdateStatusRequest(offline=False))
        except Exception:
            pass

    # ── Profile spy loop (every 5 min) ───────────────────────────
    async def _spy_loop(self, acc: Acc):
        while True:
            await asyncio.sleep(300)
            c = db.conn()
            rows = c.execute(
                "SELECT * FROM profile_spy WHERE phone=?", (acc.phone,)
            ).fetchall()
            c.close()
            for r in rows:
                try:
                    await self._check_profile(acc, dict(r))
                except Exception as e:
                    print(f"[spy] {r['user_id']}: {e}")

    async def _check_profile(self, acc: Acc, r: dict):
        from telethon.tl.functions.users import GetFullUserRequest
        entity  = await acc.client.get_entity(int(r["user_id"]))
        changes = []

        cur_name = (
            (getattr(entity, "first_name", "") or "") + " " +
            (getattr(entity, "last_name",  "") or "")
        ).strip()
        if cur_name != r["name"]:
            changes.append(f"نام: `{r['name']}` ← `{cur_name}`")
            c = db.conn()
            c.execute("UPDATE profile_spy SET name=? WHERE phone=? AND user_id=?",
                      (cur_name, acc.phone, r["user_id"]))
            c.commit(); c.close()

        cur_uname = getattr(entity, "username", "") or ""
        if cur_uname != r["username"]:
            changes.append(f"یوزرنیم: `@{r['username']}` ← `@{cur_uname}`")
            c = db.conn()
            c.execute("UPDATE profile_spy SET username=? WHERE phone=? AND user_id=?",
                      (cur_uname, acc.phone, r["user_id"]))
            c.commit(); c.close()

        photos    = await acc.client.get_profile_photos(entity, limit=1)
        cur_photo = str(photos[0].id) if photos else "none"
        if cur_photo != r["photo_hash"]:
            changes.append("عکس پروفایل عوض شد 📸")
            c = db.conn()
            c.execute("UPDATE profile_spy SET photo_hash=? WHERE phone=? AND user_id=?",
                      (cur_photo, acc.phone, r["user_id"]))
            c.commit(); c.close()

        try:
            full    = await acc.client(GetFullUserRequest(entity))
            cur_bio = getattr(full.full_user, "about", "") or ""
            if cur_bio != r["bio"]:
                changes.append(
                    f"بیو تغییر کرد ✏️\nقبلاً: `{r['bio'] or '—'}`\nالان: `{cur_bio or '—'}`")
                c = db.conn()
                c.execute("UPDATE profile_spy SET bio=? WHERE phone=? AND user_id=?",
                          (cur_bio, acc.phone, r["user_id"]))
                c.commit(); c.close()
        except Exception:
            pass

        if changes:
            label = cur_name or f"@{cur_uname}"
            await acc.client.send_message(
                "me",
                f"👁 **پروفایل {label} تغییر کرد:**\n\n" + "\n".join(changes))

    # ── Login — hash persisted to DB (survives Replit restart) ────
    async def begin_login(self, phone: str):
        if phone in self.accs:
            raise Exception("این حساب از قبل متصله")
        path   = f"sessions/{phone.replace('+', '')}"
        client = TelegramClient(path, API_ID, API_HASH)
        await client.connect()
        res = await client.send_code_request(phone)
        self._pending[phone] = {"client": client, "hash": res.phone_code_hash}
        c = db.conn()
        c.execute("INSERT OR REPLACE INTO pending_logins(phone,hash) VALUES(?,?)",
                  (phone, res.phone_code_hash))
        c.commit(); c.close()

    async def finish_login(self, phone: str, code: str, pw: str = "") -> Acc:
        p = self._pending.get(phone)
        if not p:
            # Replit restarted — recover hash from DB
            c = db.conn()
            row = c.execute(
                "SELECT hash FROM pending_logins WHERE phone=?", (phone,)
            ).fetchone()
            c.close()
            if not row:
                raise Exception(
                    "کد منقضی شد یا قبلاً استفاده شده\n"
                    "دوباره روی «Request Code» کلیک کن")
            path   = f"sessions/{phone.replace('+', '')}"
            client = TelegramClient(path, API_ID, API_HASH)
            await client.connect()
            p = {"client": client, "hash": row["hash"]}
        else:
            del self._pending[phone]

        try:
            await p["client"].sign_in(phone, code, phone_code_hash=p["hash"])
        except Exception as e:
            if "SessionPasswordNeeded" in type(e).__name__:
                if not pw:
                    self._pending[phone] = p
                    raise Exception("2FA_REQUIRED")
                await p["client"].sign_in(password=pw)
            else:
                c = db.conn()
                c.execute("DELETE FROM pending_logins WHERE phone=?", (phone,))
                c.commit(); c.close()
                raise

        c = db.conn()
        c.execute("DELETE FROM pending_logins WHERE phone=?", (phone,))
        c.commit(); c.close()
        await p["client"].disconnect()
        return await self.connect(phone)

    async def finish_2fa(self, phone: str, pw: str) -> Acc:
        p = self._pending.pop(phone)
        await p["client"].sign_in(password=pw)
        await p["client"].disconnect()
        c = db.conn()
        c.execute("DELETE FROM pending_logins WHERE phone=?", (phone,))
        c.commit(); c.close()
        return await self.connect(phone)

    async def remove(self, phone: str):
        if phone in self.accs:
            await self.stop_all(self.accs[phone])
            await self.accs[phone].client.disconnect()
            del self.accs[phone]
        c = db.conn()
        c.execute("UPDATE accounts SET active=0 WHERE phone=?", (phone,))
        c.commit(); c.close()

    def status(self) -> list:
        c = db.conn()
        accs = c.execute("SELECT * FROM accounts ORDER BY rowid").fetchall()
        out  = []
        for a in accs:
            ph    = a["phone"]
            bnrs  = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND active=1",
                              (ph,)).fetchone()["n"]
            reps  = c.execute("SELECT COUNT(*) n FROM auto_replies WHERE phone=? AND enabled=1",
                              (ph,)).fetchone()["n"]
            sends = c.execute("SELECT COUNT(*) n FROM sends WHERE phone=? AND active=1",
                              (ph,)).fetchone()["n"]
            out.append({
                "phone": ph, "name": a["name"], "username": a["username"],
                "connected": ph in self.accs, "active": bool(a["active"]),
                "banners": bnrs, "replies": reps, "sends": sends})
        c.close()
        return out
