"""
band_uploader.py
================
네이버 밴드 자동 업로드 모듈.

네이버 밴드 Open API는 글 작성(`/v2.2/band/post/create`)을
공식 지원하지만 사진 첨부는 Open API 만으로 불가능하다 (사진 업로드
엔드포인트 미제공). 따라서 두 가지 모드를 함께 제공한다:

  1) api  — 사진은 외부 호스팅(URL)으로 처리, 본문 + URL 링크 게시
            (간단/안정적, 그러나 Band 피드에 썸네일이 카드처럼 N장
             첨부되지 않고 일반 링크 미리보기로만 보임)

  2) web  — Playwright 로 web.band.us 에 로그인된 세션을 사용해
            카드뉴스 PNG 8장을 그대로 업로드 (실제 카드뉴스 게시 형태).
            세션은 storage_state.json (쿠키) 파일을 미리 만들어 두고
            BAND_STORAGE_STATE 경로로 로드한다.

흐름 (web 모드):
  1. Chromium + storage_state.json 로 로그인된 컨텍스트 생성
  2. https://band.us/band/<band_id> 이동
  3. 글쓰기 패널 열기 → textarea 에 content 입력
  4. 사진 input[type=file] 에 PNG 8장 set_input_files
  5. 업로드 완료 대기 → 게시 버튼 클릭
  6. 게시된 글 url 또는 success 토스트 확인 후 종료

주의: web 모드는 밴드 UI 변경에 취약하다. 셀렉터는 settings.band.web.
selectors 로 외부에서 조정 가능하도록 분리했다.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

BAND_OPENAPI_BASE = "https://openapi.band.us"
BAND_WEB_BASE = "https://band.us"


# ----------------------------------------------------------
# 공용 데이터 클래스
# ----------------------------------------------------------
@dataclass
class BandPostResult:
    ok: bool
    mode: str            # "api" | "web"
    band_key: str
    post_key: str | None
    post_url: str | None
    error: str | None = None


# ==========================================================
# 1) Open API 모드  (텍스트 + URL)
# ==========================================================
def post_via_api(
    content: str,
    band_key: str | None = None,
    access_token: str | None = None,
    do_push: bool = False,
    image_urls: Iterable[str] | None = None,
) -> BandPostResult:
    """
    Band Open API `/v2.2/band/post/create` 로 게시.

    image_urls 가 주어지면 본문 끝에 "\n\n[이미지 보기]\nurl1\nurl2 ..."
    형태로 추가 (밴드는 URL 자동 미리보기 카드 생성).
    """
    band_key = band_key or os.environ["BAND_KEY"]
    access_token = access_token or os.environ["BAND_ACCESS_TOKEN"]

    body = content.rstrip()
    urls = list(image_urls or [])
    if urls:
        body += "\n\n[이미지 보기]\n" + "\n".join(urls)

    r = requests.post(
        f"{BAND_OPENAPI_BASE}/v2.2/band/post/create",
        data={
            "access_token": access_token,
            "band_key": band_key,
            "content": body,
            "do_push": "Y" if do_push else "N",
        },
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()

    # Band 응답 형식:
    #   { "result_code": 1, "result_data": { "post_key": "AAB...", "band_key": "..." } }
    if j.get("result_code") != 1:
        return BandPostResult(
            ok=False,
            mode="api",
            band_key=band_key,
            post_key=None,
            post_url=None,
            error=f"Band API error: {j}",
        )

    post_key = j["result_data"]["post_key"]
    return BandPostResult(
        ok=True,
        mode="api",
        band_key=band_key,
        post_key=post_key,
        post_url=f"{BAND_WEB_BASE}/band/{band_key}/post/{post_key}",
    )


# ==========================================================
# 2) Web 모드  (Playwright 사진 첨부 게시)
# ==========================================================
DEFAULT_WEB_SELECTORS = {
    # band.us 메인 화면 글쓰기 트리거
    "open_composer": "button._btnOpenPostEditor, [data-uiselector='openPostEditor']",
    # 본문 textarea (contenteditable)
    "editor_textarea": "div._postWriteEditor, div[contenteditable='true']",
    # 사진 첨부 input (hidden)
    "photo_input": "input[type='file'][accept*='image']",
    # 게시 버튼
    "submit_button": "button._btnSubmitPost, button[data-uiselector='submitPostButton']",
    # 게시 성공 후 url 변화 또는 토스트
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
    content : 본문
    image_paths : PNG 경로 리스트 (8장)
    band_id : band.us URL의 band id (예: "12345678"). None 이면 BAND_ID 환경변수
    storage_state : 쿠키/세션 파일 경로 (None 이면 BAND_STORAGE_STATE 환경변수)
    headless : 디버그 시 False 로 두면 브라우저 창 표시
    """
    from playwright.sync_api import sync_playwright

    band_id = band_id or os.environ["BAND_ID"]
    storage_state = storage_state or os.environ["BAND_STORAGE_STATE"]
    sels = {**DEFAULT_WEB_SELECTORS, **(selectors or {})}

    image_paths = [Path(p) for p in image_paths]
    if not image_paths:
        raise ValueError("image_paths is empty")

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

            # 4) 업로드 처리 대기 (썸네일 N개 등장)
            #    selector 로 정확히 타기보단 시간 + networkidle 조합
            page.wait_for_timeout(2000)
            page.wait_for_load_state("networkidle")

            # 5) 게시
            page.click(sels["submit_button"])

            # 6) 성공 확인 (URL 변화 또는 토스트)
            try:
                page.wait_for_selector(sels["success_toast"], timeout=15000)
            except Exception:
                # 토스트가 안떠도 URL 패턴 변화로 성공 추정
                page.wait_for_url("**/post/**", timeout=15000)

            post_url = page.url
            post_key = None
            if "/post/" in post_url:
                post_key = post_url.rsplit("/post/", 1)[-1].split("?")[0]

            return BandPostResult(
                ok=True,
                mode="web",
                band_key=band_id,
                post_key=post_key,
                post_url=post_url,
            )
        except Exception as e:
            return BandPostResult(
                ok=False,
                mode="web",
                band_key=band_id,
                post_key=None,
                post_url=None,
                error=f"{type(e).__name__}: {e}",
            )
        finally:
            try:
                context.storage_state(path=storage_state)  # 세션 갱신 (선택)
            except Exception:
                pass
            context.close()
            browser.close()


# ==========================================================
# 3) 통합 진입점
# ==========================================================
def publish_band(
    *,
    mode: str,
    content: str,
    image_paths: Iterable[Path] | None = None,
    image_urls: Iterable[str] | None = None,
    band_key: str | None = None,
    band_id: str | None = None,
    do_push: bool = False,
) -> BandPostResult:
    """mode='api' | 'web' 분기."""
    if mode == "api":
        return post_via_api(
            content=content,
            band_key=band_key,
            do_push=do_push,
            image_urls=image_urls,
        )
    if mode == "web":
        if not image_paths:
            raise ValueError("web 모드는 image_paths 가 필수입니다")
        return post_via_web(
            content=content,
            image_paths=image_paths,
            band_id=band_id,
        )
    raise ValueError(f"unknown mode: {mode}")


# ----------------------------------------------------------
# CLI
# ----------------------------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["api", "web"], required=True)
    p.add_argument("--caption-file", required=True)
    p.add_argument("--images", help="쉼표 구분 PNG 경로 (web 모드)")
    p.add_argument("--urls", help="쉼표 구분 이미지 URL (api 모드)")
    p.add_argument("--push", action="store_true", help="푸시 알림 발송 (api 모드)")
    args = p.parse_args()

    caption = Path(args.caption_file).read_text(encoding="utf-8")
    image_paths = (
        [Path(s) for s in args.images.split(",") if s.strip()]
        if args.images else None
    )
    urls = [u.strip() for u in (args.urls or "").split(",") if u.strip()] or None

    result = publish_band(
        mode=args.mode,
        content=caption,
        image_paths=image_paths,
        image_urls=urls,
        do_push=args.push,
    )
    print(result)
    if not result.ok:
        raise SystemExit(1)
