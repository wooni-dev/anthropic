"""목록 페이지와 글 페이지에 실린 Next.js 데이터에서 글별 제목·발행일·소개·주제·분류를 뽑는다.

2026-10 개편 이후 목록 페이지(/engineering, /news, /research)에는 일부 글만 실린다.
여기서 못 찾은 글은 page_meta.py 가 글 페이지에서 채운다.
공식 API 가 아니라 형식이 바뀔 수 있으므로, 못 찾은 글은 '제목 없음'일 뿐 '삭제됨'으로 보지 않는다.
(존재 여부는 sitemap 이 판단)

단독 실행하면 페이지별 개수와 예시만 출력하고 아무것도 저장하지 않는다:
    python -m sync.sources.listing
"""

import json
import re

from sync import http

SITE = "https://www.anthropic.com"
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
OBJECT_START = re.compile(r'\{"_')
ARTICLE_TYPES = {"article", "post", "engineeringArticle"}
DECODER = json.JSONDecoder()


def payload(html_text):
    """페이지 HTML 에서 Next.js 데이터 조각들을 꺼내 하나의 문자열로 잇는다."""
    return "".join(json.loads(chunk) for chunk in PUSH.findall(html_text))


def slug_of(obj):
    slug = obj.get("slug")
    return slug.get("current") if isinstance(slug, dict) else slug


def article_objects(text):
    """데이터 문자열 안의 글 객체를 모두 찾아 돌려준다."""
    for m in OBJECT_START.finditer(text):
        try:
            obj, _ = DECODER.raw_decode(text, m.start())
        except ValueError:
            continue
        if (isinstance(obj, dict) and obj.get("_type") in ARTICLE_TYPES
                and obj.get("title") and slug_of(obj)):
            yield obj


def labels(value):
    """문자열·태그 객체·그 목록에서 사람이 읽는 이름만 모은다."""
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()]
    if isinstance(value, dict):
        for key in ("label", "title", "name"):
            if isinstance(value.get(key), str):
                return [value[key].strip()]
        return []
    if isinstance(value, list):
        return [name for item in value for name in labels(item)]
    return []


def unique(names):
    return list(dict.fromkeys(n for n in names if n))


def normalize(obj):
    published = obj.get("publishedOn") or None
    return {
        "title": obj["title"].strip(),
        "published": published[:10] if published else None,  # YYYY-MM-DD 로 통일
        "summary": (obj.get("summary") or "").strip() or None,
        "subjects": unique(labels(obj.get("subjects")) + labels(obj.get("topics"))
                           + labels(obj.get("topicTag")) + labels(obj.get("tags"))),
        "categories": unique(labels(obj.get("category")) + labels(obj.get("cardTeams"))
                             + labels(obj.get("teams")) + labels(obj.get("newsCategories"))),
    }


def merge(found, slug, meta):
    """같은 글이 여러 번 나오면 빈 칸을 채우고 분류를 합친다."""
    old = found.get(slug)
    if old is None:
        found[slug] = meta
        return
    for key in ("title", "published", "summary"):
        old[key] = old[key] or meta[key]
    old["subjects"] = unique(old["subjects"] + meta["subjects"])
    old["categories"] = unique(old["categories"] + meta["categories"])


def parse(html_text):
    """페이지 HTML → {slug: {title, published, summary, subjects, categories}}."""
    found = {}
    for obj in article_objects(payload(html_text)):
        merge(found, slug_of(obj), normalize(obj))
    return found


def fetch_page(name):
    return parse(http.get(f"{SITE}/{name}").decode("utf-8"))


def fetch_all(pages):
    """여러 목록 페이지를 합친다. 읽지 못한 페이지는 (결과, [(페이지, 오류)]) 로 알려 준다."""
    found, errors = {}, []
    for name in pages:
        try:
            for slug, meta in fetch_page(name).items():
                merge(found, slug, meta)
        except Exception as e:
            errors.append((name, e))
    return found, errors


if __name__ == "__main__":
    import tomllib

    with open("sync.toml", "rb") as f:
        cfg = tomllib.load(f)
    for name in cfg["listing_pages"]:
        found = fetch_page(name)
        print(f"{name:12} {len(found):4}개")
        if found:
            print("  예:", next(iter(found.items())))
