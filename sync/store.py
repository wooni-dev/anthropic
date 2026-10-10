"""upstream/<섹션>/<slug>.json 을 고정된 형식으로 읽고 쓴다.

같은 내용이면 바이트까지 같은 파일이 되도록 필드 순서·들여쓰기·줄바꿈을 고정한다.
그래야 바뀐 게 없을 때 git 에 변경이 생기지 않는다.

단독 실행하면 예시 한 건의 저장 형식만 출력하고 아무것도 쓰지 않는다:
    python -m sync.store
"""

import json
import os

ROOT = "upstream"

# 파일에 쓰는 필드와 그 순서. 여기 없는 필드는 저장하지 않는다.
FIELDS = [
    "url",
    "section",
    "slug",
    "title",
    "title_source",   # listing | slug  (slug = 제목을 못 얻어 주소로 임시 표기)
    "published",      # YYYY-MM-DD
    "lastmod",        # sitemap 의 수정일. 바뀌면 '수정된 글'
    "summary",
    "subjects",
    "state",          # active | removed
    "first_seen",     # 처음 발견한 날. 한 번 쓰면 바꾸지 않는다
    "removed_at",     # 원격에서 사라진 것을 발견한 날
]


def path_for(section, slug, root=ROOT):
    return os.path.join(root, section, slug + ".json")


def dump(record):
    """레코드 → 저장할 문자열. 같은 레코드면 항상 같은 문자열."""
    ordered = {k: record.get(k) for k in FIELDS}
    return json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"


def load_all(root=ROOT):
    """upstream/ 의 모든 레코드 → {url: record}. 폴더가 없으면 빈 dict."""
    records = {}
    if not os.path.isdir(root):
        return records
    for section in sorted(os.listdir(root)):
        folder = os.path.join(root, section)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    rec = json.load(f)
                records[rec["url"]] = rec
    return records


def write_if_changed(record, root=ROOT):
    """내용이 달라졌을 때만 파일을 쓴다. 썼으면 True."""
    path = path_for(record["section"], record["slug"], root)
    text = dump(record)
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


if __name__ == "__main__":
    example = {
        "url": "https://www.anthropic.com/engineering/managed-agents",
        "section": "engineering",
        "slug": "managed-agents",
        "title": "Scaling Managed Agents: Decoupling the brain from the hands",
        "title_source": "listing",
        "published": "2026-04-08",
        "lastmod": "2026-04-24T00:00:00.000Z",
        "summary": "(목록 페이지의 한두 줄 소개)",
        "subjects": ["Architecture"],
        "state": "active",
        "first_seen": "2026-10-10",
        "removed_at": None,
    }
    print("저장 경로:", path_for(example["section"], example["slug"]))
    print(dump(example), end="")
    assert dump(json.loads(dump(example))) == dump(example), "다시 읽어 써도 같아야 한다"
    print("확인: 읽고 다시 써도 내용이 같음")
