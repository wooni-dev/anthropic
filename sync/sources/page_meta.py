"""글 페이지 하나에서 제목·발행일·소개·주제·분류를 읽는다. 본문은 저장하지 않는다.

목록 페이지에 없는 글에만 쓴다. 글 하나당 요청 1번이다.
글 객체가 없으면(분류 페이지 등) None 을 돌려준다.
"""

from sync import http
from sync.sources import listing


def parse(html_text, slug):
    for obj in listing.article_objects(listing.payload(html_text)):
        if listing.slug_of(obj) == slug:
            return listing.normalize(obj)
    return None


def fetch(url, slug):
    return parse(http.get(url).decode("utf-8"), slug)
