import asyncio, os
from telethon import TelegramClient
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
        self.user_id  = None                     # Telegram user id of the account owner
        self.tasks:    dict[str, asyncio.Task] = {}   # "text:chatid:dbid" / "banner:id" / "click"
        self.dm_last:  dict[int, float]        = {}   # منشی cooldown
        self.fmt_skip: set[int]                = set()# حالت‌متن loop guard


class Manager:
    def __init__(self):
        self.accs:      dict[str, Acc] = {}
        self._pending:  dict = {}
        self._login_lock = asyncio.Lock()   # serialize begin_login/finish_login

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

    # ── Connect (with duplicate-connection guard) ───────────────────
    async def connect(self, phone: str) -> Acc:
        if phone in self.accs:
            raise Exception("این حساب از قبل متصله — اول حذفش کن")

        path   = f"sessions/{phone.replace('+','')}"
        client = TelegramClient(path, API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise Exception("session نیست — باید دوباره وارد بشی")

        me  = await client.get_me()
        acc = Acc(phone, client)
        acc.name     = me.first_name or ""
        acc.username = me.username   or ""
        acc.user_id  = me.id

        from commands import register
        register(client, acc, self)

        import autoclicker
        autoclicker.register(client, acc, self)

        asyncio.create_task(client.run_until_disconnected())

        await self._restore_banners(acc)
        await self._restore_sends(acc)

        self.accs[phone] = acc

        c = db.conn()
        c.execute("INSERT OR REPLACE INTO accounts(phone,name,username) VALUES(?,?,?)",
                  (phone, acc.name, acc.username))
        c.commit(); c.close()
        return acc

    # ── Banners (تیچی) ───────────────────────────────────────────
    async def _restore_banners(self, acc: Acc):
        c = db.conn()
        rows = c.execute("SELECT * FROM banners WHERE phone=? AND active=1",
                         (acc.phone,)).fetchall()
        c.close()
        for r in rows:
            t = asyncio.create_task(self._banner_loop(
                acc, r["chat_id"], r["source_chat"], r["msg_id"], r["interval_sec"], r["mode"]
            ))
            acc.tasks[f"banner:{r['id']}"] = t

    async def _banner_loop(self, acc, chat_id, source_chat, msg_id, interval, mode):
        while True:
            try:
                if mode == "fwd":
                    await acc.client.forward_messages(int(chat_id), msg_id, int(source_chat))
                else:
                    msg = await acc.client.get_messages(int(source_chat), ids=msg_id)
                    if msg:
                        await acc.client.send_message(int(chat_id), msg.text or "",
                                                      file=msg.media if msg.media else None)
            except Exception as e:
                print(f"[banner] {e}")
            await asyncio.sleep(interval)

    async def add_banner(self, acc, chat_id, source_chat, msg_id, interval, mode="copy"):
        c = db.conn()
        c.execute("INSERT INTO banners(phone,chat_id,source_chat,msg_id,interval_sec,mode)"
                  " VALUES(?,?,?,?,?,?)",
                  (acc.phone, str(chat_id), str(source_chat), msg_id, interval, mode))
        row_id = c.lastrowid; c.commit(); c.close()
        t = asyncio.create_task(
            self._banner_loop(acc, str(chat_id), str(source_chat), msg_id, interval, mode))
        acc.tasks[f"banner:{row_id}"] = t

    async def clear_banners(self, acc, chat_id=None):
        c = db.conn()
        if chat_id:
            rows = c.execute("SELECT id FROM banners WHERE phone=? AND chat_id=? AND active=1",
                             (acc.phone, str(chat_id))).fetchall()
            c.execute("UPDATE banners SET active=0 WHERE phone=? AND chat_id=?",
                      (acc.phone, str(chat_id)))
        else:
            rows = c.execute("SELECT id FROM banners WHERE phone=? AND active=1",
                             (acc.phone,)).fetchall()
            c.execute("UPDATE banners SET active=0 WHERE phone=?", (acc.phone,))
        c.commit(); c.close()
        for r in rows:
            key = f"banner:{r['id']}"
            if key in acc.tasks:
                acc.tasks[key].cancel(); del acc.tasks[key]

    # ── Scheduled text sends (.send) — now persisted to DB ─────────
    async def _restore_sends(self, acc: Acc):
        c = db.conn()
        rows = c.execute("SELECT * FROM sends WHERE phone=? AND active=1",
                         (acc.phone,)).fetchall()
        c.close()
        for r in rows:
            t = asyncio.create_task(
                self._send_loop(acc, r["id"], r["chat_id"], r["message"], r["interval_sec"]))
            acc.tasks[f"text:{r['chat_id']}"] = t

    async def _send_loop(self, acc, db_id, chat_id, text, secs):
        while True:
            try:
                await acc.client.send_message(int(chat_id), text)
            except Exception as e:
                print(f"[send] {e}")
            await asyncio.sleep(secs)

    async def start_send(self, acc, chat_id: str, text: str, secs: int):
        await self.stop_send(acc, chat_id)
        c = db.conn()
        c.execute("INSERT INTO sends(phone,chat_id,message,interval_sec) VALUES(?,?,?,?)",
                  (acc.phone, str(chat_id), text, secs))
        row_id = c.lastrowid; c.commit(); c.close()
        t = asyncio.create_task(self._send_loop(acc, row_id, chat_id, text, secs))
        acc.tasks[f"text:{chat_id}"] = t

    async def stop_send(self, acc, chat_id: str):
        key = f"text:{chat_id}"
        if key in acc.tasks:
            acc.tasks[key].cancel(); del acc.tasks[key]
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

    # ── Login flow (locked to avoid race conditions) ────────────────
    async def begin_login(self, phone: str):
        async with self._login_lock:
            if phone in self.accs:
                raise Exception("این حساب از قبل متصله")
            path   = f"sessions/{phone.replace('+','')}"
            client = TelegramClient(path, API_ID, API_HASH)
            await client.connect()
            res = await client.send_code_request(phone)
            self._pending[phone] = {"client": client, "hash": res.phone_code_hash}

    async def finish_login(self, phone: str, code: str, pw="") -> Acc:
        async with self._login_lock:
            p = self._pending.pop(phone, None)
            if not p:
                raise Exception("کد منقضی شد — دوباره امتحان کن")
            try:
                await p["client"].sign_in(phone, code, phone_code_hash=p["hash"])
            except Exception as e:
                if "SessionPasswordNeeded" in type(e).__name__:
                    if not pw:
                        self._pending[phone] = {**p, "needs2fa": True}
                        raise Exception("2FA_REQUIRED")
                    await p["client"].sign_in(password=pw)
                else:
                    await p["client"].disconnect()
                    raise
            await p["client"].disconnect()
        return await self.connect(phone)

    async def finish_2fa(self, phone: str, pw: str) -> Acc:
        async with self._login_lock:
            p = self._pending.pop(phone)
            await p["client"].sign_in(password=pw)
            await p["client"].disconnect()
        return await self.connect(phone)

    async def remove(self, phone: str):
        if phone in self.accs:
            await self.stop_all(self.accs[phone])
            await self.accs[phone].client.disconnect()
            del self.accs[phone]
        c = db.conn()
        c.execute("UPDATE accounts SET active=0 WHERE phone=?", (phone,))
        c.commit(); c.close()

    # ── Dashboard status ─────────────────────────────────────────
    def status(self) -> list:
        c = db.conn()
        accs = c.execute("SELECT * FROM accounts ORDER BY rowid").fetchall()
        out = []
        for a in accs:
            ph = a["phone"]; state = self.accs.get(ph)
            bnrs = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND active=1",(ph,)).fetchone()["n"]
            reps = c.execute("SELECT COUNT(*) n FROM auto_replies WHERE phone=? AND enabled=1",(ph,)).fetchone()["n"]
            sends = c.execute("SELECT COUNT(*) n FROM sends WHERE phone=? AND active=1",(ph,)).fetchone()["n"]
            out.append({"phone":ph,"name":a["name"],"username":a["username"],
                        "connected":ph in self.accs,"active":bool(a["active"]),
                        "banners":bnrs,"replies":reps,"sends":sends})
        c.close()
        return out
