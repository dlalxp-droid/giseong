# 보험 상담 화법 카드뉴스 자동화 시스템

인스타그램 피드용 카드뉴스(1080x1080, 8장/세트)를 Claude API로 자동 생성하고,
지정된 시간(매일 08:30 / 18:00)에 **인스타그램(Meta Graph API) + 네이버 밴드** 양쪽으로
자동 업로드하는 시스템.

타겟: 보험설계사. 콘텐츠: 보험 상담 화법 (보상 관련 주제는 자동 회피).

---

## 1. 디렉토리 구조

```
.
├── generate.py              # 카드뉴스 일괄 생성 진입점
├── scheduler.py             # 인스타 업로드 진입점 (cron)
├── band_scheduler.py        # 네이버 밴드 업로드 진입점 (cron)
├── config.yaml              # 디자인/콘텐츠/슬롯/플랫폼 설정
├── .env.example             # 환경변수 템플릿
├── requirements.txt
├── templates/
│   └── card.html            # 1080x1080 단일 템플릿 (카드 type별 분기)
├── scripts/
│   ├── content_generator.py # Claude API 호출 → 8장 분량 JSON
│   ├── renderer.py          # HTML → Playwright → PNG
│   ├── image_host.py        # Cloudinary 업로드 (Meta는 public URL 요구)
│   ├── ig_uploader.py       # Meta Graph API 캐러셀 게시
│   ├── band_uploader.py     # 네이버 밴드 게시 (api / web 모드)
│   └── band_auth.py         # 네이버 밴드 OAuth2 헬퍼
├── input/                   # 사용자 자료 (PDF 등) drop
├── output/                  # 생성물 (draft → approved 게이트)
├── captions/                # YYYY-MM-DD_AM.txt, _PM.txt
└── logs/
    ├── YYYY-MM-DD_SLOT.json # 인스타 업로드 결과
    └── band/                # 밴드 업로드 결과
```

---

## 2. 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env
# .env 파일을 열어 토큰/키 채우기
```

---

## 3. Meta Graph API 토큰 발급 (인스타용)

지시서 2-1번 참고. 핵심만:

1. 인스타그램 **프로페셔널** 계정 + 페이스북 페이지 연동
2. https://developers.facebook.com → 앱 생성 → "비즈니스"
3. 제품: Instagram Graph API
4. 권한: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`
5. 단기 토큰 → 장기 토큰(60일)으로 교환
6. `.env`:
   ```
   META_ACCESS_TOKEN=EAAxxxxxxx...
   IG_USER_ID=17841400000000000
   ```

---

## 4. 이미지 호스팅 (Cloudinary)

Meta API는 **public URL** 만 받기 때문에 PNG를 외부에 올려야 함.
밴드 `api` 모드도 같은 호스팅을 재사용.

1. https://cloudinary.com/users/register/free
2. `.env` 에 `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`

---

## 5. 네이버 밴드 자동 업로드

밴드 Open API는 **글 작성**만 공식 지원하고 **사진 첨부 업로드 엔드포인트가 없다**.
따라서 두 가지 모드를 함께 제공한다:

| 모드 | 방식 | 결과 | 추천 상황 |
|---|---|---|---|
| `api` | Open API `/v2.2/band/post/create` | 본문 + 이미지 URL 링크 (썸네일 미리보기) | 안정적이지만 카드뉴스 8장 첨부 형태 아님. 빠른 알림용 |
| `web` | Playwright + 저장된 로그인 세션 | 사진 8장 직접 첨부 (실제 카드뉴스 형태) | **운영 권장** |

### 5-1. Open API 앱 등록 (api 모드)

1. https://developers.band.us → "Create New App"
2. 앱 등록 후 **Client ID / Client Secret / Redirect URI** 확보
3. 권한 스코프: `READ_BAND`, `READ_POST`, `WRITE_POST`
4. **최초 1회 동의 화면**:
   ```bash
   export BAND_CLIENT_ID=...
   export BAND_CLIENT_SECRET=...
   export BAND_REDIRECT_URI=http://localhost/band_oauth_cb
   python scripts/band_auth.py authorize-url
   # 출력 URL을 브라우저로 열어 동의 → redirect_uri?code=XXX 의 code 복사
   python scripts/band_auth.py exchange --code XXX
   # → access_token / refresh_token 출력
   ```
5. `.env` 에 저장:
   ```
   BAND_CLIENT_ID=...
   BAND_CLIENT_SECRET=...
   BAND_REDIRECT_URI=...
   BAND_ACCESS_TOKEN=ZQAA...
   BAND_REFRESH_TOKEN=ZQAA...
   ```
6. 게시 대상 밴드 키 조회:
   ```bash
   python scripts/band_auth.py bands
   # AABbbbbb...   내 보험상담 밴드
   ```
   `BAND_KEY=AABbbbbb...` 를 `.env` 에 추가.
7. 토큰 만료 시:
   ```bash
   python scripts/band_auth.py refresh
   ```

### 5-2. 웹 자동 로그인 세션 만들기 (web 모드)

밴드 본인 인증은 캡차/2단계가 있어 헤드리스 자동 로그인은 권장하지 않는다.
대신 **로컬에서 한 번 로그인한 세션을 storage_state.json 으로 저장**해서 재사용한다.

```bash
python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=False)
    ctx = b.new_context(locale="ko-KR")
    page = ctx.new_page()
    page.goto("https://auth.band.us/login_page")
    input("브라우저에서 로그인 완료 후 Enter…")
    ctx.storage_state(path="band_storage_state.json")
    b.close()
PY
```

`.env`:
```
BAND_ID=12345678                       # https://band.us/band/<여기>
BAND_STORAGE_STATE=./band_storage_state.json
```

> 세션 만료(보통 수주 ~ 수개월): 위 스크립트로 다시 만들면 됨.

### 5-3. 즉시 게시 테스트

```bash
# 자료 점검만 (실제 게시 X)
python band_scheduler.py --slot AM --dry-run

# api 모드 — 본문 + URL 게시
python band_scheduler.py --slot AM --mode api --push

# web 모드 — 사진 8장 첨부 게시
python band_scheduler.py --slot AM --mode web
```

### 5-4. cron 등록

```cron
# 인스타 + 밴드 동시 게시
30 8  * * *  cd /path && /path/.venv/bin/python scheduler.py       --slot AM
30 8  * * *  cd /path && /path/.venv/bin/python band_scheduler.py  --slot AM --mode web
0  18 * * *  cd /path && /path/.venv/bin/python scheduler.py       --slot PM
0  18 * * *  cd /path && /path/.venv/bin/python band_scheduler.py  --slot PM --mode web
```

### 5-5. GitHub Actions

`.github/workflows/upload-band.yml` 에 정기 워크플로우 포함.
저장소 secrets:
- 공통: `NOTIFY_WEBHOOK_URL`
- api: `BAND_CLIENT_ID`, `BAND_CLIENT_SECRET`, `BAND_REFRESH_TOKEN`, `BAND_KEY`,
  `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- web: `BAND_ID`, `BAND_STORAGE_STATE_JSON` (로컬에서 만든 storage_state.json
  파일 **내용** 전체를 secret value 로 붙여넣음)

---

## 6. 일일 운영 흐름

### 6-1. 일주일치 일괄 생성

```bash
python generate.py --days 7 --slots AM,PM
```

### 6-2. 검수 → approved 이동

```bash
mv output/2026-05-04/AM/draft/*.png output/2026-05-04/AM/approved/
```

> approved/ 에 들어간 것만 자동 업로드 큐 대상 (지시서 6번).

### 6-3. 즉시 테스트

```bash
python generate.py --preview --stub
python scheduler.py      --slot AM --dry-run
python band_scheduler.py --slot AM --dry-run
```

---

## 7. 카드 구조 (지시서 1-2)

```
01 cover    표지 (강한 후킹)
02 problem  문제 상황
03 mistake  흔한 실수 멘트
04 before   기존 화법
05 after    권장 화법 (강조 멘트)
06 theory   심리학 근거 (카네기/아들러/치알디니 등)
07 summary  한 줄 요약
08 cta      저장·공유 유도 + 다음 예고
```

콘텐츠 톤:
- 추상론 금지. 실제 멘트 대본 형태
- Before/After는 따옴표로 묶인 직접 멘트
- 심리학 인용은 12자 이내 (저작권)
- 보상·약관·의료자문 주제는 system prompt에서 자동 차단

---

## 8. 자주 보는 에러

| 에러 | 원인 / 해결 |
|---|---|
| `Container ... not ready in 60s` | 이미지 URL public 아님 / 호스팅 지연 |
| `(#10) Application does not have permission` | Meta 앱 검수 미완료 또는 권한 누락 |
| `Carousel must have 2~10 items` | PNG 개수 불일치 |
| 토큰 만료 (Meta) | 60일 만료. Graph API Explorer 재발급 |
| `Band API error: ... 'result_code': N` | Band 에러 코드 표 참조 (1=정상). 토큰 만료시 `band_auth.py refresh` |
| Band web 모드 selector 실패 | 밴드 UI 개편. `config.yaml` `band.web_selectors_override` 로 덮어쓰기 |
| `BAND_STORAGE_STATE` 없음 | 5-2 절차로 storage_state.json 생성 후 경로 지정 |

---

## 9. 안전장치

- 보상 주제 자동 회피 (system prompt 차단)
- draft → approved 수동 게이트 (사람이 본 것만 게시)
- 재시도 3회 (네트워크 일시 장애 대응)
- 플랫폼별 분리 로그: `logs/*.json` (인스타) / `logs/band/*.json` (밴드)
- 알림 웹훅(선택): 실패 시 슬랙/디스코드로 통보

---

## 10. 다음 확장 (TODO)

- [ ] PDF/Google Drive 자료 입력 반영
- [ ] 주간 주제 커버리지 대시보드
- [ ] Pretendard 폰트 임베드
- [ ] Reels 분리 발행 (media_type=REELS)
- [ ] 카카오톡 채널 / 네이버 카페 어댑터 추가
