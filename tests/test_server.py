import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class DemoTests(unittest.TestCase):
    def test_sample_catalog_has_usable_images(self):
        self.assertEqual(len(server.SAMPLES), 2)
        self.assertTrue(all(item["image"].startswith("https://") for item in server.SAMPLES))

    def test_committed_catalog_seed_has_forty_real_listings(self):
        items = json.loads(server.CATALOG_SEED_FILE.read_text())
        self.assertEqual(len(items), 40)
        self.assertEqual(len({item["listing_id"] for item in items}), 40)
        self.assertTrue(all(item["source"] == "Grailed" and item["images"] for item in items))
        published = [item for item in items if item.get("visible")]
        self.assertTrue(any(item.get("store_url") == item.get("product_url") for item in published))
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "CATALOG_FILE", Path(directory) / "catalog.json"):
            self.assertEqual(len(server.load_catalog()), 40)

    def test_rejects_untrusted_image_url(self):
        with self.assertRaises(ValueError):
            server._image_part("http://localhost:3000/private")

    def test_grailed_search_normalizes_listing(self):
        calls = []
        def fake_request(url, data=None, headers=None, timeout=20):
            calls.append(url)
            if url.endswith("/shop"):
                return b'xx app_id":"ALGOLIA-ID" yy'
            if url.endswith("/api/algolia/keys"):
                return b'{"data":{"search_key":"TEST-KEY"}}'
            return json.dumps({"results": [{"hits": [{"id": 42, "title": "Black jacket", "cover_photo": {"image_url": "https://cdn.fs.grailed.com/jacket.jpg"}, "price": 90}]}]}).encode()
        with patch.object(server, "_grailed_session", return_value=None), patch.object(server, "_request", side_effect=fake_request):
            items = server.search_grailed("black jacket")
        self.assertEqual(items[0]["listing_id"], "42")
        self.assertEqual(items[0]["source"], "Grailed")
        self.assertEqual(len(calls), 3)

    def test_grailed_search_uses_tls_session_and_algolia_credentials(self):
        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = []

            def post(self, url, json=None):
                self.calls.append((url, json))
                if url.endswith("/shop"):
                    return SimpleNamespace(text='app_id":"ALGOLIA-ID"')
                if url.endswith("/api/algolia/keys"):
                    return SimpleNamespace(json=lambda: {"data": {"search_key": "TEST-KEY"}})
                return SimpleNamespace(json=lambda: {"results": [{"hits": [{"id": 42, "title": "Black jacket", "cover_photo": {"image_url": "https://cdn.fs.grailed.com/jacket.jpg"}}]}]})

        session = FakeSession()
        with patch.object(server, "_grailed_session", return_value=session):
            items = server.search_grailed("black jacket", page=2)
        self.assertEqual(len(items), 1)
        self.assertEqual(session.headers["x-algolia-application-id"], "ALGOLIA-ID")
        self.assertEqual(session.headers["x-algolia-api-key"], "TEST-KEY")
        self.assertIn("page=2", session.calls[-1][1]["requests"][0]["params"])
        self.assertIn(items[0]["image"], server.ALLOWED_GARMENT_URLS)

    def test_render_requires_key_before_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_API_KEY"):
                server.render_gemini("anything", ["anything"])

    def test_gemini_render_sends_avatar_and_garment(self):
        image = "data:image/png;base64," + __import__("base64").b64encode(b"\x89PNG\r\n\x1a\nexample").decode()
        sent = {}
        def fake_request(url, data=None, headers=None, timeout=20):
            sent["url"] = url
            sent["body"] = json.loads(data)
            return json.dumps({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": "AAAA"}}]}}]}).encode()
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch.object(server, "_request", side_effect=fake_request):
            result = server.render_gemini(image, [image])
        self.assertIn("gemini-3.1-flash-image:generateContent", sent["url"])
        self.assertEqual(len(sent["body"]["contents"][0]["parts"]), 3)
        self.assertEqual(sent["body"]["generationConfig"]["imageConfig"]["imageSize"], "1K")
        self.assertTrue(result["image"].startswith("data:image/png;base64,"))

    def test_gemini_rejects_five_garments(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ValueError, "one to four garments"):
                server.render_gemini("avatar", ["one", "two", "three", "four", "five"])

    def test_import_saves_forty_and_seller_controls_visibility_price_and_photos(self):
        def fake_search(query):
            return [{"listing_id": query + "-" + str(index), "item_name": query + " " + str(index),
                     "image": "https://media-assets.grailed.com/" + query.replace(" ", "-") + str(index),
                     "price": 50, "product_url": "https://www.grailed.com/listings/" + str(index)} for index in range(40)]
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "CATALOG_FILE", Path(directory) / "catalog.json"), patch.object(server, "CATALOG_SEED_FILE", Path(directory) / "seed.json"), patch.object(server, "search_grailed", side_effect=fake_search):
            result = server.import_catalog()
            self.assertEqual(result["imported"], 40)
            items = server.load_catalog()
            self.assertEqual(len(items), 40)
            self.assertTrue(all(not item["visible"] for item in items))
            first = items[0]
            updated = server.update_catalog_item(first["listing_id"], {"visible": True, "price": 75.25, "images": [first["image"], "https://media-assets.grailed.com/extra"]})
            self.assertEqual(updated["price"], 75.25)
            self.assertEqual(len(server.load_catalog()[0]["images"]), 2)
            self.assertEqual(len([item for item in server.load_catalog() if item["visible"]]), 1)
            server.import_catalog()
            self.assertTrue(server.load_catalog()[0]["visible"])

    def test_fetch_grailed_gallery_saves_multiple_photos(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "CATALOG_FILE", Path(directory) / "catalog.json"), patch.object(server, "CATALOG_SEED_FILE", Path(directory) / "seed.json"):
            server.save_catalog([{"listing_id": "42", "item_name": "Jacket", "images": ["https://media-assets.grailed.com/cover"], "image": "https://media-assets.grailed.com/cover", "visible": True}])
            with patch.object(server, "_grailed_session", return_value=None), patch.object(server, "_request", return_value=b'{"data":{"photos":[{"image_url":"https://media-assets.grailed.com/one"},{"image_url":"https://media-assets.grailed.com/two"}]}}'):
                item = server.fetch_grailed_photos("42")
            self.assertEqual(len(item["images"]), 3)
            self.assertEqual(server.load_catalog()[0]["image"], "https://media-assets.grailed.com/cover")

    def test_import_fills_forty_when_one_category_is_unavailable(self):
        def search(query):
            if query == "jeans":
                raise RuntimeError("temporarily unavailable")
            return [{"listing_id": query + str(index), "item_name": query,
                     "image": "https://media-assets.grailed.com/" + str(index)} for index in range(40)]
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "CATALOG_FILE", Path(directory) / "catalog.json"), patch.object(server, "CATALOG_SEED_FILE", Path(directory) / "seed.json"), patch.object(server, "search_grailed", side_effect=search):
            result = server.import_catalog()
            self.assertEqual(result["imported"], 40)
            self.assertEqual(len(result["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
