# 보험 상담 화법 카드뉴스 자동화 시스템

인스타그램 피드용 카드뉴스(1080x1080, 8장/세트)를 Claude API로 자동 생성하고,
지정된 시간(매일 08:30 / 18:00)에 Meta Graph API로 자동 업로드하는 시스템.

타겟: 보험설계사. 콘텐츠: 보험 상담 화법 (보상 관련 주제는 자동 회피).

---

## 1. 디렉토리 구조

```
cardnews-system/
├── generate.py              # 카드뉴스 일괄 생성 진입점
├── scheduler.py             # 인스타 업로드 진입점 (cron)
├── config.yaml              # 디자인/콘텐츠/슬롯 설정
├── .env.example             # 환경변수 템플릿
├── requirements.txt
├── templates/
│   └── card.html            # 1080x1080 단일 템플릿 (카드 type별 분기)
├── scripts/
│   ├── content_generator.py # Claude API 호출 → 8장 분량 JSON
│   ├── renderer.py          # HTML → Playwright → PNG
│   ├── image_host.py        # Cloudinary 업로드 (Meta는 public URL 요구)
│   └── ig_uploader.py       # Meta Graph API 캐러셀 게시
├── input/                   # 사용자 자료 (PDF 등) drop
├── output/                  # 생성물
│   └── 2026-05-04/
│       ├── AM/
│       │   ├── draft/       # 자동 생성 직후
│       │   ├── approved/    # 검수 완료 후 사람이 이동 → 업로드 큐 진입
│       │   └── _meta.json   # 재렌더용
│       └── PM/...
├── captions/                # YYYY-MM-DD_AM.txt, _PM.txt
└── logs/                    # 게시 결과 JSON 로그
```

---

## 2. 설치

```bash
# 가상환경
python -m venv .venv
source .venv/bin/activate

# 의존성
pip install -r requirements.txt

# Playwright Chromium (최초 1회)
python -m playwright install chromium

# 환경변수
cp .env.example .env
# .env 파일을 열어 토큰/키 채우기
```

---

## 3. Meta Graph API 토큰 발급 (수동, 1회)

지시서 2-1번에 해당. 핵심만 정리.

1. **인스타그램 프로페셔널 계정**으로 전환 (개인 계정은 API 사용 불가)
2. **페이스북 페이지** 생성 후 인스타와 연동
3. [Meta for Developers](https://developers.facebook.com) → 앱 생성 → 유형 "비즈니스"
4. 제품 추가: **Instagram Graph API**
5. 권한 추가:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
6. **그래프 API 탐색기**에서 단기 토큰 발급 후 → **장기 토큰**(60일)으로 교환
7. `.env`에 저장:
   ```
   META_ACCESS_TOKEN=EAAxxxxxxx...
   IG_USER_ID=17841400000000000   # GET /me/accounts → instagram_business_account.id
   ```
8. **앱 검수** 완료 후 운영 모드 전환 (개발 모드는 본인 계정에만 게시 가능)

> 토큰 만료: 60일마다 갱신 필요. 만료 1주일 전 슬랙 알림을 받도록 별도 cron 권장.

---

## 4. 이미지 호스팅 세팅 (Cloudinary)

Meta API는 **public URL** 만 받기 때문에 PNG를 외부에 올려야 함.
Cloudinary 무료 티어(월 25GB)면 충분.

1. https://cloudinary.com/users/register/free
2. Dashboard에서 cloud name / API key / API secret 복사
3. `.env`:
   ```
   CLOUDINARY_CLOUD_NAME=your_name
   CLOUDINARY_API_KEY=...
   CLOUDINARY_API_SECRET=...
   ```

---

## 5. 일일 운영 흐름

### 5-1. 일주일치 일괄 생성

```bash
python generate.py --days 7 --slots AM,PM
# → output/2026-05-04/AM/draft/card_01.png ~ card_08.png (× 14세트)
# → captions/2026-05-04_AM.txt
```

세부 주제는 `SUBTOPIC_POOL`(generate.py)에서 자동 회전. 직접 지정도 가능:

```bash
python generate.py --date 2026-05-05 --slot AM --topic "거절 처리 화법"
```

### 5-2. 검수 후 approved 이동

draft/ 폴더의 PNG 8장과 캡션을 확인한 뒤,
**문제없으면 approved/ 폴더로 옮긴다**:

```bash
mv output/2026-05-04/AM/draft/*.png output/2026-05-04/AM/approved/
```

> 운영 정책 (지시서 6번): approved 에 들어간 것만 자동 업로드 큐 대상.
> draft 그대로 발행하려면 `scheduler.py --allow-draft` 옵션 (비권장).

### 5-3. cron 등록

```cron
# crontab -e
30 8  * * *  cd /path/to/cardnews-system && /path/to/.venv/bin/python scheduler.py --slot AM
0  18 * * *  cd /path/to/cardnews-system && /path/to/.venv/bin/python scheduler.py --slot PM
```

### 5-4. 즉시 테스트

```bash
# API 호출 없이 더미 데이터로 1세트 생성 (개발용)
python generate.py --preview --stub

# Cloudinary/Meta 호출 없이 자료만 점검
python scheduler.py --slot AM --dry-run
```

---

## 6. 카드 구조 (지시서 1-2)

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

## 7. 자주 보는 에러

| 에러 | 원인 / 해결 |
|---|---|
| `Container ... not ready in 60s` | 이미지 URL이 public 아님 / 호스팅 지연. URL 직접 브라우저 접속 확인 |
| `(#10) Application does not have permission` | Meta 앱 검수 미완료 또는 권한 누락 |
| `Image must be a JPEG` | Meta는 PNG도 받지만 일부 환경에서 JPEG 강제. renderer에서 출력 포맷 변경 |
| `Carousel must have 2~10 items` | PNG 개수 불일치. cards_per_set 재확인 |
| 토큰 만료 | 장기 토큰도 60일 만료. Graph API Explorer에서 재발급 |

---

## 8. 안전장치

- **보상 주제 자동 회피**: system prompt에서 차단
- **draft → approved 수동 게이트**: 사람이 본 것만 게시
- **재시도 3회**: 네트워크 일시 장애 대응
- **로그 파일**: `logs/YYYY-MM-DD_SLOT.json` 에 게시 결과 기록
- **알림 웹훅**(선택): 실패 시 슬랙/디스코드로 즉시 통보

---

## 9. 다음 확장 (TODO)

- [ ] PDF/Google Drive 자료를 input/ 에 두면 콘텐츠 생성 시 우선 반영
- [ ] 일주일 커버리지 대시보드 (어떤 주제 다뤘는지 시각화)
- [ ] 폰트 임베드 (Pretendard) 로컬 설치 - 현재는 시스템 폰트 fallback
- [ ] Reels 분리 발행(media_type=REELS, share_to_feed=false) 모듈
