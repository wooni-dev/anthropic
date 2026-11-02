"""목록 동기화 명령.

    python -m sync.cli fetch                   원격(anthropic.com) 목록을 upstream/ 에 반영하고 커밋
    python -m sync.cli fetch --refresh-titles  목록 페이지에 실린 글의 제목·날짜·분류를 다시 확인
    python -m sync.cli fetch --force           대량 삭제 안전장치를 넘어 반영 (원인을 확인한 뒤에만)
    python -m sync.cli fetch --no-commit       파일만 바꾸고 커밋은 하지 않음
    python -m sync.cli status                  upstream/ 현황 요약 (네트워크 사용 안 함)
    python -m sync.cli pull                    pull_categories 의 안 받은 글·원문이 수정된 글을 받음
    python -m sync.cli pull 섹션/slug ...      지정한 글만 받음
    python -m sync.cli verify 섹션/slug ...    보관한 페이지를 실제 사이트와 브라우저로 비교

존재 여부는 sitemap 만 기준으로 하고, 목록·글 페이지는 제목·날짜·소개·주제·분류를 채우는 데만 쓴다.
커밋은 upstream/ 만 대상으로 하며, push 는 하지 않는다.
"""

import argparse
import subprocess
import sys
import time
import tomllib
from datetime import date

from sync import store
from sync.sources import listing, page_meta, sitemap

CONFIG = "sync.toml"
MIN_RATIO = 0.5  # sitemap 의 글 수가 알던 수의 절반 미만이면 사이트 이상으로 보고 중단
MAX_REMOVED = 10  # 이동이 아닌 삭제가 이만큼 이상이면 사이트 이상으로 보고 중단
PAGE_DELAY = 1  # 글 페이지 조회 사이에 쉬는 시간(초)


def slug_title(slug):
    words = slug.replace("-", " ").strip()
    return words[:1].upper() + words[1:]


def git(*args, stdin=None):
    return subprocess.run(["git", *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8")


def commit(changes):
    """upstream/ 에 실제 변경이 있을 때만 커밋한다. 커밋 해시(짧은 것) 또는 None."""
    git("add", "-A", "--", store.ROOT)
    if not git("status", "--porcelain", "--", store.ROOT).stdout.strip():
        return None
    counts = {k: len(v) for k, v in changes.items()}
    lines = [f"fetch: +{counts['new']} ~{counts['modified']} -{counts['removed']}"
             + (f" ^{counts['returned']}" if counts["returned"] else "")
             + (f" *{counts['updated']}" if counts["updated"] else "")
             + (f" >{counts['moved']}" if counts["moved"] else "")
             + (f" x{counts['excluded']}" if counts["excluded"] else ""), ""]
    for label, urls in changes.items():
        lines += [f"{label + ':':10}{u.split('anthropic.com/')[1]}" for u in urls]
    r = git("commit", "-q", "-F", "-", "--", store.ROOT, stdin="\n".join(lines) + "\n")
    if r.returncode != 0:
        print(f"경고: 커밋 실패 ({r.stderr.strip()}). 파일은 바뀐 상태로 남아 있다.")
        return None
    return git("rev-parse", "--short", "HEAD").stdout.strip()


def find_moves(local, remote):
    """사라진 주소와 같은 slug 가 다른 섹션에 있으면 이동으로 짝짓는다. {옛 주소: 새 주소}.

    이번 fetch 에서 일어난 이동과, 전에 '삭제'로 기록된 건을 함께 찾는다.
    옮겨 간 주소가 개편 전부터 있었던 글도 있어서, 새 주소가 새 글인지는 따지지 않는다.
    """
    def key(rec):
        return rec["slug"].lower()

    alive = {key(rec): url for url, rec in remote.items()}
    moves = {}
    for url, rec in local.items():
        target = alive.get(key(rec))
        if (url not in remote and rec["state"] in ("active", "removed")
                and target and remote[target]["section"] != rec["section"]):
            moves[url] = target
    return moves


def inherit(rec, source):
    """이동한 글이 예전 레코드의 이력을 이어받는다."""
    rec["first_seen"] = min(filter(None, [rec.get("first_seen"), source.get("first_seen")]))
    rec["moved_from"] = sorted({*(rec.get("moved_from") or []), source["url"]})
    known = ("listing", "page")
    if rec.get("title_source") not in known and source.get("title_source") in known:
        for key in ("title", "title_source", "published", "summary", "subjects"):
            rec[key] = source.get(key)
    names = list(rec.get("categories") or []) + list(source.get("categories") or [])
    if source["section"] == "engineering":
        names.append("Engineering")
    rec["categories"] = listing.unique(names)


def apply_meta(rec, meta, source):
    rec.update(title=meta["title"], title_source=source)
    rec["published"] = meta["published"] or rec.get("published")
    rec["summary"] = meta["summary"] or rec.get("summary")
    rec["subjects"] = meta["subjects"] or rec.get("subjects") or []
    rec["categories"] = listing.unique(list(rec.get("categories") or []) + meta["categories"])


def fetch(refresh_titles=False, do_commit=True, force=False):
    from sync import archive

    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    today = date.today().isoformat()
    exclude = cfg.get("exclude", [])

    # [1~2] sitemap: 지금 원격에 있는 글
    try:
        entries = sitemap.fetch_entries(cfg["sections"], exclude)
    except Exception as e:
        print(f"중단: sitemap 을 받지 못함 ({e}). 아무것도 바꾸지 않았다.")
        return 1
    remote = {e["url"]: e for e in entries}
    local = store.load_all()

    # 글이 아닌 것으로 판명돼 exclude 에 들어간 항목은 목록에서 뺀다
    excluded = [u for u in local if sitemap.is_excluded(u, exclude)]
    excluded_records = [local.pop(u) for u in excluded]

    known_active = sum(1 for r in local.values() if r["state"] == "active")
    if known_active and len(remote) < known_active * MIN_RATIO:
        print(f"중단: sitemap 글 수 {len(remote)}개가 알던 {known_active}개의 절반 미만. "
              "사이트 이상으로 보고 아무것도 바꾸지 않았다.")
        return 1

    # [3] 분류
    new = [u for u in remote if u not in local]
    modified = [u for u in remote if u in local and local[u]["lastmod"] != remote[u]["lastmod"]]
    returned = [u for u in remote if u in local and local[u]["state"] != "active"]
    removed = [u for u, r in local.items() if u not in remote and r["state"] == "active"]

    moves = find_moves(local, remote)
    targets = set(moves.values())
    new = [u for u in new if u not in targets]
    removed = [u for u in removed if u not in moves]

    # 안전장치: 이동이 아닌 대량 삭제는 사이트 구조 변화일 수 있으니 사람이 확인하기 전에는 반영하지 않는다
    wiped = [s for s in {local[u]["section"] for u in removed}
             if not any(r["state"] == "active" and r["section"] == s and u not in removed
                        for u, r in local.items())]
    if not force and (len(removed) >= MAX_REMOVED or wiped):
        print(f"중단: 글 {len(removed)}개가 사라짐"
              + (f" (섹션 전체 사라짐: {', '.join(sorted(wiped))})" if wiped else "")
              + ". 사이트 구조가 바뀌었을 수 있다. 확인 후 --force 로 반영할 것. 아무것도 바꾸지 않았다.")
        for u in removed[:20]:
            print(f"  removed   {u.split('anthropic.com/')[1]}")
        return 1

    # 레코드 뼈대를 만들고 이동한 글의 이력을 잇는다
    records = {}
    for url, e in remote.items():
        rec = dict(local.get(url) or {"url": url, "section": e["section"], "slug": e["slug"],
                                      "first_seen": today})
        rec.update(lastmod=e["lastmod"], state="active", removed_at=None, moved_to=None)
        records[url] = rec
    for old, target in sorted(moves.items()):
        inherit(records[target], local[old])

    # [4~5] 제목·날짜가 필요한 글을 목록 페이지에서 찾고, 없으면 글 페이지에서 찾는다
    need = set(new) | set(modified) | set(returned) | targets
    need |= {u for u, r in records.items() if r.get("title_source") not in ("listing", "page")}
    if refresh_titles:
        need = set(remote)
    info = {}
    if need:
        info, errors = listing.fetch_all(cfg["listing_pages"])
        for name, e in errors:
            print(f"경고: {name} 목록 페이지를 읽지 못함 ({e})")
    for url in need:
        meta = info.get(remote[url]["slug"])
        if meta:
            apply_meta(records[url], meta, "listing")

    untitled = [u for u, r in records.items() if r.get("title_source") not in ("listing", "page")]
    for url in untitled:
        try:
            meta = page_meta.fetch(url, remote[url]["slug"])
        except Exception as e:
            print(f"경고: {url} 글 페이지를 읽지 못함 ({e})")
            meta = None
        if meta:
            apply_meta(records[url], meta, "page")
        time.sleep(PAGE_DELAY)

    # [6~8] 바뀐 파일만 쓴다
    written = no_title = 0
    classified = set(new) | set(modified) | set(returned) | targets
    updated = []  # lastmod 는 그대로인데 제목·날짜·소개·주제·분류가 바뀐 글
    for url, rec in records.items():
        if not rec.get("title"):
            rec.update(title=slug_title(rec["slug"]), title_source="slug")
        no_title += rec["title_source"] == "slug"
        if store.write_if_changed(rec):
            written += 1
            if url not in classified:
                updated.append(url)
    for url in removed:
        written += store.write_if_changed(dict(local[url], state="removed", removed_at=today))
    for old, target in moves.items():
        written += store.write_if_changed(dict(local[old], state="moved", moved_to=target))
        archive.relocate(local[old], records[target])
    for rec in excluded_records:
        store.delete(rec)
        written += 1

    # [10] 결과 보고
    changes = {"new": new, "modified": modified, "removed": removed, "returned": returned,
               "updated": updated, "moved": sorted(moves), "excluded": excluded}
    print(f"새 글 {len(new)} · 수정 {len(modified)} · 삭제 {len(removed)} · 복귀 {len(returned)}"
          f" · 이동 {len(moves)} · 갱신 {len(updated)} · 제외 {len(excluded)}"
          f" · 바뀐 파일 {written} · 제목 미확보 {no_title}")
    for label, urls in changes.items():
        for u in urls[:20]:
            print(f"  {label:9} {u.split('anthropic.com/')[1]}"
                  + (f" → {moves[u].split('anthropic.com/')[1]}" if label == "moved" else ""))
        if len(urls) > 20:
            print(f"  {label:9} … 외 {len(urls) - 20}개")

    # [9] 커밋
    if do_commit and written:
        sha = commit(changes)
        print(f"커밋: {sha}" if sha else "커밋 없음 (실제 변경 없음)")
    return 0


def status():
    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    records = store.load_all()
    if not records:
        print("upstream/ 가 비어 있다. 먼저 fetch 를 실행할 것.")
        return 0
    last = git("log", "-1", "--format=%h %ad %s", "--date=format:%Y-%m-%d %H:%M", "--", store.ROOT)
    print(f"마지막 fetch 커밋: {last.stdout.strip() or '없음 (커밋 전)'}")
    dirty = git("status", "--porcelain", "--", store.ROOT).stdout.strip()
    if dirty:
        print(f"커밋되지 않은 변경: {len(dirty.splitlines())}개 파일")
    for section in cfg["sections"]:
        recs = [r for r in records.values() if r["section"] == section]
        active = sum(1 for r in recs if r["state"] == "active")
        removed = sum(1 for r in recs if r["state"] == "removed")
        print(f"  {section:12} {active:4} active · {removed} removed")
    moved = sum(1 for r in records.values() if r["state"] == "moved")
    if moved:
        print(f"  (다른 주소로 이동한 옛 레코드 {moved}개)")
    sources = {}
    for r in records.values():
        sources[r.get("title_source")] = sources.get(r.get("title_source"), 0) + 1
    print("제목 출처: " + " · ".join(f"{k} {v}" for k, v in sorted(sources.items(), key=str)))

    from sync import archive
    for category in cfg.get("pull_categories", []):
        states = {"current": 0, "modified": 0, "missing": 0}
        for r in records.values():
            if r["state"] == "active" and category in (r.get("categories") or []):
                states[archive.local_state(r)] += 1
        print(f"본문 보관 (local/) {category}: 최신 {states['current']}"
              f" · 원문 수정됨 {states['modified']} · 안 받음 {states['missing']}")
    return 0


def pull(targets, limit=0):
    """글 페이지를 리소스까지 받아 local/ 에 보관하고 본문을 마크다운으로 뽑는다.

    targets 를 주면 그 글만, 안 주면 sync.toml 의 pull_categories 에서
    아직 안 받은 글(missing)과 받은 뒤 원문이 수정된 글(modified)만 받는다.
    """
    import time

    from sync import archive, extract

    records = {f"{r['section']}/{r['slug']}": r for r in store.load_all().values()}
    code = 0
    if targets:
        todo = []
        for t in targets:
            if t in records:
                todo.append(records[t])
            else:
                print(f"{t}: upstream/ 에 없는 글. fetch 를 먼저 했는지, 이름이 맞는지 확인할 것")
                code = 1
    else:
        with open(CONFIG, "rb") as f:
            categories = tomllib.load(f).get("pull_categories", [])
        todo = [r for r in sorted(records.values(), key=lambda r: (r["section"], r["published"] or ""))
                if r["state"] == "active" and set(categories) & set(r.get("categories") or [])
                and archive.local_state(r) != "current"]
        print(f"pull 대상 {len(todo)}개 (범위: {', '.join(categories) or '없음'})")
    if limit:
        todo = todo[:limit]

    counts = {"ok": 0, "failed": 0, "new": 0, "body_changed": 0, "body_same": 0}
    for i, rec in enumerate(todo):
        target = f"{rec['section']}/{rec['slug']}"
        before = archive.local_state(rec)
        try:
            r = archive.archive(rec)
            m = extract.extract(rec)
        except Exception as e:
            print(f"{target}: 실패 ({e}) — 다음 pull 때 다시 시도")
            counts["failed"] += 1
            code = 1
            continue
        counts["ok"] += 1
        kind = "new" if m["first_time"] else ("body_changed" if m["body_changed"] else "body_same")
        counts[kind] += 1
        label = {"new": "새로 받음", "body_changed": "본문 바뀜", "body_same": "본문 그대로"}[kind]
        print(f"{target}: {label} ({before}) · 본문 {m['chars']:,}자 · 리소스 새로 받음 {r['downloaded']}"
              + (f" · 리소스 실패 {len(r['failed'])}" if r["failed"] else "")
              + (f" · 원격에서도 깨진 CSS 링크 제거 {len(r['dropped'])}" if r["dropped"] else ""))
        for f in r["failed"]:
            print(f"  ! {f}")
        if i + 1 < len(todo):
            time.sleep(1)  # 사이트에 부담을 주지 않도록 글 사이에 쉰다
    if len(todo) > 1:
        print(f"완료 {counts['ok']} (새로 {counts['new']} · 본문 바뀜 {counts['body_changed']}"
              f" · 본문 그대로 {counts['body_same']}) · 실패 {counts['failed']}")
    return code


def verify(targets):
    """보관한 페이지를 실제 사이트와 브라우저로 비교한다."""
    from sync import verify as verifier

    records = {f"{r['section']}/{r['slug']}": r for r in store.load_all().values()}
    code = 0
    for target in targets:
        rec = records.get(target)
        if not rec:
            print(f"{target}: upstream/ 에 없는 글")
            code = 1
            continue
        try:
            r = verifier.verify(rec)
        except Exception as e:
            print(f"{target}: 검증 실패 ({e})")
            code = 1
            continue
        print(f"{target}: {'통과' if r['passed'] else '불일치'}")
        print(f"  본문 일치율 {r['ratio']:.2%} (실제 {r['live_words']:,}단어 / 로컬 {r['local_words']:,}단어,"
              f" 빠짐 {r['missing_words']} · 추가 {r['extra_words']})")
        print(f"  이미지 {r['images_ok']}/{r['images_total']} 표시 · 폰트 로드 {r['fonts_loaded']}"
              f" (오류 {r['fonts_error']}) · 막힌 외부 요청 {r['blocked_requests']}")
        for u in r["blocked_sample"]:
            print(f"    ! {u[:120]}")
        print(f"  스크린샷 {r['shots'][0]} / {r['shots'][1]}")
        code = code or (0 if r["passed"] else 1)
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m sync.cli")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fetch", help="원격 목록을 upstream/ 에 반영")
    p.add_argument("--refresh-titles", action="store_true", help="모든 글의 제목·날짜를 다시 확인")
    p.add_argument("--no-commit", action="store_true", help="파일만 바꾸고 커밋하지 않음")
    p.add_argument("--force", action="store_true", help="대량 삭제 안전장치를 넘어 반영")
    sub.add_parser("status", help="upstream/ 현황 요약")
    p = sub.add_parser("pull", help="글 페이지를 리소스까지 받아 local/ 에 보관")
    p.add_argument("targets", nargs="*", metavar="섹션/slug",
                   help="예: engineering/contextual-retrieval. 생략하면 pull_categories 의 안 받은·수정된 글")
    p.add_argument("--limit", type=int, default=0, help="이번에 받을 최대 개수")
    p = sub.add_parser("verify", help="보관한 페이지를 실제 사이트와 브라우저로 비교")
    p.add_argument("targets", nargs="+", metavar="섹션/slug")
    args = ap.parse_args(argv)
    if args.command == "pull":
        return pull(args.targets, args.limit)
    if args.command == "verify":
        return verify(args.targets)
    if args.command == "fetch":
        return fetch(args.refresh_titles, not args.no_commit, args.force)
    if args.command == "status":
        return status()


if __name__ == "__main__":
    sys.exit(main())
