"""
band_scheduler.py
=================
네이버 밴드 자동 업로드 진입점 (cron / GitHub Actions).

Playwright 브라저 자동화만 사용한다 (Band Open API 미사용).
storage_state.json 로그인 세션을 재사용해 카드뉴스 PNG를 직접 첨부 게시.

scheduler.py(인스타) 와 동일한 자료 수집 규칙을 사용한다:
  output/YYYY-MM-DD/SLOT/approved/*.png  (없으면 --allow-draft 시 draft/)
  captions/YYYY-MM-DD_SLOT.txt

cron 예:
  30 8  * * *  /usr/bin/python band_scheduler.py --slot AM
  0  18 * * *  /usr/bin/python band_scheduler.py --slot PM
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

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

from band_uploader import publish_band, BandPostResult  # noqa: E402


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
# 자료 수집 (scheduler.py 와 동일 규칙)
# ----------------------------------------------------------
def _collect_slot_assets(
    target_date: date,
    slot: str,
    use_draft_if_no_approved: bool,
) -> tuple[list[Path], Path]:
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
            f"  → 검수 후 draft → approved 로 이동해야 자동 업로드 큐 진입"
        )

    caption_path = ROOT / "captions" / f"{date_str}_{slot}.txt"
    if not caption_path.exists():
        raise FileNotFoundError(f"캡션 파일 없음: {caption_path}")

    return pngs, caption_path


# ----------------------------------------------------------
# 알림 / 로그
# ----------------------------------------------------------
def _notify(msg: str, ok: bool = True) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests
        prefix = "✅" if ok else "\U0001F6A8"
        requests.post(url, json={"text": f"{prefix} [band] {msg}"}, timeout=10)
    except Exception as e:
        print(f"[band_scheduler] notify failed: {e}", file=sys.stderr)


def _log_result(target_date: date, slot: str, payload: dict) -> None:
    log_dir = ROOT / "logs" / "band"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{target_date.strftime('%Y-%m-%d')}_{slot}.json"
    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    log_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ----------------------------------------------------------
# 메인
# ----------------------------------------------------------
def run_slot(
    target_date: date,
    slot: str,
    use_draft_fallback: bool = False,
    dry_run: bool = False,
    headless: bool = True,
    config_path: Path = ROOT / "config.yaml",
) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    band_cfg = cfg.get("band", {})
    retry_max = int(band_cfg.get("retry_max", 3))
    retry_delay = int(band_cfg.get("retry_delay_sec", 30))
    selectors = band_cfg.get("web_selectors_override") or None

    pngs, caption_path = _collect_slot_assets(target_date, slot, use_draft_fallback)
    caption = caption_path.read_text(encoding="utf-8")

    print(f"[band] {target_date} {slot} pngs={len(pngs)} dry_run={dry_run}")

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "date": target_date.isoformat(),
            "slot": slot,
            "files": [str(p) for p in pngs],
            "caption_preview": caption[:120],
        }

    attempt = 0
    last_error: Exception | None = None
    while attempt < retry_max:
        try:
            result: BandPostResult = publish_band(
                content=caption,
                image_paths=pngs,
                headless=headless,
                selectors=selectors,
            )
            if not result.ok:
                raise RuntimeError(result.error or "unknown band failure")

            payload = {
                "ok": True,
                "date": target_date.isoformat(),
                "slot": slot,
                "band_id": result.band_id,
                "post_key": result.post_key,
                "post_url": result.post_url,
                "png_count": len(pngs),
                "attempts": attempt + 1,
            }
            _log_result(target_date, slot, payload)
            _notify(f"{target_date} {slot} 게시 완료 → {result.post_url}", ok=True)
            print(f"[band] ✓ published → {result.post_url}")
            return payload
        except Exception as e:
            last_error = e
            attempt += 1
            print(
                f"[band] attempt {attempt}/{retry_max} failed: {e}",
                file=sys.stderr,
            )
            if attempt < retry_max:
                time.sleep(retry_delay)

    payload = {
        "ok": False,
        "date": target_date.isoformat(),
        "slot": slot,
        "error": str(last_error),
        "trace": traceback.format_exc(),
        "attempts": retry_max,
    }
    _log_result(target_date, slot, payload)
    _notify(f"{target_date} {slot} 게시 실패: {last_error}", ok=False)
    raise RuntimeError(f"All {retry_max} attempts failed: {last_error}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slot", required=True, choices=["AM", "PM"])
    p.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--allow-draft", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-headless", action="store_true", help="브라우저 창 표시 (디버그)")
    p.add_argument("--env-file", default=str(ROOT / ".env"))
    args = p.parse_args()

    _load_dotenv(Path(args.env_file))

    target = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else date.today()
    )

    try:
        run_slot(
            target,
            args.slot,
            use_draft_fallback=args.allow_draft,
            dry_run=args.dry_run,
            headless=not args.no_headless,
        )
    except Exception as e:
        print(f"[band_scheduler] FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
