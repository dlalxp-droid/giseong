"""
generate.py
===========
카드뉴스 일괄 생성 메인 엔트리.

정보형 카드뉴스 + 8주제 일일 순환 + 주제별 세부주제 풀:
  보험 → 건강 → 생활 → 금융 → 노후·은퇴 → 부동산·주택 → 자녀·가족 → 자기계발 (8일 주기)
  각 주제마다 세부주제 15개. AM/PM은 다른 세부주제 (오프셋).
  → 8 × 15 × 2 = 약 240가지 조합. 같은 조합 반복 주기 ~ 120일+.

사용 예시:
  python generate.py --slot AM            # 오늘 날짜의 순환 주제+세부
  python generate.py --slot AM --stub     # API 없이 더미로 테스트
  python generate.py --date 2026-05-25 --slot AM --topic "건강 정보"
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from content_generator import generate_card_set, stub_card_set, CardSet  # noqa: E402
from renderer import render_card_set  # noqa: E402

import yaml  # noqa: E402


ROOT = Path(__file__).parent.resolve()


# 8개 대주제 — 날짜 기준 순환 (하루 1개 주제)
THEME_POOL = [
    "보험 정보",
    "건강 정보",
    "생활 정보",
    "금융 정보",
    "노후·은퇴 정보",
    "부동산·주택 정보",
    "자녀·가족 정보",
    "자기계발 정보",
]


# 주제별 세부주제 풀 — 같은 주제가 돌아올 때마다 다음 세부주제로 자동 진행
SUBTOPIC_POOL: dict[str, list[str]] = {
    "보험 정보": [
        "실손보험 자기부담금 점검",
        "갱신형 vs 비갱신형 비교",
        "보험 중복가입 확인법",
        "보험 가입 전 점검 체크리스트",
        "보장 분석의 기본 용어",
        "보험금 수령자 지정 유의점",
        "단체보험 vs 개인보험 차이",
        "어린이보험 점검 포인트",
        "운전자보험 기본 보장",
        "화재·재산보험 상식",
        "여행자보험 핵심 확인사항",
        "종신보험 기본 구조",
        "변액보험 일반 상식",
        "보험계약 해지 전 점검",
        "만기 환급금 이해하기",
    ],
    "건강 정보": [
        "수면 위생 기본 습관",
        "사무직 자세와 통증 예방",
        "식사 시간과 혈당 안정",
        "수분 섭취 가이드",
        "짧은 운동의 효과",
        "시력 보호 습관",
        "치아 건강 기본 관리",
        "스트레스 관리 일상 팁",
        "환절기 면역 관리",
        "영양소 균형의 기본",
        "걷기의 일상 효과",
        "호흡 습관과 안정감",
        "카페인 섭취량 가이드",
        "가공식품 줄이는 법",
        "정기 건강검진 활용법",
    ],
    "생활 정보": [
        "가전 전기료 절감 팁",
        "식재료 보관 가이드",
        "옷장 정리 기본 원칙",
        "계절별 청소 체크리스트",
        "작은 공간 활용법",
        "공과금 절약 일반 팁",
        "식비 절감 장보기 전략",
        "의류 관리 기본",
        "정리정돈 첫 습관",
        "욕실·주방 관리 팁",
        "분리수거 기본 가이드",
        "가족 일정 관리 팁",
        "비상용품 준비 체크",
        "일상 시간 활용 팁",
        "휴대폰 요금제 점검법",
    ],
    "금융 정보": [
        "예금·적금 기본 구조",
        "신용점수 관리 기본",
        "가계부 시작하기",
        "비상금 만들기 원칙",
        "세금 환급 기본 상식",
        "카드 사용 관리 팁",
        "은행 수수료 줄이기",
        "자동이체 점검 습관",
        "청약통장 기본 이해",
        "연말정산 일반 팁",
        "인터넷뱅킹 보안",
        "통장 쪼개기 전략",
        "비과세 상품 일반 상식",
        "ETF 기본 개념",
        "채권 기본 개념",
    ],
    "노후·은퇴 정보": [
        "국민연금 기본 이해",
        "개인연금 일반 상식",
        "퇴직연금 종류",
        "노후 생활비 계산법",
        "은퇴 후 의료비 준비",
        "자산 분배 기본 원칙",
        "노후 주거 옵션",
        "은퇴 후 시간 활용",
        "부부 노후 계획 대화법",
        "인플레이션 대비 기본",
        "연금 수령 방식 비교",
        "노후 건강관리 일상",
        "자녀에게 의존 줄이기",
        "노후 취미 시작",
        "사회 활동 유지의 가치",
    ],
    "부동산·주택 정보": [
        "임대차 계약 기본 확인",
        "전세 vs 월세 비교",
        "보증금 보호 기본",
        "주택청약 기본 이해",
        "이사 체크리스트",
        "입주 시 점검 사항",
        "임대인·임차인 권리 기본",
        "관리비 항목 이해",
        "등기부등본 보는 법",
        "주택 보험 기본",
        "누수·결로 일반 대응",
        "계약 갱신 기본",
        "부동산 용어 상식",
        "첫 자취 가구 가이드",
        "안전한 부동산 거래 기본",
    ],
    "자녀·가족 정보": [
        "자녀 용돈 관리 가르치기",
        "가족 대화 시간 만들기",
        "자녀 보험 점검 포인트",
        "학교 행사 관리 팁",
        "아이 수면 패턴 만들기",
        "영유아 안전 가이드",
        "가족 비상 연락망 구성",
        "부모·자녀 갈등 다루기",
        "자녀 독서 습관 만들기",
        "가족 여행 계획 팁",
        "자녀 디지털 사용 가이드",
        "아이 스트레스 신호 알기",
        "형제 다툼 다루는 법",
        "가족 가계부 운영",
        "부모 자기 돌봄",
    ],
    "자기계발 정보": [
        "아침 루틴 만들기",
        "시간 관리 기본 원칙",
        "작은 습관 시작법",
        "독서 습관 만들기",
        "메모·기록 활용법",
        "집중력 회복 일상 팁",
        "회복 탄력성 키우기",
        "일·삶 균형 점검",
        "학습 효율 높이기",
        "목표 설정 기본",
        "디지털 디톡스 일상",
        "인간관계 관리 기본",
        "감정 관리 일상 팁",
        "미루는 습관 다루기",
        "자기 점검 루틴",
    ],
}


def _rotated_theme(target_date: date) -> str:
    """날짜 기준 8일 주기 순환 (하루 1개 주제)."""
    return THEME_POOL[target_date.toordinal() % len(THEME_POOL)]


def _rotated_subtopic(target_date: date, theme: str, slot: str) -> str | None:
    """주제 안에서 세부주제 자동 회전. AM/PM은 풀의 절반만큼 어긋나게."""
    subs = SUBTOPIC_POOL.get(theme)
    if not subs:
        return None
    # 같은 주제가 돌아올 때마다 cycle 증가 → 세부주제 1칸씩 전진
    cycle = target_date.toordinal() // len(THEME_POOL)
    offset = 0 if slot == "AM" else len(subs) // 2
    return subs[(cycle + offset) % len(subs)]


def _save_caption(card_set: CardSet, out_path: Path) -> None:
    text = card_set.caption + "\n\n" + " ".join(card_set.hashtags)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")


def _save_json_meta(card_set: CardSet, out_dir: Path) -> Path:
    meta_path = out_dir / "_meta.json"
    meta_path.write_text(
        json.dumps(asdict(card_set), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta_path


def generate_one_set(
    target_date: date,
    slot: str,
    theme: str,
    sub_topic: str | None,
    use_stub: bool,
    config_path: str = "config.yaml",
) -> dict:
    """단일 슬롯에 대한 1세트(8장 + 캡션) 생성."""
    assert slot in ("AM", "PM"), f"slot must be AM or PM, got {slot}"

    print(
        f"[generate] {target_date} {slot} — theme: {theme} / sub: {sub_topic} (stub={use_stub})"
    )

    if use_stub:
        card_set = stub_card_set(theme)
    else:
        card_set = generate_card_set(theme, sub_topic=sub_topic, config_path=config_path)

    date_str = target_date.strftime("%Y-%m-%d")
    draft_dir = ROOT / "output" / date_str / slot / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / "output" / date_str / slot / "approved").mkdir(
        parents=True, exist_ok=True
    )

    png_paths = render_card_set(asdict(card_set), draft_dir, config_path=config_path)

    caption_path = ROOT / "captions" / f"{date_str}_{slot}.txt"
    _save_caption(card_set, caption_path)

    meta_path = _save_json_meta(card_set, draft_dir)

    return {
        "date": date_str,
        "slot": slot,
        "theme": theme,
        "sub_topic": sub_topic,
        "topic": card_set.topic,
        "draft_dir": str(draft_dir),
        "png_count": len(png_paths),
        "caption": str(caption_path),
        "meta": str(meta_path),
    }


def main():
    p = argparse.ArgumentParser(description="정보형 카드뉴스 생성기")
    p.add_argument("--days", type=int, default=1, help="며칠치 생성 (기본 1)")
    p.add_argument("--start-date", default=None, help="시작 날짜 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--date", default=None, help="단일 날짜 (--days 1과 동일)")
    p.add_argument("--slots", default="AM", help="슬롯 쉼표 구분 (AM 또는 AM,PM)")
    p.add_argument("--slot", default=None, help="단일 슬롯 (편의용)")
    p.add_argument("--topic", default=None, help="대주제 직접 지정 (안 하면 날짜별 자동 순환)")
    p.add_argument("--sub", default=None, help="세부주제 직접 지정 (안 하면 자동 순환)")
    p.add_argument("--preview", action="store_true", help="1세트만 빠르게")
    p.add_argument("--stub", action="store_true", help="API 호출 없이 더미 데이터로 테스트")
    p.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = p.parse_args()

    if args.preview:
        args.days = 1
        args.slots = args.slot or "AM"

    if args.slot:
        args.slots = args.slot

    if args.date:
        start = datetime.strptime(args.date, "%Y-%m-%d").date()
        args.days = 1
    elif args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start = date.today()

    slots = [s.strip() for s in args.slots.split(",") if s.strip()]
    results = []

    for day_idx in range(args.days):
        target = start + timedelta(days=day_idx)
        theme = args.topic or _rotated_theme(target)
        for slot in slots:
            sub_topic = args.sub or _rotated_subtopic(target, theme, slot)
            try:
                r = generate_one_set(target, slot, theme, sub_topic, args.stub, args.config)
                results.append(r)
            except Exception as e:
                print(f"[generate] FAILED {target} {slot}: {e}", file=sys.stderr)
                traceback.print_exc()
                results.append({
                    "date": target.strftime("%Y-%m-%d"),
                    "slot": slot,
                    "error": str(e),
                })

    ok = [r for r in results if "error" not in r]
    print("\n" + "=" * 60)
    print(f"GENERATED {len(ok)} / {len(results)} sets")
    print("=" * 60)
    for r in results:
        if "error" in r:
            print(f"  ✗ {r['date']} {r['slot']}: {r['error']}")
        else:
            print(
                f"  ✓ {r['date']} {r['slot']}: [{r['theme']} / {r.get('sub_topic')}] "
                f"{r['topic']} ({r['png_count']} cards)"
            )
    print()

    if not ok:
        print(
            "[generate] 생성된 세트가 없습니다. 위 에러를 확인하세요 "
            "(보통 ANTHROPIC_API_KEY 미설정/오류).",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
