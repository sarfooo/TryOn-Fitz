# TryOn Fitz

A small, standalone demo extracted from [the fitz hackathon repo](https://github.com/sarfooo/-fitz). It has a client shop, a local seller panel, saved Grailed inventory, photo galleries, and Gemini outfit previews. A live Grailed search on Michael's Mac returned 40 listings on November 4, 2026.

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

Open `http://localhost:8000` for the client shop and `http://localhost:8000/seller.html` for the seller panel. The catalog works without a Gemini key. The repository includes 40 real Grailed listings in `data/catalog.seed.json`. On a fresh checkout, the seller panel shows those pieces immediately; edits are written to `data/catalog.json`. The import button can fetch more live listings from jackets, tees, jeans, and sneakers. Seller uploads live in `web/uploads/`. Edits and uploads survive server restarts. Seed and new imports start hidden until the seller publishes them.

The seller can edit each item's display name and price, publish or hide it, fetch the full Grailed gallery when available, and add, upload, remove, or reorder up to 12 photos. The client can open a product to view its gallery, add up to four pieces to an outfit, and follow the original Grailed listing link. This is a local demo with no checkout or seller authentication; keep the server bound to localhost until those are built.

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
| Supabase auth, credits, render jobs, angles | Omitted from the focused demo |

## Optimization plan

The original `POST /tryon/fit` captions **each** selected garment with Gemini, then sends the avatar and all garment images to Nano Banana 2. This demo sends the images directly to Gemini first, avoiding those extra captioning calls. The `/api/render` response includes `model`, `elapsed_ms`, and available `usage`. Score garment fidelity, identity preservation, anatomy, and latency on real Grailed listings. Generate extra camera angles only when a user requests them; the original path can make four additional image calls.

Current public list prices from [Google's Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) are roughly **$0.067 per 1K image** for Gemini 3.1 Flash Image, plus image/text input and any text output. A four-angle expansion is therefore roughly another **$0.268 in image output** before input costs. Google lists Flash Lite Image at a lower price; benchmark its garment and identity fidelity before using it. OpenAI's [image API docs](https://developers.openai.com/api/reference/resources/images/methods/generate) say the original fallback `gpt-image-1` was shut down on October 23, 2026, so that fallback needs migration before comparison.

Suggested measurement set: 20 outfits (single piece, top + bottom, layered outerwear, graphics, unusual silhouettes), three runs each, fixed 1K output and prompt. Capture total cost from Gemini billing/usage, median and p95 latency, and blind 1–5 quality ratings. Cache completed outputs by avatar hash, ordered garment hashes, model, and prompt version to avoid repeat calls.

## Verification

Run `python3 -m unittest discover -s tests -v`. The local tests cover Grailed request construction, catalog persistence and publishing, Gemini request construction, and garment limits. The user's networked terminal verified Grailed search. A real render still requires a Gemini API key and a networked run.
