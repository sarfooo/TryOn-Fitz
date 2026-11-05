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
    def test_signup_duplicate_login_logout_and_saved_mannequin(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(auth, "DB_PATH", Path(directory) / "accounts.db"):
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
        with tempfile.TemporaryDirectory() as directory, patch.object(auth, "DB_PATH", Path(directory) / "accounts.db"):
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


if __name__ == "__main__":
    unittest.main()
