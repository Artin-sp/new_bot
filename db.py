import sqlite3

DB = "userbot.db"


def conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS accounts(
        phone    TEXT PRIMARY KEY,
        name     TEXT DEFAULT '',
        username TEXT DEFAULT '',
        active   INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS auto_replies(
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        phone   TEXT NOT NULL,
        keyword TEXT NOT NULL,
        reply   TEXT NOT NULL,
        enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS banners(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        phone        TEXT NOT NULL,
        chat_id      TEXT NOT NULL,
        source_chat  TEXT NOT NULL,
        msg_id       INTEGER NOT NULL,
        interval_sec INTEGER NOT NULL,
        mode         TEXT DEFAULT 'copy',
        active       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS sends(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        phone        TEXT NOT NULL,
        chat_id      TEXT NOT NULL,
        message      TEXT NOT NULL,
        interval_sec INTEGER NOT NULL,
        active       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS settings(
        phone TEXT NOT NULL,
        key   TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY(phone, key)
    );
    CREATE TABLE IF NOT EXISTS config(
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS click_rules(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        phone        TEXT NOT NULL,
        bot_username TEXT NOT NULL,
        pattern      TEXT NOT NULL,
        remaining    INTEGER NOT NULL DEFAULT -1,
        delay_sec    INTEGER NOT NULL DEFAULT 2,
        active       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS pending_logins(
        phone      TEXT PRIMARY KEY,
        hash       TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS downloads(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        phone      TEXT NOT NULL,
        chat_id    TEXT NOT NULL,
        chat_title TEXT DEFAULT '',
        UNIQUE(phone, chat_id)
    );
    CREATE TABLE IF NOT EXISTS profile_spy(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        phone      TEXT NOT NULL,
        user_id    TEXT NOT NULL,
        username   TEXT DEFAULT '',
        name       TEXT DEFAULT '',
        photo_hash TEXT DEFAULT 'none',
        bio        TEXT DEFAULT '',
        UNIQUE(phone, user_id)
    );
    """)
    c.commit()
    c.close()


def get(phone: str, key: str, default: str = "0") -> str:
    c = conn()
    row = c.execute(
        "SELECT value FROM settings WHERE phone=? AND key=?", (phone, key)
    ).fetchone()
    c.close()
    return row["value"] if row else default


def put(phone: str, key: str, value: str):
    c = conn()
    c.execute(
        "INSERT OR REPLACE INTO settings(phone,key,value) VALUES(?,?,?)",
        (phone, key, str(value))
    )
    c.commit()
    c.close()


def toggle(phone: str, key: str) -> str:
    cur = get(phone, key, "0")
    nv  = "0" if cur == "1" else "1"
    put(phone, key, nv)
    return nv


def get_config(key: str, default: str = "") -> str:
    c = conn()
    row = c.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    c.close()
    return row["value"] if row else default


def set_config(key: str, value: str):
    c = conn()
    c.execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, str(value)))
    c.commit()
    c.close()
