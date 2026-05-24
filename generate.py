"""
generate.py
===========
카드뉴스 일괄 생성 메인 엔트리.

정보형 카드뉴스 + 4주제 일일 순환:
  보험 정보 → 건강 정보 → 생활 정보 → 금융 정보 (4일 주기)
주제는 날짜 기준으로 자동 결정 — "하루 1개 주제".

사용 예시:
  python generate.py --slot AM            # 오늘 날짜의 순환 주제로 1세트
  python generate.py --slot AM --stub     # API 없이 더미로 테스트
  python generate.py --date 2026-05-25 --slot AM --topic "건강 정보"
  python generate.py --days 7 --slots AM  # 7일치 (날마다 주제 자동 순환)

출력 구조:
  /output/YYYY-MM-DD/AM/draft/      ← 자동 생성 직후
  /output/YYYY-MM-DD/AM/approved/   ← (수동 검수 운영 시) 사람이 이동
  /captions/YYYY-MM-DD_AM.txt
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


# 4개 대주제 — 날짜 기준으로 순환
THEME_POOL = [
    "보험 정보",
    "건강 정보",
    "생활 정보",
    "금융 정보",
]


def _rotated_theme(target_date: date) -> str:
    """날짜 기준 4일 주기 순환 (하루 1개 주제)."""
    return THEME_POOL[target_date.toordinal() % len(THEME_POOL)]


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
    use_stub: bool,
    config_path: str = "config.yaml",
) -> dict:
    """단일 슬롯에 대한 1세트(8장 + 캸션) 생성."""
    assert slot in ("AM", "PM"), f"slot must be AM or PM, got {slot}"

    print(f"[generate] {target_date} {slot} — theme: {theme} (stub={use_stub})")

    if use_stub:
        card_set = stub_card_set(theme)
    else:
        card_set = generate_card_set(theme, config_path=config_path)

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
    p.add_argument("--preview", action="store_true", help="1세트만 빠르게 (--days 1 --slots AM)")
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
            try:
                r = generate_one_set(target, slot, theme, args.stub, args.config)
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
            print(f"  ✓ {r['date']} {r['slot']}: [{r['theme']}] {r['topic']} ({r['png_count']} cards)")
    print()

    # 하나도 성공하지 못했으면 CI가 명확히 실패하도록 exit 1
    if not ok:
        print(
            "[generate] 생성된 세트가 없습니다. 위 에러를 확인하세요 "
            "(보통 ANTHROPIC_API_KEY 미설정/오류).",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
