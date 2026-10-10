"""글 페이지를 이미지·영상·CSS·폰트까지 받아 local/ 에 오프라인으로 열리는 HTML 로 보관한다.

    local/<섹션>/<slug>.html   경로가 로컬 리소스로 바뀐 HTML
    local/assets/<해시>.<확장자>  모든 글이 함께 쓰는 리소스 (내용이 같으면 한 번만 저장)
    local/assets.json          원래 주소 → 로컬 파일 이름 (같은 주소를 다시 받지 않기 위함)

local/ 은 원문 저작권 때문에 git 에 올리지 않는다.
"""

import hashlib
import html as htmllib
import json
import os
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from sync import http

ROOT = "local"
ASSET_DIR = os.path.join(ROOT, "assets")
ASSET_MAP = os.path.join(ROOT, "assets.json")
SITE = "https://www.anthropic.com"

EXT_BY_TYPE = {
    "image/webp": "webp", "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
    "image/svg+xml": "svg", "image/avif": "avif", "video/mp4": "mp4", "video/webm": "webm",
    "text/css": "css", "font/woff2": "woff2", "font/woff": "woff", "font/ttf": "ttf",
}
# 받아서 로컬로 바꿀 속성: <img src>, <video src/poster>, <source src>
MEDIA_ATTR = re.compile(r'(<(?:img|video|source)\b[^>]*?\s(?:src|poster)=")([^"]+)(")', re.I)
STYLESHEET = re.compile(r'<link\b[^>]*\brel="stylesheet"[^>]*>', re.I)
HREF = re.compile(r'(\shref=")([^"]+)(")', re.I)
CSS_URL = re.compile(r'url\(\s*([\'"]?)([^\'")]+)\1\s*\)')
CSS_IMPORT = re.compile(r'@import\s+([\'"])([^\'"]+)\1')


def page_path(section, slug):
    return os.path.join(ROOT, section, slug + ".html")


def load_map():
    if os.path.exists(ASSET_MAP):
        with open(ASSET_MAP, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_map(amap):
    os.makedirs(ROOT, exist_ok=True)
    with open(ASSET_MAP, "w", encoding="utf-8", newline="\n") as f:
        json.dump(amap, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def ext_for(url, content_type):
    ext = EXT_BY_TYPE.get((content_type or "").split(";")[0].strip().lower())
    if ext:
        return ext
    m = re.search(r"\.([a-z0-9]{2,5})$", urlsplit(url).path.lower())
    return m.group(1) if m else "bin"


def store_bytes(data, ext):
    """내용 해시로 이름 붙여 assets/ 에 저장하고 파일 이름을 돌려준다."""
    name = f"{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
    path = os.path.join(ASSET_DIR, name)
    if not os.path.exists(path):
        os.makedirs(ASSET_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return name


def fetch_asset(url, amap, stats, depth=0):
    """리소스 하나를 받아 로컬 파일 이름을 돌려준다. CSS 면 안쪽 url() 까지 따라간다."""
    if url in amap and os.path.exists(os.path.join(ASSET_DIR, amap[url])):
        stats["cached"] += 1
        return amap[url]
    data, ctype = http.get_with_type(url)
    ext = ext_for(url, ctype)
    if ext == "css" and depth < 3:
        data = localize_css(data.decode("utf-8", "replace"), url, amap, stats, depth + 1).encode("utf-8")
    name = store_bytes(data, ext)
    amap[url] = name
    stats["downloaded"] += 1
    return name


def localize_css(css, css_url, amap, stats, depth):
    """CSS 안의 url(...) 과 @import 를 같은 assets/ 폴더의 파일 이름으로 바꾼다."""
    def swap(target):
        # "#c" 나 "%23c" 는 인라인 SVG 안의 내부 참조라 받을 파일이 아니다
        if target.startswith(("data:", "#", "%23")):
            return None
        try:
            return fetch_asset(urljoin(css_url, target), amap, stats, depth)
        except Exception as e:
            stats["failed"].append(f"{urljoin(css_url, target)} ({e})")
            return None

    def url_sub(m):
        name = swap(m.group(2).strip())
        return f"url({name})" if name else m.group(0)

    def import_sub(m):
        name = swap(m.group(2))
        return f'@import "{name}"' if name else m.group(0)

    return CSS_URL.sub(url_sub, CSS_IMPORT.sub(import_sub, css))


def archive(record):
    """upstream 레코드 하나의 페이지를 받아 local/ 에 저장한다. 결과 요약 dict 를 돌려준다."""
    url = record["url"]
    page = http.get(url).decode("utf-8")
    amap = load_map()
    stats = {"downloaded": 0, "cached": 0, "failed": []}

    def local_ref(raw):
        """속성값(HTML 이스케이프됨) → ../assets/파일. 실패하면 None."""
        target = htmllib.unescape(raw)
        if target.startswith("data:"):
            return None
        try:
            return "../assets/" + fetch_asset(urljoin(url, target), amap, stats)
        except Exception as e:
            stats["failed"].append(f"{urljoin(url, target)} ({e})")
            return None

    # 1) 이미지·영상
    page = MEDIA_ATTR.sub(lambda m: m.group(1) + (local_ref(m.group(2)) or m.group(2)) + m.group(3), page)

    # 2) CSS 파일
    def css_link(m):
        tag = m.group(0)
        return HREF.sub(lambda h: h.group(1) + (local_ref(h.group(2)) or h.group(2)) + h.group(3), tag, count=1)
    page = STYLESHEET.sub(css_link, page)

    # 3) 오프라인에서 방해되는 것 제거
    page = re.sub(r'\ssrcset="[^"]*"', "", page, flags=re.I)          # Next.js 는 srcSet 으로 쓴다
    page = re.sub(r'\ssizes="[^"]*"', "", page, flags=re.I)
    page = re.sub(r"<script\b[^>]*>.*?</script>", "", page, flags=re.I | re.S)
    page = re.sub(r'<link\b[^>]*\brel="(?:preload|modulepreload|prefetch)"[^>]*>', "", page, flags=re.I)

    # 4) 남은 사이트 내부 링크는 원문으로 가게 절대주소로
    page = re.sub(r'(\shref=")/(?!/)', r"\1" + SITE + "/", page)

    # 5) 보관 정보: lastmod 는 나중에 upstream 과 비교해 '오래된 사본'인지 판단하는 데 쓴다
    meta = (f'<meta name="archive:url" content="{htmllib.escape(url)}">'
            f'<meta name="archive:lastmod" content="{record.get("lastmod") or ""}">'
            f'<meta name="archive:pulled_at" content="{datetime.now().isoformat(timespec="seconds")}">')
    page = re.sub(r"<head\b[^>]*>", lambda m: m.group(0) + meta, page, count=1)

    path = page_path(record["section"], record["slug"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    save_map(amap)
    return {"path": path, **stats}
