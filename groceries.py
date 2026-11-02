"""Grocery cart builder: OurGroceries "Superstore" list -> picker page -> PC Express cart.

Run: python groceries.py   (opens the picker at http://localhost:8766)

Options for each item come from a live Superstore search, ranked by what the household
has bought before (order history) and by what you picked last time (picks.json).
Checkout, delivery window and payment stay in the PC Express app.
"""

import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
import webbrowser
import winreg
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "pcexpress-mcp-server"))

from ourgroceries import OurGroceries  # noqa: E402
from pcexpress_mcp_server import PCExpressAPI  # noqa: E402
from pcid_token import TokenManager  # noqa: E402

# After every order the profile still points at that order's cart, so the library warns
# "not an open superstore cart" and finds the new one. Expected; keep the window quiet.
logging.getLogger("pcexpress-mcp").setLevel(logging.ERROR)

# settings.json (optional, never needed so far) overrides the store or list: {"store": "1234", "list": "Superstore"}.
# Store numbers come from the /pickup-locations endpoint.
_settings = json.loads((HERE / "settings.json").read_text(encoding="utf-8")) if (HERE / "settings.json").exists() else {}
BANNER = "superstore"  # delivery set in the app
LIST_NAME = _settings.get("list", "Superstore")
PORT = 8766  # 8765 is the Todo Board
HISTORY = HERE / "history.json"  # product code -> times bought, last bought, name as last bought
PICKS = HERE / "picks.json"  # list item name -> the products you chose last time
STAPLES = HERE / "staples.json"  # always-offered items that never make the list; edited from the page
CART_URL = "https://www.realcanadiansuperstore.ca/en"  # ponytail: /en/cart 404s; swap in the real cart URL once known
OPTIONS = 5
SHOP_SIZE = 40  # most-bought products in the My Shop strip

api = PCExpressAPI(TokenManager(), None, "", BANNER)
# The store the account last ordered from, so each household's copy finds its own
STORE = api.store_id = str(_settings.get("store") or api.get_customer().get("lastStoreId") or "")
if not STORE:
    raise SystemExit("Your account has no store yet. Place one order in the PC Express app, then try again.")


def env(name):
    """Env var, falling back to the Windows user env (set after this shell started)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return ""  # not set: OurGroceries is optional


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_json(path, data):
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def key(name):
    return re.sub(r"\s+", " ", name.strip().lower())


# --- OurGroceries -------------------------------------------------------------


def parse_item(value):
    """'Milk (2)' or '3 cans of soup' -> (name, qty). OurGroceries keeps quantity in the text."""
    value = value.strip()
    m = re.match(r"^(.*?)\s*\((\d+)\)$", value)
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(\d+)\s+(?:(?:cans?|bags?|boxes?|packs?|jars?|bottles?|cartons?)\s+of\s+|x\s+)?(.+)$", value, re.I)
    if m and int(m.group(1)) <= 24:  # ponytail: '2% milk' has no space after 2, so it stays a name
        return m.group(2).strip(), int(m.group(1))
    return value, 1


assert parse_item("Milk (2)") == ("Milk", 2)
assert parse_item("3 cans of elphagetti") == ("elphagetti", 3)
assert parse_item("2 bread") == ("bread", 2)
assert parse_item("2% milk") == ("2% milk", 1)
assert parse_item("eggs") == ("eggs", 1)


async def _og_list():
    og = OurGroceries(env("OURGROCERIES_USER"), env("OURGROCERIES_PASSWORD"))
    await og.login()
    lists = (await og.get_my_lists())["shoppingLists"]
    lid = next((lst["id"] for lst in lists if key(lst["name"]) == key(LIST_NAME)), None)
    if not lid:
        raise RuntimeError(f'No OurGroceries list called "{LIST_NAME}". Make one with that name, or change "list" in settings.json.')
    return og, lid


async def _og_items():
    og, lid = await _og_list()
    items = (await og.get_list_items(lid))["list"]["items"]
    # The server marks a crossed item with crossedOffAt; the library still reports crossedOff false
    return [(*parse_item(i["value"]), i["id"]) for i in items if not (i.get("crossedOff") or i.get("crossedOffAt"))]


async def _cross_off(item_ids):
    og, lid = await _og_list()
    for item_id in item_ids:
        await og.toggle_item_crossed_off(lid, item_id, cross_off=True)


def og_items():
    """(name, qty, OurGroceries item id) for everything not crossed off."""
    return asyncio.run(_og_items())


def cross_off(item_ids):
    """Cross items off the list, same as ticking them in the app (undo there)."""
    if item_ids:
        asyncio.run(_cross_off(item_ids))


# --- Order history ------------------------------------------------------------


def product_code(p):
    pid = str(p.get("id") or "")
    return pid if "_" in pid else f"{p['articleNumber']}_{p['baseUnit']}"


def load_history():
    """Times each product was bought, across online and in-store orders. Rebuilt weekly."""
    if HISTORY.exists() and time.time() - HISTORY.stat().st_mtime < 7 * 86400:
        hist = load_json(HISTORY)
        if all("name" in h for h in hist.values()):  # older caches had counts only
            return hist
    orders = api.get_historical_orders()["orderHistory"]

    def entries(o):
        try:
            return api.get_order_details(o["id"])["orderDetails"]["entries"] or []
        except Exception:
            return []  # one unreadable order shouldn't sink the rest

    hist = {}
    with ThreadPoolExecutor(6) as ex:
        for o, ents in zip(orders, ex.map(entries, orders)):
            placed = o.get("placed") or ""
            for e in ents:
                p = e["product"]
                h = hist.setdefault(product_code(p), {"count": 0, "last": ""})
                h["count"] += 1
                if placed >= h["last"]:
                    h.update(
                        last=placed,
                        name=p.get("productName") or "",
                        brand=p.get("brand") or "",
                        size=p.get("productTitleSizeDetail") or "",
                        price=p.get("price"),
                        img=p.get("primaryImage") or "",
                    )
    save_json(HISTORY, hist)
    return hist


# --- Search and options -------------------------------------------------------


def card(p, hist):
    prices = p.get("prices") or {}
    price = prices.get("price") or {}
    was = prices.get("wasPrice") or {}
    unit = (prices.get("comparisonPrices") or [{}])[0]
    imgs = p.get("imageAssets") or [{}]
    return {
        "code": p["code"],
        "name": p.get("name") or "",
        "brand": p.get("brand") or "",
        "size": p.get("packageSize") or "",
        "price": price.get("value"),
        "per": price.get("unit"),
        "sale": price.get("type") == "SPECIAL",
        "saleEnds": (price.get("expiryDate") or "")[:10] if price.get("type") == "SPECIAL" else "",
        "was": was.get("value"),
        "unitPrice": f"${unit['value']:.2f}/{unit.get('quantity', '')}{unit.get('unit', '')}"
        if unit.get("value")
        else "",
        "img": imgs[0].get("smallUrl") or imgs[0].get("thumbnailUrl") or "",
        "inStock": p.get("stockStatus") == "OK",
        "bought": hist.get(p["code"], {}).get("count", 0),
    }


def search(term, hist, size=24):
    body = {
        "lang": "en",
        "term": term,
        "storeId": STORE,
        "banner": BANNER,
        "pagination": {"from": 0, "size": size},
    }
    results = api._request("POST", f"{api.BASE_URL}/products/search", json=body).json()
    return [
        card(p, hist)
        for p in results.get("results") or []
        if p.get("shoppable", True) and not p.get("sponsored")
    ]


STOP = {"a", "an", "the", "of", "and", "some"}


def words(text):
    # crude singular so 'eggs' matches 'egg'; whole words so 'bread' skips 'flatbreads'
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9%]+", text.lower()) if w not in STOP}


assert words("Natural Bakery Rye Bread") >= words("bread")
assert not words("Garlic Naan Flatbreads") >= words("bread")


def regulars(term, hist, n=3, min_count=3):
    """Your most-bought products whose name has every word of the term. The store's
    search misses these (Natural Bakery rye, bought 31x, never came up for 'bread').
    min_count keeps one-off buys out ('vegetable' was matching crackers and pot pie)."""
    want = words(term)
    if not want:
        return []
    hits = [
        (h["count"], code)
        for code, h in hist.items()
        if h["count"] >= min_count and want <= words(f"{h.get('brand', '')} {h.get('name', '')}")
    ]
    return [code for _, code in sorted(hits, reverse=True)[:n]]


def live_card(code, found, hist, fallback):
    """Current price for a known product: from this search, else a search by its own
    name, else the saved card marked stale."""
    hit = next((c for c in found if c["code"] == code), None)
    if hit:
        return hit
    h = {**fallback, **hist.get(code, {})}
    try:
        term = f"{h.get('brand', '')} {h.get('name', '')}"
        hit = next((c for c in search(term, hist, 8) if c["code"] == code), None)
    except Exception:
        hit = None
    return hit or {
        "code": code,
        "name": h.get("name", ""),
        "brand": h.get("brand", ""),
        "size": h.get("size", ""),
        "price": h.get("price"),
        "per": h.get("per"),
        "sale": False,
        "saleEnds": "",
        "was": None,
        "unitPrice": "",
        "img": h.get("img", ""),
        "inStock": True,
        "bought": hist.get(code, {}).get("count", 0),
        "stale": True,
    }


def options(name, term, hist, picks):
    """Last picks first, then your regulars, then the store's results by times bought.
    Only past picks are pre-selected; history alone guessed wrong (egg whites -> egg white noodles)."""
    try:
        found = search(term, hist)[:12]  # ponytail: past ~12 the store's matches turn to junk
    except Exception as e:
        return {"options": [], "selected": [], "error": f"Search failed: {e}"}
    picked = picks.get(key(name)) or []
    if isinstance(picked, dict):  # saved before multi-select
        picked = [picked]
    pinned = [live_card(p["code"], found, hist, p) for p in picked]
    pinned += [live_card(c, found, hist, {}) for c in regulars(term, hist)]
    # sorted() is stable, so ties keep the store's relevance order
    ranked, seen = [], set()
    for c in pinned + sorted(found, key=lambda c: -c["bought"]):
        if c["code"] not in seen:
            seen.add(c["code"])
            ranked.append(c)
    return {"options": ranked[: max(OPTIONS, len(picked))], "selected": [p["code"] for p in picked]}


# --- My Shop ------------------------------------------------------------------


def details(code, hist):
    """Live card plus department for one product. Search results carry no department;
    the product endpoint does (breadcrumbs Food > Fruits & Vegetables > ...) but 400s without date."""
    params = {"lang": "en", "date": time.strftime("%d%m%Y"), "pickupType": "STORE", "storeId": STORE, "banner": BANNER}
    d = api._request("GET", f"{api.BASE_URL}/products/{code}", params=params).json()
    o = (d.get("offers") or [{}])[0]  # price, stock and the rest live on the offer here
    crumbs = d.get("breadcrumbs") or [{"name": "Other"}]
    return {**card({**d, **o, "prices": o, "code": d["code"]}, hist), "dept": crumbs[min(1, len(crumbs) - 1)]["name"]}


def my_shop(hist):
    """Your most-bought products, live, like the app's My Shop. Zero-price lines
    (EARN PHYSICAL STAMP) and one-off buys stay out; products the store no longer has drop."""
    top = sorted(((h["count"], c) for c, h in hist.items() if h["count"] >= 3 and h.get("price")), reverse=True)

    def one(code):
        try:
            return details(code, hist)
        except Exception:
            return None

    with ThreadPoolExecutor(6) as ex:
        return [c for c in ex.map(one, [c for _, c in top[:SHOP_SIZE]]) if c]


# --- Cart ---------------------------------------------------------------------


def is_placed(cart):
    """A cart behind an order still in its edit window. Adding to it would change the placed
    order. Placed (2026-10-19): order group SUBMITTED. Fresh (2026-10-20): group OPEN, and it
    has an orderId too, so only the status tells them apart. Anything but OPEN counts as placed."""
    return any(o.get("status") != "OPEN" for o in cart.get("orders") or [])


assert is_placed({"orders": [{"orderId": "x", "status": "SUBMITTED"}]})
assert not is_placed({"orders": [{"orderId": "x", "status": "OPEN"}]})
assert is_placed({"orders": [{"orderId": "x"}]})  # no status: assume placed


def ensure_cart():
    """An open cart to build into, created if the account has none (each order closes it).
    Never a placed order's cart. None when the only cart is an order still open for edits."""
    api._cart_id = None  # look it up fresh: after an order, a remembered id is that order's cart
    try:
        cart_id = api.cart_id
    except ValueError:
        body = {"bannerId": BANNER, "language": "en", "storeId": STORE}
        cart_id = api._request("POST", f"{api.BASE_URL}/carts", json=body).json()["id"]
    cart = api._request("GET", f"{api.BASE_URL}/carts/{cart_id}").json()
    if is_placed(cart):
        api._cart_id = None
        return None
    api._cart_id = cart_id
    return cart_id


def build(selections):
    """Add each pick to the cart and remember it, unless the row's Remember box was
    unticked (a one-off swap). add_to_cart sets the quantity.
    An item can have several picks ('vegetable' -> cucumber and carrots).
    List items whose picks all made it into the cart get crossed off OurGroceries;
    any failure keeps the item on the list. Staples have no ogId and are never touched."""
    if not ensure_cart():
        return {"results": [], "crossed": {"count": 0}, "noCart": True}
    # Save picks before adding anything: a build that dies partway (2026-11-01) still
    # comes back preselected on the next launch.
    learned = {}
    for s in selections:
        if s.get("remember", True):
            card = {k: v for k, v in s["card"].items() if k not in ("bought", "stale")}
            learned.setdefault(key(s["item"]), []).append(card)
    save_json(PICKS, {**load_json(PICKS), **learned})
    results, done, failed = [], set(), set()
    # add_to_cart sets the quantity, so two rows picking the same product (alphagetti and
    # elphagetti, 2026-10-24) would leave only the last row's count. Add each product once, summed.
    totals, added = {}, set()
    for s in selections:
        totals[s["code"]] = totals.get(s["code"], 0) + int(s["qty"])
    for s in selections:
        try:
            if s["code"] not in added:
                api.add_to_cart(s["code"], totals[s["code"]])
                added.add(s["code"])
            results.append({"item": f"{s['item']}: {s['card']['name']}", "ok": True})
            done.add(s.get("ogId"))
        except Exception as e:
            results.append({"item": f"{s['item']}: {s['card']['name']}", "ok": False, "error": str(e)[:200]})
            failed.add(s.get("ogId"))
    to_cross = done - failed - {None}
    try:
        cross_off(to_cross)
        crossed = {"count": len(to_cross), "ids": list(to_cross)}
    except Exception as e:
        crossed = {"count": 0, "error": str(e)[:200]}
    return {"results": results, "crossed": crossed}


# --- Web page -----------------------------------------------------------------


def page_data():
    hist, picks = load_history(), load_json(PICKS)
    # No OurGroceries login: run on staples, My Shop and search alone
    items = og_items() if env("OURGROCERIES_USER") else []
    on_list = {key(n) for n, _, _ in items}
    # A staple that's also on the list shows once, under the list, with the list's quantity
    staples = [(s["item"], s["qty"], None) for s in load_json(STAPLES) or [] if key(s["item"]) not in on_list]
    rows = staples + items
    with ThreadPoolExecutor(6) as ex:
        opts = list(ex.map(lambda r: options(r[0], r[0], hist, picks), rows))
    return [
        {"item": n, "qty": q, "staple": og_id is None, "ogId": og_id, **o}
        for (n, q, og_id), o in zip(rows, opts)
    ]


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send((HERE / "picker.html").read_text(encoding="utf-8"), "text/html")
        elif u.path == "/data":
            self._send(json.dumps(page_data()))
        elif u.path == "/quit":  # a new launch asks the old copy to step aside
            self._send("{}")
            threading.Thread(target=self.server.shutdown).start()
        elif u.path == "/search":
            q = parse_qs(u.query)
            res = options(q["item"][0], q["q"][0], load_history(), load_json(PICKS))
            self._send(json.dumps(res))
        elif u.path == "/myshop":  # the page asks after /data, so history is already cached
            self._send(json.dumps(my_shop(load_history())))
        else:
            self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/build":
            self._send(json.dumps({**build(body), "cartUrl": CART_URL}))
        elif self.path == "/staples":
            save_json(STAPLES, [{"item": s["item"], "qty": int(s["qty"])} for s in body])
            self._send("{}")
        else:
            self.send_error(404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    # On Windows, reuse lets a second copy share the port silently and the old one keeps answering
    ThreadingHTTPServer.allow_reuse_address = False
    # An old copy keeps serving old code (how staples didn't save on 2026-10-19), so ask it to quit
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/quit", timeout=3).read()
        time.sleep(1)
    except Exception:
        pass  # nothing running, or a copy too old to know /quit
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)  # local only
    except OSError:
        input("An older picker is still running. Close its window, then run this again.\nPress Enter to close.")
        sys.exit(1)
    print(f"Grocery picker on http://localhost:{PORT}  (Ctrl+C to stop)")
    webbrowser.open(f"http://localhost:{PORT}")
    server.serve_forever()
