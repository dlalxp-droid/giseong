"""
make_band_session.py
====================
네이버 밴드 로그인 세션(band_storage_state.json)을 만드는 1회용 스크립트.

사용법 (윈도우/맥 공통):
    python make_band_session.py

실행하면 크롬 창이 뜨고 밴드 로그인 화면이 나옵니다.
  1) 그 창에서 평소처럼 밴드(네이버)에 로그인합니다.
  2) 로그인이 끝나 밴드 화면이 보이면, 이 터미널로 돌아와 Enter 를 누릅니다.
  3) 같은 폴더에 band_storage_state.json 파일이 생성됩니다.

⚠ 이 파일은 로그인 정보와 같으므로 남에게 공유하거나 공개 저장소에 올리지 마세요.
"""

from playwright.sync_api import sync_playwright

OUT = "band_storage_state.json"
LOGIN_URL = "https://auth.band.us/login_page"


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()
        page.goto(LOGIN_URL)

        print("=" * 56)
        print(" 브라우저 창에서 밴드 로그인을 완료하세요.")
        print(" 로그인이 끝나 밴드 화면이 보이면 여기서 Enter 를 누르세요.")
        print("=" * 56)
        input(" 로그인 완료 후 Enter ▶ ")

        ctx.storage_state(path=OUT)
        browser.close()

    print(f"\n✅ 저장 완료 → {OUT}")
    print("   이 파일 내용을 GitHub Secret(BAND_STORAGE_STATE_JSON)에 붙여넣으세요.")
    print("   로컬 테스트시에는 .env 에 BAND_STORAGE_STATE=./band_storage_state.json")


if __name__ == "__main__":
    main()
