# TryOn Fitz

A small, standalone demo extracted from [the fitz hackathon repo](https://github.com/sarfooo/-fitz). It has a shopper catalog, account pages, a public seller studio preview with protected editing, saved Grailed inventory, a basic mannequin preview, and optional Gemini photo previews. The interface uses a plain white mock design.

## Run

Requires Python 3.9 or newer. No Supabase project is needed. For the most reliable Grailed search, install the same `tls-client` package used by the original fitz scraper into your existing Python:

```sh
python3 -m pip install --user -r requirements-grailed.txt
```

The server can use Python's built-in HTTP client if `tls-client` is unavailable, although Grailed may reject that client.

```sh
cd /Users/michael/fitz-demo
python3 server.py
```

Open `http://localhost:8000` for the shop. The built-in shopper demo login is `shopper@tryonfitz.demo` / `DemoShopper123`. On each start, the server prints a generated brand-owner login in the terminal. Set `FITZ_ADMIN_EMAIL` and `FITZ_ADMIN_PASSWORD` to choose your own. Anyone can preview published inventory at `/seller.html`. Sign in as a brand owner to manage inventory. Signup, login, sessions, and mannequin choices are simulated in server memory and reset on restart. The catalog works without a Gemini key. The repository includes 40 real Grailed listings in `data/catalog.seed.json`; edits are written to `data/catalog.json`. Seller uploads live in `web/uploads/`. These data files are local and ignored by Git.

## Deploy the prototype

The repository includes a Render Blueprint in `render.yaml`. Connect this GitHub repository to Render and create a Blueprint from it. Render will use `PORT` and the Blueprint sets `HOST=0.0.0.0`. Set `FITZ_ADMIN_EMAIL` and `FITZ_ADMIN_PASSWORD` in the service environment if a chosen admin login is needed. The free service is suitable for a temporary demo, but its filesystem is ephemeral: catalog edits and uploaded pictures can disappear on restart or after idle spin-down. Simulated accounts and mannequin choices always reset on restart. For durable catalog data, use a paid persistent disk mounted at `/var/data` and set both `FITZ_DATA_DIR=/var/data` and `FITZ_UPLOAD_DIR=/var/data/uploads` in the service environment. The seed catalog remains available after a reset.

The admin can add products with a name, price, picture, S/M/L stock and optional store URL. They can publish or hide products, edit details and photos, and import Grailed listings. Shoppers see only published items, can open a product gallery, choose an available size, and try the item on an S/M/L mannequin. The size choice persists for logged-in shoppers while the server is running. Buy appears only when a product has a store URL. The published sample points to its Grailed listing; no issuederror URL is bundled with this prototype.

This is a small MVC-style local demo: `auth.py` holds temporary users and sessions in server memory, the catalog functions in `server.py` store product data, `Handler` in `server.py` handles requests, and `web/` holds the views. The mannequin preview is a local image overlay with a five-second timeout and Retry option. It is an approximate visual preview, especially for nontransparent product photos; it does not measure fit. Saved looks are planned for Sprint 2.

### Gemini image rendering

Set `GOOGLE_API_KEY` in the server environment and restart the server. For example, run `export GOOGLE_API_KEY='your-key'` before `python3 server.py`. `FITZ_IMAGE_MODEL` defaults to `gemini-3.1-flash-image`. The server requests a 1K, 2:3 image and accepts up to four garments. [Google's model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image) confirms this model supports image inputs and image generation. Google lists [no free API tier](https://ai.google.dev/gemini-api/docs/pricing) for this image model. A Gemini Pro subscription does not automatically provide API billing; the API key needs access to the image model.

The render is a visual styling preview, not a measurement of actual fit. The default model photo was replaced with a drawn placeholder; upload a full-body model photo to enable rendering. Grailed search relies on an undocumented upstream flow, so it can fail when Grailed changes it or blocks automated access. Existing saved inventory remains available when Grailed is offline.

To test a real Grailed search separately from the UI, run `python3 test_grailed_live.py` from a networked terminal. It prints the listing count, first three returned items, and whether the first garment image can be downloaded for rendering.

## What was extracted

| Original fitz feature | This demo |
| --- | --- |
| Grailed TLS session and Algolia search in `backend/scraper/api.py` | `/api/search` and saved 40-item import |
| Multi-image Gemini composition in `backend/app/services/banana.py` | `/api/render` |
| Avatar + garment selection in `TryOnPanel.tsx` | Client shop fitting room |
| Supabase auth, credits, render jobs, angles | Temporary in-memory auth supports the Sprint 1 demo; credits, jobs, and angles are omitted |

## Optimization plan

The original `POST /tryon/fit` captions **each** selected garment with Gemini, then sends the avatar and all garment images to Nano Banana 2. This demo sends the images directly to Gemini first, avoiding those extra captioning calls. The `/api/render` response includes `model`, `elapsed_ms`, and available `usage`. Score garment fidelity, identity preservation, anatomy, and latency on real Grailed listings. Generate extra camera angles only when a user requests them; the original path can make four additional image calls.

Current public list prices from [Google's Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) are roughly **$0.067 per 1K image** for Gemini 3.1 Flash Image, plus image/text input and any text output. A four-angle expansion is therefore roughly another **$0.268 in image output** before input costs. Google lists Flash Lite Image at a lower price; benchmark its garment and identity fidelity before using it. OpenAI's [image API docs](https://developers.openai.com/api/reference/resources/images/methods/generate) say the original fallback `gpt-image-1` was shut down on October 23, 2026, so that fallback needs migration before comparison.

Suggested measurement set: 20 outfits (single piece, top + bottom, layered outerwear, graphics, unusual silhouettes), three runs each, fixed 1K output and prompt. Capture total cost from Gemini billing/usage, median and p95 latency, and blind 1–5 quality ratings. Cache completed outputs by avatar hash, ordered garment hashes, model, and prompt version to avoid repeat calls.

## Verification

Run `python3 -m unittest discover -s tests -v`. The tests cover accounts, duplicate email rejection, login, logout, saved mannequin choice, admin access checks, product validation, stock, store URLs, Grailed catalog persistence, and Gemini request construction. The user's networked terminal verified Grailed search. A real Gemini render still requires a key and a networked run.
