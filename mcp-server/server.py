"""
홈페이지 점검용 MCP 서버.

브라우저로 페이지를 열어 AI가 직접 읽는 대신, 순수 계산으로 처리 가능한
작업(링크 상태 확인, 게시일 추출·판정, 캐시 파일 갱신)을 코드로 수행하여
토큰 사용을 줄인다. 특정 도메인에 종속되지 않은 범용 도구로 설계했다.

실행: python server.py (stdio 기반 MCP 서버)
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("nihhs-inspector")

USER_AGENT = (
    "Mozilla/5.0 (compatible; HomepageInspectorBot/1.0; "
    "+mechanical-check-only)"
)

DATE_PATTERNS = [
    re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
    re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
]


def normalize_date(text: str) -> str | None:
    """문자열에서 YYYY-MM-DD 형식 날짜를 찾아 정규화한다. 못 찾으면 None."""
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            y, mo, d = m.groups()
            try:
                return date(int(y), int(mo), int(d)).isoformat()
            except ValueError:
                continue
    return None


def classify_recency(latest_date_str: str | None, today: date | None = None) -> dict[str, Any]:
    """정규화된 날짜 문자열을 기준일과 비교해 판정한다."""
    today = today or date.today()
    if not latest_date_str:
        return {"판정": "게시일 확인 불가", "경과일": None, "기준일": today.isoformat()}
    latest = date.fromisoformat(latest_date_str)
    threshold = today - relativedelta(months=3)
    elapsed_days = (today - latest).days
    verdict = "게시 최신성 지연" if latest <= threshold else "정상"
    return {
        "판정": verdict,
        "경과일": elapsed_days,
        "기준일": today.isoformat(),
        "3개월기준일": threshold.isoformat(),
    }


# ---------------------------------------------------------------------------
# Markdown table 파싱/갱신 (page-cache.md 같은 파이프 테이블 전용)
# ---------------------------------------------------------------------------


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != "")


def parse_md_tables(lines: list[str]) -> list[dict[str, Any]]:
    """라인 리스트에서 파이프 테이블 블록들을 찾아 header/rows/위치를 반환한다."""
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            header = _split_row(lines[i])
            j = i + 1
            if j < len(lines) and lines[j].strip().startswith("|") and _is_separator(_split_row(lines[j])):
                j += 1
            rows_start = j
            rows = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(_split_row(lines[j]))
                j += 1
            blocks.append({"header": header, "rows": rows, "rows_start_line": rows_start, "end_line": j})
            i = j
        else:
            i += 1
    return blocks


def row_to_dict(header: list[str], row: list[str]) -> dict[str, str]:
    return {h: (row[idx] if idx < len(row) else "") for idx, h in enumerate(header)}


def render_row(header: list[str], row_dict: dict[str, str]) -> str:
    cells = [row_dict.get(h, "") for h in header]
    return "| " + " | ".join(cells) + " |"


# ---------------------------------------------------------------------------
# MCP 도구
# ---------------------------------------------------------------------------


DEFAULT_ERROR_INDICATORS = [
    "요청하신 파일이나 경로는 존재하지 않습니다",
    "요청하신 페이지를 찾을 수 없습니다",
    "페이지를 찾을 수 없습니다",
    "존재하지 않는 페이지입니다",
    "잘못된 접근입니다",
    "정상적인 방법으로 다시 접속",
]


@mcp.tool()
def check_links(
    urls: list[str],
    timeout: int = 10,
    max_workers: int = 10,
    error_indicators: list[str] | None = None,
) -> list[dict[str, Any]]:
    """URL 목록의 접속 가능 여부를 병렬로 확인한다.

    일부 공공기관 CMS는 존재하지 않는 경로도 HTTP 200으로 응답하고 본문에
    커스텀 에러 이미지/문구만 표시한다 (HTTP 상태코드만으로는 404를 못 잡음).
    이를 보완하기 위해 본문에서 알려진 에러 문구를 함께 검사한다.
    error_indicators로 사이트별 에러 문구를 추가할 수 있다.

    반환: [{url, status_code, ok, error}]
    """
    indicators = DEFAULT_ERROR_INDICATORS + (error_indicators or [])

    def check_one(url: str) -> dict[str, Any]:
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            r.encoding = r.apparent_encoding
            matched = next((kw for kw in indicators if kw in r.text), None)
            if matched:
                return {
                    "url": url,
                    "status_code": r.status_code,
                    "ok": False,
                    "error": f"본문에서 에러 문구 감지: '{matched}' (HTTP {r.status_code})",
                }
            return {
                "url": url,
                "status_code": r.status_code,
                "ok": r.status_code < 400,
                "error": None if r.status_code < 400 else f"HTTP {r.status_code}",
            }
        except requests.RequestException as e:
            return {"url": url, "status_code": None, "ok": False, "error": str(e)}

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(check_one, u): u for u in urls}
        for fut in as_completed(futures):
            results.append(fut.result())

    order = {u: idx for idx, u in enumerate(urls)}
    results.sort(key=lambda r: order[r["url"]])
    return results


@mcp.tool()
def check_recency(cache_file: str, timeout: int = 15) -> list[dict[str, Any]]:
    """page-cache.md 형식의 파일을 읽어, 추출셀렉터가 있는 행은 실제로 접속해
    최신 게시일을 뽑아 3개월 기준으로 판정한다.

    - 헤더에 '추출셀렉터'가 없거나 값이 비어 있으면 '수동확인필요'로 반환하고
      실제 접속은 시도하지 않는다 (JS 렌더링 목록 등 CSS 선택자로 못 뽑는 경우).
    - CSS 선택자는 브라우저 querySelector와 동일한 문법을 사용한다.

    반환: [{콘텐츠영역, URL, 최신게시일, 판정, 경과일, 비고}]
    """
    path = Path(cache_file)
    if not path.exists():
        raise FileNotFoundError(f"cache_file not found: {cache_file}")

    lines = path.read_text(encoding="utf-8").split("\n")
    blocks = parse_md_tables(lines)

    results = []
    for block in blocks:
        header = block["header"]
        if "URL" not in header or "추출셀렉터" not in header:
            continue
        for row in block["rows"]:
            rd = row_to_dict(header, row)
            url = rd.get("URL", "").strip()
            selector = rd.get("추출셀렉터", "").strip()
            area = rd.get("콘텐츠영역", "")

            if not url:
                continue
            if not selector:
                results.append(
                    {
                        "콘텐츠영역": area,
                        "URL": url,
                        "최신게시일": None,
                        "판정": "수동확인필요(선택자없음)",
                        "경과일": None,
                        "비고": "추출셀렉터를 찾아 page-cache.md에 기록 필요",
                    }
                )
                continue

            try:
                resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
                resp.encoding = resp.apparent_encoding
                soup = BeautifulSoup(resp.text, "html.parser")
                el = soup.select_one(selector)
                raw_text = el.get_text(strip=True) if el else ""
                normalized = normalize_date(raw_text)
            except requests.RequestException as e:
                results.append(
                    {
                        "콘텐츠영역": area,
                        "URL": url,
                        "최신게시일": None,
                        "판정": "접속오류",
                        "경과일": None,
                        "비고": str(e),
                    }
                )
                continue

            if not normalized:
                results.append(
                    {
                        "콘텐츠영역": area,
                        "URL": url,
                        "최신게시일": None,
                        "판정": "수동확인필요(선택자로날짜못찾음)",
                        "경과일": None,
                        "비고": f"원문: {raw_text[:50]}",
                    }
                )
                continue

            verdict = classify_recency(normalized)
            results.append(
                {
                    "콘텐츠영역": area,
                    "URL": url,
                    "최신게시일": normalized,
                    "판정": verdict["판정"],
                    "경과일": verdict["경과일"],
                    "비고": "",
                }
            )

    return results


@mcp.tool()
def update_page_cache(cache_file: str, updates: list[dict[str, str]]) -> dict[str, Any]:
    """점검 결과를 page-cache.md류 파일에 반영한다.

    updates 각 항목은 반드시 'URL'을 포함해야 하며, 그 외 키(최신게시일,
    마지막점검일, 판정, 추출셀렉터, 비고 등)는 해당 컬럼이 테이블 헤더에
    있을 때만 갱신된다. URL이 일치하는 행이 없으면 해당 항목은 건너뛰고
    'not_found' 목록에 보고한다.
    """
    path = Path(cache_file)
    if not path.exists():
        raise FileNotFoundError(f"cache_file not found: {cache_file}")

    lines = path.read_text(encoding="utf-8").split("\n")
    blocks = parse_md_tables(lines)

    updates_by_url = {u["URL"]: u for u in updates if "URL" in u}
    applied: list[str] = []

    for block in blocks:
        header = block["header"]
        if "URL" not in header:
            continue
        for offset, row in enumerate(block["rows"]):
            rd = row_to_dict(header, row)
            url = rd.get("URL", "").strip()
            if url in updates_by_url:
                patch = updates_by_url[url]
                for key, value in patch.items():
                    if key in header:
                        rd[key] = value
                line_idx = block["rows_start_line"] + offset
                lines[line_idx] = render_row(header, rd)
                applied.append(url)

    not_found = [u for u in updates_by_url if u not in applied]
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"applied": applied, "not_found": not_found}


if __name__ == "__main__":
    mcp.run()
