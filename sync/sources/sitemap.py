"""anthropic.com sitemap.xml 에서 추적 섹션의 글 목록을 뽑는다.

sitemap 은 '지금 원격에 어떤 글이 있는가'의 기준이다.
제목과 발행일은 없고, URL 과 lastmod(수정일)만 있다.

단독 실행하면 섹션별 개수만 출력하고 아무것도 저장하지 않는다:
    python -m sync.sources.sitemap
"""

import fnmatch
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from sync import http

SITEMAP_URL = "https://www.anthropic.com/sitemap.xml"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def download(url=SITEMAP_URL):
    """sitemap.xml 원문(bytes)을 받는다. 실패하면 예외를 그대로 올린다."""
    return http.get(url)


def parse(xml_bytes):
    """sitemap XML → [(url, lastmod 또는 None)]."""
    root = ET.fromstring(xml_bytes)
    out = []
    for node in root.findall("sm:url", NS):
        loc = node.findtext("sm:loc", default="", namespaces=NS).strip()
        lastmod = node.findtext("sm:lastmod", default=None, namespaces=NS)
        if loc:
            out.append((loc, lastmod.strip() if lastmod else None))
    return out


def select(pairs, sections, exclude=()):
    """추적 섹션의 글만 골라 dict 목록으로 돌려준다.

    글로 인정하는 주소는 정확히 /<섹션>/<slug> 두 단계인 것뿐이다.
    /news 같은 섹션 첫 페이지나 더 깊은 경로는 글이 아니므로 뺀다.
    exclude 는 경로에 대한 glob 패턴이다. 예: "/news/*-hiring"
    """
    entries = []
    for url, lastmod in pairs:
        path = urlsplit(url).path.rstrip("/")
        parts = path.strip("/").split("/")
        if len(parts) != 2 or parts[0] not in sections:
            continue
        if any(fnmatch.fnmatch(path, pat) for pat in exclude):
            continue
        entries.append({"url": url, "section": parts[0], "slug": parts[1], "lastmod": lastmod})
    return entries


def fetch_entries(sections, exclude=()):
    return select(parse(download()), sections, exclude)


if __name__ == "__main__":
    import tomllib
    from collections import Counter

    with open("sync.toml", "rb") as f:
        cfg = tomllib.load(f)
    entries = fetch_entries(cfg["sections"], cfg.get("exclude", []))
    counts = Counter(e["section"] for e in entries)
    for section in cfg["sections"]:
        print(f"{section:12} {counts.get(section, 0):4}개")
    print(f"{'합계':10} {len(entries):4}개")
    no_lastmod = sum(1 for e in entries if not e["lastmod"])
    print(f"lastmod 없는 글: {no_lastmod}개")
    print("예시:", entries[0] if entries else "없음")
