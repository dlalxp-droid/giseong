# 네이버 밴드 자동 카드뉴스 시스템

매일 정해진 시각에 정보 카드뉴스(8장)를 자동으로 만들고 네이버 밴드에 게시하는 프로그램.
Claude AI로 콘텐츠 생성 + Playwright 브라우저 자동화로 밴드에 직접 업로드.

## 특징

- ✅ **매일 2회 자동 게시** (오전 08:30 / 오후 18:00, 한국시간)
- ✅ **8주제 일일 순환**: 보험 → 건강 → 생활 → 금융 → 노후·은퇴 → 부동산·주택 → 자녀·가족 → 자기계발
- ✅ **세부주제 15개×8 = 120개 풀** + AM/PM 오프셋 → 약 240가지 조합
- ✅ **가짜뉴스 방지 가드레일** (속보/수치 날조/특정종목 언급 금지)
- ✅ **클라우드 자동 실행** (GitHub Actions) — 내 PC 껌져 있어도 돌아감
- ✅ **누락 시 보충 실행** (+4시간 재시도, 중복 방지 내장)
- ✅ **세션 갱신 더블클릭** (refresh_session.bat) — 몇 주에 한 번 갱신

## 자동화 흐름

```
  GitHub Actions Cron 스케줄
              ↓
  Claude API 로 카드 8장 + 캸션 생성
              ↓
  Playwright로 1080×1080 PNG 렌더링
              ↓
  Playwright로 밴드 글쓰기 → 사진 8장 첨부 → 게시
              ↓
  state/<날짜>_<슬롯>.done 표시 기록
```

## 빠른 시작

👉 [SETUP.md](SETUP.md) 를 차례대로 따라하세요. 소요 시간 30~45분.

## 주요 파일 구조

```
.
├── generate.py              # 카드세트 생성 (Claude API + 렌더링)
├── band_scheduler.py        # 밴드 업로드 진입점
├── make_band_session.py     # 세션 생성 (최초 1회 로그인)
├── refresh_session.bat      # 세션 갱신 원클릭 스크립트 (더블클릭)
├── config.yaml              # 디자인/콘텐츠/슬롯 설정
├── requirements.txt         # Python 의존성
├── templates/
│   └── card.html            # 1080×1080 카드 HTML 템플릿
├── scripts/
│   ├── content_generator.py # Claude API 프롬프트 + JSON 스키마
│   ├── renderer.py          # HTML → PNG 렌더
│   └── band_uploader.py     # Playwright 밴드 업로드
├── .github/workflows/
│   └── upload-band.yml      # 매일 자동 실행 (클라우드)
├── state/                   # 게시 완료 표시 파일 (자동 기록)
└── output/                  # 생성된 카드 PNG (날짜별)
```

## 매일 운영

설치 끝나면 평소엔 손 대질 일 거의 없습니다:

- **자동** — 매일 08:30 / 18:00 자동 게시
- **확인** — 한 달에 한두 번 Actions 탭에서 성공/실패 확인
- **갱신** — 몇 주에 한번 `refresh_session.bat` 더블클릭으로 세션 갱신
  (클라우드 IP에서 밴드 세션이 주기적으로 풌리기 때문)

## 주제·콘텐츠 커스터마이징

### 주제 목록 변경
`generate.py` 의 `THEME_POOL` 편집:
```python
THEME_POOL = [
    "보험 정보", "건강 정보", ...
]
```

### 세부주제 변경 / 추가
`generate.py` 의 `SUBTOPIC_POOL` 딕셔너리 편집. 각 대주제마다 리스트로 자유롭게 추가/제거.

### 시스템 프롬프트 / 가드레일
`scripts/content_generator.py` 의 `SYSTEM_PROMPT` 수정.

### 카드 디자인 (색상/레이아웃)
`templates/card.html` 내 CSS 수정. 컬러 변수 `--navy`, `--cream`, `--gold`, `--red`.

### 게시 시간
`.github/workflows/upload-band.yml` 의 `cron:` 수정 (UTC 기준).

## 기술 스택

- Python 3.11+
- Anthropic Claude API (`anthropic`)
- Playwright (Chromium 자동화)
- PyYAML (설정)
- GitHub Actions (스케줄링)

## 시스템 한계 / 주의점

- **클라우드 세션 만료**: GitHub IP에서 밴드 세션이 주기적으로 풌립니다 (보통 몇 주). `refresh_session.bat` 으로 갱신 필요.
- **GitHub cron 지연**: 무료 예약 실행은 정시 보장 안 됨 (수십 분 늦거나 끊기기도). 보충 +4시간 수시로 완화.
- **가짜뉴스 위험**: AI는 실시간 뉴스를 모릅니다. 시스템 프롬프트에서 "속보/수치날조/특정종목 금지"로 제한되어 있지만 검수로 검증하면 더 안전. 검수 게이트를 켜려면 `band_scheduler.py --allow-draft` 옵션 제거.
- **API 비용**: Claude API는 사용량대로 과금. 세트당 약 수십원 수준 (Sonnet 기준).

## 라이선스 / 고지

- Personal use 기준 제작됨.
- 밴드 차용서 자동화는 네이버 밴드의 ToS 범위 내에서만 사용하세요. 과도한 호출·스팸성 게시 금지.
- Claude API·밴드·GitHub 이용약관을 본인이 확인하고 준수하세요.

## 자주 보는 문제 → [SETUP.md 하단 문제해결 섹션](SETUP.md#9-문제-해결)
