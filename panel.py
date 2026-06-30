import os
import db
from telethon import TelegramClient, events, Button

bot: TelegramClient = None

_enc = lambda p: p.replace("+", "P")
_dec = lambda s: "+" + s[1:] if s.startswith("P") else s


def _b(label, action, phone):
    return Button.inline(label, f"{action}:{_enc(phone)}".encode())

def _icon(phone, key):
    return "✅" if db.get(phone, key) == "1" else "☐"


# ── Main panel ─────────────────────────────────────────────────────

def kb_main(phone, name):
    return [
        [_b("⚙️ منو اصلی",      "menu", phone),
         _b("👤 حساب کاربری",   "acct", phone)],
        [_b("✕  بستن پنل",      "close", phone)],
    ]


def kb_menu(phone):
    return [
        [_b(f"{_icon(phone,'ar_on')} پاسخ‌خودکار",  "sub_ar",   phone),
         _b(f"{_icon(phone,'sec_on')} منشی",         "sub_sec",  phone),
         _b(f"{_icon(phone,'autoseen')} سین خودکار", "sub_seen", phone)],
        [_b("📌 تیچی",     "sub_techy", phone),
         _b("💣 اسپم",     "sub_spam",  phone),
         _b("✏️ حالت‌متن", "sub_fmt",   phone)],
        [_b("🎙 ویس / متن", "sub_tts",   phone),
         _b("🤖 هوش مصنوعی","sub_ai",    phone),
         _b("🌐 ترجمه",     "sub_tr",    phone)],
        [_b("💰 قیمت ارز",   "sub_price", phone),
         _b("🕐 ساعت‌وتاریخ","sub_clock", phone),
         _b("🏓 بینگ",       "sub_ping",  phone)],
        [_b("🎲 بازی‌ها",     "sub_games", phone),
         _b("🖱 اتوکلیکر",    "sub_click", phone)],
        [_b("🧰 ابزار دیگه",  "sub_tools", phone)],
        [_b("» بازگشت", "main", phone)],
    ]


# ── Sub-panel builders (text, keyboard) ─────────────────────────────

def _sub_ar(phone):
    c   = db.conn()
    cnt = c.execute("SELECT COUNT(*) n FROM auto_replies WHERE phone=? AND enabled=1",
                    (phone,)).fetchone()["n"]
    c.close()
    on = db.get(phone, "ar_on"); mt = db.get(phone, "ar_type", "contains")
    mt_lbl = "برابر" if mt == "exact" else "شامل"
    txt = (
        "» پاسخ‌خودکار\n\n"
        "`.افزودن پاسخ کلمه = پاسخ`  /  `.addreply`\n"
        "`.حذف پاسخ کلمه`  /  `.delreply`\n"
        "`.لیست پاسخ`  /  `.پاکسازی پاسخ`\n\n"
        f"نوع تطابق: {mt_lbl}   |   تعداد: {cnt}"
    )
    kb = [
        [_b(f"{'✅' if on=='1' else '☐'} پاسخ‌خودکار", "tog_ar", phone),
         _b(f"نوع: {mt_lbl}", "tog_art", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


def _sub_sec(phone):
    on  = db.get(phone, "sec_on")
    msg = db.get(phone, "sec_msg", "مشغولم، بعداً پاسخ می‌دم")
    tim = db.get(phone, "sec_time", "60")
    txt = (
        "» منشی — پاسخ خودکار به پیام خصوصی\n\n"
        "`.متن منشی [متن]`  /  `.sectext`\n"
        "`.تایم منشی [ثانیه]`  /  `.sectime`\n\n"
        f"تایمر: {tim} ثانیه\nمتن فعلی:\n{msg}"
    )
    kb = [
        [_b(f"{'✅' if on=='1' else '☐'} منشی", "tog_sec", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


def _sub_seen(phone):
    on  = db.get(phone, "autoseen")
    txt = "» سین خودکار\n\nوقتی پیام جدیدی بیاد، خودکار سین میشه."
    kb  = [
        [_b(f"{'✅' if on=='1' else '☐'} سین خودکار", "tog_seen", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


def _sub_techy(phone):
    c   = db.conn()
    cnt = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND active=1",
                    (phone,)).fetchone()["n"]
    c.close()
    txt = (
        f"» تیچی — بنرهای فعال: {cnt}\n\n"
        "ریپلای روی پیام مورد نظر:\n"
        "`.تنظیم بنر [ثانیه]`  /  `.setbanner`  ← کپی\n"
        "`.تنظیم بنر [ثانیه] فور`  ← فوروارد\n\n"
        "`.لیست بنر`  `.پاکسازی بنر`  `.پاکسازی کل بنر`\n\n"
        "حداقل ۱۰ ثانیه  |  حداکثر ۱۰ بنر در هر چت\n"
        "بعد از ری‌استارت سرور هم فعال می‌مونن"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_spam(phone):
    txt = (
        "» اسپم\n\n"
        "`.اسپم [تعداد] [متن]`  /  `.spam`\n"
        "`.اسپم سریع [تعداد] [متن]`  ← سریع\n"
        "`.اسپم آرام [تعداد] [متن]`  ← آرام\n"
        "`.پایان اسپم`  /  `.stopspam`  ← توقف فوری\n\n"
        "حداکثر ۱۰۰ پیام در هر بار"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_fmt(phone):
    def row(k1, l1, k2, l2):
        v1 = "✅" if db.get(phone, f"fmt_{k1}") == "1" else "☐"
        v2 = "✅" if db.get(phone, f"fmt_{k2}") == "1" else "☐"
        return [_b(f"{v1} {l1}", f"tf_{k1}", phone),
                _b(f"{v2} {l2}", f"tf_{k2}", phone)]
    txt = "» حالت‌متن\n\nهر قالبی که روشن باشه روی همه پیام خروجیت میشینه."
    kb = [
        row("bold", "بولد", "italic", "ایتالیک"),
        row("underline", "زیرخط", "strike", "خطخورده"),
        row("mono", "تکفاصله", "spoiler", "اسپویلر"),
        [_b(f"{'✅' if db.get(phone,'fmt_quote')=='1' else '☐'} نقل‌قول", "tf_quote", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


def _sub_tts(phone):
    has_key = bool(os.getenv("GROQ_API_KEY", ""))
    txt = (
        "» ویس و تبدیل به متن\n\n"
        "`.ویس [متن]`  /  `.voice`  ← متن به ویس\n"
        "(زبان فارسی/انگلیسی خودکار تشخیص داده میشه)\n\n"
        "`.ویس` (ریپلای روی پیام متنی)  ← همون پیام رو ویس میکنه\n\n"
        "`.متن` / `.totext` (ریپلای روی ویس)  ← ویس رو متن میکنه (Groq Whisper)\n"
        f"وضعیت تبدیل به متن: {'✅ فعال' if has_key else '❌ نیاز به GROQ_API_KEY'}"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_ai(phone):
    has_key = bool(os.getenv("GROQ_API_KEY", ""))
    status  = "✅ فعال (Llama 3.3 70B)" if has_key else "❌ نیاز به API Key"
    txt = (
        f"» هوش مصنوعی — {status}\n\n"
        "`.هوش [سوال]`  /  `.ai`\n\n"
        "مدل: Llama 3.3 70B (Groq — رایگان و سریع)\n\n"
        "برای فعال‌سازی، توی Replit → Secrets اضافه کن:\n"
        "کلید: GROQ_API_KEY\nمقدار: کلید رایگان از console.groq.com"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_tr(phone):
    txt = "» ترجمه\n\n`.ترجمه [متن]`  /  `.translate`  ← ترجمه به فارسی"
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_price(phone):
    txt = (
        "» قیمت ارز\n\n"
        "`.قیمت`  /  `.price`\n\n"
        "منبع: نوبیتکس (صرافی ایرانی، لحظه‌ای)\n"
        "همه قیمت‌ها به تومان — تتر، بیتکوین، اتریوم،\n"
        "بایننس‌کوین، ترون، دوج‌کوین، لایت‌کوین"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_clock(phone):
    txt = "» ساعت و تاریخ\n\n`.ساعت` یا `.تاریخ`  ← ساعت + تاریخ شمسی، به وقت تهران"
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_ping(phone):
    return "» بینگ\n\n`.پینگ` / `.ping`  ← تست سرعت اتصال", [[_b("» بازگشت", "menu", phone)]]


def _sub_games(phone):
    txt = (
        "» بازی‌ها\n\n"
        "بدون عدد = یه پرتاب رندوم\n"
        "با عدد = تا رسیدن به اون عدد دوباره میفرسته:\n\n"
        "`.تاس [1-6]`   `.دارت [1-6]` (۶=بولزای)\n"
        "`.بسکتبال [1-5]`   `.فوتبال [1-5]`\n"
        "`.بولینگ [1-6]` (۶=استرایک)\n"
        "`.اسلات [1-64]` یا `.اسلات 777` (جکپات)\n\n"
        "چون مقدار رو سرور تلگرام تصادفی میسازه، تنها راه رسیدن\n"
        "به عدد دلخواه اینه که بفرستیم، چک کنیم، نبود حذف و دوباره."
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_click(phone):
    c   = db.conn()
    cnt = c.execute("SELECT COUNT(*) n FROM click_rules WHERE phone=? AND active=1",
                    (phone,)).fetchone()["n"]
    c.close()
    txt = (
        f"» اتوکلیکر — قوانین فعال: {cnt}\n\n"
        "کلیک خودکار روی دکمه‌های پیام بات‌ها (مثل claim).\n\n"
        "اول این رو بزن (ریپلای روی پیام دکمه‌دار):\n"
        "`.دیباگ‌دکمه`  ← متن دقیق هر دکمه رو نشون میده\n\n"
        "بعد قانون بساز:\n"
        "`.افزودن‌کلیک @BotName 0 | Claim`\n"
        "(۰ = نامحدود، عددی بالاتر = همون تعداد دفعه)\n\n"
        "`.لیست‌کلیک`  `.حذف‌کلیک [شماره]`\n\n"
        "نکته: دکمه‌ها فقط متن ساده دارن، ایموجی پرمیوم/سفارشی\n"
        "روی دکمه وجود نداره — چیزی که می‌بینی همون متن واقعیه که\n"
        "`.دیباگ‌دکمه` نشونت میده."
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_tools(phone):
    txt = (
        "» ابزار دیگه\n\n"
        "`.حساب [عبارت]`  /  `.calc`  ← مثال: `.حساب 5*8+2`\n"
        "`.پسورد [طول]`  /  `.password`  ← پسورد تصادفی (به Saved Messages)\n"
        "`.کوتاه [لینک]`  /  `.short`  ← کوتاه‌کننده لینک\n"
        "`.شانس`  /  `.luck`  ← شانس امروزت (فقط برای سرگرمی)"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _acct(phone, acc):
    name  = acc.name if acc else phone
    uname = f"@{acc.username}" if acc and acc.username else "—"
    c     = db.conn()
    bnrs   = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND active=1",(phone,)).fetchone()["n"]
    reps   = c.execute("SELECT COUNT(*) n FROM auto_replies WHERE phone=? AND enabled=1",(phone,)).fetchone()["n"]
    sends  = c.execute("SELECT COUNT(*) n FROM sends WHERE phone=? AND active=1",(phone,)).fetchone()["n"]
    clicks = c.execute("SELECT COUNT(*) n FROM click_rules WHERE phone=? AND active=1",(phone,)).fetchone()["n"]
    c.close()
    txt = (
        f"» حساب کاربری\n\n"
        f"نام: {name}\nیوزرنیم: {uname}\nشماره: {phone}\n\n"
        f"ارسال‌های فعال: {sends}\nبنرهای فعال: {bnrs}\n"
        f"پاسخ‌های خودکار: {reps}\nقوانین کلیک: {clicks}"
    )
    return txt, [[_b("» بازگشت", "main", phone)]]


# ── Open panel in chat ─────────────────────────────────────────────

async def open_panel(chat_id: int, phone: str, manager) -> bool:
    if not bot:
        return False
    acc  = manager.accs.get(phone)
    name = acc.name if acc else phone
    try:
        await bot.send_message(chat_id, "Artins self", buttons=kb_main(phone, name))
        return True
    except Exception:
        pass
    try:
        if acc:
            me = await acc.client.get_me()
            await bot.send_message(me.id, "Artins self", buttons=kb_main(phone, name))
            return True
    except Exception as e:
        print(f"[panel] {e}")
    return False


# ── Callback handler — SECURITY: only the account owner may click ──

def register_callbacks(manager):

    @bot.on(events.CallbackQuery)
    async def _cb(event):
        raw = event.data.decode()
        if ":" not in raw:
            await event.answer(); return

        action, enc = raw.split(":", 1)
        phone = _dec(enc)
        acc   = manager.accs.get(phone)

        # ── Ownership check ──────────────────────────────────────
        # Only the Telegram user who actually owns this userbot account
        # (acc.user_id, set at login) may interact with its panel. Anyone
        # else clicking — e.g. another member of the same group — gets a
        # silent rejection instead of being able to change settings.
        if acc is None:
            await event.answer("⚠️ این حساب دیگه متصل نیست", alert=True)
            return
        if acc.user_id is not None and event.sender_id != acc.user_id:
            await event.answer("🔒 این پنل برای شما نیست", alert=True)
            return

        async def show(txt, kb):
            try:    await event.edit(txt, buttons=kb)
            except Exception as e: print(f"[cb] {e}")

        name = acc.name

        if   action == "main":  await show("Artins self", kb_main(phone, name))
        elif action == "menu":  await show("Artins self", kb_menu(phone))
        elif action == "close": await event.delete()
        elif action == "acct":
            t, kb = _acct(phone, acc); await show(t, kb)

        elif action == "sub_ar":    t, kb = _sub_ar(phone);    await show(t, kb)
        elif action == "sub_sec":   t, kb = _sub_sec(phone);   await show(t, kb)
        elif action == "sub_seen":  t, kb = _sub_seen(phone);  await show(t, kb)
        elif action == "sub_techy": t, kb = _sub_techy(phone); await show(t, kb)
        elif action == "sub_spam":  t, kb = _sub_spam(phone);  await show(t, kb)
        elif action == "sub_fmt":   t, kb = _sub_fmt(phone);   await show(t, kb)
        elif action == "sub_tts":   t, kb = _sub_tts(phone);   await show(t, kb)
        elif action == "sub_ai":    t, kb = _sub_ai(phone);    await show(t, kb)
        elif action == "sub_tr":    t, kb = _sub_tr(phone);    await show(t, kb)
        elif action == "sub_price": t, kb = _sub_price(phone); await show(t, kb)
        elif action == "sub_clock": t, kb = _sub_clock(phone); await show(t, kb)
        elif action == "sub_ping":  t, kb = _sub_ping(phone);  await show(t, kb)
        elif action == "sub_games": t, kb = _sub_games(phone); await show(t, kb)
        elif action == "sub_click": t, kb = _sub_click(phone); await show(t, kb)
        elif action == "sub_tools": t, kb = _sub_tools(phone); await show(t, kb)

        elif action == "tog_ar":
            db.toggle(phone, "ar_on");    t, kb = _sub_ar(phone);   await show(t, kb)
        elif action == "tog_art":
            cur = db.get(phone, "ar_type", "contains")
            db.put(phone, "ar_type", "exact" if cur == "contains" else "contains")
            t, kb = _sub_ar(phone); await show(t, kb)
        elif action == "tog_sec":
            db.toggle(phone, "sec_on");   t, kb = _sub_sec(phone);  await show(t, kb)
        elif action == "tog_seen":
            db.toggle(phone, "autoseen"); t, kb = _sub_seen(phone); await show(t, kb)
        elif action.startswith("tf_"):
            db.toggle(phone, f"fmt_{action[3:]}")
            t, kb = _sub_fmt(phone); await show(t, kb)

        else:
            await event.answer()
