import asyncio, os, random, time, tempfile, secrets, string
import html as _html
from datetime import datetime, timezone, timedelta
from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaDice, MessageMediaPhoto, MessageMediaDocument
import db

TEHRAN = timezone(timedelta(hours=3, minutes=30))
DICE   = {"تاس":"🎲","dice":"🎲","دارت":"🎯","dart":"🎯",
          "بسکتبال":"🏀","basketball":"🏀","فوتبال":"⚽","football":"⚽",
          "بولینگ":"🎳","bowling":"🎳","اسلات":"🎰","slot":"🎰"}
GAME_MAX = {"🎲":6,"🎯":6,"🏀":5,"⚽":5,"🎳":6,"🎰":64}
_spam_stop: set[str] = set()

LUCK_MSGS = [
    "امروز روز خوبیه برای شروع یه کار جدید 🌟",
    "یکم احتیاط کن، ولی زیاد هم نگران نباش 🍀",
    "صبور باش، نتیجه میگیری 🌙",
    "روز پرانرژی‌ایه، ازش استفاده کن ⚡",
    "یه خبر خوب در راهه 📬",
    "امروز روز خوبیه برای تصمیم‌های مهم ✅",
    "امروز یکم استراحت بیشتری بکن 😌",
]

# edge_tts voice map: (lang, gender) → voice name
VOICE_MAP = {
    ("fa",    "f"): "fa-IR-DilaraNeural",
    ("fa",    "m"): "fa-IR-FaridNeural",
    ("en",    "f"): "en-US-JennyNeural",
    ("en",    "m"): "en-US-GuyNeural",
    ("en-gb", "f"): "en-GB-SoniaNeural",
    ("en-gb", "m"): "en-GB-RyanNeural",
    ("en-au", "f"): "en-AU-NatashaNeural",
    ("en-au", "m"): "en-AU-WilliamNeural",
    ("ar",    "f"): "ar-SA-ZariyahNeural",
    ("ar",    "m"): "ar-SA-HamedNeural",
}

# Friendly aliases users type instead of the raw code (e.g. "persian" → "fa")
LANG_ALIASES = {
    "persian": "fa", "farsi": "fa", "فارسی": "fa", "fa-ir": "fa",
    "english": "en", "en-us": "en",
    "arabic": "ar", "عربی": "ar",
    "british": "en-gb", "uk": "en-gb",
    "australian": "en-au", "au": "en-au",
}


def _fmt(text: str, active: dict) -> str:
    t = _html.escape(text)
    if active.get("mono"):      t = f"<code>{t}</code>"
    if active.get("bold"):      t = f"<b>{t}</b>"
    if active.get("italic"):    t = f"<i>{t}</i>"
    if active.get("underline"): t = f"<u>{t}</u>"
    if active.get("strike"):    t = f"<s>{t}</s>"
    if active.get("spoiler"):   t = f"<tg-spoiler>{t}</tg-spoiler>"
    if active.get("quote"):     t = f"<blockquote>{t}</blockquote>"
    return t


def register(client, acc, manager):

    # ══════════════════════════════════════════════════════════════
    #  پنل / panel
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پنل|panel)$'))
    async def _panel(event):
        import panel
        await event.delete()
        await panel.open_panel(event.chat_id, acc.phone, manager)

    # ══════════════════════════════════════════════════════════════
    #  ارسال زمان‌بندی / send
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:send|ارسال) (.+?) (\d+)$'))
    async def _send(event):
        text  = event.pattern_match.group(1).strip()
        secs  = int(event.pattern_match.group(2))
        chat  = await event.get_chat()
        title = getattr(chat, 'title', None) or getattr(chat, 'first_name', str(event.chat_id))
        await event.delete()
        rid = await manager.start_send(acc, str(event.chat_id), text, secs)
        await client.send_message("me",
            f"✅ ارسال شروع شد (بعد ری‌استارت هم میمونه)\n"
            f"📍 {title}\n💬 `{text}`\n⏱ هر {secs} ثانیه\n🔢 آیدی: {rid}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:stop|توقف)$'))
    async def _stop(event):
        cid   = str(event.chat_id)
        chat  = await event.get_chat()
        title = getattr(chat, 'title', None) or getattr(chat, 'first_name', cid)
        await event.delete()
        keys = [k for k in acc.tasks if k.startswith(f"text:{cid}:")]
        if keys:
            await manager.stop_send(acc, cid)
            await client.send_message("me", f"⏹ {len(keys)} ارسال در **{title}** متوقف شد")
        else:
            await client.send_message("me", f"⚠️ هیچ ارسالی در {title} فعال نیست")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:stopall|توقف کل)$'))
    async def _stopall(event):
        await event.delete()
        await manager.stop_all(acc)
        await client.send_message("me", "⏹ همه ارسال‌ها متوقف شدن")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:sends|ارسال‌ها)$'))
    async def _list_sends(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM sends WHERE phone=? AND active=1 ORDER BY id",
                         (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ ارسال فعالی نیست"); return
        lines = [f"⏰ **ارسال‌های فعال ({len(rows)} تا):**\n"]
        for r in rows:
            lines.append(f"#{r['id']} — چت `{r['chat_id']}` — هر {r['interval_sec']}ث\n  💬 {r['message'][:40]}")
        await client.send_message("me", "\n".join(lines))

    # ══════════════════════════════════════════════════════════════
    #  تیچی / بنر
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:تنظیم بنر|setbanner) (\d+)(?: (کپی|فور|copy|fwd))?$'))
    async def _set_banner(event):
        if not event.is_reply:
            await event.delete()
            await client.send_message("me", "❌ روی یه پیام ریپلای کن"); return
        interval = int(event.pattern_match.group(1))
        raw_mode = (event.pattern_match.group(2) or "").lower()
        mode     = "fwd" if raw_mode in ("فور", "fwd") else "copy"
        if interval < 10:
            await event.delete()
            await client.send_message("me", "❌ حداقل ۱۰ ثانیه"); return
        c   = db.conn()
        cnt = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND chat_id=? AND active=1",
                        (acc.phone, str(event.chat_id))).fetchone()["n"]
        c.close()
        if cnt >= 10:
            await event.delete()
            await client.send_message("me", "❌ حداکثر ۱۰ بنر در هر چت"); return
        reply = await event.get_reply_message()
        await event.delete()
        await manager.add_banner(acc, event.chat_id, reply.chat_id, reply.id, interval, mode)
        await client.send_message("me",
            f"✅ بنر تنظیم شد\n⏱ هر {interval} ثانیه — {'فوروارد' if mode=='fwd' else 'کپی'}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:لیست بنر|listbanner)$'))
    async def _list_banners(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM banners WHERE phone=? AND active=1 ORDER BY id",
                         (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ بنری فعال نیست"); return
        lines = ["📋 **بنرهای فعال:**\n"]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. چت `{r['chat_id']}` — هر {r['interval_sec']}ث ({r['mode']})")
        await client.send_message("me", "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پاکسازی بنر|clearbanner)$'))
    async def _clear_banners(event):
        await event.delete()
        await manager.clear_banners(acc, str(event.chat_id))
        await client.send_message("me", "♻️ بنرهای این چت پاک شدن")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پاکسازی کل بنر|clearallbanner)$'))
    async def _clear_all_banners(event):
        await event.delete()
        await manager.clear_banners(acc)
        await client.send_message("me", "♻️ همه بنرها پاک شدن")

    # ══════════════════════════════════════════════════════════════
    #  پاسخ خودکار
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:افزودن پاسخ|addreply) (.+?) = (.+)$'))
    async def _add_reply(event):
        kw = event.pattern_match.group(1).strip()
        rp = event.pattern_match.group(2).strip()
        await event.delete()
        c  = db.conn()
        ex = c.execute("SELECT id FROM auto_replies WHERE phone=? AND keyword=?",
                       (acc.phone, kw)).fetchone()
        if ex: c.execute("UPDATE auto_replies SET reply=?,enabled=1 WHERE id=?", (rp, ex["id"]))
        else:  c.execute("INSERT INTO auto_replies(phone,keyword,reply) VALUES(?,?,?)",
                         (acc.phone, kw, rp))
        c.commit(); c.close()
        await client.send_message("me", f"✅ `{kw}` ← {rp}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:حذف پاسخ|delreply) (.+)$'))
    async def _del_reply(event):
        kw = event.pattern_match.group(1).strip()
        await event.delete()
        c  = db.conn()
        c.execute("DELETE FROM auto_replies WHERE phone=? AND keyword=?", (acc.phone, kw))
        c.commit(); c.close()
        await client.send_message("me", f"🗑️ `{kw}` حذف شد")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:لیست پاسخ|listreply)$'))
    async def _list_replies(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM auto_replies WHERE phone=? ORDER BY id",
                         (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ پاسخ خودکاری ندارید"); return
        lines = ["📋 **پاسخ‌های خودکار:**\n"]
        for r in rows:
            lines.append(f"{'✅' if r['enabled'] else '🔴'} `{r['keyword']}` ← {r['reply']}")
        await client.send_message("me", "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پاکسازی پاسخ|clearreply)$'))
    async def _clear_replies(event):
        await event.delete()
        c = db.conn()
        c.execute("DELETE FROM auto_replies WHERE phone=?", (acc.phone,))
        c.commit(); c.close()
        await client.send_message("me", "♻️ همه پاسخ‌ها پاک شدن")

    # ══════════════════════════════════════════════════════════════
    #  منشی
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:متن منشی|sectext) (.+)$'))
    async def _sec_text(event):
        txt = event.pattern_match.group(1).strip()
        await event.delete()
        db.put(acc.phone, "sec_msg", txt)
        await client.send_message("me", f"✅ متن منشی:\n{txt}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:تایم منشی|sectime) (\d+)$'))
    async def _sec_time(event):
        t = event.pattern_match.group(1)
        await event.delete()
        db.put(acc.phone, "sec_time", t)
        await client.send_message("me", f"✅ تایم منشی: {t} ثانیه")

    # ══════════════════════════════════════════════════════════════
    #  اسپم
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:اسپم|spam)(?: (سریع|آرام|fast|slow))? (\d+) (.+)$'))
    async def _spam(event):
        raw   = (event.pattern_match.group(1) or "").lower()
        count = min(int(event.pattern_match.group(2)), 100)
        text  = event.pattern_match.group(3).strip()
        cid   = event.chat_id
        await event.delete()
        delay = {"سریع":0.3,"fast":0.3,"آرام":2.5,"slow":2.5}.get(raw, 0.8)
        _spam_stop.discard(acc.phone)

        async def _run():
            sent = 0
            for i in range(count):
                if acc.phone in _spam_stop: break
                try:
                    await client.send_message(cid, text); sent += 1
                except Exception as e:
                    print(f"[spam] {e}"); break
                if i < count - 1: await asyncio.sleep(delay)
            _spam_stop.discard(acc.phone)
            await client.send_message("me", f"✅ اسپم تموم شد — {sent} پیام")

        asyncio.create_task(_run())

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پایان اسپم|stopspam)$'))
    async def _stop_spam(event):
        await event.delete()
        _spam_stop.add(acc.phone)
        await client.send_message("me", "⏹ اسپم متوقف شد")

    # ══════════════════════════════════════════════════════════════
    #  👻 ناپدید / ghost
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:ghost|ناپدید) (on|off|روشن|خاموش)$'))
    async def _ghost(event):
        arg = event.pattern_match.group(1).lower()
        on  = arg in ("on", "روشن")
        await event.delete()
        if on:
            await manager.start_ghost(acc)
            await client.send_message("me",
                "👻 **حالت ناپدید: روشن**\n"
                "هر ۳ ثانیه status آفلاین ارسال میشه\n"
                "بعد هر پیام خروجی هم بلافاصله آفلاین ست میشه\n"
                "برای خاموش کردن: `.ghost off`")
        else:
            await manager.stop_ghost(acc)
            await client.send_message("me", "👻 **حالت ناپدید: خاموش**")

    # ══════════════════════════════════════════════════════════════
    #  📥 دانلودر
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:دانلود|dl|download) (.+)$'))
    async def _dl_start(event):
        target = event.pattern_match.group(1).strip()
        await event.delete()
        try:
            entity = await client.get_entity(target)
            cid    = str(entity.id)
            title  = getattr(entity, 'title', None) or getattr(entity, 'username', cid)
        except Exception as e:
            await client.send_message("me", f"❌ چت پیدا نشد: {e}"); return
        c = db.conn()
        c.execute("INSERT OR REPLACE INTO downloads(phone,chat_id,chat_title) VALUES(?,?,?)",
                  (acc.phone, cid, title))
        c.commit(); c.close()
        await client.send_message("me",
            f"📥 **دانلودر روشن شد**\nچت: **{title}**\n"
            f"هر مدیایی که بیاد به Saved Messages فوروارد میشه")

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:پایان دانلود|stopdl|stopdownload)(?:\s+(.+))?$'))
    async def _dl_stop(event):
        target = event.pattern_match.group(1)
        await event.delete()
        c = db.conn()
        if target:
            target = target.strip()
            c.execute("DELETE FROM downloads WHERE phone=? AND (chat_id=? OR chat_title LIKE ?)",
                      (acc.phone, target, f"%{target}%"))
        else:
            c.execute("DELETE FROM downloads WHERE phone=?", (acc.phone,))
        c.commit(); c.close()
        await client.send_message("me", "📥 دانلودر خاموش شد")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:لیست دانلود|listdl)$'))
    async def _dl_list(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM downloads WHERE phone=?", (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ دانلودری فعال نیست"); return
        lines = ["📥 **دانلودرهای فعال:**\n"]
        for r in rows:
            lines.append(f"• {r['chat_title']} (`{r['chat_id']}`)")
        await client.send_message("me", "\n".join(lines))

    # ══════════════════════════════════════════════════════════════
    #  👁 جاسوس پروفایل
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:spy|جاسوس) (@?\S+)$'))
    async def _spy_add(event):
        target = event.pattern_match.group(1).strip()
        await event.delete()
        try:
            from telethon.tl.functions.users import GetFullUserRequest
            entity = await client.get_entity(target)
            uid    = str(entity.id)
            name   = ((getattr(entity, "first_name", "") or "") + " " +
                      (getattr(entity, "last_name",  "") or "")).strip()
            uname  = getattr(entity, "username", "") or ""
            photos = await client.get_profile_photos(entity, limit=1)
            photo  = str(photos[0].id) if photos else "none"
            try:
                full = await client(GetFullUserRequest(entity))
                bio  = getattr(full.full_user, "about", "") or ""
            except Exception:
                bio  = ""
        except Exception as e:
            await client.send_message("me", f"❌ یوزر پیدا نشد: {e}"); return
        c = db.conn()
        c.execute("""INSERT OR REPLACE INTO profile_spy
                     (phone,user_id,username,name,photo_hash,bio)
                     VALUES(?,?,?,?,?,?)""",
                  (acc.phone, uid, uname, name, photo, bio))
        c.commit(); c.close()
        await client.send_message("me",
            f"👁 **جاسوسی شروع شد**\nنام: {name or '—'}\nیوزرنیم: @{uname or '—'}\n\n"
            f"هر ۵ دقیقه چک میشه\nبرای توقف: `.unspy @{uname}`")

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:unspy|پایان جاسوس) (@?\S+)$'))
    async def _spy_remove(event):
        target = event.pattern_match.group(1).strip().lstrip("@")
        await event.delete()
        c = db.conn()
        c.execute("DELETE FROM profile_spy WHERE phone=? AND (username=? OR user_id=?)",
                  (acc.phone, target, target))
        c.commit(); c.close()
        await client.send_message("me", f"👁 جاسوسی @{target} متوقف شد")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:spylist|لیست جاسوس)$'))
    async def _spy_list(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM profile_spy WHERE phone=?", (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ‌کسی رو جاسوسی نمیکنی"); return
        lines = ["👁 **تحت نظر:**\n"]
        for r in rows:
            lines.append(f"• {r['name'] or '—'}  (@{r['username'] or '—'})")
        await client.send_message("me", "\n".join(lines))

    # ══════════════════════════════════════════════════════════════
    #  🎵 موزیک به ویس
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:mv|موزیک ویس|musicvoice)$'))
    async def _music_to_voice(event):
        await event.delete()
        if not event.is_reply:
            await client.send_message("me",
                "❌ روی یه فایل صوتی/موزیک ریپلای کن و `.mv` بزن"); return
        reply = await event.get_reply_message()
        if not (reply.audio or reply.voice or
                (reply.document and reply.document.mime_type and
                 reply.document.mime_type.startswith("audio"))):
            await client.send_message("me", "❌ پیام ریپلای شده فایل صوتی نیست"); return
        tmp = None
        try:
            tmp = await client.download_media(reply)
            if not tmp:
                await client.send_message("me", "❌ دانلود فایل ناموفق بود"); return
            await client.send_file(event.chat_id, tmp, voice_note=True, caption="")
        except Exception as e:
            await client.send_message("me", f"❌ موزیک به ویس: {e}")
        finally:
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass

    # ══════════════════════════════════════════════════════════════
    #  🎙 ویس (TTS) — now uses edge_tts with voice settings
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:ویس|voice)\s+(.+)$'))
    async def _voice_text(event):
        await _tts(event, event.pattern_match.group(1).strip())

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:ویس|voice)$'))
    async def _voice_reply(event):
        if not event.is_reply:
            await event.delete()
            await client.send_message("me",
                "❌ یا متن بده: `.ویس سلام`\nیا روی پیامی ریپلای کن و `.ویس` بزن"); return
        reply = await event.get_reply_message()
        if not reply.text:
            await event.delete()
            await client.send_message("me", "❌ پیام ریپلای شده متن نداره"); return
        await _tts(event, reply.text)

    # تنظیم صدا / voice settings: .ویس‌صدا [lang] [m/f]
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:ویس‌صدا|voiceset) (\S+)\s+(m|f)$'))
    async def _voiceset(event):
        lang   = event.pattern_match.group(1).strip().lower()
        lang   = LANG_ALIASES.get(lang, lang)
        gender = event.pattern_match.group(2).strip().lower()
        await event.delete()
        if (lang, gender) not in VOICE_MAP:
            valid = ", ".join(f"{l} {g}" for l, g in VOICE_MAP)
            await client.send_message("me",
                f"❌ ترکیب نامعتبر\nگزینه‌های معتبر:\n{valid}"); return
        db.put(acc.phone, "tts_lang",   lang)
        db.put(acc.phone, "tts_gender", gender)
        voice = VOICE_MAP[(lang, gender)]
        await client.send_message("me", f"✅ صدا تنظیم شد: `{voice}`")

    async def _tts(event, text):
        await event.delete()
        lang   = db.get(acc.phone, "tts_lang",   "auto")
        gender = db.get(acc.phone, "tts_gender", "f")
        # auto-detect language
        if lang == "auto":
            lang = "fa" if any('\u0600' <= ch <= '\u06FF' for ch in text) else "en"
        voice = VOICE_MAP.get((lang, gender), "fa-IR-DilaraNeural")
        fd = tmp = None
        try:
            import edge_tts
            fd, tmp = tempfile.mkstemp(suffix=".mp3")
            os.close(fd); fd = None
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp)
            await client.send_file(event.chat_id, tmp, voice_note=True, caption="")
        except Exception as e:
            await client.send_message("me", f"❌ ویس: {e}")
        finally:
            if fd is not None:
                try: os.close(fd)
                except: pass
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass

    # ══════════════════════════════════════════════════════════════
    #  📝 تبدیل ویس به متن (STT) — GROQ Whisper
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:متن|totext|stt)$'))
    async def _stt(event):
        await event.delete()
        if not event.is_reply:
            await client.send_message("me", "❌ روی یه پیام صوتی ریپلای کن"); return
        reply = await event.get_reply_message()
        if not (reply.voice or reply.audio):
            await client.send_message("me", "❌ پیامی که ریپلای کردی صوتی نیست"); return
        key = os.getenv("GROQ_API_KEY", "")
        if not key:
            await client.send_message("me",
                "❌ نیاز به GROQ_API_KEY\nرایگان از console.groq.com"); return
        tmp = None
        try:
            import requests
            tmp = await client.download_media(reply)
            if not tmp:
                await client.send_message("me", "❌ دانلود ناموفق"); return
            with open(tmp, "rb") as f:
                res = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": ("audio.ogg", f, "audio/ogg")},
                    data={"model": "whisper-large-v3"},
                    timeout=60)
            res.raise_for_status()
            text = res.json().get("text", "").strip()
            await client.send_message(event.chat_id, f"📝 {text}" if text else "متنی پیدا نشد")
        except Exception as e:
            await client.send_message("me", f"❌ تبدیل به متن: {e}")
        finally:
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass

    # ══════════════════════════════════════════════════════════════
    #  🤖 هوش مصنوعی — GROQ primary, OPENAI fallback
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:هوش|ai) (.+)$'))
    async def _ai(event):
        question = event.pattern_match.group(1).strip()
        await event.delete()

        # Special sub-commands
        if question.startswith("نام "):
            name = question[4:].strip()
            db.put(acc.phone, "ai_name", name)
            await client.send_message("me", f"✅ اسمت ذخیره شد: {name}"); return
        if question.strip() == "ریست":
            db.put(acc.phone, "ai_history", "[]")
            await client.send_message("me", "🧠 حافظه هوش مصنوعی پاک شد"); return

        groq_key  = os.getenv("GROQ_API_KEY", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if not groq_key and not openai_key:
            await client.send_message("me",
                "❌ نیاز به API Key\n\n"
                "**گزینه رایگان (توصیه‌شده):**\n"
                "از console.groq.com کلید بگیر\n"
                "Replit Secrets → GROQ_API_KEY\n\n"
                "**یا OpenAI:**\nReplit Secrets → OPENAI_API_KEY"); return

        import urllib.request, json

        # Load history
        try:
            history = json.loads(db.get(acc.phone, "ai_history", "[]"))
        except Exception:
            history = []

        ai_name = db.get(acc.phone, "ai_name", "")
        system  = (f"You are a helpful assistant"
                   f"{f', talking to {ai_name}' if ai_name else ''}. "
                   f"Reply in the same language as the user. Be concise.")
        messages = [{"role":"system","content":system}] + history + \
                   [{"role":"user","content":question}]

        try:
            if groq_key:
                body = json.dumps({
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages, "max_tokens": 800
                }).encode()
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions", body,
                    {"Content-Type":"application/json",
                     "Authorization":f"Bearer {groq_key}"})
            else:
                body = json.dumps({
                    "model": "gpt-3.5-turbo",
                    "messages": messages, "max_tokens": 800
                }).encode()
                req = urllib.request.Request(
                    "https://api.openai.com/v1/chat/completions", body,
                    {"Content-Type":"application/json",
                     "Authorization":f"Bearer {openai_key}"})

            res    = json.loads(urllib.request.urlopen(req, timeout=30).read())
            answer = res["choices"][0]["message"]["content"].strip()

            # Update history (keep last 10 exchanges = 20 messages)
            history.extend([{"role":"user","content":question},
                            {"role":"assistant","content":answer}])
            if len(history) > 20:
                history = history[-20:]
            db.put(acc.phone, "ai_history", json.dumps(history))

            await client.send_message(event.chat_id, f"🤖 {answer}")
        except Exception as e:
            await client.send_message("me", f"❌ هوش مصنوعی: {e}")

    # ══════════════════════════════════════════════════════════════
    #  ترجمه
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:ترجمه|translate) (.+)$'))
    async def _translate(event):
        text = event.pattern_match.group(1).strip()
        await event.delete()
        try:
            import urllib.request, urllib.parse, json
            url  = ("https://translate.googleapis.com/translate_a/single"
                    f"?client=gtx&sl=auto&tl=fa&dt=t&q={urllib.parse.quote(text)}")
            data = json.loads(urllib.request.urlopen(url, timeout=6).read())
            tr   = "".join(i[0] for i in data[0] if i[0])
            await client.send_message(event.chat_id, f"🌐 {tr}")
        except Exception as e:
            await client.send_message("me", f"❌ ترجمه: {e}")

    # ══════════════════════════════════════════════════════════════
    #  قیمت — Nobitex + CoinGecko fallback
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:قیمت|price)$'))
    async def _price(event):
        await event.delete()
        try:
            import urllib.request, json
            lines = ["💱 **قیمت لحظه‌ای**\n"]
            success = False
            try:
                req = urllib.request.Request(
                    "https://api.nobitex.ir/market/stats",
                    data=json.dumps({"srcCurrency":"usdt,btc,eth,bnb,trx,doge,ltc",
                                     "dstCurrency":"rls"}).encode(),
                    headers={"Content-Type":"application/json",
                             "User-Agent":"Mozilla/5.0 (compatible; Googlebot/2.1)"})
                data  = json.loads(urllib.request.urlopen(req, timeout=10).read())
                stats = data.get("stats", {})
                coins = [("usdt","🟢 تتر"),("btc","₿ بیتکوین"),("eth","⟠ اتریوم"),
                         ("bnb","⬡ بایننس"),("trx","🔺 ترون"),
                         ("doge","🐕 دوج"),("ltc","Ł لایت‌کوین")]
                for code, label in coins:
                    s = stats.get(f"{code}-rls")
                    if not s: continue
                    try:
                        t     = round(float(s.get("latest") or s.get("bestSell") or 0) / 10)
                        chg   = s.get("dayChange", "0")
                        arrow = "📈" if float(chg) >= 0 else "📉"
                        lines.append(f"{label}:  {t:,} تومان  {arrow} {chg}%")
                        success = True
                    except Exception:
                        continue
                if success:
                    lines.insert(1, "منبع: نوبیتکس\n")
            except Exception as e:
                print(f"[price/nobitex] {e}")

            if not success:
                url  = ("https://api.coingecko.com/api/v3/simple/price"
                        "?ids=bitcoin,ethereum,tether,binancecoin,tron,dogecoin,litecoin"
                        "&vs_currencies=irt")
                data = json.loads(urllib.request.urlopen(url, timeout=10).read())
                map_ = [("tether","🟢 تتر"),("bitcoin","₿ بیتکوین"),
                        ("ethereum","⟠ اتریوم"),("binancecoin","⬡ بایننس"),
                        ("tron","🔺 ترون"),("dogecoin","🐕 دوج"),
                        ("litecoin","Ł لایت‌کوین")]
                for cid, label in map_:
                    v = data.get(cid, {}).get("irt")
                    if v:
                        lines.append(f"{label}:  {round(v):,} تومان")
                lines.insert(1, "منبع: CoinGecko\n")

            await client.send_message(event.chat_id, "\n".join(lines))
        except Exception as e:
            await client.send_message("me", f"❌ قیمت: {e}")

    # ══════════════════════════════════════════════════════════════
    #  ساعت + تاریخ
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:ساعت|time|تاریخ|date)$'))
    async def _clock(event):
        await event.delete()
        now  = datetime.now(TEHRAN)
        days = ["دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه","شنبه","یکشنبه"]
        try:
            import jdatetime
            jd = jdatetime.date.fromgregorian(date=now.date())
            jalali = f"{jd.year}/{jd.month:02d}/{jd.day:02d}"
        except Exception:
            jalali = "—"
        await client.send_message(event.chat_id,
            f"🕐 **{now.strftime('%H:%M:%S')}**  —  {days[now.weekday()]}\n"
            f"📅 شمسی: {jalali}\n📅 میلادی: {now.strftime('%Y/%m/%d')}\n"
            f"🌍 به وقت تهران")

    # ══════════════════════════════════════════════════════════════
    #  بینگ
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پینگ|ping)$'))
    async def _ping(event):
        t0  = time.time()
        msg = await event.edit("🏓 ...")
        ms  = round((time.time() - t0) * 1000)
        await msg.edit(f"🏓 پینگ: **{ms}ms**")

    # ══════════════════════════════════════════════════════════════
    #  ماشین‌حساب
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:حساب|calc) (.+)$'))
    async def _calc(event):
        expr = event.pattern_match.group(1).strip()
        await event.delete()
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            await client.send_message(event.chat_id, f"🧮 `{expr}` = **{result}**")
        except:
            await client.send_message("me", "❌ عبارت اشتباهه")

    # ══════════════════════════════════════════════════════════════
    #  پسورد
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:پسورد|password)(?:\s+(\d+))?$'))
    async def _password(event):
        n     = int(event.pattern_match.group(1) or 16)
        n     = max(6, min(n, 64))
        await event.delete()
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pw    = "".join(secrets.choice(chars) for _ in range(n))
        await client.send_message("me", f"🔐 پسورد {n} کاراکتری:\n`{pw}`")

    # ══════════════════════════════════════════════════════════════
    #  کوتاه‌کننده لینک
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:کوتاه|short) (\S+)$'))
    async def _shorten(event):
        url = event.pattern_match.group(1).strip()
        await event.delete()
        try:
            import urllib.request, urllib.parse
            api   = f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(url)}"
            short = urllib.request.urlopen(api, timeout=8).read().decode().strip()
            await client.send_message(event.chat_id, f"🔗 {short}")
        except Exception as e:
            await client.send_message("me", f"❌ کوتاه‌کننده: {e}")

    # ══════════════════════════════════════════════════════════════
    #  شانس
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:شانس|luck)$'))
    async def _luck(event):
        await event.delete()
        pct = random.randint(40, 100)
        await client.send_message(event.chat_id,
            f"🎲 شانس امروزت: **{pct}%**\n{random.choice(LUCK_MSGS)}")

    # ══════════════════════════════════════════════════════════════
    #  بازی‌ها با هدف‌گذاری
    # ══════════════════════════════════════════════════════════════
    DICE_PAT = r'^\.(' + "|".join(DICE.keys()) + r')(?:\s+(\S+))?$'

    @client.on(events.NewMessage(outgoing=True, pattern=DICE_PAT))
    async def _dice(event):
        name  = event.pattern_match.group(1)
        arg   = event.pattern_match.group(2)
        emoji = DICE.get(name)
        if not emoji: return
        maxv  = GAME_MAX[emoji]
        await event.delete()

        target = None
        if arg:
            a = arg.strip().lower()
            if a in ("max","بیشترین"):     target = maxv
            elif a in ("777","jackpot","جکپات"): target = 64
            else:
                try:
                    n = int(a)
                    if 1 <= n <= maxv: target = n
                except ValueError: pass

        chat      = await event.get_input_chat()
        max_tries = 100 if emoji == "🎰" else 30

        for _ in range(max_tries):
            await client(SendMediaRequest(
                peer=chat, media=InputMediaDice(emoticon=emoji),
                message="", random_id=random.randint(1, 2**31)))
            if target is None: return

            msgs = await client.get_messages(event.chat_id, limit=1)
            if not msgs or not msgs[0].media or not hasattr(msgs[0].media, "value"): break
            val = msgs[0].media.value
            if val == target: return

            try:
                await client.delete_messages(event.chat_id, msgs[0].id)
            except FloodWaitError as e:
                if e.seconds <= 15: await asyncio.sleep(e.seconds)
                else:
                    await client.send_message("me",
                        f"⏳ تلگرام محدودیت گذاشته — {e.seconds}ث صبر کن"); return
            except Exception: pass
            await asyncio.sleep(0.5 if emoji != "🎰" else 0.7)

        await client.send_message("me", f"⚠️ بعد از {max_tries} تلاش به {target} نرسید")

    # ══════════════════════════════════════════════════════════════
    #  اتوکلیکر (preserved exactly from repo)
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:افزودن‌کلیک|addclick) (@?\w+) (-?\d+) \| (.+)$'))
    async def _add_click(event):
        botname = event.pattern_match.group(1).lstrip("@").lower()
        count   = int(event.pattern_match.group(2))
        pattern = event.pattern_match.group(3).strip()
        await event.delete()
        c = db.conn()
        c.execute("INSERT INTO click_rules(phone,bot_username,pattern,remaining,delay_sec)"
                  " VALUES(?,?,?,?,?)", (acc.phone, botname, pattern, count, 2))
        c.commit(); c.close()
        lim = "نامحدود" if count < 0 else f"{count} بار"
        await client.send_message("me",
            f"✅ قانون کلیک اضافه شد\n🤖 @{botname}\n🎯 «{pattern}»\n🔁 {lim}")

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:لیست‌کلیک|listclick)$'))
    async def _list_click(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM click_rules WHERE phone=? AND active=1 ORDER BY id",
                         (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ قانون کلیکی نداری"); return
        lines = ["🖱 **قوانین کلیک:**\n"]
        for r in rows:
            rem = "نامحدود" if r["remaining"] < 0 else f"{r['remaining']} بار"
            lines.append(f"#{r['id']} @{r['bot_username']} ← «{r['pattern']}» ({rem})")
        await client.send_message("me", "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:حذف‌کلیک|delclick) (\d+)$'))
    async def _del_click(event):
        rid = int(event.pattern_match.group(1))
        await event.delete()
        c = db.conn()
        c.execute("UPDATE click_rules SET active=0 WHERE id=? AND phone=?", (rid, acc.phone))
        c.commit(); c.close()
        await client.send_message("me", f"🗑️ قانون #{rid} حذف شد")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:دیباگ‌دکمه|debugbuttons)$'))
    async def _debug_btns(event):
        await event.delete()
        if not event.is_reply:
            await client.send_message("me", "❌ روی پیامی که دکمه داره ریپلای کن"); return
        reply = await event.get_reply_message()
        if not reply.buttons:
            await client.send_message("me", "این پیام دکمه نداره"); return
        lines = ["🔍 **متن دقیق دکمه‌ها:**\n"]
        for ri, row in enumerate(reply.buttons):
            for ci, btn in enumerate(row):
                lines.append(f"[{ri},{ci}] `{getattr(btn,'text','')}`")
        sender = await reply.get_sender()
        uname  = getattr(sender, "username", None)
        lines.append(f"\nیوزرنیم: @{uname}" if uname else "\n⚠️ فرستنده یوزرنیم نداره")
        await client.send_message("me", "\n".join(lines))

    # ══════════════════════════════════════════════════════════════
    #  وضعیت
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:status|وضعیت)$'))
    async def _status(event):
        await event.delete()
        c     = db.conn()
        reps  = c.execute("SELECT COUNT(*) n FROM auto_replies WHERE phone=? AND enabled=1",
                          (acc.phone,)).fetchone()["n"]
        bnrs  = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND active=1",
                          (acc.phone,)).fetchone()["n"]
        sends = c.execute("SELECT COUNT(*) n FROM sends WHERE phone=? AND active=1",
                          (acc.phone,)).fetchone()["n"]
        spies = c.execute("SELECT COUNT(*) n FROM profile_spy WHERE phone=?",
                          (acc.phone,)).fetchone()["n"]
        dls   = c.execute("SELECT COUNT(*) n FROM downloads WHERE phone=?",
                          (acc.phone,)).fetchone()["n"]
        clicks= c.execute("SELECT COUNT(*) n FROM click_rules WHERE phone=? AND active=1",
                          (acc.phone,)).fetchone()["n"]
        c.close()
        keys  = ["bold","italic","underline","strike","mono","spoiler","quote"]
        fmts  = [k for k in keys if db.get(acc.phone, f"fmt_{k}") == "1"]
        ghost = db.get(acc.phone, "ghost") == "1"
        saver = db.get(acc.phone, "save_expiring") == "1"
        voice = VOICE_MAP.get(
            (db.get(acc.phone,"tts_lang","auto"), db.get(acc.phone,"tts_gender","f")),
            "fa-IR-DilaraNeural")
        await client.send_message("me",
            f"📊 **{acc.name}**  (`{acc.phone}`)\n\n"
            f"👻 ناپدید:         {'✅' if ghost else '🔴'}\n"
            f"🔒 ذخیره‌پیام:    {'✅' if saver else '🔴'}\n"
            f"📩 منشی:           {'✅' if db.get(acc.phone,'sec_on')=='1' else '🔴'}\n"
            f"💬 پاسخ‌خودکار:   {'✅' if db.get(acc.phone,'ar_on')=='1' else '🔴'}  ({reps})\n"
            f"👁 جاسوس‌ها:      {spies}\n"
            f"📥 دانلودرها:     {dls}\n"
            f"⏰ ارسال‌های فعال: {sends}\n"
            f"📌 بنرهای فعال:   {bnrs}\n"
            f"🖱 قوانین کلیک:   {clicks}\n"
            f"🎙 صدای TTS:      `{voice}`\n"
            f"✏️ حالت‌متن:      {', '.join(fmts) or 'خاموش'}")

    # ══════════════════════════════════════════════════════════════
    #  راهنما
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:راهنما|help)$'))
    async def _help(event):
        await event.delete()
        await client.send_message("me",
            "📋 **دستورات Artins Self**\n\n"
            "`.پنل` ← منو اصلی\n\n"
            "**⏰ ارسال:**\n"
            "`.ارسال میو 300`  `.stop`  `.stopall`  `.sends`\n\n"
            "**📌 تیچی** (ریپلای روی پیام):\n"
            "`.تنظیم بنر 30`  `.تنظیم بنر 30 فور`\n"
            "`.لیست بنر`  `.پاکسازی بنر`\n\n"
            "**💬 پاسخ خودکار:**\n"
            "`.افزودن پاسخ سلام = سلام! 👋`\n"
            "`.حذف پاسخ سلام`  `.لیست پاسخ`\n\n"
            "**📩 منشی:**\n"
            "`.متن منشی مشغولم`  `.تایم منشی 120`\n\n"
            "**💣 اسپم:**\n"
            "`.اسپم 20 میو`  `.اسپم سریع 20 میو`  `.پایان اسپم`\n\n"
            "**👻 ناپدید:**\n"
            "`.ghost on`  `.ghost off`\n\n"
            "**📥 دانلودر:**\n"
            "`.دانلود @channel`  `.پایان دانلود`  `.لیست دانلود`\n\n"
            "**🔒 ذخیره پیام‌های یه‌بار-دیدن:**\n"
            "از پنل → ذخیره‌پیام فعال کن\n\n"
            "**👁 جاسوس پروفایل:**\n"
            "`.spy @user`  `.unspy @user`  `.spylist`\n\n"
            "**🎵 موزیک به ویس** (ریپلای روی فایل صوتی):\n"
            "`.mv`\n\n"
            "**🎙 ویس:**\n"
            "`.ویس سلام`  یا ریپلای + `.ویس`\n"
            "`.ویس‌صدا fa f`  ← تنظیم صدا (fa/en/en-gb/en-au/ar, m/f)\n"
            "`.متن` (ریپلای روی ویس) ← تبدیل به متن\n\n"
            "**🤖 هوش مصنوعی:**\n"
            "`.هوش سوالت`  `.هوش نام [اسمت]`  `.هوش ریست`\n\n"
            "**🌐 ترجمه:**  `.ترجمه Hello`\n\n"
            "**💰 قیمت:**  `.قیمت`  (نوبیتکس + CoinGecko)\n\n"
            "**🕐 ساعت:**  `.ساعت`  (شمسی + میلادی)\n\n"
            "**🎲 بازی‌ها:**\n"
            "`.تاس`  `.تاس 6`  `.اسلات 777`  `.دارت`  `.بسکتبال 5`\n\n"
            "**🧰 ابزار:**\n"
            "`.حساب 5*8`  `.پسورد 20`  `.کوتاه https://...`  `.شانس`  `.پینگ`\n\n"
            "**🖱 اتوکلیکر:**\n"
            "`.دیباگ‌دکمه` (ریپلای)  `.افزودن‌کلیک @Bot 0 | Claim`\n"
            "`.لیست‌کلیک`  `.حذف‌کلیک 1`\n\n"
            "`.status` ← وضعیت کامل")

    # ══════════════════════════════════════════════════════════════
    #  Incoming — auto-seen, downloader, view-once saver,
    #             auto-reply, secretary
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(incoming=True))
    async def _incoming(event):
        if not event.text and not event.media: return
        try:    me = await client.get_me()
        except: return
        if event.sender_id == me.id: return

        # ── Auto-seen ──────────────────────────────────────────
        if db.get(acc.phone, "autoseen") == "1":
            try: await event.mark_read()
            except: pass

        if event.media:
            # ── 🔒 View-once / auto-expiring saver ────────────
            if db.get(acc.phone, "save_expiring") == "1":
                ttl = getattr(event.media, 'ttl_seconds', None)
                if ttl:
                    asyncio.create_task(_save_viewonce(client, event))

            # ── 📥 Downloader ──────────────────────────────────
            c   = db.conn()
            row = c.execute("SELECT 1 FROM downloads WHERE phone=? AND chat_id=?",
                            (acc.phone, str(event.chat_id))).fetchone()
            c.close()
            if row:
                try:
                    # FIXED: pass message ID + from_peer (not the Message object directly)
                    await client.forward_messages("me", [event.message.id],
                                                  from_peer=event.chat_id)
                except Exception as e:
                    print(f"[download] {e}")

        if not event.text: return

        # ── Keyword auto-reply ─────────────────────────────────
        if event.is_private and db.get(acc.phone, "ar_on") == "1":
            txt  = event.text.lower()
            mt   = db.get(acc.phone, "ar_type", "contains")
            c    = db.conn()
            rows = c.execute(
                "SELECT keyword,reply FROM auto_replies WHERE phone=? AND enabled=1",
                (acc.phone,)).fetchall()
            c.close()
            for r in rows:
                kw = r["keyword"].lower()
                if (mt == "exact" and txt == kw) or (mt != "exact" and kw in txt):
                    await event.reply(r["reply"]); return

        # ── Secretary / منشی ───────────────────────────────────
        if event.is_private and db.get(acc.phone, "sec_on") == "1":
            msg  = db.get(acc.phone, "sec_msg", "مشغولم، بعداً پاسخ می‌دم")
            wait = int(db.get(acc.phone, "sec_time", "60"))
            now  = time.time()
            if now - acc.dm_last.get(event.sender_id, 0) >= wait:
                await event.reply(msg)
                acc.dm_last[event.sender_id] = now

    async def _save_viewonce(client, event):
        """Download view-once media immediately and save to Saved Messages."""
        tmp = None
        try:
            sender = await event.get_sender()
            name   = getattr(sender, 'first_name', str(event.sender_id))
            tmp    = await client.download_media(event.message)
            if not tmp:
                return
            await client.send_file(
                "me", tmp,
                caption=(f"🔒 **ذخیره‌شده خودکار**\n"
                         f"از: {name}\nچت: `{event.chat_id}`"))
        except Exception as e:
            print(f"[viewonce] {e}")
        finally:
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass

    # ══════════════════════════════════════════════════════════════
    #  Outgoing — حالت‌متن + ghost re-assert
    # ══════════════════════════════════════════════════════════════
    @client.on(events.NewMessage(outgoing=True))
    async def _outgoing(event):
        if not event.text: return

        # ── 👻 Ghost: immediately re-assert offline after any outgoing message ─
        if db.get(acc.phone, "ghost") == "1" and not event.text.startswith("."):
            try:
                from telethon.tl.functions.account import UpdateStatusRequest
                await client(UpdateStatusRequest(offline=True))
            except Exception:
                pass

        # ── حالت‌متن ──────────────────────────────────────────
        if event.text.startswith("."): return
        if event.id in acc.fmt_skip: return

        keys   = ["bold","italic","underline","strike","mono","spoiler","quote"]
        active = {k: db.get(acc.phone, f"fmt_{k}") == "1" for k in keys}
        if not any(active.values()): return

        formatted = _fmt(event.text, active)
        acc.fmt_skip.add(event.id)
        try:
            await event.edit(formatted, parse_mode="html")
        except Exception as e:
            print(f"[fmt] {e}")
        finally:
            await asyncio.sleep(0.5)
            acc.fmt_skip.discard(event.id)
