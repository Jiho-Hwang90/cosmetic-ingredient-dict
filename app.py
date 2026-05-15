"""
성분명 사전 — 한글 ↔ 영문 자동 양방향 변환
식약처 화장품성분사전(KCIA CID) 기반

실행:
  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.excel_export import default_filename, results_to_xlsx_bytes
from lib.translator import build_index, build_korean_index, load_cache, translate_list

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="성분명 사전",
    page_icon="🧴",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 880px; }
      html, body, [class*="css"], .stApp, p, span, div, label { color: #2D2D2D; }
      h1, h2, h3, h4, h5, h6 { color: #2D2D2D; font-weight: 700; }
      .toolkit-sub { color: #6B6B6B; font-size: 0.92rem; margin-top: -0.5rem; margin-bottom: 1.5rem; }
      .stCaption, [data-testid="stCaptionContainer"] { color: #6B6B6B !important; }

      .stButton>button {
        background-color: #2D2D2D !important; border: none;
        padding: 0.55rem 1.4rem; font-weight: 600; border-radius: 6px;
      }
      .stButton>button, .stButton>button * { color: #FFFFFF !important; }
      .stButton>button:hover { background-color: #444444 !important; }
      .stButton>button:hover, .stButton>button:hover * { color: #FFFFFF !important; }

      .stDownloadButton>button {
        background-color: #FFFFFF !important; border: 1px solid #2D2D2D !important;
        padding: 0.45rem 1.2rem; font-weight: 600; border-radius: 6px;
      }
      .stDownloadButton>button, .stDownloadButton>button * { color: #2D2D2D !important; }
      .stDownloadButton>button:hover { background-color: #F7F7F7 !important; }
      .stDownloadButton>button:hover, .stDownloadButton>button:hover * { color: #2D2D2D !important; }

      div[data-testid="stMetric"] {
        background-color: #F7F7F7; border-radius: 6px; padding: 0.6rem 1rem;
      }
      div[data-testid="stMetric"] label { color: #6B6B6B !important; }
      div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #2D2D2D !important; }

      /* 결과 테이블 텍스트 색 강제 */
      .stDataFrame, .stDataFrame * { color: #2D2D2D !important; }
      [data-testid="stExpander"] p, [data-testid="stExpander"] span { color: #2D2D2D !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 헤더
# ============================================================
st.markdown("# 성분명 사전")
st.markdown(
    '<div class="toolkit-sub">한글 ↔ 영문 자동 양방향 변환 · 식약처 화장품성분사전(KCIA CID) 기반</div>',
    unsafe_allow_html=True,
)


# ============================================================
# 캐시 로드
# ============================================================
@st.cache_resource(show_spinner=False)
def _load_data():
    items = load_cache()
    idx = build_index(items)
    kidx = build_korean_index(items)
    return items, idx, kidx


with st.spinner("성분 DB 불러오는 중 ..."):
    try:
        items, idx, kidx = _load_data()
    except Exception as e:
        st.error(f"성분 DB 로드 실패: {type(e).__name__} — {e}")
        st.stop()

st.caption(
    f"성분 DB: {len(items):,}건 · 영문 인덱스 {len(idx):,}키 · 한글 인덱스 {len(kidx):,}키"
)

# ============================================================
# 입력
# ============================================================
st.markdown("### 1) 성분명 붙여넣기")
st.markdown(
    '<div style="color:#6B6B6B; font-size:0.85rem;">한 줄에 하나씩 입력하세요. <b>한글이든 영문이든 자동으로 감지</b>해서 반대 언어로 변환합니다. 콤마·세미콜론 구분도 OK.</div>',
    unsafe_allow_html=True,
)

input_text = st.text_area(
    label="ingredient input",
    value="",
    placeholder="예) Water\n글리세린\nNiacinamide\n하이알루로닉애씨드\n병풀",
    height=220,
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 4])
with col1:
    run = st.button("변환하기", type="primary", use_container_width=True)
with col2:
    st.markdown(
        '<div style="color:#888888; font-size:0.8rem; padding-top: 0.6rem;">결과는 아래에 표시됩니다.</div>',
        unsafe_allow_html=True,
    )


def parse_input(text: str) -> list:
    out = []
    for line in (text or "").splitlines():
        for tok in line.replace(";", ",").split(","):
            t = tok.strip()
            if t:
                out.append(t)
    return out


# ============================================================
# 실행
# ============================================================
if run:
    inci_list = parse_input(input_text)
    if not inci_list:
        st.warning("입력이 비어있습니다.")
        st.stop()

    with st.spinner(f"매칭 중 ... ({len(inci_list)}건)"):
        results = translate_list(inci_list, items, idx, kidx)

    input_count = len(inci_list)
    ok = sum(1 for r in results if r["status"] == "OK")
    partial = sum(1 for r in results if r["status"] == "PARTIAL")
    nf = sum(1 for r in results if r["status"] == "NOT_FOUND")
    cs_prohibited = sum(1 for r in results if r.get("cs_status") == "PROHIBITED")
    cs_restricted = sum(1 for r in results if r.get("cs_status") in ("RESTRICTED", "IMPURITY"))

    st.markdown("### 2) 결과")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("입력", f"{input_count}건")
    m2.metric("정확 매칭", f"{ok}건")
    m3.metric("부분 매칭", f"{partial}건")
    m4.metric("미매칭", f"{nf}건")

    if cs_prohibited > 0:
        st.error(
            f"🚫 **107 Clean Standard 위반 {cs_prohibited}건** — 처방·PDP 사용 불가 성분이 포함되어 있습니다. "
            "표의 '107 기준' 컬럼에서 확인하세요."
        )
    elif cs_restricted > 0:
        st.warning(
            f"⚠️ **제한 사용 {cs_restricted}건** — 한도 내에서만 사용 가능한 성분입니다. "
            "함량 확인 필수."
        )

    if partial > 0:
        st.info(
            "🔍 **부분 매칭 결과**: 정확히 일치하는 표준명이 없어서 키워드가 포함된 성분도 함께 보여드립니다. "
            "PDP·전성분 표기에는 정식 표준 한글명을 사용하세요."
        )

    def _shorten(s: str, n: int = 80) -> str:
        if not s:
            return ""
        return s if len(s) <= n else s[:n].rstrip() + "…"

    df = pd.DataFrame([
        {
            "입력": r["input"],
            "방향": "영→한" if r.get("direction") == "eng→kor" else "한→영",
            "한글명": r["kor"],
            "영문명": r["eng"],
            "107 기준": r.get("cs_label", ""),
            "CAS No.": r["cas"],
            "기원·정의": _shorten(r["origin"], 80),
            "상태": r["status"],
        }
        for r in results
    ])

    def _highlight(row):
        cs_status = None
        for r in results:
            if r["input"] == row["입력"] and (r.get("kor") or "") == row["한글명"]:
                cs_status = r.get("cs_status")
                break
        if cs_status == "PROHIBITED":
            return ["background-color: #FBE5E5; color: #8B0000"] * len(row)
        if cs_status in ("RESTRICTED", "IMPURITY"):
            return ["background-color: #FFF4D9; color: #5C4400"] * len(row)
        s = row["상태"]
        if s == "PARTIAL":
            return ["background-color: #E8F1FA; color: #2D2D2D"] * len(row)
        if s == "NOT_FOUND":
            return ["background-color: #FFF2CC; color: #2D2D2D"] * len(row)
        return ["color: #2D2D2D"] * len(row)

    st.dataframe(
        df.style.apply(_highlight, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "기원·정의": st.column_config.TextColumn("기원·정의", width="medium", help="80자에서 잘림 — 전체 보려면 클릭"),
            "영문명": st.column_config.TextColumn("영문명", width="medium"),
            "한글명": st.column_config.TextColumn("한글명", width="small"),
        },
    )

    # 107 위반·제한 상세
    flagged = [r for r in results if r.get("cs_status") in ("PROHIBITED", "RESTRICTED", "IMPURITY")]
    if flagged:
        with st.expander(f"🚨 107 Clean Standard 상세 ({len(flagged)}건)", expanded=True):
            for r in flagged:
                icon = "🚫" if r["cs_status"] == "PROHIBITED" else "⚠️"
                st.markdown(
                    f"- {icon} **{r['kor'] or r['input']}** ({r['eng']}) — "
                    f"{r.get('cs_label', '')}  \n"
                    f"  *{r.get('cs_detail', '')}*"
                )

    xlsx_bytes = results_to_xlsx_bytes(results)
    st.download_button(
        label="📥 Excel 다운로드",
        data=xlsx_bytes,
        file_name=default_filename(),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if nf > 0:
        with st.expander(f"미매칭 {nf}건 — 식약처 사전에 없음"):
            for r in results:
                if r["status"] == "NOT_FOUND":
                    st.write(f"• {r['input']}  ({'영→한' if r.get('direction')=='eng→kor' else '한→영'})")
            st.caption("식약처 화장품성분사전(KCIA CID)에서 직접 확인: https://kcia.or.kr/cid/search/ingd_list.php")


# ============================================================
# 푸터
# ============================================================
st.markdown("---")
st.markdown(
    """
    <div style="color:#888888; font-size:0.78rem; line-height:1.6;">
      <b>출처</b> · 성분 데이터: 식품의약품안전처 화장품 원료성분정보 (data.go.kr 15111774)
      · 107 Clean Standard: 2026.02.05 기준<br>
      <b>면책</b> · 매칭 결과는 참고용입니다. PDP·전성분 표기의 최종 책임은 사용자에게 있으며,
      식약처 화장품성분사전(KCIA CID) 원문 확인을 권장합니다.<br>
      <b>문의·개선 요청</b> · 황지호 책임연구원
    </div>
    <div style="color:#B0B0B0; font-size:0.72rem; text-align:right; margin-top:0.8rem;">
      Made by 황지호 책임연구원
    </div>
    """,
    unsafe_allow_html=True,
)
