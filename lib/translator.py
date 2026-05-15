"""
전성분 한글화 핵심 로직 (웹·CLI 어디서든 import 해서 사용 가능)

식약처 화장품 원료성분정보 API (data.go.kr 15111774) 사용.
영문 검색이 불가능하므로 전체 21,788건을 1회 다운로드해 cache/ingredients.json 으로
저장하고, 영문 INCI → 한글명 매칭은 클라이언트 측에서 처리.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

# ============================================================
# 설정
# ============================================================
SERVICE_KEY = os.environ.get(
    "MFDS_SERVICE_KEY",
    "74d94366bbf1fb32c94c6fc1b3bf27af5bb6168cb70155497f3d5415a2ca435a",
)
BASE_URL = "https://apis.data.go.kr/1471000/CsmtcsIngdCpntInfoService01"
OPERATION = "getCsmtcsIngdCpntInfoService01"
ENDPOINT = f"{BASE_URL}/{OPERATION}"

# 식약처 API 실측 필드명
F_KOR = "INGR_KOR_NAME"
F_ENG = "INGR_ENG_NAME"
F_CAS = "CAS_NO"
F_ORIGIN = "ORIGIN_MAJOR_KOR_NAME"
F_SYNONYM = "INGR_SYNONYM"

PER_PAGE = 500
MAX_RETRIES = 4

# 식약처 DB 가 콤마 동의어로 묶어둔 탓에 부정확한 매칭이 나오는 케이스 강제 보정
OVERRIDES_ENG_TO_KOR = {
    "water": "정제수",
    "aqua": "정제수",
}

# ============================================================
# 캐시 경로
# ============================================================
PKG_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = PKG_ROOT / "cache" / "ingredients.json"


# ============================================================
# API 다운로드
# ============================================================
def _get_with_retry(params: dict) -> requests.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(ENDPOINT, params=params, timeout=60)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            time.sleep(2 * attempt)
    raise last_exc  # type: ignore[misc]


def fetch_all_ingredients(progress_callback=None) -> list:
    all_items: list = []
    page = 1
    total_count: Optional[int] = None
    while True:
        params = {
            "serviceKey": SERVICE_KEY,
            "pageNo": page,
            "numOfRows": PER_PAGE,
            "type": "json",
        }
        r = _get_with_retry(params)
        data = r.json()
        body = data.get("body", {})
        if total_count is None:
            total_count = body.get("totalCount", 0)
        items = body.get("items", [])
        if not items:
            break
        all_items.extend(items)
        if progress_callback:
            progress_callback(len(all_items), total_count or len(all_items))
        if len(items) < PER_PAGE:
            break
        page += 1
        time.sleep(0.15)
    return all_items


# ============================================================
# 캐시 로드
# ============================================================
def load_cache(force_refresh: bool = False, progress_callback=None) -> list:
    if CACHE_FILE.exists() and not force_refresh:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    items = fetch_all_ingredients(progress_callback=progress_callback)
    CACHE_FILE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return items


# ============================================================
# 인덱싱 & 매칭
# ============================================================
def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _split_eng_tokens(eng_field: str) -> list:
    if not eng_field:
        return []
    out = []
    for part in eng_field.replace(";", ",").split(","):
        t = part.strip()
        if t:
            out.append(t)
    return out


def build_index(items: list) -> dict:
    """영문 → item 인덱스 (영문명 콤마 동의어 + 영문 이명 모두 키로)"""
    idx: dict = {}
    for it in items:
        for eng_tok in _split_eng_tokens(it.get(F_ENG)):
            k = _normalize(eng_tok)
            if k and k not in idx:
                idx[k] = it
        for syn_tok in _split_eng_tokens(it.get(F_SYNONYM)):
            k = _normalize(syn_tok)
            # 영문만 (한글 이명은 별도 인덱스로)
            if k and k not in idx and not _is_korean(k):
                idx[k] = it
    return idx


def build_korean_index(items: list) -> dict:
    """한글명 → item 인덱스 (표준 한글명 + 한글 이명)"""
    kidx: dict = {}
    for it in items:
        kor = (it.get(F_KOR) or "").strip()
        if kor and kor not in kidx:
            kidx[kor] = it
        syn = it.get(F_SYNONYM) or ""
        for tok in syn.replace(";", ",").split(","):
            t = tok.strip()
            if t and _is_korean(t) and t not in kidx:
                kidx[t] = it
    return kidx


def _is_korean(s: str) -> bool:
    """문자열에 한글(가-힣 또는 ㄱ-ㅎ)이 한 글자라도 있으면 True"""
    if not s:
        return False
    for ch in s:
        if "가" <= ch <= "힣":
            return True
        if "ㄱ" <= ch <= "ㆎ":
            return True
    return False


def _find_by_kor(items: list, kor_name: str) -> Optional[dict]:
    for it in items:
        if (it.get(F_KOR) or "").strip() == kor_name:
            return it
    return None


def lookup_one(inci_eng: str, items: list, idx: dict) -> Optional[dict]:
    needle = _normalize(inci_eng)
    if not needle:
        return None
    # 0) 오버라이드
    if needle in OVERRIDES_ENG_TO_KOR:
        forced = _find_by_kor(items, OVERRIDES_ENG_TO_KOR[needle])
        if forced:
            return forced
    # 1) 정확 일치
    if needle in idx:
        return idx[needle]
    # 2) 괄호 제거 후 재시도
    no_paren = needle
    while "(" in no_paren and ")" in no_paren:
        s, e = no_paren.find("("), no_paren.find(")")
        no_paren = (no_paren[:s] + no_paren[e + 1:]).strip()
    no_paren = " ".join(no_paren.split())
    if no_paren in idx:
        return idx[no_paren]
    # 3) 자카드 유사도 0.6 이상 부분 매칭
    needle_tokens = set(needle.split())
    best = None
    best_score = 0.0
    for eng_key, it in idx.items():
        eng_tokens = set(eng_key.split())
        if not eng_tokens:
            continue
        common = needle_tokens & eng_tokens
        if not common:
            continue
        score = len(common) / len(needle_tokens | eng_tokens)
        if score > best_score and score >= 0.6:
            best_score = score
            best = it
    return best


def lookup_one_korean(kor_name: str, kidx: dict) -> Optional[dict]:
    """한글명 정확 일치(표준 한글명 또는 한글 이명)"""
    needle = (kor_name or "").strip()
    if not needle:
        return None
    if needle in kidx:
        return kidx[needle]
    # 띄어쓰기 제거 후 재시도
    no_space = needle.replace(" ", "")
    for k, it in kidx.items():
        if k.replace(" ", "") == no_space:
            return it
    return None


def search_partial_korean(query: str, items: list, limit: int = 50) -> list:
    """한글 키워드 부분 검색 (정확 → 시작 → 포함 순으로 정렬)"""
    needle = (query or "").strip()
    if not needle:
        return []
    exact, starts, contains = [], [], []
    seen: set = set()
    for it in items:
        kor = (it.get(F_KOR) or "").strip()
        syn = it.get(F_SYNONYM) or ""
        syn_tokens = [t.strip() for t in syn.replace(";", ",").split(",") if t.strip()]
        ident = kor or "_"
        if ident in seen:
            continue
        bucket = None
        if kor == needle or needle in syn_tokens:
            bucket = exact
        elif kor.startswith(needle):
            bucket = starts
        elif needle in kor or any(needle in s for s in syn_tokens):
            bucket = contains
        if bucket is not None:
            bucket.append(it)
            seen.add(ident)
    return (exact + starts + contains)[:limit]


def search_partial_english(query: str, items: list, limit: int = 50) -> list:
    """영문 키워드 부분 검색 (정확 → 시작 → 포함 순으로 정렬)"""
    needle = _normalize(query)
    if not needle:
        return []
    exact, starts, contains = [], [], []
    seen: set = set()
    for it in items:
        kor = (it.get(F_KOR) or "").strip()
        ident = kor or "_"
        if ident in seen:
            continue
        eng_tokens = [_normalize(t) for t in _split_eng_tokens(it.get(F_ENG))]
        bucket = None
        if needle in eng_tokens:
            bucket = exact
        elif any(t.startswith(needle) for t in eng_tokens):
            bucket = starts
        elif any(needle in t for t in eng_tokens):
            bucket = contains
        if bucket is not None:
            bucket.append(it)
            seen.add(ident)
    return (exact + starts + contains)[:limit]


def _item_to_row(token: str, direction: str, it: dict, status: str) -> dict:
    from lib.clean_standard import check_clean_standard
    eng = it.get(F_ENG) or ""
    cs = check_clean_standard(eng)
    return {
        "input": token,
        "direction": direction,
        "kor": it.get(F_KOR) or "",
        "eng": eng,
        "cas": it.get(F_CAS) or "",
        "origin": it.get(F_ORIGIN) or "",
        "synonym": it.get(F_SYNONYM) or "",
        "status": status,
        "cs_status": cs["status"],
        "cs_label": cs["label"],
        "cs_detail": cs["detail"],
    }


def translate_list(
    inci_list: list,
    items: list,
    idx: dict,
    kidx: Optional[dict] = None,
    partial_limit: int = 30,
) -> list:
    """입력 리스트 → 표준 결과 리스트(dict).

    각 라인마다 한글 포함 여부 자동 감지하고:
      1) 정확 매칭이 있으면 OK 행으로 최상단
      2) 부분 검색 결과(키워드 포함 성분)를 PARTIAL 행으로 함께 표시
      3) 둘 다 없으면 NOT_FOUND
    중복(정확 매칭과 같은 한글명)은 PARTIAL 에서 자동 제외.
    """
    results = []
    for raw in inci_list:
        token = (raw or "").strip()
        if not token:
            continue
        direction = "kor→eng" if _is_korean(token) else "eng→kor"

        # 1) 정확 매칭
        if direction == "kor→eng" and kidx is not None:
            exact = lookup_one_korean(token, kidx)
        else:
            exact = lookup_one(token, items, idx)

        # 2) 부분 검색 (정확 매칭 유무와 무관하게 항상 시도)
        partial = (
            search_partial_korean(token, items, partial_limit)
            if direction == "kor→eng"
            else search_partial_english(token, items, partial_limit)
        )

        # 정확 매칭과 동일 항목은 PARTIAL 에서 제외 (중복 방지)
        exact_kor = (exact.get(F_KOR) or "").strip() if exact else None
        if exact_kor:
            partial = [it for it in partial if (it.get(F_KOR) or "").strip() != exact_kor]

        any_hit = False
        if exact:
            results.append(_item_to_row(token, direction, exact, "OK"))
            any_hit = True
        for it in partial:
            results.append(_item_to_row(token, direction, it, "PARTIAL"))
            any_hit = True

        if not any_hit:
            results.append({
                "input": token, "direction": direction,
                "kor": "", "eng": "", "cas": "",
                "origin": "", "synonym": "", "status": "NOT_FOUND",
            })
    return results
