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


# ── Main panel ──────────────────────────────────────────────────────

def kb_main(phone, name):
    return [
        [_b("⚙️ منو اصلی",    "menu",  phone),
         _b("👤 حساب کاربری", "acct",  phone)],
        [_b("✕  بستن پنل",    "close", phone)],
    ]


def kb_menu(phone):
    return [
        # Row 1 — toggleable features
        [_b(f"{_icon(phone,'ar_on')} پاسخ‌خودکار",  "sub_ar",    phone),
         _b(f"{_icon(phone,'sec_on')} منشی",         "sub_sec",   phone),
         _b(f"{_icon(phone,'autoseen')} سین خودکار", "sub_seen",  phone)],
        # Row 2 — messaging
        [_b("📌 تیچی",      "sub_techy", phone),
         _b("📨 ارسال",     "sub_send",  phone),
         _b("💣 اسپم",      "sub_spam",  phone)],
        # Row 3 — formatting / voice / AI
        [_b("✏️ حالت‌متن",  "sub_fmt",   phone),
         _b("🎙 ویس / متن", "sub_tts",   phone),
         _b("🤖 هوش مصنوعی","sub_ai",    phone)],
        # Row 4 — tools
        [_b("🌐 ترجمه",     "sub_tr",    phone),
         _b("💰 قیمت ارز",  "sub_price", phone),
         _b("🕐 ساعت‌وتاریخ","sub_clock", phone)],
        # Row 5 — games / clicker / misc
        [_b("🏓 بینگ",      "sub_ping",  phone),
         _b("🎲 بازی‌ها",   "sub_games", phone),
         _b("🖱 اتوکلیکر",  "sub_click", phone)],
        # Row 6 — NEW features
        [_b(f"{_icon(phone,'ghost')} 👻 ناپدید", "sub_ghost", phone),
         _b("📥 دانلودر",                        "sub_dl",    phone),
         _b("👁 جاسوس",                           "sub_spy",   phone)],
        # Row 7 — NEW features cont.
        [_b(f"{_icon(phone,'save_expiring')} 🔒 ذخیره‌پیام", "sub_saver", phone),
         _b("🎵 موزیک→ویس",                                   "sub_mv",    phone),
         _b("🧰 ابزار دیگه",                                   "sub_tools", phone)],
        # Row 8 — management
        [_b("🛡️ مدیریت گروه", "sub_mgmt", phone)],
        [_b("» بازگشت", "main", phone)],
    ]


# ── Sub-panel builders ─────────────────────────────────────────────

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
        [_b(f"{'✅' if on=='1' else '☐'} پاسخ‌خودکار", "tog_ar",  phone),
         _b(f"نوع: {mt_lbl}",                            "tog_art", phone)],
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


def _sub_send(phone):
    c    = db.conn()
    rows = c.execute(
        "SELECT chat_id, message, interval_sec FROM sends WHERE phone=? AND active=1",
        (phone,)).fetchall()
    c.close()
    if rows:
        lines = [f"» ارسال زمان‌بندی — {len(rows)} فعال\n"]
        for r in rows:
            prev = r["message"][:30] + ("…" if len(r["message"]) > 30 else "")
            lines.append(f"• چت `{r['chat_id']}` — هر {r['interval_sec']}ث\n  «{prev}»")
        detail = "\n".join(lines)
    else:
        detail = "» ارسال زمان‌بندی\n\nهیچ ارسال فعالی نداری"
    txt = (
        f"{detail}\n\n─────────────────\n"
        "`.ارسال [پیام] [ثانیه]`  /  `.send`\n"
        "مثال: `.ارسال سلام 300`\n\n"
        "`.stop` ← متوقف کردن این چت\n"
        "`.stopall` ← همه ارسال‌ها\n\n"
        "💡 بعد از ری‌استارت سرور هم ادامه پیدا میکنه"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


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
    kb  = [
        row("bold", "بولد", "italic", "ایتالیک"),
        row("underline", "زیرخط", "strike", "خطخورده"),
        row("mono", "تکفاصله", "spoiler", "اسپویلر"),
        [_b(f"{'✅' if db.get(phone,'fmt_quote')=='1' else '☐'} نقل‌قول",
            "tf_quote", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


def _sub_tts(phone):
    lang       = db.get(phone, "tts_lang",   "auto")
    gender     = db.get(phone, "tts_gender", "f")
    gender_lbl = "زن 👩" if gender == "f" else "مرد 👨"
    lang_names = {
        "auto":  "خودکار (تشخیص فارسی/انگلیسی)",
        "fa":    "فارسی",
        "en":    "انگلیسی آمریکا",
        "en-gb": "انگلیسی بریتانیا",
        "en-au": "انگلیسی استرالیا",
        "ar":    "عربی",
    }
    lang_lbl = lang_names.get(lang, lang)
    has_key  = bool(os.getenv("GROQ_API_KEY", ""))
    txt = (
        "» ویس و تبدیل به متن\n\n"
        "`.ویس [متن]`  ← متن به ویس\n"
        "`.ویس` (ریپلای روی پیام متنی)  ← همون پیام رو ویس میکنه\n"
        "`.متن` (ریپلای روی ویس)  ← ویس رو متن میکنه\n\n"
        "**تنظیم صدا:**\n"
        "`.ویس‌صدا fa f`  ← فارسی / زن\n"
        "`.ویس‌صدا fa m`  ← فارسی / مرد\n"
        "`.ویس‌صدا en f`  ← انگلیسی آمریکا / زن\n"
        "`.ویس‌صدا en m`  ← انگلیسی آمریکا / مرد\n"
        "`.ویس‌صدا en-gb f`  ← انگلیسی بریتانیا\n"
        "`.ویس‌صدا en-au m`  ← انگلیسی استرالیا\n"
        "`.ویس‌صدا ar f`  ← عربی / زن\n\n"
        f"🎙 صدای فعلی: {lang_lbl} — {gender_lbl}\n"
        f"📝 تبدیل به متن (STT): {'✅ فعال' if has_key else '❌ نیاز به GROQ_API_KEY'}"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_ai(phone):
    has_key = bool(os.getenv("GROQ_API_KEY", ""))
    status  = "✅ فعال" if has_key else "❌ نیاز به API Key"
    ai_name = db.get(phone, "ai_name", "—")
    try:
        import json
        hist_len = len(json.loads(db.get(phone, "ai_history", "[]")))
    except Exception:
        hist_len = 0
    txt = (
        f"» هوش مصنوعی — {status}\n"
        "مدل: Llama 3.3 70B (Groq — رایگان)\n\n"
        "`.هوش [سوال]`  ← پرسیدن سوال\n"
        "`.هوش نام [اسمت]`  ← ذخیره اسم برای شخصی‌سازی\n"
        "`.هوش ریست`  ← پاک کردن حافظه\n\n"
        f"👤 اسم ذخیره‌شده: {ai_name}\n"
        f"🧠 پیام‌های در حافظه: {hist_len}\n\n"
        "برای فعال‌سازی → Replit Secrets:\n"
        "کلید: `GROQ_API_KEY` — رایگان از console.groq.com"
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
        "تتر، بیتکوین، اتریوم، بایننس، ترون، دوج، لایت‌کوین\n"
        "همه به تومان + درصد تغییر ۲۴ ساعته"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_clock(phone):
    txt = "» ساعت و تاریخ\n\n`.ساعت`  /  `.تاریخ`  ← ساعت + تاریخ شمسی، به وقت تهران"
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_ping(phone):
    return "» بینگ\n\n`.پینگ`  /  `.ping`  ← تست سرعت اتصال", \
           [[_b("» بازگشت", "menu", phone)]]


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
        "اول ریپلای روی پیام دکمه‌دار:\n"
        "`.دیباگ‌دکمه`  ← متن دقیق دکمه‌ها رو نشون میده\n\n"
        "بعد قانون بساز:\n"
        "`.افزودن‌کلیک @BotName 0 | Claim`\n"
        "(۰ = نامحدود، عددی بالاتر = همون تعداد دفعه)\n\n"
        "`.لیست‌کلیک`  `.حذف‌کلیک [شماره]`"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _sub_tools(phone):
    txt = (
        "» ابزار دیگه\n\n"
        "`.حساب [عبارت]`  /  `.calc`\n"
        "`.پسورد [طول]`  /  `.password`\n"
        "`.کوتاه [لینک]`  /  `.short`\n"
        "`.شانس`  /  `.luck`"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


# ── NEW: Ghost mode ─────────────────────────────────────────────────

def _sub_ghost(phone):
    on  = db.get(phone, "ghost")
    txt = (
        "» حالت ناپدید 👻\n\n"
        "هر ۳ ثانیه status آفلاین میفرسته\n"
        "همچنین بعد از هر پیام خروجی هم بلافاصله آفلاین ست میشه\n"
        "با این کار عملاً آنلاین نمیافتی حتی وقتی فعال هستی\n\n"
        f"وضعیت: {'✅ روشن' if on=='1' else '🔴 خاموش'}"
    )
    kb = [
        [_b(f"{'✅' if on=='1' else '☐'} حالت ناپدید", "tog_ghost", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


# ── NEW: Downloader ─────────────────────────────────────────────────

def _sub_dl(phone):
    c    = db.conn()
    rows = c.execute("SELECT * FROM downloads WHERE phone=?", (phone,)).fetchall()
    c.close()
    if rows:
        items = "\n".join(f"• {r['chat_title'] or r['chat_id']} (`{r['chat_id']}`)"
                         for r in rows)
        header = f"» دانلودر — {len(rows)} فعال\n\n{items}\n\n"
    else:
        header = "» دانلودر\n\nهیچ دانلودری فعال نیست\n\n"
    txt = (
        f"{header}"
        "هر مدیایی که توی چت مشخص شده بیاد\nبه Saved Messages فوروارد میشه\n\n"
        "`.دانلود @channel`  ← شروع\n"
        "`.پایان دانلود @channel`  ← توقف\n"
        "`.لیست دانلود`  ← لیست فعال"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


# ── NEW: Profile spy ───────────────────────────────────────────────

def _sub_spy(phone):
    c    = db.conn()
    rows = c.execute("SELECT * FROM profile_spy WHERE phone=?", (phone,)).fetchall()
    c.close()
    if rows:
        items = "\n".join(
            f"• {r['name'] or '—'}  (@{r['username'] or '—'})"
            for r in rows
        )
        header = f"» جاسوس پروفایل — {len(rows)} نفر زیر نظر\n\n{items}\n\n"
    else:
        header = "» جاسوس پروفایل\n\nهیچ‌کسی زیر نظر نیست\n\n"
    txt = (
        f"{header}"
        "هر ۵ دقیقه چک میشه\n"
        "اگه نام، یوزرنیم، عکس، یا بیو تغییر کنه بهت خبر میده\n\n"
        "`.spy @user`  ← شروع جاسوسی\n"
        "`.unspy @user`  ← توقف\n"
        "`.spylist`  ← لیست"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


# ── NEW: Music to voice ────────────────────────────────────────────

def _sub_mv(phone):
    txt = (
        "» موزیک به ویس 🎵\n\n"
        "روی هر فایل صوتی/موزیک ریپلای کن و بنویس:\n"
        "`.mv`  /  `.موزیک ویس`\n\n"
        "فایل دانلود میشه و به عنوان ویس نوت فرستاده میشه\n"
        "همه فرمت‌ها قبول میشه (MP3, AAC, M4A, OGG, ...)"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


# ── NEW: View-once / auto-expiring saver ─────────────────────────────

def _sub_saver(phone):
    on  = db.get(phone, "save_expiring")
    txt = (
        "» ذخیره پیام‌های خودکار-حذف 🔒\n\n"
        "وقتی کسی بهت عکس یا ویدیو «یه‌بار-دیدن» میفرسته،\n"
        "قبل از اینکه حذف بشه دانلود و به Saved Messages میفرسته\n\n"
        f"وضعیت: {'✅ روشن' if on=='1' else '🔴 خاموش'}\n\n"
        "⚠️ فقط در پیام‌های خصوصی (PV) کار میکنه\n"
        "تلگرام ممکنه دانلود بعضی view-once ها رو بلاک کنه"
    )
    kb = [
        [_b(f"{'✅' if on=='1' else '☐'} ذخیره خودکار", "tog_saver", phone)],
        [_b("» بازگشت", "menu", phone)],
    ]
    return txt, kb


# ── Account info ────────────────────────────────────────────────────

def _sub_mgmt(phone):
    txt = (
        "» مدیریت گروه 🛡️\n\n"
        "همه دستورات روی ریپلای یا با @یوزرنیم کار میکنن:\n\n"
        "**بن / محدودیت:**\n"
        "`.بن @user [دلیل]`  ←  بن دائمی\n"
        "`.آن‌بن @user`  ←  آن‌بن\n"
        "`.کیک @user`  ←  اخراج از گروه\n"
        "`.میوت @user [دقیقه]`  ←  میوت\n"
        "`.آن‌میوت @user`  ←  آن‌میوت\n\n"
        "**پیام:**\n"
        "`.پین`  ←  ریپلای روی پیام → پین\n"
        "`.آن‌پین`  ←  برداشتن پین\n"
        "`.پاک [تعداد]`  ←  حذف N پیام آخر\n"
        "`.هشدار @user [دلیل]`  ←  ارسال هشدار\n\n"
        "**ادمین:**\n"
        "`.پروموت @user [عنوان]`  ←  ادمین کردن\n"
        "`.دموت @user`  ←  برداشتن ادمین\n"
        "`.ادمین‌ها`  ←  لیست ادمین‌ها\n"
        "`.اعضا`  ←  تعداد اعضا\n\n"
        "**فورس جوین:**\n"
        "`.فورس @user @channel`\n"
        "یا ریپلای روی پیام یوزر + `.فورس @channel`\n"
        "(DM میفرسته و میگه باید عضو بشه)"
    )
    return txt, [[_b("» بازگشت", "menu", phone)]]


def _acct(phone, acc):
    name  = acc.name if acc else phone
    uname = f"@{acc.username}" if acc and acc.username else "—"
    c     = db.conn()
    bnrs   = c.execute("SELECT COUNT(*) n FROM banners WHERE phone=? AND active=1",
                       (phone,)).fetchone()["n"]
    reps   = c.execute("SELECT COUNT(*) n FROM auto_replies WHERE phone=? AND enabled=1",
                       (phone,)).fetchone()["n"]
    sends  = c.execute("SELECT COUNT(*) n FROM sends WHERE phone=? AND active=1",
                       (phone,)).fetchone()["n"]
    clicks = c.execute("SELECT COUNT(*) n FROM click_rules WHERE phone=? AND active=1",
                       (phone,)).fetchone()["n"]
    spies  = c.execute("SELECT COUNT(*) n FROM profile_spy WHERE phone=?",
                       (phone,)).fetchone()["n"]
    dls    = c.execute("SELECT COUNT(*) n FROM downloads WHERE phone=?",
                       (phone,)).fetchone()["n"]
    c.close()
    ghost = db.get(phone, "ghost") == "1"
    saver = db.get(phone, "save_expiring") == "1"
    txt = (
        f"» حساب کاربری\n\n"
        f"نام: {name}\nیوزرنیم: {uname}\nشماره: {phone}\n\n"
        f"👻 ناپدید:          {'✅' if ghost else '🔴'}\n"
        f"🔒 ذخیره‌پیام:     {'✅' if saver else '🔴'}\n"
        f"ارسال‌های فعال:   {sends}\n"
        f"بنرهای فعال:      {bnrs}\n"
        f"پاسخ‌های خودکار: {reps}\n"
        f"قوانین کلیک:      {clicks}\n"
        f"جاسوس‌ها:         {spies}\n"
        f"دانلودرها:        {dls}"
    )
    return txt, [[_b("» بازگشت", "main", phone)]]


# ── Open panel ─────────────────────────────────────────────────────

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


# ── Callback handler ────────────────────────────────────────────────

def register_callbacks(manager):

    @bot.on(events.CallbackQuery)
    async def _cb(event):
        raw = event.data.decode()
        if ":" not in raw:
            await event.answer(); return

        action, enc = raw.split(":", 1)
        phone = _dec(enc)
        acc   = manager.accs.get(phone)

        # Security: only the account owner may interact with their panel
        if acc is None:
            await event.answer("⚠️ این حساب دیگه متصل نیست", alert=True); return
        if acc.user_id is not None and event.sender_id != acc.user_id:
            await event.answer("🔒 این پنل برای شما نیست", alert=True); return

        async def show(txt, kb):
            try:    await event.edit(txt, buttons=kb)
            except Exception as e: print(f"[cb] {e}")

        # Navigation
        if   action == "main":  await show("Artins self", kb_main(phone, acc.name))
        elif action == "menu":  await show("Artins self", kb_menu(phone))
        elif action == "close": await event.delete()
        elif action == "acct":
            t, kb = _acct(phone, acc); await show(t, kb)

        # Existing sub-panels
        elif action == "sub_ar":    t, kb = _sub_ar(phone);    await show(t, kb)
        elif action == "sub_sec":   t, kb = _sub_sec(phone);   await show(t, kb)
        elif action == "sub_seen":  t, kb = _sub_seen(phone);  await show(t, kb)
        elif action == "sub_techy": t, kb = _sub_techy(phone); await show(t, kb)
        elif action == "sub_send":  t, kb = _sub_send(phone);  await show(t, kb)
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

        # NEW sub-panels
        elif action == "sub_ghost": t, kb = _sub_ghost(phone); await show(t, kb)
        elif action == "sub_dl":    t, kb = _sub_dl(phone);    await show(t, kb)
        elif action == "sub_spy":   t, kb = _sub_spy(phone);   await show(t, kb)
        elif action == "sub_mv":    t, kb = _sub_mv(phone);    await show(t, kb)
        elif action == "sub_saver": t, kb = _sub_saver(phone); await show(t, kb)
        elif action == "sub_mgmt":  t, kb = _sub_mgmt(phone);  await show(t, kb)

        # Existing toggles
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

        # NEW toggles
        elif action == "tog_ghost":
            # Actually start/stop the ghost task — not just a DB toggle
            if db.get(phone, "ghost") == "1":
                await manager.stop_ghost(acc)
            else:
                await manager.start_ghost(acc)
            t, kb = _sub_ghost(phone); await show(t, kb)

        elif action == "tog_saver":
            db.toggle(phone, "save_expiring")
            t, kb = _sub_saver(phone); await show(t, kb)

        else:
            await event.answer()
