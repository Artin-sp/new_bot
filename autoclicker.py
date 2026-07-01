# autoclicker.py — watches incoming bot messages for inline buttons and clicks
# any button whose label matches a configured rule. See commands.py for the
# .addclick / .debugbuttons dot-commands that manage rules.
#
# NOTE on "premium emoji" buttons: Telegram inline buttons only ever carry a
# plain text label — there is no formatting/entity system for button text like
# there is for message text, so a "custom/premium emoji" cannot actually live
# inside a button. What you're seeing is a normal Unicode emoji. Matching by
# plain text (case-insensitive substring, Unicode-normalized) is reliable.
# Use `.دیباگ‌دکمه` (reply to the message with buttons) to print the EXACT
# text Telegram sees for each button, then copy that exact text into your rule.

import asyncio, unicodedata
from telethon import events
import db


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip().lower()


async def _find_and_click(acc, msg, pattern: str) -> bool:
    if not msg.buttons:
        return False
    target = _norm(pattern)
    for row in msg.buttons:
        for btn in row:
            label = _norm(getattr(btn, "text", "") or "")
            if target and target in label:
                try:
                    await msg.click(text=btn.text)
                except Exception as e:
                    print(f"[autoclick] click failed: {e}")
                    return False
                return True
    return False


async def _handle_msg(client, acc, event):
    """Shared handler for both new and edited messages."""
    msg = event.message
    if not msg.buttons:
        return
    try:
        sender = await event.get_sender()
    except Exception:
        return
    uname = (getattr(sender, "username", "") or "").lower()
    if not uname:
        return

    c = db.conn()
    rules = c.execute(
        "SELECT * FROM click_rules WHERE phone=? AND active=1 AND bot_username=?",
        (acc.phone, uname)
    ).fetchall()
    c.close()
    if not rules:
        return

    for r in rules:
        delay = r["delay_sec"] or 2
        await asyncio.sleep(delay)

        # Re-fetch the message so we have the latest buttons (edit may have changed them)
        try:
            fresh = await client.get_messages(msg.chat_id, ids=msg.id)
            target_msg = fresh if fresh else msg
        except Exception:
            target_msg = msg

        if not target_msg or not target_msg.buttons:
            continue

        ok = await _find_and_click(acc, target_msg, r["pattern"])
        if not ok:
            continue

        c = db.conn()
        if r["remaining"] > 0:
            newrem = r["remaining"] - 1
            if newrem <= 0:
                c.execute("UPDATE click_rules SET active=0, remaining=0 WHERE id=?", (r["id"],))
            else:
                c.execute("UPDATE click_rules SET remaining=? WHERE id=?", (newrem, r["id"]))
            c.commit()
        c.close()

        try:
            tag = "✏️ ویرایش‌شده — " if getattr(event, 'message', None) and hasattr(event, 'original_update') else ""
            await client.send_message("me",
                f"🖱 کلیک خودکار روی «{r['pattern']}» — {tag}پیام از @{uname}")
        except Exception:
            pass


def register(client, acc, manager):

    @client.on(events.NewMessage(incoming=True))
    async def _watch_new(event):
        await _handle_msg(client, acc, event)

    @client.on(events.MessageEdited(incoming=True))
    async def _watch_edit(event):
        await _handle_msg(client, acc, event)
