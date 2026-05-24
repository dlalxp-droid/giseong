"""
band_debug.py
=============
밴드 글쓰기 자동화가 실패할 때, 실제 페이지의 버튼/입력창 구조를
찾아내기 위한 진단 스크립트.

실행:
    python band_debug.py

하는 일:
  - band_storage_state.json 세션으로 밴드에 접속
  - 화면을 band_debug.png 로 저장
  - 전체 HTML 을 band_debug.html 로 저장
  - 글쓰기/사진/게시 관련 후보 요소들을 터미널에 출력

이 결과(band_debug.png + 터미널 출력)를 개발자에게 보내면
정확한 셀렉터로 교정해 줄 수 있다.
"""

import os

from playwright.sync_api import sync_playwright

BAND_ID = os.environ.get("BAND_ID", "").strip()
STORAGE = os.environ.get("BAND_STORAGE_STATE", "band_storage_state.json").strip()
KEYWORDS = ["글쓰기", "글 쓰기", "새 글", "사진", "게시", "등록", "올리기", "작성", "확인"]

# JS 안에 삽입할 키워드 배열 (유니코드 이스케이프)
KW_JS = "[" + ",".join('"' + k + '"' for k in KEYWORDS) + "]"


def main() -> None:
    if not BAND_ID:
        print("❌ 먼저: set BAND_ID=<밴드숫자> 를 해주세요")
        return
    if not os.path.exists(STORAGE):
        print(f"❌ 세션 파일 없음: {STORAGE}")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=STORAGE,
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        print(f"→ 접속 중: https://band.us/band/{BAND_ID}")
        page.goto(f"https://band.us/band/{BAND_ID}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        print("→ 현재 URL:", page.url)
        if "auth.band.us" in page.url or "login" in page.url:
            print("⚠ 로그인 화면으로 팁겼습니다 → 세션 만료. make_band_session.py 재실행 필요")

        page.screenshot(path="band_debug.png", full_page=True)
        with open("band_debug.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("→ band_debug.png / band_debug.html 저장 완료")

        js = (
            "() => {"
            "  const kws = " + KW_JS + ";"
            "  const out = [];"
            "  const els = document.querySelectorAll("
            "    'button, a, div[role=button], [contenteditable], input[type=file]');"
            "  els.forEach(el => {"
            "    const t = (el.innerText || el.value || '').trim().slice(0, 24);"
            "    const tag = el.tagName.toLowerCase();"
            "    const cls = (el.className && el.className.toString)"
            "      ? el.className.toString().slice(0, 70) : '';"
            "    const ce = el.getAttribute('contenteditable');"
            "    const ty = el.getAttribute('type');"
            "    const uisel = el.getAttribute('data-uiselector');"
            "    const isFile = (tag === 'input' && ty === 'file');"
            "    const isCE = (ce === 'true' || ce === '');"
            "    const hasKw = kws.some(k => t.includes(k));"
            "    if (isFile || isCE || hasKw) {"
            "      out.push(tag + ' | text=\"' + t + '\" | class=' + cls"
            "        + ' | type=' + ty + ' | ce=' + ce + ' | uiselector=' + uisel);"
            "    }"
            "  });"
            "  return out;"
            "}"
        )
        cands = page.evaluate(js)

        print("\n========== 후보 요소 (이 화면을 측정해 보내주세요) ==========")
        if not cands:
            print("  (찾은 후보 없음 — band_debug.png 를 보내주세요)")
        for c in cands:
            print("  -", c)
        print("========================================================\n")

        input("확인 후 Enter ▶ (그동안 크롬 창에서 밴드 화면을 둘러봐도 됩니다) ")
        browser.close()


if __name__ == "__main__":
    main()
