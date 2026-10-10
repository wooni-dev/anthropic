"""섹션 목록 페이지(/engineering, /news, /research)에서 글별 제목·발행일·소개·주제를 뽑는다.

목록 페이지는 화면에 일부만 보여 주지만, 페이지에 실린 Next.js 데이터(self.__next_f.push)에는
섹션 전체 글이 들어 있다. 공식 API 가 아니라 형식이 바뀔 수 있으므로,
여기서 못 찾은 글은 '제목 없음'일 뿐 '삭제됨'으로 보지 않는다. (존재 여부는 sitemap 이 판단)

단독 실행하면 섹션별 개수와 예시만 출력하고 아무것도 저장하지 않는다:
    python -m sync.sources.listing
"""

import json
import re

from sync import http

SITE = "https://www.anthropic.com"
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
SLUG = re.compile(r'"slug":\{"_type":"slug","current":"([^"]+)"\}')
DECODER = json.JSONDecoder()


def payload(html_text):
    """페이지 HTML 에서 Next.js 데이터 조각들을 꺼내 하나의 문자열로 잇는다."""
    return "".join(json.loads(chunk) for chunk in PUSH.findall(html_text))


def article_object(text, slug_pos, slug):
    """slug 위치를 감싸는 글 객체를 찾는다.

    slug 앞의 '{' 를 가까운 것부터 하나씩 JSON 으로 읽어 보고,
    그 slug 와 title 을 가진 첫 객체를 글로 본다. (중첩된 이미지 객체 등은 건너뛴다)
    """
    i = slug_pos
    while True:
        i = text.rfind("{", 0, i)
        if i < 0:
            return None
        try:
            obj, _ = DECODER.raw_decode(text, i)
        except ValueError:
            continue
        if (isinstance(obj, dict) and obj.get("title")
                and (obj.get("slug") or {}).get("current") == slug):
            return obj


def normalize(obj):
    published = obj.get("publishedOn") or None
    return {
        "title": obj["title"].strip(),
        "published": published[:10] if published else None,  # YYYY-MM-DD 로 통일
        "summary": (obj.get("summary") or "").strip() or None,
        "subjects": [t["label"] for t in obj.get("subjects") or [] if t.get("label")],
    }


def parse(html_text):
    """목록 페이지 HTML → {slug: {title, published, summary, subjects}}."""
    text = payload(html_text)
    found = {}
    for m in SLUG.finditer(text):
        slug = m.group(1)
        if slug in found:
            continue
        obj = article_object(text, m.start(), slug)
        if obj:
            found[slug] = normalize(obj)
    return found


def fetch_section(section):
    return parse(http.get(f"{SITE}/{section}").decode("utf-8"))


if __name__ == "__main__":
    import tomllib

    with open("sync.toml", "rb") as f:
        cfg = tomllib.load(f)
    for section in cfg["sections"]:
        found = fetch_section(section)
        no_date = sum(1 for v in found.values() if not v["published"])
        print(f"{section:12} {len(found):4}개 (날짜 없음 {no_date})")
        slug, info = next(iter(found.items()))
        print(f"  예: {slug} → {info}")
