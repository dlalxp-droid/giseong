"""
scheduler.py
============
지시서 4번:
  30 8  * * *  /usr/bin/python /cardnews-system/scheduler.py --slot AM
  0  18 * * *  /usr/bin/python /cardnews-system/scheduler.py --slot PM

흐름:
  1. 오늘 날짜 + 슬롯의 approved/ 폴더 PNG 8장 로드 (없으면 draft/ fallback 옵션)
  2. captions/YYYY-MM-DD_SLOT.txt 캡션 로드
  3. 각 PNG → 이미지 호스팅 (Cloudinary)
  4. Meta Graph API 캐러셀 게시
  5. 결과 로그 기록 + (옵션) 실패 시 웹훅 알림
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

# 같은 디렉토리의 scripts/ 모듈 임포트
ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

from image_host import upload_image  # noqa: E402
from ig_uploader import publish_carousel  # noqa: E402


# ----------------------------------------------------------
# .env 로드 (python-dotenv 없어도 동작)
# ----------------------------------------------------------
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


# ----------------------------------------------------------
# 슬롯별 자료 수집
# ----------------------------------------------------------
def _collect_slot_assets(
    target_date: date,
    slot: str,
    use_draft_if_no_approved: bool,
) -> tuple[list[Path], Path]:
    """approved/ 우선, 옵션에 따라 draft/ fallback. PNG 정렬 보장."""
    date_str = target_date.strftime("%Y-%m-%d")
    slot_dir = ROOT / "output" / date_str / slot

    approved = sorted((slot_dir / "approved").glob("*.png"))
    if approved:
        pngs = approved
    elif use_draft_if_no_approved:
        pngs = sorted((slot_dir / "draft").glob("*.png"))
    else:
        pngs = []

    if not pngs:
        raise FileNotFoundError(
            f"PNG 파일을 찾을 수 없습니다: {slot_dir}/approved (또는 draft)\n"
            f"  → 운영 정책: 검수 완료 후 draft → approved 로 이동해야 업로드 큐 진입 (지시서 6번)"
        )

    caption_path = ROOT / "captions" / f"{date_str}_{slot}.txt"
    if not caption_path.exists():
        raise FileNotFoundError(f"캡션 파일 없음: {caption_path}")

    return pngs, caption_path


# ----------------------------------------------------------
# 알림
# ----------------------------------------------------------
def _notify(msg: str, ok: bool = True) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests
        prefix = "✅" if ok else "🚨"
        requests.post(url, json={"text": f"{prefix} [cardnews] {msg}"}, timeout=10)
    except Exception as e:
        print(f"[scheduler] notify failed: {e}", file=sys.stderr)


# ----------------------------------------------------------
# 로그
# ----------------------------------------------------------
def _log_result(target_date: date, slot: str, payload: dict) -> None:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{target_date.strftime('%Y-%m-%d')}_{slot}.json"
    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------------------------------------
# 메인
# ----------------------------------------------------------
def run_slot(
    target_date: date,
    slot: str,
    use_draft_fallback: bool = False,
    dry_run: bool = False,
    config_path: Path = ROOT / "config.yaml",
) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    api_version = cfg["instagram"]["api_version"]
    retry_max = cfg["instagram"]["retry_max"]
    retry_delay = cfg["instagram"]["retry_delay_sec"]

    pngs, caption_path = _collect_slot_assets(target_date, slot, use_draft_fallback)
    caption = caption_path.read_text(encoding="utf-8")

    print(f"[scheduler] {target_date} {slot} — {len(pngs)} PNGs, dry_run={dry_run}")

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "date": target_date.isoformat(),
            "slot": slot,
            "files": [str(p) for p in pngs],
            "caption_preview": caption[:120],
        }

    # 1) 이미지 호스팅
    print(f"[scheduler] uploading {len(pngs)} images to host …")
    public_urls = []
    for png in pngs:
        public_id = f"{target_date.isoformat()}_{slot}_{png.stem}"
        url = upload_image(png, public_id=public_id)
        public_urls.append(url)
        print(f"  · {png.name} → {url}")

    # 2) 캐러셀 게시 (재시도 포함)
    attempt = 0
    last_error: Exception | None = None
    while attempt < retry_max:
        try:
            media_id = publish_carousel(
                public_urls, caption, api_version=api_version
            )
            payload = {
                "ok": True,
                "date": target_date.isoformat(),
                "slot": slot,
                "media_id": media_id,
                "image_urls": public_urls,
                "attempts": attempt + 1,
            }
            _log_result(target_date, slot, payload)
            _notify(
                f"{target_date} {slot} 게시 완료 (media_id={media_id})", ok=True
            )
            print(f"[scheduler] ✓ published media_id={media_id}")
            return payload
        except Exception as e:
            last_error = e
            attempt += 1
            print(
                f"[scheduler] attempt {attempt}/{retry_max} failed: {e}",
                file=sys.stderr,
            )
            if attempt < retry_max:
                time.sleep(retry_delay)

    # 모든 재시도 실패
    payload = {
        "ok": False,
        "date": target_date.isoformat(),
        "slot": slot,
        "error": str(last_error),
        "trace": traceback.format_exc(),
        "image_urls": public_urls,
        "attempts": retry_max,
    }
    _log_result(target_date, slot, payload)
    _notify(f"{target_date} {slot} 게시 실패: {last_error}", ok=False)
    raise RuntimeError(f"All {retry_max} attempts failed: {last_error}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slot", required=True, choices=["AM", "PM"])
    p.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 오늘)")
    p.add_argument(
        "--allow-draft",
        action="store_true",
        help="approved 폴더가 비어있으면 draft 폴더 PNG 사용 (운영에서는 비권장)",
    )
    p.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 자료만 점검")
    p.add_argument("--env-file", default=str(ROOT / ".env"))
    args = p.parse_args()

    _load_dotenv(Path(args.env_file))

    target = (
        datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    )

    try:
        run_slot(target, args.slot, args.allow_draft, args.dry_run)
    except Exception as e:
        print(f"[scheduler] FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
