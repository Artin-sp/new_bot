from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn, db

app = FastAPI()
mgr = None


@app.get("/")
async def root():
    with open("dashboard.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/accounts")
async def accounts():
    return mgr.status()

class PhoneReq(BaseModel): phone: str
class CodeReq(BaseModel):  phone: str; code: str; pw: str = ""
class TFAReq(BaseModel):   phone: str; pw: str

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
        out.append({"phone": r["phone"], "name": acc.name if acc else r["phone"],
                    "chat_id": r["chat_id"], "message": r["message"],
                    "interval_sec": r["interval_sec"]})
    return out

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

@app.delete("/api/clicks/{cid}")
async def del_click(cid: int):
    c = db.conn(); c.execute("UPDATE click_rules SET active=0 WHERE id=?",(cid,))
    c.commit(); c.close(); return {"ok": True}

async def start():
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning")
    await uvicorn.Server(config).serve()
