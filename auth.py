"""Local account and session storage for the Sprint 1 demo."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from http.cookies import SimpleCookie
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "accounts.sqlite3"
SESSION_SECONDS = 7 * 24 * 60 * 60
SIZES = {"S", "M", "L"}


def session_cookie(token):
    return f"fitz_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_SECONDS}"


def clear_cookie():
    return "fitz_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, salt BLOB NOT NULL, password_hash BLOB NOT NULL, role TEXT NOT NULL DEFAULT 'shopper', mannequin TEXT NOT NULL DEFAULT 'M')")
    connection.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL)")
    connection.commit()
    return connection


def _password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240000)


def create_user(email, password, role="shopper"):
    email = str(email or "").strip().lower()
    if not email or "@" not in email or len(email) > 254:
        raise ValueError("Enter a valid email address")
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if role not in {"shopper", "admin"}:
        raise ValueError("Invalid account role")
    salt = os.urandom(16)
    with closing(_connect()) as connection, connection:
        try:
            cursor = connection.execute("INSERT INTO users (email, salt, password_hash, role) VALUES (?, ?, ?, ?)", (email, salt, _password_hash(password, salt), role))
        except sqlite3.IntegrityError as exc:
            raise ValueError("This email is already in use") from exc
        return get_user(cursor.lastrowid, connection)


def get_user(user_id, connection=None):
    owned = connection is None
    connection = connection or _connect()
    try:
        row = connection.execute("SELECT id, email, role, mannequin FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if owned:
            connection.close()


def login(email, password):
    email = str(email or "").strip().lower()
    with closing(_connect()) as connection, connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not isinstance(password, str) or not hmac.compare_digest(_password_hash(password, row["salt"]), row["password_hash"]):
            raise ValueError("Email or password is incorrect.")
        token = secrets.token_urlsafe(32)
        connection.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], int(time.time()) + SESSION_SECONDS))
        return token, get_user(row["id"], connection)


def user_from_cookie(header):
    cookie = SimpleCookie()
    try:
        cookie.load(header or "")
    except Exception:
        return None
    morsel = cookie.get("fitz_session")
    if not morsel:
        return None
    token_hash = hashlib.sha256(morsel.value.encode()).hexdigest()
    with closing(_connect()) as connection, connection:
        row = connection.execute("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?", (token_hash, int(time.time()))).fetchone()
        return get_user(row["user_id"], connection) if row else None


def logout(header):
    cookie = SimpleCookie()
    cookie.load(header or "")
    morsel = cookie.get("fitz_session")
    if morsel:
        with closing(_connect()) as connection, connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(morsel.value.encode()).hexdigest(),))


def set_mannequin(user_id, size):
    if size not in SIZES:
        raise ValueError("Choose S, M, or L")
    with closing(_connect()) as connection, connection:
        connection.execute("UPDATE users SET mannequin = ? WHERE id = ?", (size, user_id))
        return get_user(user_id, connection)


def bootstrap_admin():
    with closing(_connect()) as connection, connection:
        exists = connection.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if exists:
        return None
    email = os.getenv("FITZ_ADMIN_EMAIL", "admin@tryonfitz.local")
    password = os.getenv("FITZ_ADMIN_PASSWORD") or secrets.token_urlsafe(15)
    create_user(email, password, role="admin")
    return email, password
