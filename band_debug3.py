"""
band_debug3.py
==============
3단계 진단: 사진 첨부까지 마친 뒤 "게시" 버튼을 눌렀을 때 무슨 화면이
뜨는지(확인 팝업/게시판 선택 등)를 측정한다.

실행:
    python band_debug3.py

결과:
  - band_debug3_before.png : 게시 누르기 직전
  - band_debug3_after.png  : 게시 누른 직후
  - 터미널에 화면 요소 목록 출력

⚠ 이 스크립트는 실제 게시를 시도합니다 (테스트 글이 올라갈 수 있음).
"""

import glob
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BAND_ID = os.environ.get("BAND_ID", "").strip()
STORAGE = os.environ.get("BAND_STORAGE_STATE", "band_storage_state.json").strip()

SELS = {
    "open": "button._btnOpenWriteLayer",
    "editor": "div.contentEditor._richEditor",
    "file": "input[type='file']",
    "confirm": "button:has-text('첨부하기')",
    "submit": "button._btnSubmitPost",
}

DUMP_JS = (
    "() => {"
    "  const out = [];"
    "  const sel = 'button, a, [role=dialog], [class*=confirm], [class*=Confirm],"
    " [class*=popup], [class*=Popup], [class*=layer], [class*=Layer]';"
    "  document.querySelectorAll(sel).forEach(el => {"
    "    const t = (el.innerText || '').trim().slice(0, 30);"
    "    if (!t) return;"
    "    const cls = (el.className && el.className.toString) ? el.className.toString().slice(0,55) : '';"
    "    out.push(el.tagName.toLowerCase() + ' | ' + cls + ' | ' + t);"
    "  });"
    "  return out.slice(0, 50);"
    "}"
)


def find_pngs():
    for slot_dir in sorted(glob.glob("output/*/AM"), reverse=True):
        for sub in ("approved", "draft"):
            ps = sorted(glob.glob(f"{slot_dir}/{sub}/*.png"))
            if ps:
                return [Path(p) for p in ps]
    return []


def main():
    if not BAND_ID:
        print("❌ set BAND_ID=<숫자> 먼저")
        return
    pngs = find_pngs()
    if not pngs:
        print("❌ 카드 PNG 없음 → python generate.py --slot AM --stub 먼저")
        return
    print("→ 사진", len(pngs), "장")

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False)
        ctx = b.new_context(storage_state=STORAGE, locale="ko-KR",
                            viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        page.goto(f"https://band.us/band/{BAND_ID}")
        page.wait_for_load_state("networkidle")
        page.click(SELS["open"])
        page.wait_for_selector(SELS["editor"])
        ed = page.locator(SELS["editor"]).first
        ed.click()
        ed.fill("자동 게시 테스트")
        page.locator(SELS["file"]).first.set_input_files([str(p) for p in pngs])
        page.wait_for_selector(SELS["confirm"], timeout=15000)
        page.wait_for_timeout(min(2000 + 1000 * len(pngs), 15000))
        page.click(SELS["confirm"])
        page.wait_for_selector(SELS["confirm"], state="hidden", timeout=20000)
        page.wait_for_timeout(2000)

        page.screenshot(path="band_debug3_before.png", full_page=True)
        print(">>> 게시 버튼 클릭")
        page.click(SELS["submit"])
        page.wait_for_timeout(4000)
        page.screenshot(path="band_debug3_after.png", full_page=True)

        try:
            ed_visible = (page.locator(SELS["editor"]).count() > 0
                          and page.locator(SELS["editor"]).first.is_visible())
        except Exception:
            ed_visible = False
        print("→ 게시 후 에디터 아직 보임?:", ed_visible)
        print("→ URL:", page.url)

        print("\n========== 게시 누른 직후 화면 요소 ==========")
        for c in page.evaluate(DUMP_JS):
            print("  -", c)
        print("==============================================\n")

        input("확인 후 Enter ▶ ")
        b.close()


if __name__ == "__main__":
    main()
