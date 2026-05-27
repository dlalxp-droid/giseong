"""
band_uploader.py
================
네이버 밴드 자동 업로드 모듈 (Playwright 전용).

밴드 Open API 앱 등록이 어려워 API 방식을 전면 제거했다.
web.band.us 에 로그인된 브라저 세션(band_storage_state.json)을 재사용해
카드뉴스 PNG 여러 장을 직접 첨부하는 방식만 사용한다.

세션 생성: python make_band_session.py (1회 수동 로그인)

실제 밴드 글쓰기 흐름:
  1. button._btnOpenWriteLayer        → 글쓰기 레이어 열기
  2. div.contentEditor._richEditor     → 본문 입력 (CKEditor)
  3. input[type=file] (첫 번째)        → 사진 선택
  4. "사진 올리기" 다이얼로그 → button[첨부하기] 클릭
  4b. 에디터 -loading 이 사라질 때까지(사진 업로드 완료) 대기
  5. button._btnSubmitPost             → 게시
  6. 글쓰기 레이어(본문 editor)가 사라지면 게시 완료

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

# 에디터 업로드 완료 감지용 JS (사진 처리 중이면 class에 -loading 이 붙음)
_NOT_LOADING_JS = (
    "() => {"
    "  const e = document.querySelector('div.contentEditor._richEditor');"
    "  return !!e && !String(e.className).includes('-loading');"
    "}"
)


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
        # 네이티브 확인창(confirm/alert)이 뜨면 자동으로 확인(accept).
        page.on("dialog", lambda d: d.accept())

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
            try:
                page.wait_for_selector(sels["confirm_photos"], timeout=15000)
                page.wait_for_timeout(min(2000 + 1000 * len(image_paths), 15000))
                page.click(sels["confirm_photos"])
                page.wait_for_selector(
                    sels["confirm_photos"], state="hidden", timeout=20000
                )
            except Exception:
                pass  # 확인 다이얼로그가 안 뜨는 경우도 허용

            # 4b) 사진 업로드 처리 완료 대기 (에디터 -loading 이 사라질 때까지)
            #    클라우드/헤드리스는 업로드가 느려 완료 전 게시하면 창이 안 닫힌다.
            page.wait_for_timeout(3000)  # -loading 이 붙을 시간 확보
            try:
                page.wait_for_function(_NOT_LOADING_JS, timeout=90000)
            except Exception:
                pass
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

            # 5) 게시 (버튼이 활성화될 때까지 Playwright 가 자동 대기)
            page.click(sels["submit_button"])

            # 6) 성공 판정: 글쓰기 레이어(본문 editor)가 사라지면 게시 완료
            page.wait_for_selector(
                sels["editor_textarea"], state="hidden", timeout=40000
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
