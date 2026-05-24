"""
content_generator.py
====================
Claude API를 호출해 정보형 카드뉴스 1세트(8장) 분량을 JSON으로 반환.

대주제(theme): 보험 정보 / 건강 정보 / 생활 정보 / 금융 정보 중 하나.
카드 구조:
  cover → intro → point×3 → tip → summary → cta

⚠ 실시간 뉴스/속보는 생성하지 않는다 (지식 한계로 사실 오류 위험).
검증된 일반 정보·상식 수준만, 특정 회사·상품·종목 언급 없이.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from typing import Optional

import yaml


# ----------------------------------------------------------
# 데이터 구조
# ----------------------------------------------------------
@dataclass
class CardSet:
    topic: str           # 구체 소주제 (e.g. "실손보험 자기부담금")
    hook: str            # 표지 후킹 한 줄
    cards: list[dict]    # 카드 8장
    caption: str         # 밴드 게시글 본문
    hashtags: list[str]  # 해시태그


# ----------------------------------------------------------
# 시스템 프롬프트
# ----------------------------------------------------------
SYSTEM_PROMPT = """\
당신은 일반 대중을 위한 정보 카드뉴스를 만드는 한국어 콘텐츠 에디터입니다.
주어진 '대주제'(보험/건강/생활/금융 정보 중 하나)에 대해, 밴드 구독자가
저장하고 싶어지는 8장짜리 정보 카드뉴스를 만듭니다.

# 매우 중요 — 사실 정확성 규칙 (위반 시 치명적)
- 당신은 실시간 뉴스/속보를 알 수 없습니다. "이번주", "오늘", 특정 날짜,
  최신 사건을 단정적으로 쓰지 마세요.
- 검증되지 않은 통계·수치·연구 결과를 지어내지 마세요. 널리 알려진 상식
  수준만, 단정 대신 "~인 경우가 많습니다" 같은 완화된 톤으로.
- 특정 보험사·상품·금융 종목·병원·약품 이름을 언급하지 마세요.
- 의료 진단/처방, 투자 권유, 법률 단정은 금지. "정확한 건 전문가·기관 확인"으로 안내.

# 대주제별 방향
- 보험 정보: 소비자가 알아두면 좋은 보험 일반 상식 (용어, 구조, 점검 포인트)
- 건강 정보: 생활 속 건강 습관·상식 (진단/처방 아님, 일반 정보)
- 생활 정보: 절약·생활 꿀팁·알아두면 편한 정보
- 금융 정보: 금융 기초 상식·재테크 개념 (종목 추천 아님)

# 작성 원칙
1. 쉽고 구체적으로. 막연한 일반론 대신 바로 써먹는 정보.
2. 핵심 정보는 3가지로 정리 (point 카드 3장).
3. 글자 수 상한 (1080x1080 캔버스):
   - headline: 26자 이내
   - subhead: 70자 이내
   - body(point/tip): 80자 이내
4. 표지(cover)는 강한 후킹 — 숫자/의문문/의외성 중 택1.
5. 마지막 카드(cta)는 저장·공유 유도 + 다음 편 예고.

# 출력 형식 — 반드시 아래 JSON만, 다른 텍스트 절대 금지
{
  "topic": "구체 소주제",
  "theme": "대주제(보험 정보/건강 정보/생활 정보/금융 정보)",
  "hook": "표지 후킹 한 줄 (24자 이내)",
  "cards": [
    {"type": "cover",   "label": "대주제명", "headline": "표지 메인 카피", "accent": "강조 단어(없으면 빈문자열)", "subhead": "표지 서브 카피"},
    {"type": "intro",   "label": "왜 중요할까", "headline": "왜 알아야 하는지", "accent": "", "subhead": "배경 설명 2~3줄"},
    {"type": "point",   "label": "01", "headline": "핵심 정보 1 제목", "body": "구체 설명 (80자 이내)"},
    {"type": "point",   "label": "02", "headline": "핵심 정보 2 제목", "body": "구체 설명"},
    {"type": "point",   "label": "03", "headline": "핵심 정보 3 제목", "body": "구체 설명"},
    {"type": "tip",     "label": "실전 TIP", "headline": "바로 써먹는 팁", "body": "실생활 적용 팁 또는 주의점"},
    {"type": "summary", "label": "핵심 요약", "headline": "한 줄 요약", "accent": "강조 단어", "subhead": "오늘의 핵심 3가지 정리"},
    {"type": "cta",     "label": "저장 & 공유", "headline": "저장·공유 유도 카피", "subhead": "가족·지인과 나눠보세요. 다음 편은 ___ 정보."}
  ],
  "caption": "밴드 게시글 본문 (200~400자, 핵심 요약 + 행동 유도)",
  "hashtags": ["#관련태그", "..."]
}
"""


# ----------------------------------------------------------
# 핵심 함수
# ----------------------------------------------------------
def _extract_json(raw: str) -> dict:
    """LLM이 ```json 블록이나 앞뒤 텍스트를 추가해도 안전하게 파싱."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON object not found in LLM output:\n{raw[:300]}")
    return json.loads(cleaned[start : end + 1])


EXPECTED_TYPES = [
    "cover", "intro", "point", "point", "point", "tip", "summary", "cta",
]


def _validate(cs: dict, expected_cards: int = 8) -> None:
    required_top = {"topic", "hook", "cards", "caption", "hashtags"}
    missing = required_top - cs.keys()
    if missing:
        raise ValueError(f"Missing top-level keys: {missing}")
    if len(cs["cards"]) != expected_cards:
        raise ValueError(
            f"Expected {expected_cards} cards, got {len(cs['cards'])}"
        )
    for i, (card, want) in enumerate(zip(cs["cards"], EXPECTED_TYPES)):
        if card.get("type") != want:
            raise ValueError(
                f"Card {i} type mismatch: expected '{want}', got '{card.get('type')}'"
            )


def generate_card_set(
    theme: Optional[str] = None,
    config_path: str = "config.yaml",
    api_key: Optional[str] = None,
) -> CardSet:
    """
    Claude API를 호출해 정보형 카드뉴스 한 세트를 생성한다.

    Args:
        theme: 대주제. "보험 정보" / "건강 정보" / "생활 정보" / "금융 정보".
               None이면 LLM이 4개 중 하나 자동 선택.
        config_path: config.yaml 경로.
        api_key: Anthropic API 키. None이면 ANTHROPIC_API_KEY env 사용.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    llm_cfg = cfg["llm"]
    cards_per_set = cfg["design"]["cards_per_set"]

    user_msg = (
        f"대주제: {theme}\n"
        if theme
        else "대주제: 자유 선택 (보험 정보/건강 정보/생활 정보/금융 정보 중 택1)\n"
    )
    user_msg += f"카드 수: {cards_per_set}장\n"
    user_msg += "위 시스템 프롬프트 형식대로 JSON만 출력해주세요."

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model=llm_cfg["model"],
        max_tokens=llm_cfg["max_tokens"],
        temperature=llm_cfg["temperature"],
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    )

    data = _extract_json(raw_text)
    _validate(data, expected_cards=cards_per_set)

    return CardSet(
        topic=data["topic"],
        hook=data["hook"],
        cards=data["cards"],
        caption=data["caption"],
        hashtags=data["hashtags"],
    )


# ----------------------------------------------------------
# 더미 (LLM 호출 없이 테스트할 때)
# ----------------------------------------------------------
def stub_card_set(theme: str = "보험 정보") -> CardSet:
    """API 키 없이 시스템 검수용 더미 데이터."""
    return CardSet(
        topic="실손보험 기본 점검",
        hook="내 실손, 제대로 알고 계세요?",
        cards=[
            {
                "type": "cover",
                "label": theme,
                "headline": "실손보험, 자기부담금부터 확인하세요",
                "accent": "자기부담금",
                "subhead": "가입만 해두고 내용을 모르면 정작 필요할 때 손해봅니다.",
            },
            {
                "type": "intro",
                "label": "왜 중요할까",
                "headline": "같은 보험도 조건따라 다릅니다",
                "accent": "",
                "subhead": "가입 시기·유형에 따라 보장 범위와 부담금이 달라질 수 있습니다.",
            },
            {
                "type": "point",
                "label": "01",
                "headline": "자기부담금을 확인하세요",
                "body": "병원비 중 본인이 내는 부분입니다. 가입 시기에 따라 비율이 다른 경우가 많습니다.",
            },
            {
                "type": "point",
                "label": "02",
                "headline": "갱신형·비갱신형 구분",
                "body": "갱신형은 시간이 지나면 보험료가 오를 수 있습니다. 가입 전 유형을 꼭 확인하세요.",
            },
            {
                "type": "point",
                "label": "03",
                "headline": "중복가입은 실익이 적습니다",
                "body": "실손은 여러 개 들어도 실제 쓴 만큼만 나눠 보장됩니다. 중복 여부를 점검하세요.",
            },
            {
                "type": "tip",
                "label": "실전 TIP",
                "headline": "1년에 한 번은 점검하세요",
                "body": "보장 내용·갱신 주기·자기부담금을 연 1회 확인하면 불필요한 지출을 줄일 수 있습니다.",
            },
            {
                "type": "summary",
                "label": "핵심 요약",
                "headline": "알고 가입하면 손해 안 봅니다",
                "accent": "알고",
                "subhead": "자기부담금 · 갱신 여부 · 중복 — 이 3가지만 기억하세요.",
            },
            {
                "type": "cta",
                "label": "저장 & 공유",
                "headline": "이 카드, 가족과 나눌보세요",
                "subhead": "저장해두고 보험 점검할 때 꺼내보세요. 다음 편은 건강 정보.",
            },
        ],
        caption=(
            "실손보험, 가입만 해두고 내용은 모르시는 분 많죠?\n\n"
            "✅ 자기부담금 확인\n"
            "✅ 갱신형/비갱신형 구분\n"
            "✅ 중복가입 점검\n\n"
            "1년에 한 번만 점검해도 불필요한 지출을 줄일 수 있습니다.\n"
            "정확한 건 가입한 보험사·전문가에게 확인하세요.\n\n"
            "이 카드, 저장해두고 가족과 나눠보세요."
        ),
        hashtags=[
            "#보험상식", "#실손보험", "#생활정보", "#재테크",
            "#생활꿀팁", "#정보공유", "#고객정보", "#보험",
        ],
    )


# ----------------------------------------------------------
# CLI
# ----------------------------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--theme", default=None, help="대주제 (없으면 자동 선택)")
    p.add_argument("--stub", action="store_true", help="API 호출 없이 더미 데이터 사용")
    p.add_argument("--out", default=None, help="JSON 저장 경로 (없으면 stdout)")
    args = p.parse_args()

    cs = stub_card_set(args.theme or "보험 정보") if args.stub else generate_card_set(args.theme)

    out_json = json.dumps(asdict(cs), ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"[content_generator] saved: {args.out}", file=sys.stderr)
    else:
        print(out_json)
