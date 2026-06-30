# commands.py — every dot-command, registered per user account.
# Every command works in both Persian and English (e.g. .قیمت or .price).
import asyncio, os, random, time, tempfile, secrets, string
import html as _html
from datetime import datetime, timezone, timedelta
from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaDice
import db

TEHRAN = timezone(timedelta(hours=3, minutes=30))
_spam_stop: set[str] = set()

# emoji → max value, per Telegram's official dice spec (core.telegram.org/api/dice)
GAME_EMOJI = {
    "تاس": "🎲", "dice": "🎲",
    "دارت": "🎯", "dart": "🎯",
    "بسکتبال": "🏀", "basketball": "🏀",
    "فوتبال": "⚽", "football": "⚽",
    "بولینگ": "🎳", "bowling": "🎳",
    "اسلات": "🎰", "slot": "🎰",
}
GAME_MAX = {"🎲": 6, "🎯": 6, "🏀": 5, "⚽": 5, "🎳": 6, "🎰": 64}
TARGET_WORDS = {
    "max": None, "بیشترین": None, "777": 64, "جکپات": 64, "jackpot": 64,
    "بولزای": 6, "bullseye": 6, "استرایک": 6, "strike": 6,
}

LUCK_MSGS = [
    "امروز روز خوبیه برای شروع یه کار جدید 🌟",
    "یکم احتیاط کن، ولی زیاد هم نگران نباش 🍀",
    "بهتره امروز صبور باشی، نتیجه میگیری 🌙",
    "روز پرانرژی‌ایه، ازش استفاده کن ⚡",
    "یه خبر خوب در راهه 📬",
    "امروز روز خوبیه برای تصمیم‌های مهم ✅",
    "بهتره امروز یکم استراحت کنی 😌",
]


def _fmt(text: str, active: dict) -> str:
    """HTML formatting so spoiler/underline/blockquote render correctly (not literal markdown)."""
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

    # ── پنل / panel ───────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پنل|panel)$'))
    async def _panel(event):
        import panel
        await event.delete()
        await panel.open_panel(event.chat_id, acc.phone, manager)

    # ── ارسال زمان‌بندی / send ───────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:send|ارسال) (.+?) (\d+)$'))
    async def _send(event):
        text  = event.pattern_match.group(1).strip()
        secs  = int(event.pattern_match.group(2))
        chat  = await event.get_chat()
        title = getattr(chat, 'title', None) or getattr(chat, 'first_name', str(event.chat_id))
        await event.delete()
        await manager.start_send(acc, str(event.chat_id), text, secs)
        await client.send_message("me",
            f"✅ ارسال شروع شد (بعد از ری‌استارت هم ادامه پیدا میکنه)\n"
            f"📍 {title}\n💬 `{text}`\n⏱ هر {secs} ثانیه")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:stop|توقف)$'))
    async def _stop(event):
        cid   = str(event.chat_id)
        chat  = await event.get_chat()
        title = getattr(chat, 'title', None) or getattr(chat, 'first_name', cid)
        await event.delete()
        if f"text:{cid}" in acc.tasks:
            await manager.stop_send(acc, cid)
            await client.send_message("me", f"⏹ ارسال در **{title}** متوقف شد")
        else:
            await client.send_message("me", f"⚠️ ارسالی فعال در {title} پیدا نشد")

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:stopall|توقف کل|توقف‌کل|توقف همه)$'))
    async def _stopall(event):
        await event.delete()
        await manager.stop_all(acc)
        await client.send_message("me", "⏹ همه ارسال‌ها و بنرها متوقف شدن")

    # ── تیچی / بنر / banner ───────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:تنظیم بنر|setbanner) (\d+)(?: (کپی|فور|copy|fwd))?$'))
    async def _set_banner(event):
        if not event.is_reply:
            await event.delete()
            await client.send_message("me", "❌ این دستور رو روی یه پیام ریپلای کن")
            return
        interval  = int(event.pattern_match.group(1))
        raw_mode  = (event.pattern_match.group(2) or "").lower()
        mode      = "fwd" if raw_mode in ("فور", "fwd") else "copy"
        if interval < 10:
            await event.delete()
            await client.send_message("me", "❌ حداقل ۱۰ ثانیه"); return
        c   = db.conn()
        cnt = c.execute(
            "SELECT COUNT(*) n FROM banners WHERE phone=? AND chat_id=? AND active=1",
            (acc.phone, str(event.chat_id))).fetchone()["n"]
        c.close()
        if cnt >= 10:
            await event.delete()
            await client.send_message("me", "❌ حداکثر ۱۰ بنر در هر چت"); return
        reply = await event.get_reply_message()
        await event.delete()
        await manager.add_banner(acc, event.chat_id, reply.chat_id, reply.id, interval, mode)
        await client.send_message("me",
            f"✅ بنر تنظیم شد\n⏱ هر {interval} ثانیه — {'فوروارد' if mode == 'fwd' else 'کپی'}")

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

    # ── پاسخ خودکار / auto-reply ─────────────────────────────────
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
        await client.send_message("me", f"✅ اضافه شد:\n`{kw}` ← {rp}")

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

    # ── منشی / secretary ─────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:متن منشی|sectext) (.+)$'))
    async def _sec_text(event):
        txt = event.pattern_match.group(1).strip()
        await event.delete()
        db.put(acc.phone, "sec_msg", txt)
        await client.send_message("me", f"✅ متن منشی تغییر کرد:\n{txt}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:تایم منشی|sectime) (\d+)$'))
    async def _sec_time(event):
        t = event.pattern_match.group(1)
        await event.delete()
        db.put(acc.phone, "sec_time", t)
        await client.send_message("me", f"✅ تایم منشی: {t} ثانیه")

    # ── اسپم / spam ───────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:اسپم|spam)(?: (سریع|آرام|fast|slow))? (\d+) (.+)$'))
    async def _spam(event):
        raw   = (event.pattern_match.group(1) or "").lower()
        count = min(int(event.pattern_match.group(2)), 100)
        text  = event.pattern_match.group(3).strip()
        cid   = event.chat_id
        await event.delete()

        delay = {"سریع": 0.3, "fast": 0.3, "آرام": 2.5, "slow": 2.5}.get(raw, 0.8)
        _spam_stop.discard(acc.phone)

        async def _run():
            sent = 0
            for i in range(count):
                if acc.phone in _spam_stop:
                    break
                try:
                    await client.send_message(cid, text)
                    sent += 1
                except Exception as e:
                    print(f"[spam] {e}"); break
                if i < count - 1:
                    await asyncio.sleep(delay)
            _spam_stop.discard(acc.phone)
            await client.send_message("me", f"✅ اسپم تموم شد — {sent} پیام ارسال شد")

        asyncio.create_task(_run())

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پایان اسپم|stopspam)$'))
    async def _stop_spam(event):
        await event.delete()
        _spam_stop.add(acc.phone)
        await client.send_message("me", "⏹ اسپم متوقف شد")

    # ── ویس (TTS) / voice ────────────────────────────────────────
    async def _do_tts(target_event, text):
        await target_event.delete()
        fd = tmp = None
        try:
            from gtts import gTTS
            lang = "fa" if any('\u0600' <= ch <= '\u06FF' for ch in text) else "en"
            fd, tmp = tempfile.mkstemp(suffix=".mp3")
            os.close(fd); fd = None
            gTTS(text=text, lang=lang).save(tmp)
            await client.send_file(target_event.chat_id, tmp, voice_note=True, caption="")
        except Exception as e:
            await client.send_message("me", f"❌ ویس: {e}")
        finally:
            if fd is not None:
                try: os.close(fd)
                except: pass
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:ویس|voice)\s+(.+)$'))
    async def _voice_text(event):
        await _do_tts(event, event.pattern_match.group(1).strip())

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:ویس|voice)$'))
    async def _voice_reply(event):
        if not event.is_reply:
            await event.delete()
            await client.send_message("me",
                "❌ یا متن بده: `.ویس سلام`\nیا روی یه پیام متنی ریپلای کن و `.ویس` بزن")
            return
        reply = await event.get_reply_message()
        if not reply.text:
            await event.delete()
            await client.send_message("me", "❌ پیامی که ریپلای کردی متن نداره")
            return
        await _do_tts(event, reply.text)

    # ── متن (STT) / totext — reply to a voice note ──────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:متن|totext|stt)$'))
    async def _speech_to_text(event):
        await event.delete()
        if not event.is_reply:
            await client.send_message("me", "❌ روی یه پیام صوتی/ویس ریپلای کن"); return
        reply = await event.get_reply_message()
        if not (reply.voice or reply.audio):
            await client.send_message("me", "❌ پیامی که ریپلای کردی صوتی نیست"); return
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            await client.send_message("me",
                "❌ **این قابلیت نیاز به API Key داره**\n\n"
                "توی Replit → Secrets این رو اضافه کن:\n"
                "کلید: `OPENAI_API_KEY`\nمقدار: کلیدت از platform.openai.com")
            return
        tmp = None
        try:
            tmp = await client.download_media(reply, file=tempfile.mktemp(suffix=".ogg"))
            import requests

            def _upload():
                with open(tmp, "rb") as f:
                    r = requests.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {key}"},
                        files={"file": f}, data={"model": "whisper-1"}, timeout=60)
                r.raise_for_status()
                return r.json()

            res  = await asyncio.get_event_loop().run_in_executor(None, _upload)
            text = (res.get("text") or "").strip()
            await client.send_message(event.chat_id, f"📝 {text}" if text else "متنی پیدا نشد")
        except Exception as e:
            await client.send_message("me", f"❌ تبدیل به متن: {e}")
        finally:
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass

    # ── هوش مصنوعی / ai ──────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:هوش|ai) (.+)$'))
    async def _ai(event):
        question = event.pattern_match.group(1).strip()
        await event.delete()
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            await client.send_message("me",
                "❌ **هوش مصنوعی نیاز به API Key داره**\n\n"
                "توی Replit → Secrets اضافه کن:\nکلید: `GEMINI_API_KEY`\n"
                "مقدار: کلیدت از aistudio.google.com")
            return
        try:
            import requests as _req, json
            def _call_gemini():
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
                body = {
                    "contents": [{"parts": [{"text": "You are a helpful assistant. Always reply in the same language the user writes in. Be concise.\n\n" + question}]}]
                }
                r = _req.post(url, json=body, timeout=30)
                r.raise_for_status()
                return r.json()
            res    = await asyncio.get_event_loop().run_in_executor(None, _call_gemini)
            answer = res["candidates"][0]["content"]["parts"][0]["text"].strip()
            await client.send_message(event.chat_id, f"🤖 {answer}")
        except Exception as e:
            await client.send_message("me", f"❌ هوش مصنوعی: {e}")

    # ── ترجمه / translate ────────────────────────────────────────
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

    # ── قیمت / price — real-time from Nobitex exchange, in Toman ────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:قیمت|price)$'))
    async def _price(event):
        await event.delete()
        try:
            import urllib.request, json
            req = urllib.request.Request(
                "https://api.nobitex.ir/market/stats",
                data=json.dumps({"dstCurrency": "rls"}).encode(),
                headers={"Content-Type": "application/json"})
            data  = json.loads(urllib.request.urlopen(req, timeout=10).read())
            stats = data.get("stats", {})

            def toman(pair):
                s = stats.get(pair)
                if not s: return None, None
                latest = float(s.get("latest") or s.get("bestSell") or 0)
                return round(latest / 10), s.get("dayChange", "0")

            coins = [("usdt","🟢 تتر (≈ دلار آزاد)"), ("btc","₿ بیتکوین"),
                     ("eth","⟠ اتریوم"), ("bnb","⬡ بایننس‌کوین"),
                     ("trx","🔺 ترون"), ("doge","🐕 دوج‌کوین"), ("ltc","Ł لایت‌کوین")]
            lines = ["💱 **قیمت لحظه‌ای — منبع: نوبیتکس**\n"]
            for code, label in coins:
                t, chg = toman(f"{code}-rls")
                if t is None:
                    continue
                try:    arrow = "📈" if float(chg) >= 0 else "📉"
                except: arrow = "•"
                lines.append(f"{label}:  {t:,} تومان   {arrow} {chg}%")
            await client.send_message(event.chat_id, "\n".join(lines))
        except Exception as e:
            await client.send_message("me", f"❌ قیمت: {e}")

    # ── ساعت + تاریخ / time + date (Tehran tz, Jalali calendar) ────
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:ساعت|time|تاریخ|date)$'))
    async def _clock(event):
        await event.delete()
        now  = datetime.now(TEHRAN)
        days = ["دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه","شنبه","یکشنبه"]
        try:
            import jdatetime
            jd     = jdatetime.date.fromgregorian(date=now.date())
            jalali = f"{jd.year}/{jd.month:02d}/{jd.day:02d}"
        except Exception:
            jalali = "—"
        msg = (
            f"🕐 **{now.strftime('%H:%M:%S')}**  —  {days[now.weekday()]}\n"
            f"📅 شمسی: {jalali}\n"
            f"📅 میلادی: {now.strftime('%Y/%m/%d')}\n"
            f"🌍 به وقت تهران"
        )
        await client.send_message(event.chat_id, msg)

    # ── بینگ / ping ───────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:پینگ|ping)$'))
    async def _ping(event):
        t0  = time.time()
        msg = await event.edit("🏓 ...")
        ms  = round((time.time() - t0) * 1000)
        await msg.edit(f"🏓 پینگ: **{ms}ms**")

    # ── ماشین‌حساب / calc ─────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:حساب|calc) (.+)$'))
    async def _calc(event):
        expr = event.pattern_match.group(1).strip()
        await event.delete()
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            await client.send_message(event.chat_id, f"🧮 `{expr}` = **{result}**")
        except:
            await client.send_message("me", "❌ عبارت اشتباهه")

    # ── پسورد / password ─────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:پسورد|password)(?:\s+(\d+))?$'))
    async def _password(event):
        length = int(event.pattern_match.group(1) or 16)
        length = max(6, min(length, 64))
        await event.delete()
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pw = "".join(secrets.choice(chars) for _ in range(length))
        await client.send_message("me", f"🔐 پسورد {length} کاراکتری:\n`{pw}`")

    # ── کوتاه‌کننده لینک / short url ─────────────────────────────
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

    # ── شانس / luck (just for fun, not tied to any real source) ─────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:شانس|luck)$'))
    async def _luck(event):
        await event.delete()
        pct = random.randint(40, 100)
        await client.send_message(event.chat_id,
            f"🎲 شانس امروزت: {pct}%\n{random.choice(LUCK_MSGS)}")

    # ── بازی‌ها با قابلیت گرفتن عدد دلخواه / dice with target ───────
    # بدون عدد = یه پرتاب رندوم. با عدد = تا رسیدن به اون عدد، پیام رو حذف
    # و دوباره میفرسته (تنها راه واقعی برای "گرفتن" یه عدد خاص، چون مقدار
    # رو سرور تلگرام رندوم تولید میکنه، نه کلاینت).
    DICE_PATTERN = r'^\.(' + "|".join(GAME_EMOJI.keys()) + r')(?:\s+(\S+))?$'

    @client.on(events.NewMessage(outgoing=True, pattern=DICE_PATTERN))
    async def _dice(event):
        name  = event.pattern_match.group(1)
        arg   = event.pattern_match.group(2)
        emoji = GAME_EMOJI.get(name)
        if not emoji:
            return
        maxv = GAME_MAX[emoji]
        await event.delete()

        target = None
        if arg:
            a = arg.strip().lower()
            if a in TARGET_WORDS:
                target = TARGET_WORDS[a] if TARGET_WORDS[a] is not None else maxv
            else:
                try:
                    n = int(a)
                    if 1 <= n <= maxv:
                        target = n
                except ValueError:
                    pass

        chat = await event.get_input_chat()

        if target is None:
            await client(SendMediaRequest(
                peer=chat, media=InputMediaDice(emoticon=emoji),
                message="", random_id=random.randint(1, 2**31)))
            return

        max_tries = 100 if emoji == "🎰" else 30
        delay     = 0.7 if emoji == "🎰" else 0.5
        last_val  = None

        for _ in range(max_tries):
            await client(SendMediaRequest(
                peer=chat, media=InputMediaDice(emoticon=emoji),
                message="", random_id=random.randint(1, 2**31)))
            msgs = await client.get_messages(event.chat_id, limit=1)
            if not msgs or not msgs[0].media or not hasattr(msgs[0].media, "value"):
                break
            last_val = msgs[0].media.value
            if last_val == target:
                return
            try:
                await client.delete_messages(event.chat_id, msgs[0].id)
            except FloodWaitError as e:
                if e.seconds <= 15:
                    await asyncio.sleep(e.seconds)
                else:
                    await client.send_message("me",
                        f"⏳ تلگرام محدودیت گذاشته، {e.seconds} ثانیه صبر کن و دوباره امتحان کن")
                    return
            except Exception:
                pass
            await asyncio.sleep(delay)

        await client.send_message("me",
            f"⚠️ بعد از {max_tries} تلاش به {target} نرسید (آخرین نتیجه: {last_val})\n"
            f"اگه توی گروهه، بقیه ممکنه پیام‌های حذف‌شده رو دیده باشن")

    # ── اتوکلیکر / autoclick ──────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:افزودن‌کلیک|افزودن کلیک|addclick) (@?\w+) (-?\d+) \| (.+)$'))
    async def _add_click(event):
        botname = event.pattern_match.group(1).lstrip("@").lower()
        count   = int(event.pattern_match.group(2))
        pattern = event.pattern_match.group(3).strip()
        await event.delete()
        c = db.conn()
        c.execute("INSERT INTO click_rules(phone,bot_username,pattern,remaining,delay_sec)"
                  " VALUES(?,?,?,?,?)", (acc.phone, botname, pattern, count, 2))
        c.commit(); c.close()
        limit_txt = "نامحدود" if count < 0 else f"{count} بار"
        await client.send_message("me",
            f"✅ قانون کلیک اضافه شد\n🤖 ربات: @{botname}\n🎯 الگو: «{pattern}»\n🔁 تعداد: {limit_txt}")

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:لیست‌کلیک|لیست کلیک|listclick)$'))
    async def _list_click(event):
        await event.delete()
        c    = db.conn()
        rows = c.execute("SELECT * FROM click_rules WHERE phone=? AND active=1 ORDER BY id",
                         (acc.phone,)).fetchall()
        c.close()
        if not rows:
            await client.send_message("me", "هیچ قانون کلیکی نداری"); return
        lines = ["🖱 **قوانین کلیک فعال:**\n"]
        for r in rows:
            rem = "نامحدود" if r["remaining"] < 0 else f"{r['remaining']} بار مونده"
            lines.append(f"#{r['id']} — @{r['bot_username']} ← «{r['pattern']}» ({rem})")
        await client.send_message("me", "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:حذف‌کلیک|حذف کلیک|delclick) (\d+)$'))
    async def _del_click(event):
        rid = int(event.pattern_match.group(1))
        await event.delete()
        c = db.conn()
        c.execute("UPDATE click_rules SET active=0 WHERE id=? AND phone=?", (rid, acc.phone))
        c.commit(); c.close()
        await client.send_message("me", f"🗑️ قانون #{rid} حذف شد")

    @client.on(events.NewMessage(outgoing=True,
               pattern=r'^\.(?:دیباگ‌دکمه|دیباگ دکمه|debugbuttons)$'))
    async def _debug_buttons(event):
        await event.delete()
        if not event.is_reply:
            await client.send_message("me", "❌ روی پیامی که دکمه داره ریپلای کن"); return
        reply = await event.get_reply_message()
        if not reply.buttons:
            await client.send_message("me", "این پیام دکمه نداره"); return
        lines = ["🔍 **متن دقیق دکمه‌ها** (این رو توی `.افزودن‌کلیک` کپی کن):\n"]
        for ri, row in enumerate(reply.buttons):
            for ci, btn in enumerate(row):
                lines.append(f"[{ri},{ci}] `{getattr(btn,'text','')}`")
        sender = await reply.get_sender()
        uname  = getattr(sender, "username", None)
        lines.append(f"\nیوزرنیم فرستنده: @{uname}" if uname else "\n⚠️ فرستنده یوزرنیم نداره — باید داشته باشه")
        await client.send_message("me", "\n".join(lines))

    # ── وضعیت / status ───────────────────────────────────────────
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
        clicks= c.execute("SELECT COUNT(*) n FROM click_rules WHERE phone=? AND active=1",
                          (acc.phone,)).fetchone()["n"]
        c.close()
        keys = ["bold","italic","underline","strike","mono","spoiler","quote"]
        fmts = [k for k in keys if db.get(acc.phone, f"fmt_{k}") == "1"]
        await client.send_message("me",
            f"📊 **{acc.name}**  (`{acc.phone}`)\n\n"
            f"منشی:           {'✅' if db.get(acc.phone,'sec_on')=='1' else '🔴'}\n"
            f"پاسخ‌خودکار:   {'✅' if db.get(acc.phone,'ar_on')=='1' else '🔴'}  ({reps} پاسخ)\n"
            f"سین خودکار:    {'✅' if db.get(acc.phone,'autoseen')=='1' else '🔴'}\n"
            f"حالت‌متن:      {', '.join(fmts) or 'خاموش'}\n"
            f"ارسال‌های فعال: {sends}\n"
            f"بنرهای فعال:   {bnrs}\n"
            f"قوانین کلیک:    {clicks}")

    # ── راهنما / help ─────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:راهنما|help)$'))
    async def _help(event):
        await event.delete()
        await client.send_message("me",
            "📋 **دستورات Artins Self**  (فارسی یا انگلیسی، هر دو کار میکنن)\n\n"
            "`.پنل` / `.panel`\n\n"
            "**⏰ ارسال:**\n"
            "`.send میو 300` / `.ارسال میو 300`  ← بعد ری‌استارت هم می‌مونه\n"
            "`.stop` / `.توقف`    `.stopall` / `.توقف کل`\n\n"
            "**📌 تیچی** (ریپلای روی پیام):\n"
            "`.تنظیم بنر 30` / `.setbanner 30`\n"
            "`.تنظیم بنر 30 فور` ← فوروارد به‌جای کپی\n"
            "`.لیست بنر`  `.پاکسازی بنر`  `.پاکسازی کل بنر`\n\n"
            "**💬 پاسخ خودکار:**\n"
            "`.افزودن پاسخ سلام = سلام! مشغولم 👋`\n"
            "`.حذف پاسخ سلام`  `.لیست پاسخ`  `.پاکسازی پاسخ`\n\n"
            "**📩 منشی:**\n"
            "`.متن منشی مشغولم، بعداً جواب میدم`\n"
            "`.تایم منشی 120`\n\n"
            "**💣 اسپم:**\n"
            "`.اسپم 20 سلام`  `.اسپم سریع 20 سلام`  `.اسپم آرام 20 سلام`\n"
            "`.پایان اسپم`\n\n"
            "**🎙 ویس (تبدیل دوطرفه):**\n"
            "`.ویس سلام به همه` ← متن به ویس (فارسی/انگلیسی خودکار تشخیص داده میشه)\n"
            "`.ویس` (ریپلای روی پیام متنی) ← همون پیام رو ویس میکنه\n"
            "`.متن` / `.totext` (ریپلای روی ویس) ← ویس رو متن میکنه — نیاز به OPENAI_API_KEY\n\n"
            "**🤖 هوش مصنوعی:**\n"
            "`.هوش [سوال]` ← نیاز به OPENAI_API_KEY\n\n"
            "**🌐 ابزار:**\n"
            "`.ترجمه Hello world` ← به فارسی\n"
            "`.قیمت` / `.price` ← قیمت لحظه‌ای تومان (منبع: نوبیتکس)\n"
            "`.ساعت` / `.تاریخ` ← ساعت + تاریخ شمسی، به وقت تهران\n"
            "`.پینگ`  `.حساب 5*8+2`  `.پسورد 20`  `.کوتاه https://...`  `.شانس`\n\n"
            "**🎮 بازی (با عدد دلخواه):**\n"
            "بدون عدد = یه پرتاب رندوم. با عدد = تا رسیدن به اون عدد دوباره میفرسته:\n"
            "`.تاس 6`  `.دارت 6`(بولزای)  `.بسکتبال 5`  `.فوتبال 5`\n"
            "`.بولینگ 6`(استرایک)  `.اسلات 777`(جکپات، کمی طول میکشه)\n"
            "توضیح: چون مقدار رو سرور تلگرام رندوم میسازه، تنها راه گرفتن عدد خاص\n"
            "اینه که پیام رو بفرستیم، چک کنیم، اگه نبود حذف و دوباره بفرستیم.\n\n"
            "**🖱 اتوکلیکر** (کلیک خودکار روی دکمه بات‌ها):\n"
            "`.دیباگ‌دکمه` (ریپلای روی پیام دکمه‌دار) ← متن دقیق هر دکمه رو نشون میده\n"
            "`.افزودن‌کلیک @BotName 0 | Claim` ← 0 یعنی نامحدود، عدد مثبت = تعداد دفعات\n"
            "`.لیست‌کلیک`  `.حذف‌کلیک 1`\n\n"
            "`.status` / `.وضعیت`")

    # ── پیام‌های ورودی (سین، پاسخ‌خودکار، منشی) ───────────────────────
    @client.on(events.NewMessage(incoming=True))
    async def _incoming(event):
        if not event.text: return
        try:    me = await client.get_me()
        except: return
        if event.sender_id == me.id: return

        if db.get(acc.phone, "autoseen") == "1":
            try: await event.mark_read()
            except: pass

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

        if event.is_private and db.get(acc.phone, "sec_on") == "1":
            msg  = db.get(acc.phone, "sec_msg", "مشغولم، بعداً پاسخ می‌دم")
            wait = int(db.get(acc.phone, "sec_time", "60"))
            now  = time.time()
            if now - acc.dm_last.get(event.sender_id, 0) >= wait:
                await event.reply(msg)
                acc.dm_last[event.sender_id] = now

    # ── حالت‌متن (HTML formatting) ───────────────────────────────────
    @client.on(events.NewMessage(outgoing=True))
    async def _format(event):
        if not event.text or event.text.startswith("."): return
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
