"""
band_uploader.py
================
네이버 밴드 자동 업로드 모듈 (Playwright 전용).

밴드 Open API 앱 등록이 계속 거절되어 API 방식을 전면 제거했다.
이제 �은 web.band.us 에 로그인된 브라저 세션을 그대로 재사용해
카드뉴스 PNG 여러 장을 직접 첨부하는 방식만 사용한다.

세션 유지:
  로컬에서 한 번 로그인한 쿠키를 band_storage_state.json 으로 저장해 둔 뒤
  BAND_STORAGE_STATE 경로로 로드한다. (쿠키 만드는 방법은 README 5장)

흐름:
  1. Chromium + storage_state.json 으로 로그인된 컨텍스트 생성
  2. https://band.us/band/<band_id> 이동
  3. 글쓰기 패널 열기 → 본문 입력
  4. 사진 input[type=file] 에 PNG 여러 장 set_input_files
  5. 업로드 처리 대기 → 게시 버튼 클릭
  6. 게시 성공(URL 변화/토스트) 확인 후 종료

주의: 밴드 UI 변경에 취약. 셀렉터는 config.yaml band.web_selectors_override
로 외부에서 덮어쓸 수 있다.
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


# band.us 기본 셀렉터 (UI 변경 시 config 로 오버라이드)
DEFAULT_WEB_SELECTORS = {
    # 메인 화면 글쓰기 트리거
    "open_composer": "button._btnOpenPostEditor, [data-uiselector='openPostEditor']",
    # 본문 editor (contenteditable)
    "editor_textarea": "div._postWriteEditor, div[contenteditable='true']",
    # 사진 첨부 input (hidden)
    "photo_input": "input[type='file'][accept*='image']",
    # 게시 버튼
    "submit_button": "button._btnSubmitPost, button[data-uiselector='submitPostButton']",
    # 게시 성공 토스트
    "success_toast": ".uiCommonToastView, .toast-message",
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

    Parameters
    ----------
    content : 본문 (캸션 + 해시태그)
    image_paths : PNG 경로 리스트
    band_id : band.us URL의 band id (예: "12345678"). None 이면 BAND_ID 환경변수
    storage_state : 쿠키/세션 파일 경로. None 이면 BAND_STORAGE_STATE 환경변수
    headless : 디버그 시 False 로 두면 브라우저 창 표시
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
            f"  → README 5장 절차로 band_storage_state.json 을 먼저 생성하세요"
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

            # 세션 만료 감지: 로그인 페이지로 팁겨졌으면 세션 만료
            if "auth.band.us" in page.url or "login" in page.url:
                return BandPostResult(
                    ok=False,
                    band_id=band_id,
                    post_key=None,
                    post_url=None,
                    error="로그인 세션 만료 (storage_state 재생성 필요)",
                )

            # 1) 글쓰기 패널 열기
            page.click(sels["open_composer"])
            page.wait_for_selector(sels["editor_textarea"])

            # 2) 본문 입력
            editor = page.locator(sels["editor_textarea"]).first
            editor.click()
            editor.fill(content)

            # 3) 사진 첨부
            page.set_input_files(
                sels["photo_input"],
                [str(p) for p in image_paths],
            )

            # 4) 업로드 처리 대기
            page.wait_for_timeout(2000)
            page.wait_for_load_state("networkidle")

            # 5) 게시
            page.click(sels["submit_button"])

            # 6) 성공 확인 (토스트 또는 URL 변화)
            try:
                page.wait_for_selector(sels["success_toast"], timeout=15000)
            except Exception:
                page.wait_for_url("**/post/**", timeout=15000)

            post_url = page.url
            post_key = None
            if "/post/" in post_url:
                post_key = post_url.rsplit("/post/", 1)[-1].split("?")[0]

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
