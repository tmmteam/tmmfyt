# ╔══════════════════════════════════════════════════════════════╗
# ║         VCFIGHTER — Database Layer (Mongo + Local Fallback)  ║
# ║         File: VCFIGHTERS/database/mangodb.py                 ║
# ╚══════════════════════════════════════════════════════════════╝

import json
import os
import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

import Config
from VCFIGHTERS.logging import LOGGER

log = LOGGER("Database")

# ─────────────────────────────────────────────
# CONNECTION & FALLBACK STATE
# ─────────────────────────────────────────────

_client: AsyncIOMotorClient | None = None
db = None
_USE_FALLBACK = False

_LOCAL_DB_FILE = os.path.join(os.path.dirname(__file__), "vcfighter_db.json")

_SETTINGS_ID = "global"
_DEFAULT_SETTINGS = {
    "_id":         _SETTINGS_ID,
    "mode":        "dm",
    "logger_chat": None,
    "pytgcalls": {
        "stream_type":       "audio",
        "quality":           "medium",
        "noise_suppression": False,
    },
}

_FFMPEG_ID = "global"
_DEFAULT_FFMPEG = {
    "_id":        _FFMPEG_ID,
    "volume":     1.0,
    "compressor": False,
    "limiter":    False,
    "bass":       0,
    "pitch":      "normal",
    "echo":       False,
}

_local_db: dict = {
    "settings": _DEFAULT_SETTINGS.copy(),
    "ffmpeg": _DEFAULT_FFMPEG.copy(),
    "userbots": [],
    "targets": [],
    "sudo": [],
    "recordings": []
}


def _load_local_db():
    global _local_db
    if os.path.exists(_LOCAL_DB_FILE):
        try:
            with open(_LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                _local_db.update(loaded)
        except Exception as e:
            log.warning(f"Failed to load local DB file: {e}")


def _save_local_db():
    try:
        with open(_LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(_local_db, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to save local DB file: {e}")


async def init_db():
    """Connect to MongoDB. If auth or network fails, gracefully fall back to local database."""
    global _client, db, _USE_FALLBACK
    _load_local_db()

    mongo_uri = getattr(Config, "MONGO_URI", None)
    if not mongo_uri:
        _USE_FALLBACK = True
        log.warning("⚠️ No MONGO_URI provided. Using Local JSON Database.")
        return

    try:
        _client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db_name = Config.DB_NAME if hasattr(Config, "DB_NAME") and Config.DB_NAME else "vcfighter"
        db = _client[db_name]
        await db.command("ping")
        _USE_FALLBACK = False
        log.info("✅ MongoDB connected successfully")
    except Exception as e:
        _USE_FALLBACK = True
        log.warning(f"⚠️ MongoDB connection/auth failed: {e}")
        log.info("🛡️ Switching to Local Database Fallback! Bot will continue running smoothly.")


def _col(name: str):
    """Shortcut — returns a collection handle if MongoDB is active."""
    if _USE_FALLBACK or db is None:
        return None
    return db[name]


# ══════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════

async def get_settings() -> dict:
    if _USE_FALLBACK:
        return _local_db.get("settings", _DEFAULT_SETTINGS.copy())
    try:
        doc = await _col("settings").find_one({"_id": _SETTINGS_ID})
        if not doc:
            await _col("settings").insert_one(_DEFAULT_SETTINGS.copy())
            return _DEFAULT_SETTINGS.copy()
        return doc
    except Exception:
        return _local_db.get("settings", _DEFAULT_SETTINGS.copy())


async def save_settings(fields: dict):
    if _USE_FALLBACK:
        _local_db.setdefault("settings", _DEFAULT_SETTINGS.copy()).update(fields)
        _save_local_db()
        return
    try:
        await _col("settings").update_one(
            {"_id": _SETTINGS_ID},
            {"$set": fields},
            upsert=True,
        )
    except Exception:
        _local_db.setdefault("settings", _DEFAULT_SETTINGS.copy()).update(fields)
        _save_local_db()


async def get_mode() -> str:
    s = await get_settings()
    return s.get("mode", "dm")


async def set_mode(mode: str):
    await save_settings({"mode": mode})


async def get_logger_chat() -> int | None:
    s = await get_settings()
    return s.get("logger_chat")


async def get_pytgcalls_settings() -> dict:
    s = await get_settings()
    return s.get("pytgcalls", _DEFAULT_SETTINGS["pytgcalls"].copy())


async def save_pytgcalls_settings(pytg: dict):
    await save_settings({"pytgcalls": pytg})


# ══════════════════════════════════════════════
#  FFMPEG
# ══════════════════════════════════════════════

async def get_ffmpeg_settings() -> dict:
    if _USE_FALLBACK:
        return _local_db.get("ffmpeg", _DEFAULT_FFMPEG.copy())
    try:
        doc = await _col("ffmpeg").find_one({"_id": _FFMPEG_ID})
        if not doc:
            await _col("ffmpeg").insert_one(_DEFAULT_FFMPEG.copy())
            return _DEFAULT_FFMPEG.copy()
        return doc
    except Exception:
        return _local_db.get("ffmpeg", _DEFAULT_FFMPEG.copy())


async def save_ffmpeg_settings(fields: dict):
    if _USE_FALLBACK:
        _local_db.setdefault("ffmpeg", _DEFAULT_FFMPEG.copy()).update(fields)
        _save_local_db()
        return
    try:
        await _col("ffmpeg").update_one(
            {"_id": _FFMPEG_ID},
            {"$set": fields},
            upsert=True,
        )
    except Exception:
        _local_db.setdefault("ffmpeg", _DEFAULT_FFMPEG.copy()).update(fields)
        _save_local_db()


async def reset_ffmpeg_settings():
    if _USE_FALLBACK:
        _local_db["ffmpeg"] = _DEFAULT_FFMPEG.copy()
        _save_local_db()
        return
    try:
        await _col("ffmpeg").replace_one(
            {"_id": _FFMPEG_ID},
            _DEFAULT_FFMPEG.copy(),
            upsert=True,
        )
    except Exception:
        _local_db["ffmpeg"] = _DEFAULT_FFMPEG.copy()
        _save_local_db()


# ══════════════════════════════════════════════
#  USERBOTS
# ══════════════════════════════════════════════

async def get_all_userbots() -> list[dict]:
    if _USE_FALLBACK:
        return list(_local_db.get("userbots", []))
    try:
        return await _col("userbots").find().to_list(length=None)
    except Exception:
        return list(_local_db.get("userbots", []))


async def get_active_userbots() -> list[dict]:
    if _USE_FALLBACK:
        return [u for u in _local_db.get("userbots", []) if u.get("active")]
    try:
        return await _col("userbots").find({"active": True}).to_list(length=None)
    except Exception:
        return [u for u in _local_db.get("userbots", []) if u.get("active")]


async def get_all_sessions() -> list[str]:
    if _USE_FALLBACK:
        return [u["session_string"] for u in _local_db.get("userbots", []) if u.get("session_string")]
    try:
        docs = await _col("userbots").find({}).to_list(length=None)
        return [d["session_string"] for d in docs if d.get("session_string")]
    except Exception:
        return [u["session_string"] for u in _local_db.get("userbots", []) if u.get("session_string")]


async def get_userbot_by_phone(phone: str) -> dict | None:
    if _USE_FALLBACK:
        for u in _local_db.get("userbots", []):
            if u.get("phone") == phone:
                return u
        return None
    try:
        return await _col("userbots").find_one({"phone": phone})
    except Exception:
        return None


async def get_userbot_by_session(session: str) -> dict | None:
    if _USE_FALLBACK:
        for u in _local_db.get("userbots", []):
            if u.get("session_string") == session:
                return u
        return None
    try:
        return await _col("userbots").find_one({"session_string": session})
    except Exception:
        return None


async def add_userbot(data: dict):
    if _USE_FALLBACK:
        existing = False
        for i, u in enumerate(_local_db.get("userbots", [])):
            if u.get("session_string") == data.get("session_string"):
                _local_db["userbots"][i] = data
                existing = True
                break
        if not existing:
            _local_db.setdefault("userbots", []).append(data)
        _save_local_db()
        return

    try:
        existing = await get_userbot_by_session(data["session_string"])
        if existing:
            await _col("userbots").update_one(
                {"session_string": data["session_string"]},
                {"$set": data},
            )
        else:
            await _col("userbots").insert_one(data)
    except Exception:
        _local_db.setdefault("userbots", []).append(data)
        _save_local_db()


async def delete_userbot(session: str):
    if _USE_FALLBACK:
        _local_db["userbots"] = [u for u in _local_db.get("userbots", []) if u.get("session_string") != session]
        _save_local_db()
        return
    try:
        await _col("userbots").delete_one({"session_string": session})
    except Exception:
        _local_db["userbots"] = [u for u in _local_db.get("userbots", []) if u.get("session_string") != session]
        _save_local_db()


async def delete_all_userbots():
    if _USE_FALLBACK:
        _local_db["userbots"] = []
        _save_local_db()
        return
    try:
        await _col("userbots").delete_many({})
    except Exception:
        _local_db["userbots"] = []
        _save_local_db()


async def set_userbot_active(session: str, active: bool):
    if _USE_FALLBACK:
        for u in _local_db.get("userbots", []):
            if u.get("session_string") == session:
                u["active"] = active
                break
        _save_local_db()
        return
    try:
        await _col("userbots").update_one(
            {"session_string": session},
            {"$set": {"active": active}},
        )
    except Exception:
        for u in _local_db.get("userbots", []):
            if u.get("session_string") == session:
                u["active"] = active
                break
        _save_local_db()


async def userbot_count() -> int:
    if _USE_FALLBACK:
        return len(_local_db.get("userbots", []))
    try:
        return await _col("userbots").count_documents({})
    except Exception:
        return len(_local_db.get("userbots", []))


async def active_userbot_count() -> int:
    if _USE_FALLBACK:
        return len([u for u in _local_db.get("userbots", []) if u.get("active")])
    try:
        return await _col("userbots").count_documents({"active": True})
    except Exception:
        return len([u for u in _local_db.get("userbots", []) if u.get("active")])


# ══════════════════════════════════════════════
#  TARGETS
# ══════════════════════════════════════════════

async def get_all_targets() -> list[dict]:
    if _USE_FALLBACK:
        return list(_local_db.get("targets", []))
    try:
        return await _col("targets").find().to_list(length=None)
    except Exception:
        return list(_local_db.get("targets", []))


async def get_target_by_chat_id(chat_id: int) -> dict | None:
    if _USE_FALLBACK:
        for t in _local_db.get("targets", []):
            if t.get("chat_id") == chat_id:
                return t
        return None
    try:
        return await _col("targets").find_one({"chat_id": chat_id})
    except Exception:
        return None


async def get_primary_target() -> dict | None:
    if _USE_FALLBACK:
        targets = _local_db.get("targets", [])
        return targets[-1] if targets else None
    try:
        return await _col("targets").find_one(sort=[("added_at", -1)])
    except Exception:
        targets = _local_db.get("targets", [])
        return targets[-1] if targets else None


async def add_target(data: dict):
    if _USE_FALLBACK:
        existing = False
        for i, t in enumerate(_local_db.get("targets", [])):
            if t.get("chat_id") == data.get("chat_id"):
                _local_db["targets"][i] = data
                existing = True
                break
        if not existing:
            _local_db.setdefault("targets", []).append(data)
        _save_local_db()
        return

    try:
        existing = await get_target_by_chat_id(data["chat_id"])
        if existing:
            await _col("targets").update_one(
                {"chat_id": data["chat_id"]},
                {"$set": data},
            )
        else:
            await _col("targets").insert_one(data)
    except Exception:
        _local_db.setdefault("targets", []).append(data)
        _save_local_db()


async def delete_target(chat_id: int):
    if _USE_FALLBACK:
        _local_db["targets"] = [t for t in _local_db.get("targets", []) if t.get("chat_id") != chat_id]
        _save_local_db()
        return
    try:
        await _col("targets").delete_one({"chat_id": chat_id})
    except Exception:
        _local_db["targets"] = [t for t in _local_db.get("targets", []) if t.get("chat_id") != chat_id]
        _save_local_db()


async def delete_all_targets():
    if _USE_FALLBACK:
        _local_db["targets"] = []
        _save_local_db()
        return
    try:
        await _col("targets").delete_many({})
    except Exception:
        _local_db["targets"] = []
        _save_local_db()


async def update_target_joined(chat_id: int, phone: str):
    if _USE_FALLBACK:
        for t in _local_db.get("targets", []):
            if t.get("chat_id") == chat_id:
                t.setdefault("userbots_joined", [])
                if phone not in t["userbots_joined"]:
                    t["userbots_joined"].append(phone)
        _save_local_db()
        return
    try:
        await _col("targets").update_one(
            {"chat_id": chat_id},
            {"$addToSet": {"userbots_joined": phone}},
        )
    except Exception:
        pass


# ══════════════════════════════════════════════
#  SUDO
# ══════════════════════════════════════════════

async def get_sudo_users() -> list[int]:
    if _USE_FALLBACK:
        return [s["user_id"] for s in _local_db.get("sudo", [])]
    try:
        docs = await _col("sudo").find().to_list(length=None)
        return [d["user_id"] for d in docs]
    except Exception:
        return [s["user_id"] for s in _local_db.get("sudo", [])]


async def get_sudo_users_full() -> list[dict]:
    if _USE_FALLBACK:
        return list(_local_db.get("sudo", []))
    try:
        return await _col("sudo").find().to_list(length=None)
    except Exception:
        return list(_local_db.get("sudo", []))


async def add_sudo_user(data: dict):
    if _USE_FALLBACK:
        if not any(s.get("user_id") == data.get("user_id") for s in _local_db.get("sudo", [])):
            _local_db.setdefault("sudo", []).append(data)
            _save_local_db()
        return
    try:
        existing = await _col("sudo").find_one({"user_id": data["user_id"]})
        if not existing:
            await _col("sudo").insert_one(data)
    except Exception:
        _local_db.setdefault("sudo", []).append(data)
        _save_local_db()


async def remove_sudo_user(user_id: int):
    if _USE_FALLBACK:
        _local_db["sudo"] = [s for s in _local_db.get("sudo", []) if s.get("user_id") != user_id]
        _save_local_db()
        return
    try:
        await _col("sudo").delete_one({"user_id": user_id})
    except Exception:
        _local_db["sudo"] = [s for s in _local_db.get("sudo", []) if s.get("user_id") != user_id]
        _save_local_db()


async def is_sudo_user(user_id: int) -> bool:
    if _USE_FALLBACK:
        return any(s.get("user_id") == user_id for s in _local_db.get("sudo", []))
    try:
        doc = await _col("sudo").find_one({"user_id": user_id})
        return doc is not None
    except Exception:
        return any(s.get("user_id") == user_id for s in _local_db.get("sudo", []))


# ══════════════════════════════════════════════
#  RECORDINGS
# ══════════════════════════════════════════════

async def save_recording(file_path: str, user_id: int) -> str:
    if _USE_FALLBACK:
        entry = {"file_path": file_path, "user_id": user_id, "timestamp": int(time.time())}
        _local_db.setdefault("recordings", []).append(entry)
        _save_local_db()
        return str(len(_local_db["recordings"]))
    try:
        result = await _col("recordings").insert_one({
            "file_path": file_path,
            "user_id":   user_id,
            "timestamp": int(time.time()),
        })
        return str(result.inserted_id)
    except Exception:
        return str(int(time.time()))


async def get_recording(user_id: int) -> dict | None:
    if _USE_FALLBACK:
        user_recs = [r for r in _local_db.get("recordings", []) if r.get("user_id") == user_id]
        return user_recs[-1] if user_recs else None
    try:
        return await _col("recordings").find_one(
            {"user_id": user_id},
            sort=[("timestamp", -1)],
        )
    except Exception:
        return None


async def delete_recording(file_path: str):
    if _USE_FALLBACK:
        _local_db["recordings"] = [r for r in _local_db.get("recordings", []) if r.get("file_path") != file_path]
        _save_local_db()
        return
    try:
        await _col("recordings").delete_one({"file_path": file_path})
    except Exception:
        pass


async def delete_all_recordings_for_user(user_id: int):
    if _USE_FALLBACK:
        _local_db["recordings"] = [r for r in _local_db.get("recordings", []) if r.get("user_id") != user_id]
        _save_local_db()
        return
    try:
        await _col("recordings").delete_many({"user_id": user_id})
    except Exception:
        pass


async def cleanup_old_recordings(older_than_seconds: int = 3600):
    cutoff = int(time.time()) - older_than_seconds
    if _USE_FALLBACK:
        _local_db["recordings"] = [r for r in _local_db.get("recordings", []) if r.get("timestamp", 0) >= cutoff]
        _save_local_db()
        return
    try:
        result = await _col("recordings").delete_many({"timestamp": {"$lt": cutoff}})
        if result.deleted_count:
            log.info(f"🧹 Cleaned up {result.deleted_count} old recording(s)")
    except Exception:
        pass


# ══════════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════════

async def db_stats() -> dict:
    return {
        "userbots":  await userbot_count(),
        "active_ub": await active_userbot_count(),
        "targets":   len(await get_all_targets()),
        "sudo":      len(await get_sudo_users()),
    }
