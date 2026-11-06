"""Temporary, process-local accounts for the Sprint 1 prototype."""

import hashlib
import hmac
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie

SESSION_SECONDS = 7 * 24 * 60 * 60
SIZES = {"S", "M", "L"}
_LOCK = threading.RLock()
_USERS_BY_EMAIL = {}
_USERS_BY_ID = {}
_SESSIONS = {}
_NEXT_ID = 1


def session_cookie(token):
    return f"fitz_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_SECONDS}"


def clear_cookie():
    return "fitz_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"


def _password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240000)


def _public_user(row):
    return {key: row[key] for key in ("id", "email", "role", "mannequin")}


def _cookie_token(header):
    cookie = SimpleCookie()
    try:
        cookie.load(header or "")
    except Exception:
        return None
    morsel = cookie.get("fitz_session")
    return morsel.value if morsel else None


def create_user(email, password, role="shopper"):
    global _NEXT_ID
    email = str(email or "").strip().lower()
    if not email or "@" not in email or len(email) > 254:
        raise ValueError("Enter a valid email address")
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if role not in {"shopper", "admin"}:
        raise ValueError("Invalid account role")
    with _LOCK:
        if email in _USERS_BY_EMAIL:
            raise ValueError("This email is already in use")
        salt = os.urandom(16)
        row = {"id": _NEXT_ID, "email": email, "role": role, "mannequin": "M",
               "salt": salt, "password_hash": _password_hash(password, salt)}
        _NEXT_ID += 1
        _USERS_BY_EMAIL[email] = row
        _USERS_BY_ID[row["id"]] = row
        return _public_user(row)


def get_user(user_id):
    with _LOCK:
        row = _USERS_BY_ID.get(user_id)
        return _public_user(row) if row else None


def login(email, password):
    email = str(email or "").strip().lower()
    with _LOCK:
        row = _USERS_BY_EMAIL.get(email)
        if not row or not isinstance(password, str) or not hmac.compare_digest(_password_hash(password, row["salt"]), row["password_hash"]):
            raise ValueError("Email or password is incorrect.")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        _SESSIONS[token_hash] = (row["id"], int(time.time()) + SESSION_SECONDS)
        return token, _public_user(row)


def user_from_cookie(header):
    token = _cookie_token(header)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _LOCK:
        session = _SESSIONS.get(token_hash)
        if not session:
            return None
        if session[1] <= int(time.time()):
            _SESSIONS.pop(token_hash, None)
            return None
        row = _USERS_BY_ID.get(session[0])
        return _public_user(row) if row else None


def logout(header):
    token = _cookie_token(header)
    if token:
        with _LOCK:
            _SESSIONS.pop(hashlib.sha256(token.encode()).hexdigest(), None)


def set_mannequin(user_id, size):
    if size not in SIZES:
        raise ValueError("Choose S, M, or L")
    with _LOCK:
        row = _USERS_BY_ID.get(user_id)
        if not row:
            raise ValueError("Account no longer exists")
        row["mannequin"] = size
        return _public_user(row)


def bootstrap_admin():
    with _LOCK:
        if any(row["role"] == "admin" for row in _USERS_BY_ID.values()):
            return None
    email = os.getenv("FITZ_ADMIN_EMAIL", "admin@tryonfitz.local")
    password = os.getenv("FITZ_ADMIN_PASSWORD") or secrets.token_urlsafe(15)
    create_user(email, password, role="admin")
    return email, password


def bootstrap_demo_shopper():
    email = "shopper@tryonfitz.demo"
    with _LOCK:
        if email not in _USERS_BY_EMAIL:
            create_user(email, "DemoShopper123")
