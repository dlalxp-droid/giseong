"""
band_debug2.py
==============
2단계 진단: "글쓰기" 버튼을 누른 뒤 나오는 글 입력창/사진첨부/게시 버튼을 찾는다.

실행:
    python band_debug2.py

결과:
  - 글쓰기 화면을 band_debug2.png 로 저장
  - 해당 화면 HTML 을 band_debug2.html 로 저장
  - 입력창/파일입력/게시버튼 후보를 터미널에 출력
"""

import os

from playwright.sync_api import sync_playwright

BAND_ID = os.environ.get("BAND_ID", "").strip()
STORAGE = os.environ.get("BAND_STORAGE_STATE", "band_storage_state.json").strip()

OPEN_CANDIDATES = ["button._btnOpenWriteLayer", "button._btnPostWrite"]

DUMP_JS = (
    "() => {"
    "  const kws = ['게시','등록','완료','확인','올리기','사진','동영상'];"
    "  const out = [];"
    "  const els = document.querySelectorAll("
    "    'button, a, div[role=button], [contenteditable], input[type=file], textarea');"
    "  els.forEach(el => {"
    "    const t = (el.innerText || el.value || el.getAttribute('placeholder') || '').trim().slice(0, 24);"
    "    const tag = el.tagName.toLowerCase();"
    "    const cls = (el.className && el.className.toString)"
    "      ? el.className.toString().slice(0, 70) : '';"
    "    const ce = el.getAttribute('contenteditable');"
    "    const ty = el.getAttribute('type');"
    "    const isFile = (tag === 'input' && ty === 'file');"
    "    const isCE = (ce === 'true' || ce === '');"
    "    const isTA = (tag === 'textarea');"
    "    const hasKw = kws.some(k => t.includes(k));"
    "    if (isFile || isCE || isTA || hasKw) {"
    "      out.push(tag + ' | text=\"' + t + '\" | class=' + cls + ' | type=' + ty + ' | ce=' + ce);"
    "    }"
    "  });"
    "  return out;"
    "}"
)


def main() -> None:
    if not BAND_ID:
        print("❌ 먼저: set BAND_ID=<밴드숫자>")
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
        page.goto(f"https://band.us/band/{BAND_ID}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        clicked = False
        for sel in OPEN_CANDIDATES:
            try:
                page.click(sel, timeout=5000)
                clicked = True
                print("→ 글쓰기 버튼 클릭 성공:", sel)
                break
            except Exception:
                print("→ 클릭 실패:", sel)
        if not clicked:
            print("⚠ 글쓰기 버튼을 못 눌렀습니다")

        page.wait_for_timeout(3000)
        print("→ 현재 URL:", page.url)

        page.screenshot(path="band_debug2.png", full_page=True)
        with open("band_debug2.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("→ band_debug2.png / band_debug2.html 저장 완료")

        cands = page.evaluate(DUMP_JS)
        print("\n========== 글쓰기 화면 후보 요소 (이 화면을 보내주세요) ==========")
        if not cands:
            print("  (후보 없음 — band_debug2.png 를 보내주세요)")
        for c in cands:
            print("  -", c)
        print("=================================================================\n")

        input("확인 후 Enter ▶ ")
        browser.close()


if __name__ == "__main__":
    main()
