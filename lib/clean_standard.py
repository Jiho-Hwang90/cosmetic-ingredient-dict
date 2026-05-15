"""
107 Clean Standard (2026.02.05 기준) — 금지·제한 성분 자동 체크 로직

원본 기준표: c:\\Users\\ajfxo\\OneDrive - oneoseven\\99. 문서\\06. 107 Lab\\
            12 Clean Standard\\2026.02.05 Clean standard.pdf

매칭 방식:
  1) 영문명 정확 일치 (INCI 토큰 기준)
  2) 영문 패턴 포함 (PEG-, perfluor, paraben 등)
"""
from __future__ import annotations

# ============================================================
# 1) 완전 금지 (Prohibited)
# ============================================================
PROHIBITED_EXACT = {
    "4-methylbenzylidene camphor",
    "acetaldehyde",
    "acetone",
    # Acrylates
    "ethyl methacrylate",
    "butyl methacrylate",
    "methyl methacrylate",
    "hydroxypropyl methacrylate",
    "tetrahydrofurfuryl methacrylate",
    "trimethylolpropane trimethacrylate",
    # Aluminum salts (soluble)
    "aluminum chloride",
    "aluminum chlorohydrate",
    "aluminum chlorohydrex",
    "aluminum dichlorohydrate",
    "aluminum sesquichlorohydrate",
    "aluminum zirconium octachlorohydrate",
    "aluminum zirconium pentachlorohydrate",
    "aluminum zirconium tetrachlorohydrate",
    "aluminum zirconium trichlorohydrate",
    "aluminum zirconium octachlorohydrex gly",
    "aluminum zirconium pentachlorohydrex gly",
    "aluminum zirconium tetrachlorohydrex gly",
    "aluminum zirconium trichlorohydrex gly",
    # Animal-derived
    "animal musk",
    # Benzophenones
    "benzophenone",
    "benzophenone-1", "benzophenone-2", "benzophenone-3", "benzophenone-4",
    "benzophenone-5", "benzophenone-6", "benzophenone-7", "benzophenone-8",
    "benzophenone-9", "benzophenone-10", "benzophenone-11", "benzophenone-12",
    "oxybenzone",
    "methyl benzophenone",
    "stearaminocarbonyl benzophenone-4",
    "trimethylbenzophenone",
    # BHA / BHT
    "bha",
    "butylated hydroxyanisole",
    "bht",
    "butylated hydroxytoluene",
    # EDTA
    "edta",
    "disodium edta",
    "calcium disodium edta",
    "tetrasodium edta",
    "trisodium edta",
    # Formaldehyde-releasing
    "2-bromo-2-nitropropane-1,3-diol",
    "bronopol",
    "5-bromo-5-nitro-1,3-dioxane",
    "benzylhemiformal",
    "diazolidinyl urea",
    "dmdm hydantoin",
    "imidazolidinyl urea",
    "methenamine",
    "quaternium-15",
    "sodium hydroxymethylglycinate",
    "methanediol",
    "methylene glycol",
    "glyoxal",
    # Hydroquinones
    "hydroquinone",
    # Isothiazolinone
    "methylchloroisothiazolinone",
    "methylisothiazolinone",
    # Mineral oil
    "mineral oil",
    "hydrogenated mineral oil",
    # Nitromusks
    "musk ketone",
    "hexamethylindanopyran",
    "acetyl hexamethyl tetralin",
    "acetyl hexamethyl indan",
    # UV
    "octinoxate",
    "ethylhexyl methoxycinnamate",
    "octocrylene",
    # Paraffin
    "paraffin",
    # Resorcinol
    "resorcinol",
    # Retinyl palmitate
    "retinyl palmitate",
    # Cyclic silicones
    "cyclotetrasiloxane",
    "cyclopentasiloxane",
    "cyclohexasiloxane",
    # Styrene
    "styrene",
    # Sulfates
    "sodium laureth sulfate",
    "sodium lauryl sulfate",
    # Toluene
    "toluene",
    # Anti-bacterial
    "triclocarban",
    "triclosan",
    # TEA
    "triethanolamine",
}

# 부분 일치 패턴 — 단어가 포함되기만 하면 금지
PROHIBITED_PATTERNS = [
    ("perfluor", "PFAS (perfluor 계열)"),
    ("polyfluor", "PFAS (polyfluor 계열)"),
    ("paraben", "Parabens"),
    ("benzophenone-", "Benzophenones 시리즈"),
]

# ============================================================
# 2) 불순물 한도 (Impurity Limit)
# ============================================================
IMPURITY_LIMIT_EXACT = {
    "1,4-dioxane": "Rinse off ≤ 10ppm / Lip ≤ 2ppm / Leave on ≤ 3ppm",
    "ethylene oxide": "Lip < 2ppm / All other < 7ppm",
}

# ============================================================
# 3) 제한 사용 (Restricted — 한도 내 허용)
# ============================================================
RESTRICTED_EXACT = {
    "arbutin": "face cream ≤ 2% / body lotion ≤ 0.5%",
    "alpha-arbutin": "face cream ≤ 7%",
    "daidzein": "≤ 0.02%",
    "synthetic fragrance": "< 1%",
    "fragrance": "합성향료일 경우 < 1%",
    "parfum": "합성향료일 경우 < 1%",
    "genistein": "≤ 0.007%",
    "kojic acid": "≤ 1%",
    "retinol": "body lotion ≤ 0.05%RE / Others ≤ 0.3%RE",
    "retinyl acetate": "body lotion ≤ 0.05%RE / Others ≤ 0.3%RE",
}

RESTRICTED_PATTERNS = [
    ("peg-", "PEGs — INCI에 PEG 포함 성분 전반 제한"),
    ("peg/", "PEGs — INCI에 PEG 포함 성분 전반 제한"),
]


# ============================================================
# 매칭 함수
# ============================================================
def _split_eng(eng_field: str) -> list:
    out = []
    for part in (eng_field or "").replace(";", ",").split(","):
        t = part.strip().lower()
        if t:
            out.append(t)
    return out


def check_clean_standard(eng_name: str) -> dict:
    """매칭된 영문명을 클린스탠다드와 대조.

    반환:
        {"status": "PROHIBITED" | "IMPURITY" | "RESTRICTED" | "OK",
         "label": 표시할 레이블,
         "detail": 설명·한도}
    """
    if not eng_name:
        return {"status": "UNKNOWN", "label": "확인불가", "detail": "영문명 없음"}

    eng_tokens = _split_eng(eng_name)
    full_text = " ".join(eng_tokens)

    # 1) 완전 금지 — 정확 일치
    for tok in eng_tokens:
        if tok in PROHIBITED_EXACT:
            return {"status": "PROHIBITED", "label": "🚫 금지", "detail": f"{tok} (Prohibited)"}

    # 2) 완전 금지 — 패턴 일치
    for pattern, label in PROHIBITED_PATTERNS:
        if pattern in full_text:
            return {"status": "PROHIBITED", "label": "🚫 금지", "detail": label}

    # 3) 불순물 한도
    for tok in eng_tokens:
        if tok in IMPURITY_LIMIT_EXACT:
            return {"status": "IMPURITY", "label": "⚠️ 불순물 한도", "detail": IMPURITY_LIMIT_EXACT[tok]}

    # 4) 제한 사용 — 정확 일치
    for tok in eng_tokens:
        if tok in RESTRICTED_EXACT:
            return {"status": "RESTRICTED", "label": "⚠️ 제한", "detail": RESTRICTED_EXACT[tok]}

    # 5) 제한 사용 — 패턴
    for pattern, label in RESTRICTED_PATTERNS:
        if pattern in full_text:
            return {"status": "RESTRICTED", "label": "⚠️ 제한", "detail": label}

    return {"status": "OK", "label": "✅ 사용가능", "detail": ""}
