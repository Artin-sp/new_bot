from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn, db, asyncio, os, subprocess

app = FastAPI()
mgr = None


@app.get("/")
async def root():
    with open("dashboard.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/accounts")
async def accounts():
    return mgr.status()

class PhoneReq(BaseModel):  phone: str
class CodeReq(BaseModel):   phone: str; code: str; pw: str = ""
class TFAReq(BaseModel):    phone: str; pw: str
class ClickReq(BaseModel):  phone: str; bot_username: str; pattern: str; remaining: int = -1; delay_sec: int = 2
class SendReq(BaseModel):   phone: str; chat_id: str; message: str; interval_sec: int = 60
class BannerEdit(BaseModel): chat_id: str; source_chat: str; msg_id: int; interval_sec: int; mode: str = "copy"
class ReplyEdit(BaseModel):  keyword: str; reply: str; enabled: bool = True
class ClickEdit(BaseModel):  bot_username: str; pattern: str; remaining: int = -1; delay_sec: int = 2

@app.post("/api/login/code")
async def send_code(r: PhoneReq):
    try: await mgr.begin_login(r.phone); return {"ok": True}
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/login/verify")
async def verify(r: CodeReq):
    try:
        acc = await mgr.finish_login(r.phone, r.code, r.pw)
        return {"ok": True, "name": acc.name}
    except Exception as e:
        if "2FA_REQUIRED" in str(e): return {"ok": False, "need2fa": True}
        raise HTTPException(400, str(e))

@app.post("/api/login/2fa")
async def tfa(r: TFAReq):
    try:
        acc = await mgr.finish_2fa(r.phone, r.pw)
        return {"ok": True, "name": acc.name}
    except Exception as e: raise HTTPException(400, str(e))

@app.delete("/api/accounts/{phone}")
async def remove(phone: str):
    await mgr.remove(phone.replace("-","+")); return {"ok": True}

# ── Scheduled sends — now reads from the persisted `sends` table ─────
@app.get("/api/tasks")
async def tasks():
    c = db.conn()
    rows = c.execute("SELECT * FROM sends WHERE active=1 ORDER BY id DESC").fetchall()
    c.close()
    out = []
    for r in rows:
        acc = mgr.accs.get(r["phone"])
        out.append({"id": r["id"], "phone": r["phone"], "name": acc.name if acc else r["phone"],
                    "chat_id": r["chat_id"], "message": r["message"],
                    "interval_sec": r["interval_sec"]})
    return out

@app.put("/api/tasks/{tid}")
async def edit_task(tid: int, r: SendReq):
    if r.phone not in mgr.accs:
        raise HTTPException(400, "Account not connected")
    chat = r.chat_id.strip()
    if not chat:
        raise HTTPException(400, "Chat ID is required")
    try:
        await mgr.edit_send(mgr.accs[r.phone], tid, chat, r.message, max(10, r.interval_sec))
    except Exception as e:
        raise HTTPException(404, str(e))
    return {"ok": True}

@app.post("/api/tasks")
async def add_task(r: SendReq):
    phone = r.phone
    if phone not in mgr.accs:
        raise HTTPException(400, "Account not connected")
    chat = r.chat_id.strip()
    if not chat:
        raise HTTPException(400, "Chat ID is required")
    await mgr.start_send(mgr.accs[phone], chat, r.message, max(10, r.interval_sec))
    return {"ok": True}

@app.delete("/api/tasks/{phone}/{chat_id}")
async def stop_task(phone: str, chat_id: str):
    phone = phone.replace("-","+")
    acc = mgr.accs.get(phone)
    if acc: await mgr.stop_send(acc, chat_id)
    return {"ok": True}

@app.get("/api/banners")
async def banners():
    c = db.conn()
    rows = c.execute("SELECT * FROM banners WHERE active=1 ORDER BY id DESC").fetchall()
    c.close(); return [dict(r) for r in rows]

@app.put("/api/banners/{bid}")
async def edit_banner(bid: int, r: BannerEdit):
    c = db.conn()
    row = c.execute("SELECT phone FROM banners WHERE id=?", (bid,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "Banner not found")
    acc = mgr.accs.get(row["phone"])
    if not acc:
        raise HTTPException(400, "Account not connected")
    await mgr.edit_banner(acc, bid, r.chat_id.strip(), r.source_chat.strip(), r.msg_id, max(10, r.interval_sec), r.mode)
    return {"ok": True}

@app.delete("/api/banners/{bid}")
async def del_banner(bid: int):
    c = db.conn()
    row = c.execute("SELECT phone FROM banners WHERE id=?",(bid,)).fetchone()
    if row:
        c.execute("UPDATE banners SET active=0 WHERE id=?",(bid,)); c.commit()
        acc = mgr.accs.get(row["phone"])
        if acc:
            key = f"banner:{bid}"
            if key in acc.tasks: acc.tasks[key].cancel(); del acc.tasks[key]
    c.close(); return {"ok": True}

# ── Auto-replies — fixed: was querying nonexistent table "replies" ───
@app.get("/api/replies")
async def replies():
    c = db.conn()
    rows = c.execute("SELECT * FROM auto_replies ORDER BY id DESC").fetchall()
    c.close(); return [dict(r) for r in rows]

@app.put("/api/replies/{rid}")
async def edit_reply(rid: int, r: ReplyEdit):
    c = db.conn()
    row = c.execute("SELECT id FROM auto_replies WHERE id=?", (rid,)).fetchone()
    if not row:
        c.close(); raise HTTPException(404, "Reply rule not found")
    c.execute("UPDATE auto_replies SET keyword=?, reply=?, enabled=? WHERE id=?",
              (r.keyword.strip(), r.reply, 1 if r.enabled else 0, rid))
    c.commit(); c.close(); return {"ok": True}

@app.delete("/api/replies/{rid}")
async def del_reply(rid: int):
    c = db.conn(); c.execute("DELETE FROM auto_replies WHERE id=?",(rid,))
    c.commit(); c.close(); return {"ok": True}

# ── Autoclicker rules ──────────────────────────────────────────────
@app.get("/api/clicks")
async def clicks():
    c = db.conn()
    rows = c.execute("SELECT * FROM click_rules WHERE active=1 ORDER BY id DESC").fetchall()
    c.close(); return [dict(r) for r in rows]

@app.post("/api/clicks")
async def add_click(r: ClickReq):
    phone = r.phone
    if phone not in mgr.accs:
        raise HTTPException(400, "Account not connected")
    botname = r.bot_username.lstrip("@").lower().strip()
    if not botname:
        raise HTTPException(400, "Bot username is required")
    c   = db.conn()
    cur = c.execute(
        "INSERT INTO click_rules(phone, bot_username, pattern, remaining, delay_sec)"
        " VALUES(?,?,?,?,?)",
        (phone, botname, r.pattern.strip(), r.remaining, max(1, r.delay_sec))
    )
    rule_id = cur.lastrowid; c.commit(); c.close()
    return {"ok": True, "id": rule_id}

@app.put("/api/clicks/{cid}")
async def edit_click(cid: int, r: ClickEdit):
    c = db.conn()
    row = c.execute("SELECT id FROM click_rules WHERE id=?", (cid,)).fetchone()
    if not row:
        c.close(); raise HTTPException(404, "Rule not found")
    botname = r.bot_username.lstrip("@").lower().strip()
    if not botname:
        c.close(); raise HTTPException(400, "Bot username is required")
    c.execute(
        "UPDATE click_rules SET bot_username=?, pattern=?, remaining=?, delay_sec=? WHERE id=?",
        (botname, r.pattern.strip(), r.remaining, max(1, r.delay_sec), cid))
    c.commit(); c.close(); return {"ok": True}

@app.delete("/api/clicks/{cid}")
async def del_click(cid: int):
    c = db.conn(); c.execute("UPDATE click_rules SET active=0 WHERE id=?",(cid,))
    c.commit(); c.close(); return {"ok": True}

# ── GitHub push ────────────────────────────────────────────────────
@app.post("/api/git/push")
async def git_push():
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise HTTPException(400, "GITHUB_TOKEN secret is not set")
    def _push():
        remote_url = f"https://{token}@github.com/Artin-sp/new_bot.git"
        cmds = [
            ["git", "config", "user.email", "bot@replit.com"],
            ["git", "config", "user.name", "Replit Bot"],
            ["git", "add", "-A"],
            ["git", "commit", "-m", "Auto-push from dashboard", "--allow-empty"],
            ["git", "push", remote_url, "HEAD:main", "--force"],
        ]
        log = []
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd="/home/runner/workspace")
            log.append((r.stdout + r.stderr).strip())
        return "\n".join(l for l in log if l)
    try:
        out = await asyncio.get_event_loop().run_in_executor(None, _push)
        return {"ok": True, "log": out}
    except Exception as e:
        raise HTTPException(500, str(e))

async def start():
    config = uvicorn.Config(app, host="0.0.0.0", port=5000, log_level="warning")
    await uvicorn.Server(config).serve()
