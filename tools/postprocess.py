#!/usr/bin/env python3
"""Turn the raw WordPress mirror into a GitHub Pages-ready static site.

1. Swap 2560px "-scaled" originals for the 2048px variant WordPress already made
   (keeps the lightbox sharp, cuts ~400 MB).
2. Strip WordPress-only head tags and LiteSpeed server calls.
3. Rewrite absolute https://luisandjessie.com/ URLs to relative paths so the site
   works both at username.github.io/repo/ and on a custom domain.
"""
import os, re, sys, glob

ROOT = sys.argv[1] if len(sys.argv) > 1 else "site"
HOST = r"(?:www\.)?luisandjessie\.com"

# ---------- 1. scaled -> 2048 map ----------
scaled_map = {}
for f in glob.glob(f"{ROOT}/wp-content/uploads/**/*-scaled.*", recursive=True):
    d, name = os.path.split(f)
    stem, ext = os.path.splitext(name)
    base = stem[: -len("-scaled")]
    best, area = None, 0
    for g in os.listdir(d):
        m = re.fullmatch(re.escape(base) + r"-(\d+)x(\d+)" + re.escape(ext), g)
        if m and int(m[1]) * int(m[2]) > area and max(int(m[1]), int(m[2])) <= 2048:
            best, area = g, int(m[1]) * int(m[2])
    if best and max(map(int, re.findall(r"-(\d+)x(\d+)", best)[-1])) >= 1536:
        scaled_map[name] = best
print(f"scaled images with a >=1536px replacement: {len(scaled_map)}")


def fix_scaled(html):
    def srcset(m):
        attr, val = m.group(1), m.group(2)
        parts = [p.strip() for p in val.split(",") if p.strip()]
        keep = [p for p in parts if not any(p.split()[0].endswith("/" + s) for s in scaled_map)]
        return f'{attr}="{", ".join(keep or parts)}"'
    html = re.sub(r'((?:data-)?srcset)="([^"]*)"', srcset, html)
    for s, r in scaled_map.items():
        html = html.replace("/" + s, "/" + r)
    return html


# ---------- 2. strip WordPress-only bits ----------
HEAD_JUNK = [
    r'<link[^>]+rel=["\']alternate["\'][^>]*(?:feed|oembed|wp-json)[^>]*>\s*',
    r'<link[^>]+rel=["\']https://api\.w\.org/["\'][^>]*>\s*',
    r'<link[^>]+rel=["\']EditURI["\'][^>]*>\s*',
    r'<link[^>]+rel=["\']shortlink["\'][^>]*>\s*',
    r'<link[^>]+rel=["\']canonical["\'][^>]*>\s*',
    r'<meta[^>]+name=["\']generator["\'][^>]*>\s*',
    # LiteSpeed "vary" cookie ping to guest.vary.php (server-side only)
    r'<script data-no-optimize="1">var litespeed_vary=.*?</script>\s*',
]


def strip_junk(html):
    for p in HEAD_JUNK:
        html = re.sub(p, "", html, flags=re.S | re.I)
    return html


# ---------- 3. absolute -> relative ----------
def rel_prefix(path):
    depth = os.path.relpath(os.path.dirname(path), ROOT).count(os.sep) + 1
    if os.path.dirname(path) == ROOT or os.path.relpath(os.path.dirname(path), ROOT) == ".":
        depth = 0
    return "../" * depth


def relativize(text, prefix, escaped_ok=True):
    home = prefix or "./"
    # JSON-escaped (inside inline scripts): https:\/\/luisandjessie.com\/...
    if escaped_ok:
        esc = prefix.replace("/", "\\/")
        text = re.sub(r"https?:\\/\\/" + HOST + r"\\/", esc if esc else ".\\/", text)
    text = re.sub(r"(?:https?:)?//" + HOST + r"/", prefix if prefix else "./", text)
    text = re.sub(r"(?:https?:)?//" + HOST + r"(?=[\"'\s<)])", home, text)
    # root-relative URLs (/cf-fonts/..., /wp-content/...) break under username.github.io/repo/
    text = re.sub(r"""(url\(\s*['"]?|\b(?:src|href|data-src|srcset|data-srcset|poster)=["'])/(?![/\\])""",
                  lambda m: m.group(1) + (prefix or "./"), text)
    text = re.sub(r"(,\s*)/(wp-content|wp-includes|cf-fonts)/", lambda m: m.group(1) + prefix + m.group(2) + "/", text)
    # a few WP inline scripts use root-relative paths
    text = re.sub(r'(["\(])/(wp-content|wp-includes|cf-fonts)/', lambda m: m.group(1) + prefix + f"{m.group(2)}/", text)
    # "./wp-content" at root is fine; tidy "./"+"./"
    return text


BASE_SNIPPET = (
    "<script>(function(){var p=location.pathname.split('/');"
    "var b=/github\\.io$/.test(location.hostname)&&p.length>2?'/'+p[1]+'/':'/';"
    "document.write('<base href=\"'+b+'\">');})();</script>"
)

n_html = n_css = 0
for dirpath, _, files in os.walk(ROOT):
    for fn in files:
        path = os.path.join(dirpath, fn)
        if fn.endswith(".html"):
            html = open(path, encoding="utf-8", errors="surrogateescape").read()
            html = strip_junk(fix_scaled(html))
            if os.path.relpath(path, ROOT) == "404.html":
                # 404 is served at any depth, so resolve against the site root via <base>
                # search needs WordPress; swap it for a link home
                html = re.sub(r'<form role="search".*?</form>', '<p><a href="./">Go to the home page</a></p>', html, flags=re.S)
                html = html.replace("Maybe try a search?", "")
                html = relativize(html, "")
                html = html.replace('="./', '="')
                html = re.sub(r"<head([^>]*)>", lambda m: f"<head{m.group(1)}>" + BASE_SNIPPET, html, count=1)
            else:
                html = relativize(html, rel_prefix(path))
            open(path, "w", encoding="utf-8", errors="surrogateescape").write(html)
            n_html += 1
        elif fn.endswith(".css"):
            css = open(path, encoding="utf-8", errors="surrogateescape").read()
            new = relativize(fix_scaled(css), rel_prefix(path), escaped_ok=False)
            if new != css:
                open(path, "w", encoding="utf-8", errors="surrogateescape").write(new)
            n_css += 1

# ---------- delete scaled originals that are no longer referenced ----------
removed = 0
for name in scaled_map:
    for f in glob.glob(f"{ROOT}/wp-content/uploads/**/{glob.escape(name)}", recursive=True):
        os.remove(f)
        removed += 1

open(os.path.join(ROOT, ".nojekyll"), "w").close()
print(f"html={n_html} css={n_css} scaled_removed={removed}")
