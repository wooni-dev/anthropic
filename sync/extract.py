"""보관한 HTML(local/<섹션>/<slug>.html)에서 본문만 꺼내 마크다운(local/<섹션>/<slug>.md)으로 저장한다.

위키를 만들 때 LLM 이 읽는 입력 파일이다. 네트워크를 쓰지 않는다.
그림은 보관된 로컬 이미지(../assets/...)를 가리키는 마크다운 이미지로, 캡션은 그 아래 기울임 글씨로 남긴다.
"""

import hashlib
import json
import os
import re

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

from sync import archive

# 본문에 있어도 읽을 내용이 아닌 것 (코드 복사 버튼, 아이콘 등)
DROP = ["button", "svg", "script", "style", "noscript"]

# 본문 영역을 찾는 순서. 블로그 글은 <article>, Claude Code 문서로 리디렉션되는 글은 .mdx-content
BODY_SELECTORS = ["article", ".mdx-content", "main"]


def find_body(soup):
    for sel in BODY_SELECTORS:
        el = soup.select_one(sel)
        if el is not None:
            return el
    return None


class Converter(MarkdownConverter):
    def convert_figure(self, el, text, *args, **kwargs):
        img = el.find("img")
        cap = el.find("figcaption")
        alt = (img.get("alt") or "").strip() if img else ""
        caption = cap.get_text(" ", strip=True) if cap else ""
        lines = []
        if img and img.get("src"):
            lines.append(f"![{alt or caption}]({img['src']})")
        if caption:
            lines.append(f"*{caption}*")
        return "\n\n" + "\n\n".join(lines) + "\n\n"


def md_path(section, slug):
    return os.path.join(archive.ROOT, section, slug + ".md")


def frontmatter(record, body_hash):
    keys = ["url", "section", "slug", "title", "published", "lastmod", "subjects"]
    lines = ["---"]
    for k in keys:
        lines.append(f"{k}: {json.dumps(record.get(k), ensure_ascii=False)}")
    lines.append(f"html: {json.dumps(record['slug'] + '.html')}")
    lines.append(f"body_sha256: {json.dumps(body_hash)}")
    lines.append("---")
    return "\n".join(lines)


def read_body_hash(path):
    """기존 .md 의 body_sha256. 없으면 None."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        m = re.search(r'^body_sha256: "([0-9a-f]+)"$', f.read(4000), re.M)
    return m.group(1) if m else None


def extract(record):
    """레코드의 보관 HTML 을 마크다운으로 바꿔 저장한다. 결과 요약 dict 를 돌려준다."""
    html_file = archive.page_path(record["section"], record["slug"])
    with open(html_file, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    body = find_body(soup)
    if body is None:
        raise ValueError(f"{html_file} 에서 본문 영역({', '.join(BODY_SELECTORS)})을 찾지 못함")
    for tag in body.find_all(DROP):
        tag.decompose()

    md = Converter(heading_style="ATX", bullets="-", strong_em_symbol="*").convert_soup(body)
    md = "\n".join(line.rstrip() for line in md.strip().splitlines())
    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")
    # 본문 지문: lastmod 가 바뀌어도 이 값이 같으면 본문은 그대로다 (위키를 다시 만들 필요 없음)
    body_hash = hashlib.sha256(md.encode("utf-8")).hexdigest()
    text = f"{frontmatter(record, body_hash)}\n\n# {record['title']}\n\n{md}\n"

    path = md_path(record["section"], record["slug"])
    old_hash = read_body_hash(path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"path": path, "chars": len(md), "body_changed": old_hash is not None and old_hash != body_hash,
            "first_time": old_hash is None}
