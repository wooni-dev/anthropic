"""목록 동기화 명령.

    python -m sync.cli fetch                   원격(anthropic.com) 목록을 upstream/ 에 반영하고 커밋
    python -m sync.cli fetch --refresh-titles  모든 글의 제목·날짜를 목록 페이지로 다시 확인
    python -m sync.cli fetch --no-commit       파일만 바꾸고 커밋은 하지 않음
    python -m sync.cli status                  upstream/ 현황 요약 (네트워크 사용 안 함)
    python -m sync.cli pull 섹션/slug ...      글 페이지를 리소스까지 받아 local/ 에 보관
    python -m sync.cli verify 섹션/slug ...    보관한 페이지를 실제 사이트와 브라우저로 비교

존재 여부는 sitemap 만 기준으로 하고, 목록 페이지는 제목·날짜·소개·주제를 채우는 데만 쓴다.
커밋은 upstream/ 만 대상으로 하며, push 는 하지 않는다.
"""

import argparse
import subprocess
import sys
import tomllib
from datetime import date

from sync import store
from sync.sources import listing, sitemap

CONFIG = "sync.toml"
MIN_RATIO = 0.5  # sitemap 의 글 수가 알던 수의 절반 미만이면 사이트 이상으로 보고 중단


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
             + (f" *{counts['updated']}" if counts["updated"] else ""), ""]
    for label, urls in changes.items():
        lines += [f"{label + ':':10}{u.split('anthropic.com/')[1]}" for u in urls]
    r = git("commit", "-q", "-F", "-", "--", store.ROOT, stdin="\n".join(lines) + "\n")
    if r.returncode != 0:
        print(f"경고: 커밋 실패 ({r.stderr.strip()}). 파일은 바뀐 상태로 남아 있다.")
        return None
    return git("rev-parse", "--short", "HEAD").stdout.strip()


def fetch(refresh_titles=False, do_commit=True):
    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    today = date.today().isoformat()

    # [1~2] sitemap: 지금 원격에 있는 글
    try:
        entries = sitemap.fetch_entries(cfg["sections"], cfg.get("exclude", []))
    except Exception as e:
        print(f"중단: sitemap 을 받지 못함 ({e}). 아무것도 바꾸지 않았다.")
        return 1
    remote = {e["url"]: e for e in entries}
    local = store.load_all()
    known_active = sum(1 for r in local.values() if r["state"] == "active")
    if known_active and len(remote) < known_active * MIN_RATIO:
        print(f"중단: sitemap 글 수 {len(remote)}개가 알던 {known_active}개의 절반 미만. "
              "사이트 이상으로 보고 아무것도 바꾸지 않았다.")
        return 1

    # [3] 분류
    new = [u for u in remote if u not in local]
    modified = [u for u in remote if u in local and local[u]["lastmod"] != remote[u]["lastmod"]]
    returned = [u for u in remote if u in local and local[u]["state"] == "removed"]
    removed = [u for u, r in local.items() if u not in remote and r["state"] == "active"]

    # [4~5] 제목·날짜가 필요한 글만 목록 페이지에서 찾는다
    need = set(new) | set(modified) | set(returned)
    need |= {u for u in remote if u in local and local[u].get("title_source") != "listing"}
    if refresh_titles:
        need = set(remote)
    info = {}
    for section in sorted({remote[u]["section"] for u in need}):
        try:
            found = listing.fetch_section(section)
        except Exception as e:
            print(f"경고: {section} 목록 페이지를 읽지 못함 ({e}). 제목은 다음 fetch 때 다시 시도한다.")
            continue
        for slug, meta in found.items():
            info[(section, slug)] = meta

    # [6~8] 레코드를 만들고, 바뀐 파일만 쓴다
    written = no_title = 0
    classified = set(new) | set(modified) | set(returned)
    updated = []  # lastmod 는 그대로인데 제목·날짜·소개·주제가 바뀐 글 (주로 --refresh-titles)
    for url, e in remote.items():
        old = local.get(url, {})
        rec = dict(old) or {"url": url, "section": e["section"], "slug": e["slug"],
                            "first_seen": today, "subjects": []}
        rec["lastmod"] = e["lastmod"]
        rec["state"] = "active"
        rec["removed_at"] = None
        meta = info.get((e["section"], e["slug"])) if url in need else None
        if meta:
            rec.update(title=meta["title"], title_source="listing", published=meta["published"],
                       summary=meta["summary"], subjects=meta["subjects"])
        elif not rec.get("title"):
            rec.update(title=slug_title(e["slug"]), title_source="slug", published=None, summary=None)
        no_title += rec["title_source"] == "slug"
        if store.write_if_changed(rec):
            written += 1
            if url not in classified:
                updated.append(url)
    for url in removed:
        rec = dict(local[url], state="removed", removed_at=today)
        written += store.write_if_changed(rec)

    # [10] 결과 보고
    changes = {"new": new, "modified": modified, "removed": removed,
               "returned": returned, "updated": updated}
    print(f"새 글 {len(new)} · 수정 {len(modified)} · 삭제 {len(removed)} · 복귀 {len(returned)}"
          f" · 갱신 {len(updated)} · 바뀐 파일 {written} · 제목 미확보 {no_title}")
    for label, urls in changes.items():
        for u in urls[:20]:
            print(f"  {label:9} {u.split('anthropic.com/')[1]}")
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
        print(f"  {section:12} {active:4} active · {len(recs) - active} removed")
    sources = {}
    for r in records.values():
        sources[r.get("title_source")] = sources.get(r.get("title_source"), 0) + 1
    print("제목 출처: " + " · ".join(f"{k} {v}" for k, v in sorted(sources.items(), key=str)))
    return 0


def pull(targets):
    """지정한 글(섹션/slug)의 페이지를 리소스까지 받아 local/ 에 보관한다."""
    from sync import archive

    records = {f"{r['section']}/{r['slug']}": r for r in store.load_all().values()}
    code = 0
    for target in targets:
        rec = records.get(target)
        if not rec:
            print(f"{target}: upstream/ 에 없는 글. fetch 를 먼저 했는지, 이름이 맞는지 확인할 것")
            code = 1
            continue
        try:
            r = archive.archive(rec)
        except Exception as e:
            print(f"{target}: 실패 ({e})")
            code = 1
            continue
        print(f"{target}: 저장 {r['path']} · 리소스 새로 받음 {r['downloaded']} · "
              f"이미 있음 {r['cached']} · 실패 {len(r['failed'])}")
        for f in r["failed"]:
            print(f"  ! {f}")
        try:
            from sync import extract
            m = extract.extract(rec)
            print(f"  본문 {m['path']} ({m['chars']:,}자)")
        except Exception as e:
            print(f"  ! 본문 추출 실패 ({e})")
            code = 1
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
    sub.add_parser("status", help="upstream/ 현황 요약")
    p = sub.add_parser("pull", help="글 페이지를 리소스까지 받아 local/ 에 보관")
    p.add_argument("targets", nargs="+", metavar="섹션/slug", help="예: engineering/contextual-retrieval")
    p = sub.add_parser("verify", help="보관한 페이지를 실제 사이트와 브라우저로 비교")
    p.add_argument("targets", nargs="+", metavar="섹션/slug")
    args = ap.parse_args(argv)
    if args.command == "pull":
        return pull(args.targets)
    if args.command == "verify":
        return verify(args.targets)
    if args.command == "fetch":
        return fetch(args.refresh_titles, not args.no_commit)
    if args.command == "status":
        return status()


if __name__ == "__main__":
    sys.exit(main())
