"""
content_generator.py
====================
Claude API를 호출해 카드뉴스 1세트(8장) 분량의 콘텐츠를 JSON으로 반환.

지시서 1-2 구조 준수:
  ① 문제 상황 → ② 흔한 실수 멘트 → ③ 권장 화법(Before/After)
  → ④ 심리학 근거 → ⑤ 한 줄 요약 + 표지/CTA

보상(보험금 청구·심사 분쟁) 관련 주제는 시스템 프롬프트에서 차단.
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
    topic: str           # 세부 주제 (e.g. "거절 처리 화법")
    hook: str            # 표지에 들어갈 후킹 한 줄
    cards: list[dict]    # 카드 8장
    caption: str         # 인스타 캡션
    hashtags: list[str]  # 해시태그


# ----------------------------------------------------------
# 시스템 프롬프트
# ----------------------------------------------------------
SYSTEM_PROMPT = """\
당신은 한국 보험업계 15년 경력의 시니어 보험설계사 겸 세일즈 트레이너입니다.
타겟 독자는 현장에서 일하는 보험설계사이며, 인스타그램 카드뉴스 8장 분량의
'보험 상담 화법' 콘텐츠를 만들어야 합니다.

# 절대 금지 주제 (사실관계 오류 위험)
- 보험금 청구 / 심사 / 보상 분쟁
- 약관 해석 / 면책 조항
- 의료자문 / 질병 코드
- 특정 회사·상품 비교
주제가 위 항목과 닿으면 인접한 '상담 화법' 영역으로 즉시 회전하세요.

# 작성 원칙
1. 추상론 금지. "고객 신뢰 중요" 같은 일반론 X. 실제 멘트 대본 형태로 작성.
2. Before/After 형식의 화법 비교는 반드시 따옴표로 묶인 직접 멘트로.
3. 심리학 근거는 카네기, 아들러, 치알디니, 다니엘 카너먼, 로버트 시알디니 중 1명.
   인용은 12자 이내로 짧게 (저작권 한도 준수).
4. 카드별 글자 수 상한 엄수 (1080x1080 캔버스에 들어가야 함):
   - headline: 24자 이내
   - subhead: 60자 이내
   - quote: 50자 이내
5. 표지(cover)는 강한 후킹 — 숫자, 의문문, 의외성 중 택1.
6. 마지막 카드(cta)는 저장·공유 유도 + 다음 콘텐츠 예고.

# 출력 형식 — 반드시 아래 JSON 스키마만, 다른 텍스트 절대 금지
{
  "topic": "구체 세부 주제",
  "hook": "표지 후킹 한 줄 (24자 이내)",
  "cards": [
    {
      "type": "cover",
      "label": "INSURANCE TALK",
      "headline": "표지 메인 카피",
      "accent": "headline 안에서 강조할 단어 (없으면 빈 문자열)",
      "subhead": "표지 서브 카피"
    },
    {
      "type": "problem",
      "label": "02 문제 상황",
      "headline": "이런 상황 익숙하시죠?",
      "subhead": "구체 상황 묘사 2~3줄"
    },
    {
      "type": "mistake",
      "label": "03 흔한 실수",
      "headline": "이렇게 말하고 있다면",
      "bad_quote": "설계사가 자주 하는 잘못된 멘트",
      "explain": "왜 이 멘트가 안 통하는지 한 줄"
    },
    {
      "type": "before",
      "label": "04 BEFORE",
      "headline": "기존 화법",
      "bad_quote": "Before 멘트 직접 인용"
    },
    {
      "type": "after",
      "label": "05 AFTER",
      "headline": "권장 화법",
      "good_quote": "After 멘트 직접 인용",
      "accent": "good_quote 안에서 강조할 핵심 단어"
    },
    {
      "type": "theory",
      "label": "06 WHY IT WORKS",
      "author": "심리학자/이론가 이름",
      "quote": "12자 이내 핵심 개념",
      "explain": "왜 이 화법이 통하는지 2줄 설명"
    },
    {
      "type": "summary",
      "label": "07 ONE-LINER",
      "headline": "한 줄 요약 카피",
      "accent": "헤드라인 안 강조 단어",
      "subhead": "오늘 가져갈 한 가지 행동"
    },
    {
      "type": "cta",
      "label": "08 SAVE & SHARE",
      "headline": "이 멘트, 내일 상담에서",
      "subhead": "저장하고 다음에 한 번 써보세요. 다음 카드는 ___ 편."
    }
  ],
  "caption": "인스타 캡션 (300~500자, 핵심 멘트 다시 정리 + 행동 유도)",
  "hashtags": ["#보험설계사", "#영업화법", "..."]
}
"""


# ----------------------------------------------------------
# 핵심 함수
# ----------------------------------------------------------
def _extract_json(raw: str) -> dict:
    """LLM이 ```json 블록을 붙이거나 앞뒤 텍스트를 추가해도 안전하게 파싱."""
    # 코드펜스 제거
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    # 첫 { 부터 마지막 } 까지
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON object not found in LLM output:\n{raw[:300]}")
    return json.loads(cleaned[start : end + 1])


def _validate(cs: dict, expected_cards: int = 8) -> None:
    required_top = {"topic", "hook", "cards", "caption", "hashtags"}
    missing = required_top - cs.keys()
    if missing:
        raise ValueError(f"Missing top-level keys: {missing}")
    if len(cs["cards"]) != expected_cards:
        raise ValueError(
            f"Expected {expected_cards} cards, got {len(cs['cards'])}"
        )

    expected_types = [
        "cover", "problem", "mistake", "before",
        "after", "theory", "summary", "cta",
    ]
    for i, (card, want) in enumerate(zip(cs["cards"], expected_types)):
        if card.get("type") != want:
            raise ValueError(
                f"Card {i} type mismatch: expected '{want}', got '{card.get('type')}'"
            )


def generate_card_set(
    sub_topic: Optional[str] = None,
    config_path: str = "config.yaml",
    api_key: Optional[str] = None,
) -> CardSet:
    """
    Claude API를 호출해 카드뉴스 한 세트를 생성한다.

    Args:
        sub_topic: '거절 처리', '클로징', '추천 요청' 등 세부 주제.
                   None이면 LLM이 다양한 화법 주제 중 하나를 자동 선택.
        config_path: config.yaml 경로.
        api_key: Anthropic API 키. None이면 ANTHROPIC_API_KEY env 변수 사용.

    Returns:
        CardSet 객체.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    llm_cfg = cfg["llm"]
    cards_per_set = cfg["design"]["cards_per_set"]

    user_msg = (
        f"세부 주제: {sub_topic}\n"
        if sub_topic
        else "세부 주제: 자유 선택 (거절처리/니즈환기/클로징/추천요청/DB콜 첫30초 중 택1)\n"
    )
    user_msg += f"카드 수: {cards_per_set}장\n"
    user_msg += "위 시스템 프롬프트 형식대로 JSON만 출력해주세요."

    # lazy import — stub 모드에서는 anthropic 패키지가 없어도 OK
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
# 더미 (LLM 호출 없이 테스트할 때 사용)
# ----------------------------------------------------------
def stub_card_set(sub_topic: str = "거절 처리 화법") -> CardSet:
    """API 키 없이 시스템 검수용 더미 데이터."""
    return CardSet(
        topic=sub_topic,
        hook=f"\"{sub_topic}\" — 한 마디면 끝납니다",
        cards=[
            {
                "type": "cover",
                "label": "INSURANCE TALK",
                "headline": "거절을 \"기회\"로 바꾸는 한 마디",
                "accent": "기회",
                "subhead": "고객이 \"생각해볼게요\" 했을 때, 당신의 다음 멘트는?",
            },
            {
                "type": "problem",
                "label": "02 문제 상황",
                "headline": "\"생각해볼게요\" 의 진짜 의미",
                "subhead": "고객은 거절하는 게 아닙니다.\n결정할 정보가 부족할 뿐입니다.",
            },
            {
                "type": "mistake",
                "label": "03 흔한 실수",
                "headline": "이렇게 매달리면 끝납니다",
                "bad_quote": "\"언제 결정하실 수 있을까요? 다음 주에 다시 연락드릴게요.\"",
                "explain": "결정 시점만 묻는 순간, 고객은 도망갈 명분을 얻습니다.",
            },
            {
                "type": "before",
                "label": "04 BEFORE",
                "headline": "쫓는 화법",
                "bad_quote": "\"천천히 생각해보시고 연락주세요.\"",
            },
            {
                "type": "after",
                "label": "05 AFTER",
                "headline": "끌어당기는 화법",
                "good_quote": "\"무엇이 가장 마음에 걸리세요? 그 부분만 정리해드릴게요.\"",
                "accent": "마음에 걸리세요",
            },
            {
                "type": "theory",
                "label": "06 WHY IT WORKS",
                "author": "데일 카네기",
                "quote": "관심을 받는 사람",
                "explain": "사람은 자신의 고민에 집중해주는 상대에게\n마음을 엽니다. 결정 압박 대신 경청을 주세요.",
            },
            {
                "type": "summary",
                "label": "07 ONE-LINER",
                "headline": "거절은 \"질문\"으로 받습니다",
                "accent": "질문",
                "subhead": "오늘 한 명의 고객에게 이 멘트를 써보세요.",
            },
            {
                "type": "cta",
                "label": "08 SAVE & SHARE",
                "headline": "이 멘트, 내일 상담에서",
                "subhead": "저장하고 한 번 써보세요. 다음 카드는 \"클로징 3초\" 편.",
            },
        ],
        caption=(
            "고객의 \"생각해볼게요\"는 거절이 아닙니다.\n"
            "결정할 정보가 아직 부족하다는 신호입니다.\n\n"
            "❌ \"언제 결정하실까요?\"\n"
            "✅ \"무엇이 가장 마음에 걸리세요?\"\n\n"
            "쫓아가지 말고, 끌어당기세요.\n"
            "오늘 한 명의 고객에게 이 한 마디를 써보세요.\n\n"
            "이 카드, 저장하고 내일 상담에서 꺼내쓰세요."
        ),
        hashtags=[
            "#보험설계사", "#보험영업", "#영업화법", "#보험상담",
            "#FC", "#설계사일상", "#보험인", "#클로징",
            "#거절처리", "#세일즈",
        ],
    )


# ----------------------------------------------------------
# CLI
# ----------------------------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--topic", default=None, help="세부 주제 (없으면 자동 선택)")
    p.add_argument("--stub", action="store_true", help="API 호출 없이 더미 데이터 사용")
    p.add_argument("--out", default=None, help="JSON 저장 경로 (없으면 stdout)")
    args = p.parse_args()

    cs = stub_card_set(args.topic or "거절 처리 화법") if args.stub else generate_card_set(args.topic)

    out_json = json.dumps(asdict(cs), ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"[content_generator] saved: {args.out}", file=sys.stderr)
    else:
        print(out_json)
