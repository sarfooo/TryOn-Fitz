import base64
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import auth
import server


class SprintOneTests(unittest.TestCase):
    def setUp(self):
        auth._USERS_BY_EMAIL.clear()
        auth._USERS_BY_ID.clear()
        auth._SESSIONS.clear()
        auth._NEXT_ID = 1

    def test_signup_duplicate_login_logout_and_saved_mannequin(self):
        shopper = auth.create_user("Michael@example.com", "correct123")
        self.assertEqual(shopper["role"], "shopper")
        with self.assertRaisesRegex(ValueError, "already in use"):
            auth.create_user("michael@example.com", "another123")
        with self.assertRaisesRegex(ValueError, "Email or password is incorrect."):
            auth.login("michael@example.com", "wrong123")
        token, user = auth.login("michael@example.com", "correct123")
        cookie = "fitz_session=" + token
        self.assertEqual(user["email"], "michael@example.com")
        auth.set_mannequin(user["id"], "L")
        self.assertEqual(auth.login("michael@example.com", "correct123")[1]["mannequin"], "L")
        self.assertEqual(auth.user_from_cookie(cookie)["role"], "shopper")
        auth.logout(cookie)
        self.assertIsNone(auth.user_from_cookie(cookie))

    def test_product_validation_publish_stock_and_store_link(self):
        picture = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nexample").decode()
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "CATALOG_FILE", Path(directory) / "catalog.json"), patch.object(server, "CATALOG_SEED_FILE", Path(directory) / "seed.json"), patch.object(server, "UPLOAD_DIR", Path(directory) / "uploads"):
            for missing in ("item_name", "price", "image"):
                payload = {"item_name": "Jacket", "price": 80, "image": picture}
                del payload[missing]
                with self.assertRaises(ValueError): server.create_catalog_item(payload)
            item = server.create_catalog_item({"item_name": "Jacket", "price": 80, "image": picture, "sizes": {"S": 2, "M": 0, "L": 1}, "store_url": "https://issuederror.example/jacket", "visible": True})
            self.assertEqual(item["sizes"]["M"], 0)
            self.assertTrue((Path(directory) / "uploads" / item["image"].split("/")[-1]).exists())
            self.assertEqual([row["listing_id"] for row in server.load_catalog() if row["visible"]], [item["listing_id"]])
            self.assertEqual(server.update_catalog_item(item["listing_id"], {"store_url": ""})["store_url"], None)

    def test_shopper_is_denied_admin_api(self):
        shopper = auth.create_user("shopper@example.com", "correct123")
        admin = auth.create_user("owner@example.com", "correct123", role="admin")
        handler = object.__new__(server.Handler)
        handler.headers = Message()
        sent = []
        handler.send_json = lambda status, payload, cookie=None: sent.append((status, payload))
        handler.current_user = lambda: shopper
        self.assertFalse(handler.require_admin())
        self.assertEqual(sent[-1][0], 403)
        handler.current_user = lambda: admin
        self.assertTrue(handler.require_admin())

    def test_demo_accounts_clear_on_process_reset(self):
        auth.create_user("shopper@example.com", "correct123")
        token, _ = auth.login("shopper@example.com", "correct123")
        auth._USERS_BY_EMAIL.clear()
        auth._USERS_BY_ID.clear()
        auth._SESSIONS.clear()
        self.assertIsNone(auth.user_from_cookie("fitz_session=" + token))
        with self.assertRaisesRegex(ValueError, "Email or password is incorrect."):
            auth.login("shopper@example.com", "correct123")

    def test_builtin_demo_shopper(self):
        auth.bootstrap_demo_shopper()
        auth.bootstrap_demo_shopper()
        _, user = auth.login("shopper@tryonfitz.demo", "DemoShopper123")
        self.assertEqual(user["role"], "shopper")

    def test_account_http_routes(self):
        def request(path, method="GET", payload=None, cookie=None):
            handler = object.__new__(server.Handler)
            handler.path = path
            handler.headers = Message()
            if cookie:
                handler.headers["Cookie"] = cookie
            body = json.dumps(payload).encode() if payload is not None else b""
            handler.headers["Content-Length"] = str(len(body))
            handler.rfile = io.BytesIO(body)
            handler.wfile = io.BytesIO()
            response_headers = {}
            handler.send_response = lambda status: setattr(handler, "status", status)
            handler.send_header = lambda key, value: response_headers.__setitem__(key, value)
            handler.end_headers = lambda: None
            getattr(handler, "do_" + method)()
            return handler.status, response_headers, json.loads(handler.wfile.getvalue())

        status, headers, result = request("/api/signup", "POST", {"email": "demo@example.com", "password": "correct123"})
        self.assertEqual(status, 201)
        self.assertEqual(result["user"]["email"], "demo@example.com")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(request("/api/signup", "POST", {"email": "demo@example.com", "password": "correct123"})[0], 400)
        self.assertEqual(request("/api/login", "POST", {"email": "demo@example.com", "password": "wrong123"})[2]["error"], "Email or password is incorrect.")
        self.assertEqual(request("/api/me/mannequin", "PATCH", {"size": "L"}, cookie)[2]["user"]["mannequin"], "L")
        self.assertEqual(request("/api/admin/catalog", cookie=cookie)[0], 403)
        self.assertEqual(request("/api/logout", "POST", cookie=cookie)[0], 200)
        self.assertIsNone(request("/api/me", cookie=cookie)[2]["user"])
        status, headers, _ = request("/api/login", "POST", {"email": "demo@example.com", "password": "correct123"})
        self.assertEqual(status, 200)
        self.assertEqual(request("/api/me", cookie=headers["Set-Cookie"].split(";", 1)[0])[2]["user"]["mannequin"], "L")


if __name__ == "__main__":
    unittest.main()
