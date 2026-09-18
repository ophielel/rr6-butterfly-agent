"""从 limbuscompany.wiki.gg 抓取资料（经 r.jina.ai 代理，绕过 Cloudflare）。

为什么需要代理：wiki.gg 对非浏览器请求返回 Cloudflare 挑战（403），
本机直连（含 `api.php`）一律失败；`r.jina.ai` 可以代理 MediaWiki API 并返回纯文本。

用法：
    python3 tools/wiki_fetch.py search "Coin Reuse"
    python3 tools/wiki_fetch.py page "Coin Reuse" --raw
    python3 tools/wiki_fetch.py page "Funeral of the Dead Butterflies"
    python3 tools/wiki_fetch.py category "E.G.O with Coin Reuse"

缓存目录：`_sources/`（已 gitignore）。所有抓取结果都带 `fetched_at` 与来源 URL，
用于 docs 里的 provenance 记录。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

WIKI = "https://limbuscompany.wiki.gg"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_sources")
UA = "rr6sim-research/0.1 (mechanics audit; contact: local)"


def _fetch(url: str, retries: int = 3) -> str:
    proxied = "https://r.jina.ai/" + urllib.parse.quote(url, safe="")
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(proxied, headers={"User-Agent": UA, "Accept": "text/plain"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"抓取失败 {url}: {last}")


def _strip_jina(text: str) -> str:
    """去掉 r.jina.ai 的头部包装，返回正文。"""
    marker = "Markdown Content:"
    if marker in text:
        text = text.split(marker, 1)[1]
    return text.lstrip("\n")


def _cache_path(kind: str, name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return os.path.join(CACHE, kind, safe + ".txt")


def _save(kind: str, name: str, body: str, meta: dict) -> str:
    path = _cache_path(kind, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        f.write(body)
    return path


def _load(kind: str, name: str):
    path = _cache_path(kind, name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        return meta, f.read()


def api(params: dict) -> str:
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    key = json.dumps(params, sort_keys=True, ensure_ascii=False)
    cached = _load("api", key)
    if cached:
        return cached[1]
    url = f"{WIKI}/api.php?{q}"
    body = _strip_jina(_fetch(url))
    _save("api", key, body, {"url": url, "params": params,
                             "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return body


def parse_page(title: str) -> dict:
    """取页面 wikitext。"""
    cached = _load("page", title)
    if cached:
        return json.loads(cached[1])
    body = api({"action": "parse", "page": title, "prop": "wikitext"})
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = {"raw": body}
    _save("page", title, json.dumps(data, ensure_ascii=False),
          {"url": f"{WIKI}/wiki/{urllib.parse.quote(title)}",
           "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return data


def wikitext(title: str) -> str:
    data = parse_page(title)
    return (data.get("parse", {}) or {}).get("wikitext", data.get("raw", ""))


def search(term: str, limit: int = 10) -> list:
    body = api({"action": "query", "list": "search", "srsearch": term, "srlimit": limit})
    data = json.loads(body)
    return data.get("query", {}).get("search", [])


def category(name: str, limit: int = 200) -> list:
    body = api({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{name}",
                "cmlimit": limit})
    data = json.loads(body)
    return data.get("query", {}).get("categorymembers", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("term")
    s.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("page")
    p.add_argument("title")
    p.add_argument("--raw", action="store_true")
    p.add_argument("--head", type=int, default=4000)
    c = sub.add_parser("category")
    c.add_argument("name")
    args = ap.parse_args()

    if args.cmd == "search":
        for r in search(args.term, args.limit):
            print(f"- {r['title']}  (id={r.get('pageid')})")
    elif args.cmd == "page":
        text = wikitext(args.title)
        if args.raw:
            print(text)
        else:
            print(text[:args.head])
    else:
        for m in category(args.name):
            print(f"- {m['title']}")


if __name__ == "__main__":
    main()
