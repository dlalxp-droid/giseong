"""
band_uploader.py
================
네이버 밴드 자동 업로드 모듈 (Playwright 전용).

밴드 Open API 앱 등록이 어려워 API 방식을 전면 제거했다.
web.band.us 에 로그인된 브라저 세션(band_storage_state.json)을 재사용해
카드뉴스 PNG 여러 장을 직접 첨부하는 방식만 사용한다.

세션 생성: python make_band_session.py (1회 수동 로그인)

실제 밴드 글쓰기 흐름 (2026-05 기준, band_debug 로 확인):
  1. button._btnOpenWriteLayer        → 글쓰기 레이어 열기
  2. div.contentEditor._richEditor     → 본문 입력 (CKEditor)
  3. input[type=file] (첫 번째)        → 사진 선택
  4. "사진 올리기" 다이얼로그 → button[첨부하기] 클릭
  5. button._btnSubmitPost             → 게시

UI 변경 시 config.yaml band.web_selectors_override 로 덮어쓴다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BAND_WEB_BASE = "https://band.us"


@dataclass
class BandPostResult:
    ok: bool
    band_id: str
    post_key: str | None
    post_url: str | None
    error: str | None = None


# band.us 실측 셀렉터 (UI 변경 시 config 로 오버라이드)
DEFAULT_WEB_SELECTORS = {
    # 메인 화면 글쓰기 트리거
    "open_composer": "button._btnOpenWriteLayer",
    # 본문 editor (CKEditor contenteditable)
    "editor_textarea": "div.contentEditor._richEditor",
    # 사진 첨부 input (숨겨진 file input 중 첫 번째 = 사진)
    "photo_input": "input[type='file']",
    # "사진 올리기" 다이얼로그의 [첨부하기] 버튼
    "confirm_photos": "button:has-text('첨부하기')",
    # 게시 버튼
    "submit_button": "button._btnSubmitPost",
}


def post_via_web(
    content: str,
    image_paths: Iterable[Path],
    band_id: str | None = None,
    storage_state: str | None = None,
    headless: bool = True,
    timeout_ms: int = 60000,
    selectors: dict | None = None,
) -> BandPostResult:
    """
    Playwright 로그인 세션으로 사진 첨부 게시.
    """
    from playwright.sync_api import sync_playwright

    band_id = band_id or os.environ["BAND_ID"]
    storage_state = storage_state or os.environ["BAND_STORAGE_STATE"]
    sels = {**DEFAULT_WEB_SELECTORS, **(selectors or {})}

    image_paths = [Path(p) for p in image_paths]
    if not image_paths:
        raise ValueError("image_paths is empty")
    for p in image_paths:
        if not p.exists():
            raise FileNotFoundError(f"image not found: {p}")

    if not Path(storage_state).exists():
        raise FileNotFoundError(
            f"로그인 세션 파일 없음: {storage_state}\n"
            f"  → python make_band_session.py 로 먼저 생성하세요"
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            page.goto(f"{BAND_WEB_BASE}/band/{band_id}")
            page.wait_for_load_state("networkidle")

            # 세션 만료 감지
            if "auth.band.us" in page.url or "/login" in page.url:
                return BandPostResult(
                    ok=False,
                    band_id=band_id,
                    post_key=None,
                    post_url=None,
                    error="로그인 세션 만료 (make_band_session.py 재실행 필요)",
                )

            # 1) 글쓰기 레이어 열기
            page.click(sels["open_composer"])
            page.wait_for_selector(sels["editor_textarea"])

            # 2) 본문 입력 (CKEditor contenteditable)
            editor = page.locator(sels["editor_textarea"]).first
            editor.click()
            try:
                editor.fill(content)
            except Exception:
                page.keyboard.type(content)

            # 3) 사진 선택 (숨겨진 file input 중 첫 번째)
            page.locator(sels["photo_input"]).first.set_input_files(
                [str(p) for p in image_paths]
            )

            # 4) "사진 올리기" 확인 다이얼로그 → [첨부하기] 클릭
            #    (밴드는 파일 선택 후 별도 확인 창을 띄운다)
            try:
                page.wait_for_selector(sels["confirm_photos"], timeout=15000)
                # 썸네일 업로드 처리 대기 (장수에 비례, 최대 15초)
                page.wait_for_timeout(min(2000 + 1000 * len(image_paths), 15000))
                page.click(sels["confirm_photos"])
                # 다이얼로그 닫힘 대기
                page.wait_for_selector(
                    sels["confirm_photos"], state="hidden", timeout=20000
                )
            except Exception:
                # 확인 다이얼로그가 안 뜨는 경우도 허용
                pass

            page.wait_for_load_state("networkidle")

            # 5) 게시 (버튼이 활성화될 때까지 Playwright 가 자동 대기)
            page.click(sels["submit_button"])

            # 6) 성공 판정: 글쓰기 레이어(게시 버튼)가 사라지면 완료
            page.wait_for_selector(
                sels["submit_button"], state="hidden", timeout=30000
            )
            page.wait_for_load_state("networkidle")

            post_url = page.url
            post_key = None
            if "/post/" in post_url:
                tail = post_url.rsplit("/post/", 1)[-1].split("?")[0].strip("/")
                post_key = tail or None

            return BandPostResult(
                ok=True,
                band_id=band_id,
                post_key=post_key,
                post_url=post_url,
            )
        except Exception as e:
            return BandPostResult(
                ok=False,
                band_id=band_id,
                post_key=None,
                post_url=None,
                error=f"{type(e).__name__}: {e}",
            )
        finally:
            try:
                context.storage_state(path=storage_state)  # 세션 갱신
            except Exception:
                pass
            context.close()
            browser.close()


def publish_band(
    *,
    content: str,
    image_paths: Iterable[Path],
    band_id: str | None = None,
    storage_state: str | None = None,
    headless: bool = True,
    selectors: dict | None = None,
) -> BandPostResult:
    """통합 진입점 (Playwright web 전용)."""
    if not image_paths:
        raise ValueError("image_paths 가 필요합니다")
    return post_via_web(
        content=content,
        image_paths=image_paths,
        band_id=band_id,
        storage_state=storage_state,
        headless=headless,
        selectors=selectors,
    )


# ----------------------------------------------------------
# CLI
# ----------------------------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--caption-file", required=True)
    p.add_argument("--images", required=True, help="쉼표 구분 PNG 경로")
    p.add_argument("--no-headless", action="store_true", help="브라우저 창 표시 (디버그)")
    args = p.parse_args()

    caption = Path(args.caption_file).read_text(encoding="utf-8")
    image_paths = [Path(s) for s in args.images.split(",") if s.strip()]

    result = publish_band(
        content=caption,
        image_paths=image_paths,
        headless=not args.no_headless,
    )
    print(result)
    if not result.ok:
        raise SystemExit(1)
