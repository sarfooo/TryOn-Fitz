"""Small API for the fitz clothing-to-outfit demo."""

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import auth

try:
    import tls_client
except ImportError:
    tls_client = None

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("FITZ_DATA_DIR", str(ROOT / "data")))
CATALOG_FILE = DATA_DIR / "catalog.json"
CATALOG_SEED_FILE = ROOT / "data" / "catalog.seed.json"
UPLOAD_DIR = Path(os.getenv("FITZ_UPLOAD_DIR", str(ROOT / "web" / "uploads")))
CATALOG_LOCK = threading.Lock()
MODEL = os.getenv("FITZ_IMAGE_MODEL", "gemini-3.1-flash-image")
MAX_BODY = 36 * 1024 * 1024
MAX_IMAGE = 5 * 1024 * 1024
ALLOWED_GARMENT_URLS = set()


def load_catalog():
    source = CATALOG_FILE if CATALOG_FILE.exists() else CATALOG_SEED_FILE
    if not source.exists():
        return []
    with source.open(encoding="utf-8") as file:
        items = json.load(file)
    for item in items:
        ALLOWED_GARMENT_URLS.update(url for url in item.get("images", []) if url.startswith("https://"))
    return items


def save_catalog(items):
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CATALOG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(CATALOG_FILE)


def catalog_item(listing):
    images = listing.get("images") or [listing["image"]]
    raw_price = listing.get("price") or 0
    if isinstance(raw_price, dict):
        raw_price = raw_price.get("amount") or 0
    try:
        price = round(float(raw_price), 2)
    except (TypeError, ValueError):
        price = 0
    return {"listing_id": listing["listing_id"], "item_name": listing["item_name"],
            "images": images, "image": images[0], "price": price,
            "grailed_price": price, "size": listing.get("size"),
            "category": listing.get("category"), "source": "Grailed",
            "product_url": listing.get("product_url"), "visible": False}


def import_catalog():
    """Save up to 40 distinct Grailed listings across outfit categories."""
    found = []
    seen = set()
    errors = []
    extras = []
    for query in ("black jacket", "graphic t shirt", "jeans", "sneakers"):
        try:
            results = search_grailed(query)
        except Exception as exc:
            errors.append(query + ": " + str(exc))
            continue
        extras.extend(results[10:])
        for listing in results[:10]:
            if listing["listing_id"] not in seen:
                found.append(catalog_item(listing))
                seen.add(listing["listing_id"])
    for listing in extras:
        if len(found) >= 40:
            break
        if listing["listing_id"] not in seen:
            found.append(catalog_item(listing))
            seen.add(listing["listing_id"])
    if not found:
        raise RuntimeError("Grailed import failed. " + "; ".join(errors))
    with CATALOG_LOCK:
        existing = load_catalog()
        by_id = {item["listing_id"]: item for item in existing}
        for item in found:
            by_id.setdefault(item["listing_id"], item)
        saved = list(by_id.values())
        save_catalog(saved)
    return {"imported": len(found), "total": len(saved), "errors": errors}


def update_catalog_item(listing_id, changes):
    with CATALOG_LOCK:
        items = load_catalog()
        item = next((row for row in items if row["listing_id"] == listing_id), None)
        if item is None:
            raise ValueError("Listing not found")
        if "item_name" in changes:
            name = str(changes["item_name"]).strip()
            if not 1 <= len(name) <= 160:
                raise ValueError("Name must be 1–160 characters")
            item["item_name"] = name
        if "price" in changes:
            try:
                price = round(float(changes["price"]), 2)
            except (TypeError, ValueError):
                raise ValueError("Price must be a number")
            if not 0 <= price <= 100000:
                raise ValueError("Price must be between $0 and $100,000")
            item["price"] = price
        if "visible" in changes:
            if not isinstance(changes["visible"], bool):
                raise ValueError("Visibility must be true or false")
            item["visible"] = changes["visible"]
        if "images" in changes:
            images = changes["images"]
            if not isinstance(images, list) or not 1 <= len(images) <= 12:
                raise ValueError("Use 1–12 images per item")
            for url in images:
                if not isinstance(url, str) or not (url.startswith("https://") or re.fullmatch(r"/uploads/[a-f0-9]{32}\.(jpg|png|webp)", url)):
                    raise ValueError("Images must be HTTPS URLs or uploaded files")
            item["images"] = images
            item["image"] = images[0]
            ALLOWED_GARMENT_URLS.update(url for url in images if url.startswith("https://"))
        if "store_url" in changes:
            item["store_url"] = validate_store_url(changes["store_url"])
        if "sizes" in changes:
            item["sizes"] = validate_sizes(changes["sizes"])
        save_catalog(items)
        return item


def validate_store_url(value):
    if value in (None, ""):
        return None
    parsed = urllib.parse.urlparse(str(value))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Store link must be an HTTPS URL")
    return str(value)


def validate_sizes(value):
    if not isinstance(value, dict) or set(value) != {"S", "M", "L"}:
        raise ValueError("Set stock for S, M, and L")
    sizes = {}
    for size, stock in value.items():
        if isinstance(stock, bool) or not isinstance(stock, int) or not 0 <= stock <= 100000:
            raise ValueError("Size stock must be a nonnegative whole number")
        sizes[size] = stock
    return sizes


def create_catalog_item(payload):
    name = str(payload.get("item_name") or "").strip()
    if not 1 <= len(name) <= 160:
        raise ValueError("Name is required (1–160 characters)")
    try:
        price = round(float(payload.get("price")), 2)
    except (TypeError, ValueError):
        raise ValueError("Price is required")
    if not 0 < price <= 100000:
        raise ValueError("Price must be greater than $0")
    image = payload.get("image")
    if not isinstance(image, str) or not image:
        raise ValueError("A product picture is required")
    sizes = validate_sizes(payload.get("sizes", {"S": 1, "M": 1, "L": 1}))
    store_url = validate_store_url(payload.get("store_url"))
    if not isinstance(payload.get("visible", False), bool):
        raise ValueError("Visibility must be true or false")
    data, mime = _load_image(image) if image.startswith("data:") else (None, None)
    if data is not None:
        suffix = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        image = "/uploads/" + uuid4().hex + "." + suffix
        (UPLOAD_DIR / image.rsplit("/", 1)[-1]).write_bytes(data)
    elif not image.startswith("https://"):
        raise ValueError("Picture must be an uploaded image or HTTPS URL")
    item = {"listing_id": "brand-" + uuid4().hex, "item_name": name, "price": price,
            "image": image, "images": [image], "category": str(payload.get("category") or "Clothing")[:80],
            "source": "Admin", "sizes": sizes, "store_url": store_url,
            "visible": payload.get("visible", False)}
    with CATALOG_LOCK:
        items = load_catalog()
        items.append(item)
        save_catalog(items)
    if image.startswith("https://"):
        ALLOWED_GARMENT_URLS.add(image)
    return item


def upload_item_image(listing_id, data_url):
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise ValueError("Upload a JPEG, PNG, or WebP image")
    data, mime = _load_image(data_url)
    suffix = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
    with CATALOG_LOCK:
        items = load_catalog()
        item = next((row for row in items if row["listing_id"] == listing_id), None)
        if item is None:
            raise ValueError("Listing not found")
        if len(item["images"]) >= 12:
            raise ValueError("An item can have at most 12 images")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        from uuid import uuid4
        url = "/uploads/" + uuid4().hex + "." + suffix
        (UPLOAD_DIR / url.rsplit("/", 1)[-1]).write_bytes(data)
        item["images"].append(url)
        save_catalog(items)
        return item


def fetch_grailed_photos(listing_id):
    """Read the public listing detail for its full photo gallery when available."""
    if not re.fullmatch(r"\d+", listing_id):
        raise ValueError("Only numeric Grailed listings can fetch photos")
    url = "https://www.grailed.com/api/listings/" + listing_id
    session = _grailed_session()
    result = session.get(url).json() if session else json.loads(_request(url))
    detail = result.get("data") or result
    detail = detail.get("listing") or detail
    photos = detail.get("photos") or detail.get("images") or []
    images = []
    for photo in photos:
        image = photo if isinstance(photo, str) else (photo.get("image_url") or photo.get("url") if isinstance(photo, dict) else None)
        if isinstance(image, str) and image.startswith("https://") and image not in images:
            images.append(image)
        if len(images) >= 12:
            break
    if not images:
        raise RuntimeError("Grailed did not return additional photos for this listing")
    current = next((item for item in load_catalog() if item["listing_id"] == listing_id), None)
    if current is None:
        raise ValueError("Listing not found")
    merged = list(current["images"])
    merged.extend(image for image in images if image not in merged)
    return update_catalog_item(listing_id, {"images": merged[:12]})

SAMPLES = [
    {"listing_id": "sample-shirt", "item_name": "Archive shirt", "image": "https://raw.githubusercontent.com/sarfooo/-fitz/main/outfits/shirt/2dc5b07853d84dbbb1ac40a5816dd97e.jpg", "category": "Top", "source": "fitz sample", "product_url": None},
    {"listing_id": "sample-pants", "item_name": "Archive pants", "image": "https://raw.githubusercontent.com/sarfooo/-fitz/main/outfits/pants/4479187819f8485689f45a70c05ed6c0.jpg", "category": "Bottom", "source": "fitz sample", "product_url": None},
]


def _request(url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _grailed_session():
    """Use the same browser-like TLS session as fitz when installed."""
    if tls_client is None:
        return None
    session = tls_client.Session(client_identifier="chrome112", random_tls_extension_order=True)
    session.headers = {
        "accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    }
    return session


def search_grailed(query, page=0):
    """Use fitz's Grailed session, dynamic Algolia credentials, and listing index."""
    if not query.strip():
        return []
    session = _grailed_session()
    shop = session.post("https://www.grailed.com/shop").text if session else _request("https://www.grailed.com/shop", data=b"").decode("utf-8", "replace")
    match = re.search(r'app_id\\?":"([^"]+)', shop)
    if not match:
        raise RuntimeError("Grailed search configuration is unavailable")
    key_response = session.post("https://www.grailed.com/api/algolia/keys").json() if session else json.loads(_request("https://www.grailed.com/api/algolia/keys", data=b""))
    key = key_response["data"]["search_key"]
    params = urllib.parse.urlencode({"query": query, "hitsPerPage": 40, "page": page, "analytics": "false"})
    payload = json.dumps({"requests": [{"indexName": "Listing_by_listing_quality_production", "params": params}]}).encode()
    url = "https://mnrwefss2q-dsn.algolia.net/1/indexes/*/queries"
    if session:
        session.headers["x-algolia-application-id"] = match.group(1)
        session.headers["x-algolia-api-key"] = key
        results = session.post(url, json=json.loads(payload)).json()
    else:
        raw = _request(url, data=payload, headers={"Content-Type": "application/json", "x-algolia-application-id": match.group(1), "x-algolia-api-key": key})
        results = json.loads(raw)
    hits = results.get("results", [{}])[0].get("hits", [])
    items = []
    for hit in hits:
        cover = hit.get("cover_photo") or {}
        image = cover.get("image_url") or cover.get("url")
        if not image:
            continue
        ALLOWED_GARMENT_URLS.add(image)
        listing_id = str(hit.get("id") or hit.get("objectID") or "")
        if not listing_id:
            continue
        images = [image]
        for photo in hit.get("photos") or hit.get("images") or []:
            url = photo if isinstance(photo, str) else (photo.get("image_url") or photo.get("url") if isinstance(photo, dict) else None)
            if isinstance(url, str) and url.startswith("https://") and url not in images:
                images.append(url)
            if len(images) >= 12:
                break
        ALLOWED_GARMENT_URLS.update(images)
        items.append({
            "listing_id": listing_id,
            "item_name": hit.get("title") or "Untitled listing",
            "image": image,
            "images": images,
            "category": hit.get("category_path") or hit.get("category"),
            "price": hit.get("price"),
            "size": hit.get("size"),
            "source": "Grailed",
            "product_url": hit.get("url") if str(hit.get("url") or "").startswith("https://www.grailed.com/") else "https://www.grailed.com/listings/" + listing_id,
        })
    return items


def _load_image(value):
    if not isinstance(value, str):
        raise ValueError("Each image must be a data URL or HTTPS URL")
    if value.startswith("data:image/"):
        header, encoded = value.split(",", 1)
        mime = header[5:].split(";", 1)[0]
        data = base64.b64decode(encoded, validate=True)
    elif re.fullmatch(r"/uploads/[a-f0-9]{32}\.(jpg|png|webp)", value):
        path = UPLOAD_DIR / value.rsplit("/", 1)[-1]
        data = path.read_bytes()
        mime = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[path.suffix]
    else:
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or (parsed.hostname != "raw.githubusercontent.com" and value not in ALLOWED_GARMENT_URLS):
            raise ValueError("Image URL must come from a Grailed search or the fitz samples")
        data = _request(value)
        mime = "image/jpeg" if data.startswith(b"\xff\xd8") else "image/png" if data.startswith(b"\x89PNG") else "image/webp" if data.startswith(b"RIFF") else ""
    if mime not in {"image/jpeg", "image/png", "image/webp"} or not data or len(data) > MAX_IMAGE:
        raise ValueError("Images must be JPEG, PNG, or WebP and under 5 MB")
    return data, mime


def _image_part(value):
    data, mime = _load_image(value)
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}


def render_gemini(avatar, garments, model=MODEL):
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Set GOOGLE_API_KEY on the server to enable real rendering")
    if not isinstance(garments, list) or not 1 <= len(garments) <= 4:
        raise ValueError("Select one to four garments")
    parts = [{"text": (
        "Create one photorealistic, full-body fashion lookbook image. The first image is the person; "
        "all subsequent images are garments. Dress the same person in every selected garment, preserving "
        "their face, body proportions, garment colors, graphics, and cut. Show the entire person head to shoes, "
        "standing front-facing against a plain white studio background. Do not invent extra garments. "
        "This is a visual styling preview, not an exact fit or size measurement."
    )}, _image_part(avatar)]
    parts.extend(_image_part(value) for value in garments)
    body = json.dumps({"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "2:3", "imageSize": "1K"}}}).encode()
    url = "https://generativelanguage.googleapis.com/v1/models/" + urllib.parse.quote(model, safe="") + ":generateContent"
    started = time.monotonic()
    raw = _request(url, body, {"Content-Type": "application/json", "x-goog-api-key": os.environ["GOOGLE_API_KEY"]}, timeout=180)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    result = json.loads(raw)
    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            image = part.get("inlineData") or part.get("inline_data")
            if image and image.get("data"):
                return {"image": "data:" + (image.get("mimeType") or image.get("mime_type") or "image/png") + ";base64," + image["data"], "provider": "gemini", "model": model, "elapsed_ms": elapsed_ms, "usage": result.get("usageMetadata", {})}
    raise RuntimeError("Image model returned no render")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def translate_path(self, path):
        url_path = urllib.parse.urlparse(path).path
        if re.fullmatch(r"/uploads/[a-f0-9]{32}\.(jpg|png|webp)", url_path):
            return str(UPLOAD_DIR / url_path.rsplit("/", 1)[-1])
        return super().translate_path(path)

    def send_json(self, status, payload, cookie=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def current_user(self):
        return auth.user_from_cookie(self.headers.get("Cookie"))

    def require_admin(self):
        user = self.current_user()
        if user and user["role"] == "admin":
            return True
        self.send_json(403 if user else 401, {"error": "Brand owner access required"})
        return False

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        expected = self.headers.get("Host", "")
        if parsed.scheme in {"http", "https"} and parsed.netloc == expected:
            return True
        self.send_json(403, {"error": "Cross-origin request blocked"})
        return False

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_BODY:
            raise ValueError("Request is too large or empty")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload

    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        if path.path == "/api/me":
            return self.send_json(200, {"user": self.current_user()})
        if path.path == "/api/config":
            return self.send_json(200, {"image_model": {"enabled": bool(os.getenv("GOOGLE_API_KEY")), "model": MODEL, "max_garments": 4}})
        if path.path == "/api/catalog":
            return self.send_json(200, {"items": [item for item in load_catalog() if item.get("visible")]})
        if path.path == "/api/admin/catalog":
            if not self.require_admin(): return
            return self.send_json(200, {"items": load_catalog()})
        if path.path == "/api/samples":
            return self.send_json(200, {"items": SAMPLES})
        if path.path == "/api/search":
            query = urllib.parse.parse_qs(path.query).get("q", [""])[0][:100]
            try:
                page = max(0, min(10, int(urllib.parse.parse_qs(path.query).get("page", ["0"])[0])))
            except ValueError:
                return self.send_json(400, {"error": "Page must be a number"})
            try:
                return self.send_json(200, {"items": search_grailed(query, page), "page": page, "source": "Grailed"})
            except Exception as exc:
                return self.send_json(502, {"error": "Live Grailed search is unavailable: " + str(exc)})
        if path.path.startswith("/api/"):
            return self.send_json(404, {"error": "API route not found"})
        if path.path == "/seller.html":
            user = self.current_user()
            if not user or user["role"] != "admin":
                self.send_response(303)
                self.send_header("Location", "/account.html?next=/seller.html")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
        if path.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if not self.same_origin(): return
        try:
            if self.path == "/api/signup":
                payload = self.read_json()
                user = auth.create_user(payload.get("email"), payload.get("password"))
                token, user = auth.login(payload.get("email"), payload.get("password"))
                return self.send_json(201, {"user": user}, auth.session_cookie(token))
            if self.path == "/api/login":
                payload = self.read_json()
                token, user = auth.login(payload.get("email"), payload.get("password"))
                return self.send_json(200, {"user": user}, auth.session_cookie(token))
            if self.path == "/api/logout":
                auth.logout(self.headers.get("Cookie"))
                return self.send_json(200, {"ok": True}, auth.clear_cookie())
            if self.path.startswith("/api/admin/") and not self.require_admin(): return
            if self.path == "/api/admin/items":
                return self.send_json(201, {"item": create_catalog_item(self.read_json())})
            if self.path == "/api/admin/import":
                return self.send_json(200, import_catalog())
            if self.path.startswith("/api/admin/items/") and self.path.endswith("/upload"):
                listing_id = self.path.split("/")[4]
                return self.send_json(200, {"item": upload_item_image(listing_id, self.read_json().get("image"))})
            if self.path.startswith("/api/admin/items/") and self.path.endswith("/fetch-photos"):
                listing_id = self.path.split("/")[4]
                return self.send_json(200, {"item": fetch_grailed_photos(listing_id)})
            if self.path == "/api/render":
                payload = self.read_json()
                return self.send_json(200, render_gemini(payload.get("avatar"), payload.get("garments")))
            return self.send_json(404, {"error": "Not found"})
        except (ValueError, KeyError) as exc:
            self.send_json(400, {"error": str(exc)})
        except urllib.error.HTTPError as exc:
            self.send_json(502, {"error": "Image provider returned HTTP " + str(exc.code)})
        except Exception as exc:
            self.send_json(502, {"error": str(exc)})

    def do_PATCH(self):
        if not self.same_origin(): return
        if self.path == "/api/me/mannequin":
            user = self.current_user()
            if not user: return self.send_json(401, {"error": "Log in to save your mannequin"})
            try:
                return self.send_json(200, {"user": auth.set_mannequin(user["id"], self.read_json().get("size"))})
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
        if not self.path.startswith("/api/admin/items/"):
            return self.send_json(404, {"error": "Not found"})
        if not self.require_admin(): return
        try:
            listing_id = self.path.split("/")[4]
            return self.send_json(200, {"item": update_catalog_item(listing_id, self.read_json())})
        except (ValueError, KeyError) as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(502, {"error": str(exc)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    auth.bootstrap_demo_shopper()
    admin = auth.bootstrap_admin()
    if admin:
        print("Brand owner login: " + admin[0] + " / " + admin[1], flush=True)
    print("fitz demo: http://localhost:" + str(port), flush=True)
    ThreadingHTTPServer((os.getenv("HOST", "127.0.0.1"), port), Handler).serve_forever()
