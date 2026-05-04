"""
generate.py
===========
지시서 4번 실행 명령어를 구현하는 메인 엔트리.

사용 예시:
  # 일주일치 카드뉴스 일괄 생성 (14세트)
  python generate.py --days 7 --topic "보험 상담 화법" --slots AM,PM

  # 즉시 1세트 테스트 (오늘 AM 슬롯, 더미 데이터)
  python generate.py --topic "거절 처리 화법" --preview --stub

  # 특정 날짜 1세트만
  python generate.py --date 2026-05-05 --slot AM --topic "클로징 화법"

출력 구조 (지시서 1-3, 6번):
  /output/YYYY-MM-DD/AM/draft/      ← 자동 생성 직후
  /output/YYYY-MM-DD/AM/approved/   ← 검수 후 사람이 이동
  /captions/YYYY-MM-DD_AM.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import shutil
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

# 같은 디렉토리의 모듈 임포트
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from content_generator import generate_card_set, stub_card_set, CardSet  # noqa: E402
from renderer import render_card_set  # noqa: E402

import yaml  # noqa: E402


ROOT = Path(__file__).parent.resolve()


# 슬롯별 추천 세부 주제 풀 (LLM이 sub_topic=None 일 때만 사용)
SUBTOPIC_POOL = [
    "거절 처리 화법",
    "니즈 환기 질문법",
    "클로징 3초 화법",
    "DB콜 첫 30초",
    "추천 요청 화법",
    "재무주치의 포지셔닝",
    "가족 동반 상담 진행법",
    "가격 저항 다루기",
    "경쟁사 비교 응대",
    "재계약·증액 화법",
    "갱신 안내 멘트",
    "신뢰 형성 오프닝",
    "상담 마무리 follow-up",
    "고객 침묵 다루기",
]


def _slot_subtopic(slot: str, day_idx: int, used: set[str]) -> str:
    """주제 중복 최소화 — 단순 라운드로빈 + 사용 이력 회피."""
    pool = [t for t in SUBTOPIC_POOL if t not in used] or SUBTOPIC_POOL
    return pool[(day_idx * 2 + (0 if slot == "AM" else 1)) % len(pool)]


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
    sub_topic: str | None,
    use_stub: bool,
    config_path: str = "config.yaml",
) -> dict:
    """단일 슬롯에 대한 1세트(8장 + 캡션) 생성."""
    assert slot in ("AM", "PM"), f"slot must be AM or PM, got {slot}"

    print(f"[generate] {target_date} {slot} — topic: {sub_topic or 'auto'} (stub={use_stub})")

    # 1) 콘텐츠 생성
    if use_stub:
        card_set = stub_card_set(sub_topic or "거절 처리 화법")
    else:
        card_set = generate_card_set(sub_topic, config_path=config_path)

    # 2) 출력 경로 구성
    date_str = target_date.strftime("%Y-%m-%d")
    draft_dir = ROOT / "output" / date_str / slot / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    # approved 폴더도 미리 만들어둠 (지시서 6번)
    (ROOT / "output" / date_str / slot / "approved").mkdir(
        parents=True, exist_ok=True
    )

    # 3) PNG 렌더링
    png_paths = render_card_set(asdict(card_set), draft_dir, config_path=config_path)

    # 4) 캡션 저장
    caption_path = ROOT / "captions" / f"{date_str}_{slot}.txt"
    _save_caption(card_set, caption_path)

    # 5) 메타 JSON 저장 (재렌더 가능하도록)
    meta_path = _save_json_meta(card_set, draft_dir)

    return {
        "date": date_str,
        "slot": slot,
        "topic": card_set.topic,
        "draft_dir": str(draft_dir),
        "png_count": len(png_paths),
        "caption": str(caption_path),
        "meta": str(meta_path),
    }


def main():
    p = argparse.ArgumentParser(description="카드뉴스 일괄 생성기")
    p.add_argument("--days", type=int, default=1, help="며칠치 생성 (기본 1)")
    p.add_argument("--start-date", default=None, help="시작 날짜 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--date", default=None, help="단일 날짜 (--days 1과 동일)")
    p.add_argument("--slots", default="AM,PM", help="슬롯 쉼표 구분 (AM,PM)")
    p.add_argument("--slot", default=None, help="단일 슬롯 (편의용)")
    p.add_argument("--topic", default=None, help="세부 주제 (지정 안 하면 자동 회전)")
    p.add_argument("--preview", action="store_true", help="1세트만 빠르게 (--days 1 --slots AM 동등)")
    p.add_argument("--stub", action="store_true", help="API 호출 없이 더미 데이터로 테스트")
    p.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = p.parse_args()

    # 인자 정규화
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
    used_topics: set[str] = set()
    results = []

    for day_idx in range(args.days):
        target = start + timedelta(days=day_idx)
        for slot in slots:
            sub = args.topic or _slot_subtopic(slot, day_idx, used_topics)
            used_topics.add(sub)
            try:
                r = generate_one_set(target, slot, sub, args.stub, args.config)
                results.append(r)
            except Exception as e:
                print(f"[generate] FAILED {target} {slot}: {e}", file=sys.stderr)
                results.append({
                    "date": target.strftime("%Y-%m-%d"),
                    "slot": slot,
                    "error": str(e),
                })

    # 요약 출력
    print("\n" + "=" * 60)
    print(f"GENERATED {len([r for r in results if 'error' not in r])} / {len(results)} sets")
    print("=" * 60)
    for r in results:
        if "error" in r:
            print(f"  ✗ {r['date']} {r['slot']}: {r['error']}")
        else:
            print(f"  ✓ {r['date']} {r['slot']}: {r['topic']} ({r['png_count']} cards)")
    print()


if __name__ == "__main__":
    main()
