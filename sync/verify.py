"""보관한 페이지가 실제 사이트와 같은지 브라우저(Playwright)로 확인한다.

  1) 본문 일치: 실제 사이트와 로컬 HTML 을 각각 열어 <article> 의 화면 텍스트를 단어 단위로 비교
  2) 오프라인 완결성: 로컬 HTML 을 네트워크를 막고 열어, 이미지가 그려졌는지·폰트가 로드됐는지·
     밖으로 나가려던 요청이 있었는지 확인
  3) 화면 비교(참고용): 두 페이지 스크린샷을 local/_verify/ 에 저장

본문 내용은 출력하지 않고 수치만 보고한다.
"""

import difflib
import os
import re

from playwright.sync_api import sync_playwright

from sync import archive
from sync.extract import BODY_SELECTORS

SHOT_DIR = os.path.join(archive.ROOT, "_verify")
PASS_RATIO = 0.99


def words(text):
    return re.findall(r"\S+", text)


def article_text(page):
    """extract 와 같은 순서로 본문 영역을 찾아 화면 텍스트를 돌려준다."""
    for sel in BODY_SELECTORS:
        loc = page.locator(sel)
        if loc.count():
            return loc.first.inner_text()
    return ""


def load_lazy_images(page):
    """loading="lazy" 이미지는 화면에 들어와야 불러오므로 끝까지 스크롤한 뒤 로드를 기다린다."""
    page.evaluate("""async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 600) {
            window.scrollTo(0, y);
            await new Promise(r => setTimeout(r, 100));
        }
        await Promise.all([...document.images].map(i => i.complete ? null :
            new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 5000); })));
        window.scrollTo(0, 0);
    }""")


def verify(record):
    html_file = os.path.abspath(archive.page_path(record["section"], record["slug"]))
    if not os.path.exists(html_file):
        raise FileNotFoundError(f"{html_file} 가 없다. 먼저 pull 할 것")
    os.makedirs(SHOT_DIR, exist_ok=True)
    name = f"{record['section']}-{record['slug']}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        size = {"width": 1280, "height": 900}

        # 실제 사이트
        live = browser.new_page(viewport=size)
        live.goto(record["url"], wait_until="load", timeout=60000)
        live.wait_for_timeout(2000)
        load_lazy_images(live)
        live_text = article_text(live)
        live.screenshot(path=os.path.join(SHOT_DIR, name + "-live.png"), full_page=True)

        # 로컬 사본: http/https 요청은 전부 막고, 막힌 요청을 센다
        ctx = browser.new_context(viewport=size)
        blocked = []

        def guard(route):
            if route.request.url.startswith(("http://", "https://")):
                blocked.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        ctx.route("**/*", guard)
        local = ctx.new_page()
        local.goto("file:///" + html_file.replace("\\", "/"), wait_until="load")
        local.evaluate("document.fonts.ready")
        load_lazy_images(local)
        local.wait_for_timeout(500)
        local_text = article_text(local)
        images = local.evaluate("""() => [...document.images].map(i => i.complete && i.naturalWidth > 0)""")
        fonts = local.evaluate("""() => { const f = [...document.fonts];
            return {loaded: f.filter(x => x.status === 'loaded').length,
                    error: f.filter(x => x.status === 'error').length}; }""")
        local.screenshot(path=os.path.join(SHOT_DIR, name + "-local.png"), full_page=True)
        browser.close()

    a, b = words(live_text), words(local_text)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    missing = sum(i2 - i1 for op, i1, i2, _, _ in sm.get_opcodes() if op in ("delete", "replace"))
    extra = sum(j2 - j1 for op, _, _, j1, j2 in sm.get_opcodes() if op in ("insert", "replace"))
    ratio = sm.ratio() if a else 0.0
    result = {
        "live_words": len(a), "local_words": len(b), "ratio": ratio,
        "missing_words": missing, "extra_words": extra,
        "images_ok": sum(images), "images_total": len(images),
        "fonts_loaded": fonts["loaded"], "fonts_error": fonts["error"],
        "blocked_requests": len(blocked), "blocked_sample": sorted(set(blocked))[:5],
        "shots": [os.path.join(SHOT_DIR, name + s) for s in ("-live.png", "-local.png")],
    }
    result["passed"] = (ratio >= PASS_RATIO and result["images_ok"] == result["images_total"]
                        and fonts["error"] == 0 and not blocked)
    return result
