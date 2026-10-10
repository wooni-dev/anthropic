"""anthropic.com 요청 공용 함수."""

import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; anthropic-blog-sync)"
TIMEOUT = 30


def get(url):
    """url 을 받아 bytes 로 돌려준다. 실패하면 예외를 그대로 올린다."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()
