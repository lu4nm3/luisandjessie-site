#!/usr/bin/env python3
"""Static mirror of luisandjessie.com for GitHub Pages.

Downloads rendered HTML pages plus every same-origin asset they reference
(CSS, JS, fonts, images incl. srcset/lightbox links), then rewrites absolute
URLs into relative ones so the copy works on username.github.io/repo/ AND on
a custom domain.
"""
import os, re, sys, json, hashlib, posixpath, threading
from urllib.parse import urljoin, urlparse, urlunparse, unquote
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

HOST = "luisandjessie.com"
BASE = f"https://{HOST}"
OUT = sys.argv[1] if len(sys.argv) > 1 else "site"
SEEDS = [l.strip() for l in open("seeds.txt")] if os.path.exists("seeds.txt") else [BASE + "/"]

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"

SKIP = re.compile(r"/(wp-admin|wp-login|wp-json|xmlrpc|feed|comments/feed|author|wp-cron)|[?&](s|p|page_id|replytocom|attachment_id)=|/embed/?$")
ASSET_EXT = re.compile(r"\.(css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|mp4|webm|json|map)$", re.I)
CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)|@import\s+(['"])([^'"]+)\3""")

pages_done, assets_done = set(), set()
lock = threading.Lock()
log = open("crawl.log", "a")


def norm(u, base):
    u = urljoin(base, u.strip())
    p = urlparse(u)
    if p.scheme not in ("http", "https") or p.netloc.lower().removeprefix("www.") != HOST:
        return None
    return urlunparse(("https", HOST, p.path or "/", "", p.query, ""))


def local_path(u):
    p = urlparse(u)
    path = unquote(p.path)
    if path.endswith("/") or not posixpath.splitext(path)[1]:
        path = path.rstrip("/") + "/index.html"
    return os.path.join(OUT, path.lstrip("/"))


def is_asset(u):
    return bool(ASSET_EXT.search(urlparse(u).path)) or "/wp-content/" in u or "/wp-includes/" in u


def fetch(u):
    for _ in range(3):
        try:
            r = S.get(u, timeout=60)
            return r
        except Exception as e:
            err = e
    print("FAIL", u, err, file=log, flush=True)
    return None


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def get_asset(u):
    key = urlunparse(urlparse(u)._replace(query=""))
    with lock:
        if key in assets_done:
            return []
        assets_done.add(key)
    r = fetch(u)
    if r is None or r.status_code != 200:
        print("ASSET", r.status_code if r else "ERR", u, file=log, flush=True)
        return []
    save(local_path(key), r.content)
    more = []
    if urlparse(u).path.endswith(".css"):
        for m in CSS_URL.finditer(r.text):
            ref = m.group(2) or m.group(4)
            if ref.startswith("data:"):
                continue
            n = norm(ref, u)
            if n:
                more.append(n)
    return more


def srcset_urls(v):
    return [part.strip().split()[0] for part in v.split(",") if part.strip()]


def parse_page(u, html):
    soup = BeautifulSoup(html, "lxml")
    links, assets = set(), set()
    for tag in soup.find_all(True):
        for attr in ("href", "src", "data-src", "data-lazy-src", "data-bg", "poster", "data-full-image",
                     "data-light-image", "data-image", "data-large_image", "content"):
            v = tag.get(attr)
            if not v or not isinstance(v, str):
                continue
            n = norm(v, u)
            if not n:
                continue
            if tag.name == "a" and not is_asset(n):
                links.add(n)
            elif tag.name == "link" and attr == "href" and not is_asset(n):
                continue  # rel=canonical, shortlink, api links, etc.
            elif tag.name == "meta" and not is_asset(n):
                continue
            elif is_asset(n):
                assets.add(n)
        for attr in ("srcset", "data-srcset", "data-lazy-srcset"):
            v = tag.get(attr)
            if v:
                for s in srcset_urls(v):
                    n = norm(s, u)
                    if n:
                        assets.add(n)
        st = tag.get("style")
        if st:
            for m in CSS_URL.finditer(st):
                n = norm(m.group(2) or m.group(4) or "", u)
                if n:
                    assets.add(n)
    for st in soup.find_all("style"):
        for m in CSS_URL.finditer(st.get_text()):
            n = norm(m.group(2) or m.group(4) or "", u)
            if n:
                assets.add(n)
    # URLs embedded in inline scripts / JSON (escaped slashes)
    for m in re.finditer(r"https?:(?:\\?/){2}(?:www\.)?" + re.escape(HOST) + r"((?:\\?/)[^\s\"'<>)]*)", html):
        path = m.group(1).replace("\\/", "/")
        n = norm(BASE + path, u)
        if n and is_asset(n):
            assets.add(n)
    return links, assets


def crawl():
    # LiteSpeed "guest mode" serves first-time visitors a stripped-down page
    # (critical CSS only, no web fonts) and then reloads into the full page once
    # this endpoint sets the _lscache_vary cookie. Get the cookie up front so we
    # capture the full page real browsers end up seeing.
    try:
        S.post(BASE + "/wp-content/plugins/litespeed-cache/guest.vary.php", timeout=30)
    except Exception as e:
        print("vary cookie failed:", e, file=sys.stderr)
    print("cookies:", list(S.cookies.keys()), file=sys.stderr)
    queue = list(dict.fromkeys(SEEDS))
    all_assets = set()
    while queue:
        u = queue.pop(0)
        if u in pages_done or SKIP.search(u):
            continue
        pages_done.add(u)
        r = fetch(u)
        if r is None:
            continue
        ctype = r.headers.get("content-type", "")
        final = norm(r.url, u) or u
        if "text/html" not in ctype:
            if r.status_code == 200:
                save(local_path(u), r.content)
            continue
        if r.status_code != 200:
            print("PAGE", r.status_code, u, file=log, flush=True)
            continue
        if final != u and final in pages_done:
            continue
        save(local_path(u), r.content)
        print("page", u, file=sys.stderr)
        links, assets = parse_page(u, r.text)
        all_assets |= assets
        for l in sorted(links):
            if l not in pages_done and not SKIP.search(l) and not urlparse(l).query:
                queue.append(l)
    # 404 page for GitHub Pages
    r = fetch(BASE + "/this-page-does-not-exist-404/")
    if r is not None and "text/html" in r.headers.get("content-type", ""):
        save(os.path.join(OUT, "404.html"), r.content)
        all_assets |= parse_page(BASE + "/404.html", r.text)[1]
    # assets (breadth-first so CSS -> fonts/images are followed)
    todo = set(all_assets)
    with ThreadPoolExecutor(16) as ex:
        while todo:
            batch, todo = list(todo), set()
            for more in ex.map(get_asset, batch):
                todo |= {m for m in more if urlunparse(urlparse(m)._replace(query="")) not in assets_done}
    print(f"pages={len(pages_done)} assets={len(assets_done)}", file=sys.stderr)


if __name__ == "__main__":
    crawl()
