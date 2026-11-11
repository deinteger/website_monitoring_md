#!/usr/bin/env python3
"""설정·점검 대상 관리 도구 (표준 라이브러리만 사용).

소스 코드를 열지 않고 workspace/ 의 settings.json · site-profile.json 을 명령으로 안전하게 바꾼다.
AI 채팅에서 "우리 기관 사이트 추가해줘"라고 하면 에이전트가 이 명령을 실행한다. 사람이 직접 JSON 을 고쳐도 같다.
API 키 등 비밀값은 파일에 저장하지 않는다(환경변수 LLM_API_KEY 사용).

  python scripts/setup.py init --site-name "OO 홈페이지" --contact "정보화담당관 홍길동(031-000-0000)"
  python scripts/setup.py show
  python scripts/setup.py set stale_months 2
  python scripts/setup.py llm --provider anthropic --model <모델명> --allow yes
  python scripts/setup.py board add --id notice --name 공지사항 --url https://대상주소/board/notice.do --owner 총무과 --cycle daily
  python scripts/setup.py board set notice cycle=weekly owner=기획과
  python scripts/setup.py board remove notice
  python scripts/setup.py board import-draft            # discover.py 초안의 게시판을 프로필에 추가
  python scripts/setup.py board list
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = re.compile(r"(key|token|secret|password|passwd|pwd)", re.I)
PROVIDERS = ("openai", "openai-responses", "anthropic")
LLM_KEYS = {"allowed": bool, "provider": str, "base_url": str, "model": str}
BOARD_BOOL = ("irregular", "recency_exempt", "exclude")
BOARD_STR = ("name", "system", "url", "owner", "cycle", "exclude_reason", "render", "page_url_template", "date_source", "date_regex", "row_tag", "row_class")


class SetupError(Exception):
    pass


def paths(ws):
    return os.path.join(ws, "settings.json"), os.path.join(ws, "site-profile.json")


def example(name):
    p = os.path.join(ROOT, "config.example", name)
    return ml.load_json(p, {}) if os.path.exists(p) else {}


def parse_value(raw):
    low = raw.strip().lower()
    if low in ("true", "yes", "y", "예", "on"):
        return True
    if low in ("false", "no", "n", "아니오", "off"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def check_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise SetupError("URL 형식 오류(http/https 주소여야 함): %s" % url)
    return url


def load_user_settings(ws):
    return ml.load_json(paths(ws)[0], {}) or {}


def set_setting(ws, key, raw):
    if SECRET.search(key):
        raise SetupError("비밀값은 파일에 저장하지 않습니다. 환경변수(LLM_API_KEY)를 사용하세요: %s" % key)
    parts = key.split(".")
    defaults = ml.DEFAULT_SETTINGS
    if parts[0] == "llm":
        if len(parts) != 2 or parts[1] not in LLM_KEYS:
            raise SetupError("llm 하위 키는 %s 만 가능합니다" % ", ".join(LLM_KEYS))
        want = LLM_KEYS[parts[1]]
    else:
        node = defaults
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                raise SetupError("알 수 없는 설정 키: %s (python scripts/setup.py show 로 확인)" % key)
            node = node[p]
        want = type(node)
    val = parse_value(raw)
    if want is float and isinstance(val, int) and not isinstance(val, bool):
        val = float(val)
    if want is str:
        val = raw
    if not isinstance(val, want) or (want in (int, float) and isinstance(val, bool)):
        raise SetupError("%s 값 형식 오류: %r (기대 %s)" % (key, raw, want.__name__))
    if key == "llm.provider" and val not in PROVIDERS:
        raise SetupError("provider 는 %s 중 하나" % ", ".join(PROVIDERS))
    if key == "llm.base_url" and val:
        check_url(val)
    s = load_user_settings(ws)
    node = s
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = val
    ml.save_json(paths(ws)[0], s)
    return val


def load_prof(ws):
    prof = ml.load_json(paths(ws)[1])
    if prof is None:
        raise SetupError("프로필이 없습니다. 먼저: python scripts/setup.py init --site-name \"이름\" --base-url https://주소/")
    return prof


def save_prof(ws, prof, allow_empty=False):
    """저장 전에 검증한다(실패 시 파일을 바꾸지 않음)."""
    path = paths(ws)[1]
    if prof.get("boards") or not allow_empty:
        tmp = os.path.join(ws, ".validate-profile.json")
        ml.save_json(tmp, prof)
        try:
            check_dir = os.path.join(ws, ".validate")
            os.makedirs(check_dir, exist_ok=True)
            shutil.copyfile(tmp, os.path.join(check_dir, "site-profile.json"))
            try:
                ml.load_profile(check_dir)
            except ml.ProfileError as e:
                raise SetupError(str(e))
        finally:
            shutil.rmtree(os.path.join(ws, ".validate"), ignore_errors=True)
            if os.path.exists(tmp):
                os.remove(tmp)
    ml.save_json(path, prof)


def cmd_init(a):
    ws = a.workspace
    os.makedirs(ws, exist_ok=True)
    sp, pp = paths(ws)
    if not os.path.exists(sp):
        s = {k: v for k, v in example("settings.example.json").items()}
        if a.contact:
            s["contact"] = a.contact
        ml.save_json(sp, s)
        print("생성: %s" % sp)
    elif a.contact:
        set_setting(ws, "contact", a.contact)
    if not os.path.exists(pp):
        prof = {"site_name": a.site_name or "", "base_url": check_url(a.base_url) if a.base_url else "", "allowed_domains": [], "boards": []}
        ml.save_json(pp, prof)
        print("생성: %s (게시판은 board add 또는 discover.py 후 board import-draft 로 추가)" % pp)
    print("작업 폴더(이 PC 로컬): %s" % os.path.abspath(ws))
    return 0


def cmd_show(a):
    ws = a.workspace
    s = ml.load_settings(ws)
    print("# 현재 설정 (%s)\n" % os.path.abspath(ws))
    print("- 담당/연락처: %s" % (s.get("contact") or "(미입력 — set contact \"부서 이름(연락처)\")"))
    print("- 지연 기준: %s개월 / 요청 간격 %ss / 동시 %s" % (s["stale_months"], s["min_interval_sec"], s["max_concurrency"]))
    llm = s.get("llm", {})
    print("- 외부 AI 전송: %s (provider=%s, model=%s, base_url=%s, API 키 환경변수 LLM_API_KEY: %s)" % (
        "허용" if llm.get("allowed") else "미허용", llm.get("provider", "openai"), llm.get("model") or "(미지정)",
        llm.get("base_url") or "(기본)", "설정됨" if os.environ.get("LLM_API_KEY") else "없음"))
    print("- 게시글 오타 점검: %s" % ("켜짐" if s["typo_check"]["enabled"] else "꺼짐"))
    prof = ml.load_json(paths(ws)[1])
    if prof is None:
        print("\n점검 대상: 프로필 없음 → setup.py init")
        return 0
    print("\n## 점검 대상: %s (%s)\n" % (prof.get("site_name", ""), prof.get("base_url", "")))
    print("| id | 이름 | 시스템 | 주기 | 담당 | 제외 | URL |\n| --- | --- | --- | --- | --- | --- | --- |")
    for b in prof.get("boards", []):
        print("| %s | %s | %s | %s | %s | %s | %s |" % (b.get("id"), b.get("name"), b.get("system", ""), b.get("cycle", "weekly"), b.get("owner", ""),
                                                    "예" if b.get("exclude") else "", b.get("url")))
    if not prof.get("boards"):
        print("(등록된 게시판 없음)")
    return 0


def cmd_set(a):
    v = set_setting(a.workspace, a.key, a.value)
    print("설정 완료: %s = %r" % (a.key, v))
    return 0


def cmd_llm(a):
    ws = a.workspace
    if a.provider:
        set_setting(ws, "llm.provider", a.provider)
    if a.model:
        set_setting(ws, "llm.model", a.model)
    if a.base_url is not None:
        set_setting(ws, "llm.base_url", a.base_url)
    if a.allow:
        set_setting(ws, "llm.allowed", a.allow)
    llm = ml.load_settings(ws).get("llm", {})
    print("외부 AI 설정: 허용=%s provider=%s model=%s base_url=%s" % (llm.get("allowed"), llm.get("provider", "openai"), llm.get("model") or "(미지정)", llm.get("base_url") or "(기본)"))
    print("API 키는 파일에 저장하지 않습니다. 터미널에서 환경변수로 지정하세요:\n  Linux/macOS: export LLM_API_KEY=...   Windows(PowerShell): $env:LLM_API_KEY=\"...\"")
    print("※ 외부 AI 전송은 기관 보안 승인 후에만 allow yes 로 하세요.")
    return 0


def new_board(a):
    if not re.match(r"^[A-Za-z0-9_-]+$", a.id):
        raise SetupError("id는 영문·숫자·_-만 가능합니다: %s" % a.id)
    b = {"id": a.id, "name": a.name, "url": check_url(a.url), "type": "board", "cycle": a.cycle, "owner": a.owner or ""}
    if a.system:
        b["system"] = a.system
    if a.irregular:
        b["irregular"] = True
    return b


def cmd_board(a):
    ws = a.workspace
    if a.action == "list":
        return cmd_show(a)
    prof = load_prof(ws)
    boards = prof.setdefault("boards", [])
    if a.action == "add":
        if any(b["id"] == a.id for b in boards):
            raise SetupError("이미 있는 id: %s (수정은 board set)" % a.id)
        boards.append(new_board(a))
        msg = "추가: %s (%s)" % (a.id, a.name)
    elif a.action == "remove":
        n = len(boards)
        prof["boards"] = [b for b in boards if b["id"] != a.id]
        if len(prof["boards"]) == n:
            raise SetupError("없는 id: %s" % a.id)
        msg = "삭제: %s" % a.id
    elif a.action == "set":
        b = next((x for x in boards if x["id"] == a.id), None)
        if b is None:
            raise SetupError("없는 id: %s" % a.id)
        for kv in a.pairs:
            if "=" not in kv:
                raise SetupError("항목=값 형식이어야 합니다: %s" % kv)
            k, v = kv.split("=", 1)
            if k in BOARD_BOOL:
                b[k] = bool(parse_value(v))
            elif k == "url":
                b[k] = check_url(v)
            elif k == "pages":
                b[k] = int(v)
            elif k in BOARD_STR:
                b[k] = v
            else:
                raise SetupError("수정할 수 없는 항목: %s (가능: %s, pages)" % (k, ", ".join(BOARD_BOOL + BOARD_STR)))
        msg = "수정: %s" % a.id
    elif a.action == "import-draft":
        draft = ml.load_json(os.path.join(ws, "site-profile.draft.json"))
        if draft is None:
            raise SetupError("초안이 없습니다. 먼저 discover.py 를 실행하세요.")
        have = {b["id"] for b in boards}
        added = [b for b in draft.get("boards", []) if b.get("id") not in have and (not a.pairs or b.get("id") in a.pairs)]
        boards.extend(added)
        if not prof.get("base_url"):
            prof["base_url"] = draft.get("base_url", "")
        msg = "초안에서 %d개 추가 (검수 필요: core/onboarding.md 3절)" % len(added)
    else:
        raise SetupError("알 수 없는 작업")
    save_prof(ws, prof, allow_empty=True)
    print(msg)
    return 0


def cmd_site(a):
    prof = load_prof(a.workspace)
    if a.name:
        prof["site_name"] = a.name
    if a.base_url:
        prof["base_url"] = check_url(a.base_url)
    for d in a.allow_domain or []:
        prof.setdefault("allowed_domains", [])
        if d.lower() not in prof["allowed_domains"]:
            prof["allowed_domains"].append(d.lower())
    save_prof(a.workspace, prof, allow_empty=True)
    print("사이트 정보 저장: %s (%s)" % (prof.get("site_name"), prof.get("base_url")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--site-name"); p.add_argument("--base-url"); p.add_argument("--contact"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("show"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("set"); p.add_argument("key"); p.add_argument("value"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("llm"); p.add_argument("--provider"); p.add_argument("--model"); p.add_argument("--base-url"); p.add_argument("--allow"); p.set_defaults(fn=cmd_llm)
    p = sub.add_parser("site"); p.add_argument("--name"); p.add_argument("--base-url"); p.add_argument("--allow-domain", action="append"); p.set_defaults(fn=cmd_site)
    p = sub.add_parser("board")
    p.add_argument("action", choices=["add", "set", "remove", "list", "import-draft"])
    p.add_argument("pairs", nargs="*", help="set: 항목=값 / import-draft: 가져올 id(생략 시 전체)")
    p.add_argument("--id"); p.add_argument("--name"); p.add_argument("--url"); p.add_argument("--system"); p.add_argument("--owner")
    p.add_argument("--cycle", default="weekly", choices=["daily", "weekly", "monthly", "quarterly"]); p.add_argument("--irregular", action="store_true")
    p.set_defaults(fn=cmd_board)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "board":
        if a.action in ("set", "remove") and not a.id and a.pairs:
            a.id, a.pairs = a.pairs[0], a.pairs[1:]      # board set notice cycle=daily
        need = {"add": ("id", "name", "url"), "set": ("id",), "remove": ("id",)}.get(a.action, ())
        for n in need:
            if not getattr(a, n):
                print("[오류] board %s 에는 --%s 가 필요합니다" % (a.action, n), file=sys.stderr)
                return 1
    try:
        return a.fn(a)
    except (SetupError, ml.ProfileError, ValueError) as e:
        print("[오류] %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
