# 설치 가이드

이 가이드는 **처음 설치하는 분을 위한 단계별 안내**입니다. 코딩 지식 없어도 따라할 수 있게 쓰였습니다.

**소요 시간**: 약 30~45분 (익숙해지면 20분 내)

---

## 0. 준비물 체크리스트

- [ ] Windows PC (Mac이나 Linux도 가능하지만 이 가이드는 Windows 기준)
- [ ] **GitHub 계정** (무료) — https://github.com/signup
- [ ] **Anthropic 계정 + API 키** (유료, 섬 소액) — https://console.anthropic.com
- [ ] **네이버 밴드 계정** + 운영 중인 밴드 1개 (본인이 리더/매니저인 밴드)
- [ ] 인터넷

---

## 1. 저장소 Fork (내 계정으로 복제)

1. 브라우저에서 **https://github.com/dlalxp-droid/giseong** 접속
2. 우측 상단 **Fork** 버튼 클릭 → 본인 계정 선택 → Create fork
3. 포크된 내 저장소 URL을 메모 (예: `https://github.com/myusername/giseong`)

> 이후 모든 설명에서 `<YOUR_REPO>` 는 본인 fork 주소로 읽으세요.

---

## 2. Python 설치

1. https://www.python.org/downloads/ → 노란 **Download Python 3.x** 버튼 클릭
2. 다운로드된 설치 파일 실행
3. ⚠ **첫 화면 맨 아래 "Add python.exe to PATH" 체크박스 반드시 켜기** (가장 중요)
4. **Install Now** 구클릭 → 완료 대기 → Close
5. 설치 확인: `Windows키 + R` → `cmd` 타이핑 → Enter → 아래 입력
   ```
   python --version
   ```
   `Python 3.12.x` 같이 버전이 나오면 OK. "명령이 아닙니다" 이 뜨면 PATH 체크가 해제된 것 → 재설치.

---

## 3. Git 설치

1. https://git-scm.com/download/win → 다운로드 자동 시작
2. 설치 파일 실행 → 모든 옵션 **Next 며눇** 으로 기본값 설치
3. 설치 후 **cmd 창을 닫고 새로 열기** (이게 중요)
4. 확인: `git --version` → 버전 정상 출력 시 OK

---

## 4. 코드 받기 + 의존성 설치

새 cmd 창에서 (폴더는 `C:\Users\<내이름>\giseong` 으로 설명, 원하는 곳으로 변경 가능):

```
git clone https://github.com/<YOUR_USERNAME>/giseong.git
```
```
cd giseong
```
```
python -m pip install -r requirements.txt
```
```
python -m playwright install chromium
```

> 마지막 명령은 100MB 정도 다운로드합니다. 몇 분 소요.

---

## 5. 밴드 ID 확인

1. PC 크롬에서 **band.us** 접속 후 로그인
2. 게시할 대상 밴드로 이동
3. 주소창을 보면 `https://band.us/band/12345678` — **끝의 숫자**가 곳이 BAND_ID
4. 따로 메모

---

## 6. 밴드 로그인 세션 생성 (최초 1회)

대신 로그인해서 쓰고 버릴 "세션 파일"을 만듭니다.

cmd에서 (`giseong` 폴더 안에서):
```
python make_band_session.py
```

1. 크롬 창이 뜨면서 밴드 로그인 화면 표시
2. 평소처럼 계정 로그인 (캐프차/2단계 있으면 그 창에서 처리)
3. 로그인이 끝나 밴드 메인이 보이면 **cmd 창으로 돌아와서 Enter**
4. 같은 폴더에 `band_storage_state.json` 생성 확인

> ⚠ 이 파일은 로그인 정보와 같습니다. 남에게 주거나 공개 저장소에 올리지 마세요.
> `.gitignore`에 이미 포함되어 있어 git으로는 자동 제외됩니다.

---

## 7. Anthropic API 키 발급

1. https://console.anthropic.com 접속 → 회원가입 (이메일 인증)
2. 결제수단 등록 (좌측 **Plans & Billing** → 크레딧 충전, 최소 충전만 해도 몇 개월 운영 가능)
3. 좌측 **API Keys** → **Create Key** → 이름 입력 → 생성
4. **`sk-ant-api03-...`** 로 시작하는 키 복사 (한 번만 보이므로 안전한 곳에 메모)

---

## 8. GitHub Secrets 등록

1. 브라우저에서 내 fork 저장소 접속: `https://github.com/<YOUR_USERNAME>/giseong`
2. 상단 **Settings** 탭 → 좌측 **Secrets and variables → Actions**
3. **New repository secret** 버튼으로 아래 4개 등록:

| Name | Value |
|---|---|
| `BAND_ID` | 5단계에서 메모한 숫자 (예: `12345678`) |
| `BAND_STORAGE_STATE_JSON` | `band_storage_state.json` 파일 **내용 전체** (아래 참고) |
| `ANTHROPIC_API_KEY` | 7단계의 `sk-ant-api03-...` 키 |
| `BRAND_NAME` | 카드 하단 사인오프 (예: `@mybrand`) |

### `BAND_STORAGE_STATE_JSON` 넣는 법
- cmd에서 `notepad band_storage_state.json` → 메모장으로 파일 열림
- **전체 선택(Ctrl+A) → 복사(Ctrl+C)**
- GitHub Secret Value 칸에 붙여넣기(Ctrl+V) → Save
- `{` 로 시작해 `}` 로 끝나는 내용이 통으로 올라가야 함

---

## 9. 내 fork에 맞게 URL 하나 수정 (1회용)

`refresh_session.bat` 파일에는 세션 갱신 후 열릴 GitHub Secrets 페이지 URL이 원본 저장소로 고정돼 있습니다. 본인 fork의 주소로 한 번만 바꿔주세요.

1. 메모장으로 `refresh_session.bat` 열기
2. 아래 줄 찾기:
   ```
   start "" "https://github.com/dlalxp-droid/giseong/settings/secrets/actions"
   ```
3. `dlalxp-droid/giseong` 자리에 본인 아이디/저장소로 교체 (예: `myname/giseong`)
4. 저장

---

## 10. 첫 테스트 실행 (점검)

1. 브라우저 → `https://github.com/<YOUR_USERNAME>/giseong/actions`
2. 좌측 `Auto Generate & Upload to Naver Band` 클릭
3. 우측 **Run workflow** 버튼 →
   - Branch: **main**
   - slot: **AM**
   - **dry_run: `true`** (실제 게시 안 됨, 생성만 점검)
4. Run workflow 클릭
5. 몇 분 후 목록에 새 실행 나타남 → 끝나면 ✅ 되는지 확인

초록불이면 모든 설정이 정상입니다. 다음으로 진행.

---

## 11. 실제 게시 테스트

10번과 동일한 방식으로 다시 실행하되, 이번엔 **dry_run: `false`** 으로.

- 몇 분 후 내 밴드에 카드 8장의 새 글이 올라오면 성공
- `state/<오늘날짜>_AM.done` 파일이 자동 생성됨

성공했다면 **내일 아침 08:30부터 자동으로 계속 돌아갑니다.**

---

## 12. 자동 실행 시간

기본 스케줄 (`.github/workflows/upload-band.yml`):

| 시간 (한국) | 슬롯 | 스케줄의 의미 |
|---|---|---|
| 08:30 | AM | 원래 목표 시각 |
| 12:30 | AM | +4시간 보충 (08:30이 실패했을 때만 게시) |
| 18:00 | PM | 원래 목표 시각 |
| 22:00 | PM | +4시간 보충 |

다른 시간 원하면 워크플로우 파일의 `cron:` 수정 (UTC 기준, 한국 시간 = UTC+9).

---

## 13. 세션 갱신 (몇 주에 한 번)

클라우드 IP에서 밴드 세션이 주기적으로 해제됩니다. 그때마다:

1. `giseong` 폴더의 **`refresh_session.bat` 더블클릭**
2. 안내에 따라 Enter → 뜨운 크롬에서 밴드 재로그인 → cmd로 돌아와 Enter
3. 자동으로 GitHub Secrets 페이지 열림 + 새 세션 클립보드에 복사됨
4. 그 페이지에서 `BAND_STORAGE_STATE_JSON` 클릭 → Update → 기존 내용 지우고 Ctrl+V → Update secret

시간 소요 약 30소.

### 편의: 바탕화면 바로가기
`refresh_session.bat` 우클릭 → "보내기 → 바탕화면(바로가기 만들기)"

---

## 주제 커스터마이징

주제 목록, 세부주제는 `generate.py` 시작 부분의 `THEME_POOL`, `SUBTOPIC_POOL`을 직접 편집하면 됩니다. 다음 스케줄 실행부터 적용.

```python
THEME_POOL = [
    "보험 정보",       # 원하는 주제로 교체/추가
    ...
]

SUBTOPIC_POOL = {
    "보험 정보": [
        "실손보험 자기부담금",  # 자유롭게 교체/추가
        ...
    ],
    ...
}
```

주의: 주제 추가·삭제 후에는 cmd에서 변경을 commit·push 해야 클라우드에 적용됩니다:
```
git add generate.py
git commit -m "update themes"
git push
```

---

## 9. 문제 해결

### Actions 탭에 빨간불 ❌
1. 빨간불 실행 클릭 → 실패한 단계 펼치기 → 빨간 에러 메시지 확인
2. 자주 나오는 에러별 원인:

| 에러 | 원인 / 해결 |
|---|---|
| `로그인 세션 만료` | 밴드 세션 주기적 해제. `refresh_session.bat` 더블클릭 |
| `model: ... not_found_error` | `config.yaml`의 LLM `model` 값이 잘못됨. 현재 유효한 모델 ID로 교체 |
| `secrets.BAND_STORAGE_STATE_JSON not set` | Secret 등록 누락. 설치 8장 |
| `TimeoutError: Page.click: ...` | 밴드 UI 셀렉터 명칭 변경 가능성. 개발자에게 문의 |
| `Insufficient credit` | Anthropic 크레딧 소진. Console 결제 수단 충전 |

### 게시는 되는데 몇 시간 늦게 올라감
GitHub 무료 cron의 정상 특성(수십 분 지연이 일반적). +4시간 보충 실행이 그래서 있습니다. 정확한 시간이 매우 중요하면 로컬 PC 작업 스케줄러 병행 고려.

### 같은 날 AM·PM 둘 다 안 올라갑
`state/<날짜>_AM.done`, `_PM.done` 파일 존재 여부로 판별. 둘 다 없으면 cron 누락, 하나만 있으면 해당 슬롯만 실패.

### 활립면에 안 올라올 때
절대적으로 안 올라오는 경우는 드물니다. 대부분 계세장이 아닌 세션 만료 → 13번 절차.

---

## 더 고급 설정 (선택)

### 실패 알림 (슬랙/디스코드 웹훅)
Secret 에 `NOTIFY_WEBHOOK_URL` 추가 → 실패 시 해당 URL로 POST 알림

### 검수 게이트 활성화 (자동 게시 대신 수동 승인)
워크플로우의 `--allow-draft` 제거 → `output/<날짜>/<슬롯>/approved/` 에 PNG 이동된 후에만 게시.

### 주제 수정 시 자동 커밋 (로컬)
```
git add -A
git commit -m "주제 업데이트"
git push
```

---

## 최종 체크리스트

다 끝났다면 아래가 모두 ✅ 인지 확인:

- [ ] 저장소 Fork 완료
- [ ] Python / Git 설치, 버전 확인 됨
- [ ] `pip install -r requirements.txt` 성공
- [ ] `playwright install chromium` 성공
- [ ] `make_band_session.py` 로 `band_storage_state.json` 생성
- [ ] GitHub Secrets 4개 등록 (BAND_ID / BAND_STORAGE_STATE_JSON / ANTHROPIC_API_KEY / BRAND_NAME)
- [ ] `refresh_session.bat` 내 URL 본인 fork로 교체
- [ ] dry_run=true 테스트 실행 ✅
- [ ] dry_run=false 실제 게시 테스트 ✅ → 밴드에 글 올라온 것 확인
- [ ] 바탕화면 `refresh_session.bat` 바로가기 만들기

이 철차 끝난 다음 날부터 아래처럼 돌아갑니다:
```
매일 08:30 → 자동 생성 + 게시
매일 18:00 → 자동 생성 + 게시
몇 주에 한 번 → refresh_session.bat 더블클릭
```

수고하셔어요!
