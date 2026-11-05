"""Run a real Grailed search from a networked terminal."""

import sys

from server import _load_image, search_grailed, tls_client


def main():
    if tls_client is None:
        print("tls_client is unavailable in this Python installation", file=sys.stderr)
        return 1
    try:
        items = search_grailed("black jacket")
    except Exception as exc:
        print("Grailed search failed: " + str(exc), file=sys.stderr)
        return 1
    if not items:
        print("Grailed search returned no items", file=sys.stderr)
        return 1
    print("Grailed search OK: {} listings".format(len(items)))
    for item in items[:3]:
        print("- {} | {} | {}".format(item["listing_id"], item["item_name"], item["image"]))
    try:
        image, mime = _load_image(items[0]["image"])
    except Exception as exc:
        print("Listing search worked, but downloading its image failed: " + str(exc), file=sys.stderr)
        return 1
    print("First listing image OK: {} bytes, {}".format(len(image), mime))
    return 0


if __name__ == "__main__":
    sys.exit(main())
