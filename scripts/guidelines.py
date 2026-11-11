#!/usr/bin/env python3
"""가이드라인 규칙팩 관리 도구 (표준 라이브러리만 사용). 매년 개정되는 가이드라인을 git으로 갱신할 때 쓴다.

  python scripts/guidelines.py list                               # 규칙팩·버전·현재 버전·규칙 수
  python scripts/guidelines.py validate [--pack uiux]             # 규칙 스키마와 원문 인용(근거) 검증
  python scripts/guidelines.py pages uiux 220-232                 # 원문 쪽 텍스트 읽기 (이미지 제외)
  python scripts/guidelines.py pages uiux --find 건너뛰기          # 키워드가 있는 쪽 찾기
  python scripts/guidelines.py new uiux 2026.08 --from 2025.08    # 새 버전 초안 폴더 생성(모든 규칙 draft)
  python scripts/guidelines.py diff uiux 2025.08 2026.08          # 개정 비교(추가·삭제·변경)
  python scripts/guidelines.py review-queue uiux                  # AI 규칙 검수 대기열 생성(규칙·원문 쪽·검사 설명)
  python scripts/guidelines.py review-apply uiux                  # AI 검수 결과(review.json) 반영
  python scripts/guidelines.py use uiux 2026.08                   # 현재 버전 전환(검증 통과 시)

개정 절차 전체는 core/guideline-update.md.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402
import policy_check as pc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gdir_of(args):
    return args.guidelines_dir or os.path.join(ROOT, "guidelines")


def versions(gdir, pack):
    d = os.path.join(gdir, pack)
    return sorted(v for v in os.listdir(d) if os.path.isdir(os.path.join(d, v))) if os.path.isdir(d) else []


def norm(s):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"```text|```", "", s)
    return re.sub(r"\s+", "", s)


def load_source_pages(base, meta):
    path = os.path.join(base, meta.get("source_md", "source/guideline.md"))
    if not os.path.exists(path):
        return None
    t = open(path, encoding="utf-8").read()
    parts = re.split(r"\n## p\.(\d+)\n", t)
    if len(parts) == 1:          # 쪽 구분이 없는 원문(예: hwpx 본문 추출본)은 전체를 0번 쪽으로 본다
        return {0: t}
    return dict((int(parts[i]), parts[i + 1]) for i in range(1, len(parts), 2))


def validate_pack(gdir, pack, version, all_ids):
    errs, warns = [], []
    base = os.path.join(gdir, pack, version)
    meta = ml.load_json(os.path.join(base, "meta.json"))
    data = ml.load_json(os.path.join(base, "rules.json"))
    if meta is None:
        errs.append("meta.json 없음")
        meta = {}
    if data is None or not isinstance(data.get("rules"), list):
        return errs + ["rules.json 없음 또는 rules 목록 없음"], warns
    if data.get("pack") != pack or data.get("version") != version:
        errs.append("rules.json의 pack/version(%s/%s)이 폴더(%s/%s)와 다름" % (data.get("pack"), data.get("version"), pack, version))
    pages = load_source_pages(base, meta)
    grounded = meta.get("grounding") == "required"
    if grounded and pages is None:
        if os.path.isdir(os.path.join(base, "source")):
            errs.append("grounding=required 인데 원문(source md)이 없음")
        else:
            warns.append("원문(source/)이 배포되지 않은 패키지라 원문 인용 검증을 건너뜀 (저장소 원본에서는 검증됨)")
    ids = set()
    for r in data["rules"]:
        rid = r.get("id", "?")
        for k in ("id", "category", "text", "method", "status"):
            if not r.get(k):
                errs.append("%s: '%s' 누락" % (rid, k))
        if rid in ids:
            errs.append("%s: 규칙 ID 중복" % rid)
        ids.add(rid)
        if r.get("method") not in pc.METHODS:
            errs.append("%s: method는 %s 중 하나" % (rid, "/".join(pc.METHODS)))
        if r.get("status") not in pc.STATUSES:
            errs.append("%s: status는 %s 중 하나" % (rid, "/".join(pc.STATUSES)))
        if r.get("method") == "auto" and not r.get("checks"):
            errs.append("%s: auto 규칙에는 checks가 필요" % rid)
        for c in r.get("checks") or []:
            if c.get("type") not in pc.CHECK_TYPES:
                errs.append("%s: 알 수 없는 검사 유형 '%s' (엔진이 지원하지 않음)" % (rid, c.get("type")))
        if r.get("pack_ref") and not os.path.isdir(os.path.join(gdir, r["pack_ref"])):
            errs.append("%s: pack_ref '%s' 규칙팩이 없음" % (rid, r["pack_ref"]))
        if r.get("needs_review"):
            warns.append("%s: needs_review (개정 초안, 검수 필요)" % rid)
        sp, sq = r.get("source_page"), r.get("source_quote")
        key = sp if sp is not None else (0 if pages is not None and 0 in pages else None)
        if sq and pages is not None:
            if key is None or key not in pages:
                errs.append("%s: source_page %s 가 원문에 없음" % (rid, sp))
            elif norm(sq) not in norm(pages[key]):
                errs.append("%s: 원문%s에서 source_quote를 찾지 못함(인용 검증 실패): %s" % (rid, (" %d쪽" % key) if key else "", sq[:40]))
        elif grounded and r.get("status") == "active" and not sq:
            errs.append("%s: grounding=required 규칙은 active 상태에 source_quote(원문 인용)가 필요" % rid)
        elif sq and pages is None:
            warns.append("%s: 원문이 없어 인용 검증을 건너뜀" % rid)
    for rid in ids:
        if rid in all_ids and all_ids[rid] != pack:
            errs.append("%s: 다른 규칙팩(%s)과 규칙 ID 중복 (응답 기록이 충돌함)" % (rid, all_ids[rid]))
        all_ids.setdefault(rid, pack)
    kf = meta.get("keywords_file")
    if kf and not os.path.exists(os.path.join(base, kf)):
        errs.append("keywords_file '%s' 없음" % kf)
    if not meta.get("reviewed"):
        warns.append("meta.reviewed=false: 사람 검수 전 규칙팩 (결과에 주의 문구 표시)")
    return errs, warns


def cmd_list(args):
    gdir = gdir_of(args)
    idx = ml.load_json(os.path.join(gdir, "index.json"), {"packs": {}})
    for pack in sorted(os.listdir(gdir)):
        if not os.path.isdir(os.path.join(gdir, pack)):
            continue
        cur = (idx["packs"].get(pack) or {}).get("current")
        print("%s (현재: %s)" % (pack, cur))
        for v in versions(gdir, pack):
            rules = (ml.load_json(os.path.join(gdir, pack, v, "rules.json"), {}) or {}).get("rules", [])
            meta = ml.load_json(os.path.join(gdir, pack, v, "meta.json"), {}) or {}
            from collections import Counter
            c = Counter(r.get("method") for r in rules)
            d = sum(1 for r in rules if r.get("status") == "draft")
            print("  %s%s: 규칙 %d개 (자동 %d, 증거수집 %d, 사람확인 %d, draft %d) 검수 %s" % ("* " if v == cur else "  ", v, len(rules), c["auto"], c["assist"], c["attest"], d, "완료" if meta.get("reviewed") else "전"))
    return 0


def cmd_validate(args):
    gdir = gdir_of(args)
    idx = ml.load_json(os.path.join(gdir, "index.json"), {"packs": {}})
    packs = [args.pack] if args.pack else sorted(idx["packs"])
    all_ids, bad = {}, 0
    for pack in packs:
        cur = (idx["packs"].get(pack) or {}).get("current")
        if not cur or cur not in versions(gdir, pack):
            print("[오류] %s: index.json의 현재 버전 '%s' 폴더가 없음" % (pack, cur))
            bad += 1
            continue
        for v in versions(gdir, pack) if args.all_versions else [cur]:
            errs, warns = validate_pack(gdir, pack, v, all_ids)
            print("%s %s: 오류 %d, 경고 %d" % (pack, v, len(errs), len(warns)))
            for e in errs:
                print("  [오류] " + e)
            for w in warns[:8]:
                print("  [경고] " + w)
            bad += len(errs)
    return 1 if bad else 0


def cmd_pages(args):
    gdir = gdir_of(args)
    ver = args.version or (ml.load_json(os.path.join(gdir, "index.json"), {"packs": {}})["packs"].get(args.pack) or {}).get("current")
    base = os.path.join(gdir, args.pack, ver)
    meta = ml.load_json(os.path.join(base, "meta.json"), {}) or {}
    pages = load_source_pages(base, meta)
    if pages is None:
        print("[오류] 원문 md가 없습니다: %s" % os.path.join(base, meta.get("source_md", "source/guideline.md")), file=sys.stderr)
        return 1

    def clean(b):
        b = re.sub(r"!\[[^\]]*\]\([^)]*\)\n?", "", b)
        b = re.sub(r"```text\n?|```", "", b)
        return re.sub(r"\n\s*\n", "\n", b).strip().strip("-").strip()
    if args.find:
        hits = [n for n in sorted(pages) if args.find in clean(pages[n])]
        print("'%s' 포함 %d쪽: %s" % (args.find, len(hits), ", ".join(map(str, hits[:80]))))
        return 0
    m = re.match(r"^(\d+)(?:-(\d+))?$", args.range or "")
    if not m:
        print("[오류] 쪽 범위는 220 또는 220-232 형식 (또는 --find 키워드)", file=sys.stderr)
        return 1
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if b - a > 40:
        print("[오류] 한 번에 41쪽 이상 읽지 않습니다 (토큰 보호). 범위를 나누세요.", file=sys.stderr)
        return 1
    for n in range(a, b + 1):
        if n in pages:
            print("=== p.%d\n%s\n" % (n, clean(pages[n])))
    return 0


def cmd_new(args):
    gdir = gdir_of(args)
    src = os.path.join(gdir, args.pack, args.base)
    dst = os.path.join(gdir, args.pack, args.version)
    if not os.path.isdir(src):
        print("[오류] 기준 버전 폴더가 없음: %s" % src, file=sys.stderr)
        return 1
    if os.path.exists(dst):
        print("[오류] 이미 있음: %s" % dst, file=sys.stderr)
        return 1
    os.makedirs(os.path.join(dst, "source"))
    data = ml.load_json(os.path.join(src, "rules.json"))
    data["version"] = args.version
    for r in data["rules"]:
        r["status"] = "draft"
        r["needs_review"] = True
        r["prev_version_ref"] = {"version": args.base, "id": r["id"]}
    ml.save_json(os.path.join(dst, "rules.json"), data)
    meta = ml.load_json(os.path.join(src, "meta.json"), {}) or {}
    meta.update({"version": args.version, "derived_from": args.base, "reviewed": False,
                 "source_note": "이전 버전(%s)에서 복사한 초안. 새 원문을 source/에 넣고 core/guideline-update.md 절차로 규칙을 갱신·검수" % args.base})
    ml.save_json(os.path.join(dst, "meta.json"), meta)
    kf = meta.get("keywords_file")
    if kf and os.path.exists(os.path.join(src, kf)):
        shutil.copy2(os.path.join(src, kf), os.path.join(dst, kf))
    open(os.path.join(dst, "source", "README.md"), "w", encoding="utf-8").write("# 원본 보관\n\n새 버전의 원문(md 변환본 등)을 여기에 넣으세요. 절차: core/guideline-update.md\n")
    print("생성: %s (규칙 %d개를 draft로 복사). 다음: 원문 추가 → 규칙 갱신 → validate → diff → use" % (dst, len(data["rules"])))
    return 0


def cmd_diff(args):
    gdir = gdir_of(args)
    a = (ml.load_json(os.path.join(gdir, args.pack, args.old, "rules.json"), {}) or {}).get("rules", [])
    b = (ml.load_json(os.path.join(gdir, args.pack, args.new, "rules.json"), {}) or {}).get("rules", [])
    A, B = dict((r["id"], r) for r in a), dict((r["id"], r) for r in b)
    added = [r for i, r in B.items() if i not in A]
    removed = [r for i, r in A.items() if i not in B]
    changed = []
    for i in A:
        if i in B:
            diffs = [k for k in ("text", "method", "checks", "source_quote", "source_page") if A[i].get(k) != B[i].get(k)]
            if diffs:
                changed.append((i, diffs, A[i], B[i]))
    print("# %s 개정 비교: %s → %s\n" % (args.pack, args.old, args.new))
    print("- 추가 %d, 삭제 %d, 변경 %d, 동일 %d\n" % (len(added), len(removed), len(changed), len(A) - len(removed) - len(changed)))
    renamed = []
    for r in list(removed):
        best = max(added, key=lambda x: difflib.SequenceMatcher(None, r["text"], x["text"]).ratio(), default=None)
        if best and difflib.SequenceMatcher(None, r["text"], best["text"]).ratio() >= 0.8:
            renamed.append((r, best))
    for r, n in renamed:
        print("- [ID 변경 의심] %s → %s : %s" % (r["id"], n["id"], n["text"][:60]))
    for r in added:
        print("- [추가] %s (%s/%s) %s" % (r["id"], r["method"], r["status"], r["text"][:70]))
    for r in removed:
        print("- [삭제] %s %s" % (r["id"], r["text"][:70]))
    for i, d, x, y in changed:
        print("- [변경] %s (%s)" % (i, ", ".join(d)))
        if "text" in d:
            print("    전: %s\n    후: %s" % (x["text"][:90], y["text"][:90]))
    return 0


def _clean_page(b):
    b = re.sub(r"!\[[^\]]*\]\([^)]*\)\n?", "", b)
    b = re.sub(r"```text\n?|```", "", b)
    return re.sub(r"\n\s*\n", "\n", b).strip().strip("-").strip()


REVIEW_INSTRUCTIONS = (
    "각 규칙(item)을 검수해 review.json 을 작성한다. 판정 기준: (1) 규칙 text 가 source_quote 와 source_text(원문 쪽)의 내용을 충실히 반영하는가 — 원문에 없는 요건을 "
    "덧붙이거나 범위를 넓히지 않았는가. (2) method 가 적절한가: 홈페이지로 확인 가능하고 판정이 명확하면 auto, 증거만 모을 수 있으면 assist, 계획 수립·화면 판단은 attest. "
    "(3) checks 의 검사 유형(check_doc 설명)이 규칙 요건을 실제로 확인하는가 — 근사이면 hint 에 한계가 적혀 있는가. 거짓 충족·거짓 미충족 위험이 있는가. "
    "verdict: ok(수정 불필요) / revise(수정 필요, note 에 구체적 수정안) / reject(근거 부족·부적절). 모든 item 에 note(근거 1~2문장)를 쓴다. 추측으로 ok 를 주지 않는다.")


def cmd_review_queue(args):
    gdir = gdir_of(args)
    idx = ml.load_json(os.path.join(gdir, "index.json"), {"packs": {}})
    ver = args.version or (idx["packs"].get(args.pack) or {}).get("current")
    base = os.path.join(gdir, args.pack, ver)
    meta = ml.load_json(os.path.join(base, "meta.json"), {}) or {}
    rules = (ml.load_json(os.path.join(base, "rules.json"), {}) or {}).get("rules", [])
    pages = load_source_pages(base, meta)
    items = []
    for r in rules:
        key = r.get("source_page") if r.get("source_page") is not None else (0 if pages and 0 in pages else None)
        text = _clean_page(pages[key])[:2500] if pages and key in pages else ""
        items.append({"id": r["id"], "category": r["category"], "text": r["text"], "method": r["method"], "status": r["status"], "source_ref": r.get("source_ref"),
                      "source_quote": r.get("source_quote"), "source_text": text, "checks": r.get("checks"), "hint": r.get("hint")})
    used = set(c["type"] for r in rules for c in (r.get("checks") or []))
    out = {"pack": args.pack, "version": ver, "instructions": REVIEW_INSTRUCTIONS, "result_schema":
           {"reviewer": "AI(모델명)", "date": "YYYY-MM-DD", "items": [{"id": "규칙ID", "verdict": "ok|revise|reject", "note": "근거"}]},
           "check_doc": dict((k, pc.CHECK_DOC.get(k, "")) for k in sorted(used)), "items": items}
    path = os.path.join(base, "review", "review-queue.json")
    ml.save_json(path, out)
    print("검수 대상 %d개 규칙 → %s" % (len(items), path))
    return 0


def cmd_review_apply(args):
    gdir = gdir_of(args)
    idx = ml.load_json(os.path.join(gdir, "index.json"), {"packs": {}})
    ver = args.version or (idx["packs"].get(args.pack) or {}).get("current")
    base = os.path.join(gdir, args.pack, ver)
    rp = os.path.join(base, "rules.json")
    data = ml.load_json(rp)
    rules = dict((r["id"], r) for r in data["rules"])
    rev = ml.load_json(args.file or os.path.join(base, "review", "review.json"))
    if not rev or not rev.get("reviewer") or not rev.get("date"):
        print("[오류] review.json 에 reviewer, date 가 필요합니다.", file=sys.stderr)
        return 1
    errs, seen = [], set()
    for it in rev.get("items", []):
        if it.get("id") not in rules:
            errs.append("알 수 없는 규칙 ID: %s" % it.get("id"))
        elif it.get("id") in seen:
            errs.append("중복 검수: %s" % it["id"])
        elif it.get("verdict") not in ("ok", "revise", "reject"):
            errs.append("%s: verdict 는 ok/revise/reject" % it["id"])
        elif len((it.get("note") or "").strip()) < 8:
            errs.append("%s: note(근거)가 비어 있거나 너무 짧음" % it["id"])
        seen.add(it.get("id"))
    missing = [i for i in rules if i not in seen]
    if missing:
        errs.append("검수되지 않은 규칙: %s" % ", ".join(missing))
    if errs:
        for e in errs:
            print("[오류] " + e, file=sys.stderr)
        return 1
    n = {"ok": 0, "revise": 0, "reject": 0}
    for it in rev["items"]:
        r = rules[it["id"]]
        r["review"] = {"by": rev["reviewer"], "date": rev["date"], "verdict": it["verdict"], "note": it["note"].strip()}
        n[it["verdict"]] += 1
        if it["verdict"] == "ok":
            r.pop("needs_review", None)
        else:
            r["status"], r["needs_review"] = "draft", True
    ml.save_json(rp, data)
    mp = os.path.join(base, "meta.json")
    meta = ml.load_json(mp, {}) or {}
    all_ok = n["revise"] == 0 and n["reject"] == 0
    meta.update({"reviewed": all_ok, "reviewed_by": rev["reviewer"] if all_ok else meta.get("reviewed_by"), "reviewed_at": rev["date"] if all_ok else meta.get("reviewed_at")})
    meta.setdefault("human_confirmed", False)
    ml.save_json(mp, meta)
    print("검수 반영: ok %d, 수정 필요 %d, 거부 %d → 규칙팩 reviewed=%s (사람 최종 확인 human_confirmed=%s)" % (n["ok"], n["revise"], n["reject"], all_ok, meta["human_confirmed"]))
    return 0 if all_ok else 3


def cmd_use(args):
    gdir = gdir_of(args)
    if args.version not in versions(gdir, args.pack):
        print("[오류] 버전 폴더가 없음: %s/%s" % (args.pack, args.version), file=sys.stderr)
        return 1
    errs, warns = validate_pack(gdir, args.pack, args.version, {})
    drafts = [r for r in (ml.load_json(os.path.join(gdir, args.pack, args.version, "rules.json"), {}) or {}).get("rules", []) if r.get("needs_review")]
    if (errs or drafts) and not args.force:
        print("[거부] 현재 버전으로 전환할 수 없습니다 (--force 로 무시 가능, 권장하지 않음).", file=sys.stderr)
        if errs:
            print("  검증 오류 %d건 (guidelines.py validate):" % len(errs), file=sys.stderr)
            for e in errs[:10]:
                print("    - " + e, file=sys.stderr)
        if drafts:
            print("  needs_review 규칙 %d개: 검수 후 needs_review 를 제거하고 status 를 active 로 바꾸세요." % len(drafts), file=sys.stderr)
        return 1
    ip = os.path.join(gdir, "index.json")
    idx = ml.load_json(ip, {"packs": {}})
    idx["packs"].setdefault(args.pack, {})["current"] = args.version
    ml.save_json(ip, idx)
    print("현재 버전 전환: %s → %s" % (args.pack, args.version))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guidelines-dir", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    v = sub.add_parser("validate")
    v.add_argument("--pack", default="")
    v.add_argument("--all-versions", action="store_true")
    g = sub.add_parser("pages")
    g.add_argument("pack")
    g.add_argument("range", nargs="?", default="")
    g.add_argument("--version", default="")
    g.add_argument("--find", default="")
    n = sub.add_parser("new")
    n.add_argument("pack")
    n.add_argument("version")
    n.add_argument("--from", dest="base", required=True)
    rq = sub.add_parser("review-queue")
    rq.add_argument("pack")
    rq.add_argument("--version", default="")
    ra = sub.add_parser("review-apply")
    ra.add_argument("pack")
    ra.add_argument("--version", default="")
    ra.add_argument("--file", default="")
    d = sub.add_parser("diff")
    d.add_argument("pack")
    d.add_argument("old")
    d.add_argument("new")
    u = sub.add_parser("use")
    u.add_argument("pack")
    u.add_argument("version")
    u.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    return {"list": cmd_list, "validate": cmd_validate, "pages": cmd_pages, "new": cmd_new, "diff": cmd_diff, "use": cmd_use,
            "review-queue": cmd_review_queue, "review-apply": cmd_review_apply}[args.cmd](args)


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
