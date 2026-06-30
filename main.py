import asyncio, os
from dotenv import load_dotenv
load_dotenv()

import db
from manager import Manager
import web

db.init()

async def main():
    mgr = Manager()
    web.mgr = mgr

    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    if BOT_TOKEN:
        from telethon import TelegramClient
        import panel
        panel.bot = TelegramClient(
            "sessions/helperbot",
            int(os.getenv("API_ID", "0")),
            os.getenv("API_HASH", "")
        )
        await panel.bot.start(bot_token=BOT_TOKEN)
        panel.register_callbacks(mgr)
        asyncio.create_task(panel.bot.run_until_disconnected())
        print("🤖 پنل: فعال")
    else:
        print("⚠️  BOT_TOKEN نیست — پنل غیرفعاله")

    print("\n📲 بارگذاری حساب‌ها...")
    await mgr.load()

    print(f"\n✅ {len(mgr.accs)} حساب متصل")
    print(f"🌐 داشبورد: http://0.0.0.0:5000")
    print(f"   توی تلگرام بنویس: .راهنما\n")

    await web.start()

if __name__ == "__main__":
    asyncio.run(main())
