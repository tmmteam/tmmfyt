import asyncio
import importlib
import os
import glob
from pyrogram import idle
import Config
from VCFIGHTERS.logging import LOGGER
from VCFIGHTERS.database.mangodb import init_db, get_all_sessions

log = LOGGER("VCFIGHTER")


def validate_config():
    required = ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URI", "OWNER_ID"]
    missing = [k for k in required if not getattr(Config, k, None)]
    if missing:
        LOGGER("Config").error(f"Missing config values: {missing}")
        exit(1)
    LOGGER("Config").info("Config validation passed")


def load_handlers():
    """
    FIGHTERS folder ke saare handlers manually load karta hai.
    bot.py mein plugins=dict(...) NAHI hona chahiye — warna double registration hoga!
    """
    LOGGER("Loader").info("Injecting Handlers into Bot...")
    fighters_dir = os.path.join(os.path.dirname(__file__), "FIGHTERS")
    for file in glob.glob(os.path.join(fighters_dir, "*.py")):
        name = os.path.basename(file)[:-3]
        if name != "__init__":
            try:
                importlib.import_module(f"VCFIGHTERS.FIGHTERS.{name}")
                LOGGER("Loader").info(f"✅ Handler Active: {name}")
            except Exception as e:
                LOGGER("Loader").error(f"❌ Failed to load {name}: {e}")


async def start_web_server():
    """
    Render, Koyeb, ya Railway ke liye health check web server.
    PORT environment variable milte hi port bind karta hai taaki deploy timeout na ho.
    """
    port_str = os.environ.get("PORT")
    if not port_str:
        return None
    try:
        from aiohttp import web
        port = int(port_str)
        routes = web.RouteTableDef()

        @routes.get("/")
        async def index(_):
            return web.Response(text="⚔️ VCFIGHTER is Alive and Running!")

        @routes.get("/health")
        async def health(_):
            return web.Response(text="OK")

        web_app = web.Application()
        web_app.add_routes(routes)
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        LOGGER("Web").info(f"✅ Web server listening on 0.0.0.0:{port} for Render/Cloud health checks")
        return runner
    except Exception as e:
        LOGGER("Web").warning(f"Failed to start web server on port {port_str}: {e}")
        return None


async def init():
    # Render port binding sabse pehle taaki port scan fail na ho
    web_runner = await start_web_server()

    validate_config()

    LOGGER("DB").info("Connecting to MongoDB...")
    await init_db()

    from VCFIGHTERS.core.bot import app

    # Handlers load karo — app.start() se PEHLE
    # (Pyrogram plugins system bypass karne ke liye)
    load_handlers()

    LOGGER("Bot").info("Starting bot...")
    await app.start()
    LOGGER("Bot").info("Bot started successfully")

    LOGGER("Userbots").info("Starting userbots...")
    from VCFIGHTERS.core.userbot import userbot_manager
    try:
        sessions = await get_all_sessions()
        if sessions:
            await userbot_manager.start_all(sessions)
            LOGGER("Userbots").info(f"{len(sessions)} userbot(s) started")
        else:
            LOGGER("Userbots").warning("No userbots in DB.")
    except Exception as e:
        LOGGER("Userbots").error(f"Userbot error: {e}")

    LOGGER("PyTgCalls").info("Starting PyTgCalls...")
    from VCFIGHTERS.core.call import vc
    await vc.start()

    # ─── AUTO MODE: Mic listener register karo ───────────────
    # Yeh ZAROOR chahiye — bina iske auto mode kaam nahi karega
    from VCFIGHTERS.FIGHTERS.Voice import register_participant_handlers
    await register_participant_handlers()
    # ─────────────────────────────────────────────────────────

    log.info("\n⚔️ VCFIGHTER IS NOW ACTIVE - Ready to Destroy VCs ⚔️\n")

    await idle()

    log.info("Shutting down...")
    try:
        await userbot_manager.stop_all()
        await vc.stop_all()
    except Exception:
        pass
    if web_runner:
        try:
            await web_runner.cleanup()
        except Exception:
            pass
    await app.stop()


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(init())
    
