# GitHub Actions 운영 가이드

GitHub Actions로 카드뉴스 자동 생성 + 인스타 자동 업로드를 구동하는 단계별 가이드입니다.

> 사전 조건: 3-4단계(Meta 페이지 토큰 + IG_USER_ID + Cloudinary)는 완료된 상태여야 합니다.

---

## 5-1. GitHub 저장소 생성

### ① GitHub 로그인 + 새 저장소

1. https://github.com 접속 → 로그인
2. 우측 상단 **"+" → "New repository"**
3. 입력:
   - **Repository name**: `cardnews-system` (자유)
   - **Visibility**: **Private** ⭐ (반드시 Private. Public이면 git 히스토리에 토큰이 남을 위험)
   - **Initialize with README**: 체크 안 함
4. **"Create repository"** 클릭

### ② 로컬에서 코드 푸시

터미널에서 (압축 해제한 cardnews-system 폴더 안에서):

```bash
cd cardnews-system

# git 초기화
git init
git add .
git commit -m "Initial commit"

# GitHub 저장소 연결 (본인 username으로 치환)
git branch -M main
git remote add origin https://github.com/본인username/cardnews-system.git
git push -u origin main
```

> 💡 처음 push 시 인증 요구하면 GitHub Personal Access Token 발급:
> Settings → Developer settings → Personal access tokens → Fine-grained tokens → 저장소에 read/write 권한

푸시 후 GitHub 저장소 페이지를 새로고침하면 모든 파일이 보입니다.

---

## 5-2. GitHub Secrets 등록 (토큰/키 저장)

`.env` 파일은 git에 안 올라가니까, GitHub Secrets에 따로 등록합니다.

### 등록 방법

1. 저장소 페이지 → **Settings** 탭
2. 좌측 메뉴 **Secrets and variables → Actions**
3. **"New repository secret"** 버튼

### 등록할 Secret 7개

순서대로 하나씩 등록:

| Name (대소문자 정확히) | Value |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com에서 발급한 sk-ant-... |
| `META_ACCESS_TOKEN` | 토큰 C (페이지 무기한 토큰) |
| `IG_USER_ID` | 17841400000000000 형식의 숫자 |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary dashboard의 Cloud Name |
| `CLOUDINARY_API_KEY` | Cloudinary API Key |
| `CLOUDINARY_API_SECRET` | Cloudinary API Secret |
| `BRAND_NAME` | 카드 하단에 표시할 본인 브랜드명 (@your_brand) |

선택 (실패 알림 받고 싶으면):

| `NOTIFY_WEBHOOK_URL` | 슬랙/디스코드 웹훅 URL |

### 등록 확인

Settings → Secrets and variables → Actions 화면에 7개(또는 8개)가 모두 보이면 OK.
값은 등록 후엔 **GitHub도 다시 보여주지 않습니다**. 메모장에 백업 보관.

---

## 5-3. 첫 테스트 — 카드 생성 워크플로우 수동 실행

먼저 카드를 생성해야 업로드할 게 생깁니다.

### ① Actions 탭으로 이동

저장소 → **Actions** 탭 클릭

> 첫 진입 시 "Workflows aren't being run" 같은 메시지 나오면 **"I understand my workflows, go ahead and enable them"** 클릭

### ② Generate Weekly Cards 워크플로우 선택

좌측 목록에서 **"Generate Weekly Cards"** 클릭

### ③ 수동 실행

우측 **"Run workflow"** 드롭다운 클릭 → 입력:

- **Branch**: main
- **며칠치 생성**: `1` (테스트니까 1일치만)
- **시작 날짜**: 비워두거나 내일 날짜
- **슬롯**: `AM`
- **특정 주제**: `거절 처리 화법` (또는 비워두고 자동 회전)

**"Run workflow"** 버튼 클릭

### ④ 실행 진행 확인

5초쯤 후 페이지 새로고침 → 노란색 점 깜박이는 실행 항목이 보임 → 클릭하면 진행 중인 로그 실시간 확인 가능.

5분 정도 후 **녹색 체크** 표시되면 성공.

### ⑤ 결과 확인

성공하면 자동으로 **검수 PR이 생성**됩니다:
- 저장소 → **Pull requests** 탭 → "[검수 요청] 카드뉴스..." PR 클릭
- **Files changed** 탭 → 생성된 카드 8장 PNG가 보임
- 캡션 텍스트도 확인

---

## 5-4. 검수 후 approved 폴더로 이동

draft에 있는 걸 approved로 옮겨야 자동 업로드 대상이 됩니다.

### 방법 A — 로컬에서 옮기기 (안전, 추천)

```bash
# main 브랜치로 PR 머지 먼저
# (GitHub에서 PR 페이지 → "Merge pull request" 클릭)

# 로컬에서 최신 받기
git pull

# draft → approved 이동
git mv output/2026-05-05/AM/draft/*.png output/2026-05-05/AM/approved/
git commit -m "Approve 2026-05-05 AM"
git push
```

### 방법 B — GitHub 웹에서 직접 (느리지만 가능)

웹에서 파일 단위로 옮길 수 있지만, 8장씩 매번 하기 번거로움. 추천 안 함.

### 방법 C — 검수 자동화 (옵션)

PR 머지 시 자동으로 draft → approved 옮기는 워크플로우를 추가할 수도 있습니다. 단, **사람 검수 게이트가 사라지는 위험**이 있어서 처음엔 수동 권장.

---

## 5-5. 첫 테스트 — 업로드 워크플로우 수동 실행

approved 폴더에 PNG 8장이 들어있는 상태에서 시도:

### ① Daily Instagram Upload 선택

Actions 탭 → 좌측 **"Daily Instagram Upload"** 클릭

### ② 수동 실행 (드라이런)

**"Run workflow"** 드롭다운 → 입력:

- **Branch**: main
- **슬롯**: `AM`
- **날짜**: approved에 자료가 있는 날짜 (예: `2026-05-05`)
- **드라이런**: ✅ **체크** ⭐

> 드라이런 모드는 실제 업로드 안 하고 자료만 점검합니다. 첫 테스트는 무조건 드라이런으로.

**"Run workflow"** 클릭 → 1분 후 녹색 체크 확인

### ③ 진짜 업로드 테스트

드라이런 성공하면, 같은 방식으로 **드라이런 체크 해제** 후 다시 실행. 인스타에 게시되는 데 1~3분 걸립니다.

본인 인스타 앱에서 게시물 확인되면 ✅ **5단계 완료**.

---

## 5-6. cron 자동 실행 활성화

수동 테스트가 끝났으면 정기 자동 실행은 **이미 활성화되어 있습니다**. 별도 설정 불필요.

스케줄:

| 워크플로우 | 시간 (한국시간) | 동작 |
|---|---|---|
| Generate Weekly Cards | 매주 일요일 21:00 | 다음 주 7일치 14세트 생성 → PR 생성 |
| Daily Instagram Upload (AM) | 매일 08:30 | 오늘 AM 슬롯 approved 폴더 게시 |
| Daily Instagram Upload (PM) | 매일 18:00 | 오늘 PM 슬롯 approved 폴더 게시 |
| Token Health Check | 매월 1일 09:00 | 토큰 유효성 검증 |

> ⚠️ GitHub Actions의 cron은 정확한 시간에 발동 안 될 수 있습니다 (보통 5~15분 지연). Meta API도 게시까지 1~2분 걸리므로, 실제 게시 시각은 cron 시각보다 5~20분 늦을 수 있음.

---

## 5-7. 일상 운영 루틴

```
[매주 일요일 21:00]
  → Actions가 자동으로 14세트 생성 + 검수 PR 생성
  → 본인에게 GitHub 알림 (이메일/앱)

[월요일 또는 미리 검수]
  → PR 열어서 카드 8장 × 14세트 + 캡션 검토
  → OK인 세트만 머지
  → 머지 후 로컬에서 git pull → draft → approved 이동 → push
  → 또는 PR 닫고 새로 생성 트리거

[매일 08:30 / 18:00]
  → Actions가 자동으로 인스타 업로드
  → 실패 시 NOTIFY_WEBHOOK_URL로 슬랙/디스코드 알림 (설정한 경우)

[매월 1일]
  → 토큰 자동 점검
  → 문제 있으면 알림
```

---

## 5-8. 자주 막히는 케이스

### "Workflow run failed" 빨간 X 표시

1. 실패한 실행 항목 클릭 → 빨간 X 있는 step 확장
2. 에러 로그 확인. 흔한 원인:
   - **Secret 이름 오타** → `META_ACCESS_TOKEN`인데 `META_TOKEN`으로 등록한 경우. 정확한 이름 확인
   - **Secret 값 끝에 공백** → 토큰 끝에 줄바꿈 끼었을 때. 다시 등록
   - **PNG가 approved에 없음** → draft만 있고 approved 비어있음. PR 머지 + draft→approved 이동 확인

### "scheduler.py 가 PNG를 못 찾음"

- approved/ 폴더 비어있음
- 또는 날짜 인자가 실제 파일 있는 날짜와 안 맞음

### "Cloudinary 업로드 실패"

- Cloudinary 무료 한도 초과 (월 25GB) → 한 달 운영 시 이론상 약 4MB × 14세트 × 8장 × 30일 = 약 13GB. 한도 내
- API Key/Secret 오타 → Secret 다시 등록

### "Meta API (#100) Invalid parameter"

- 이미지 URL이 public 아님. Cloudinary URL을 브라우저로 직접 열어서 이미지가 보이는지 확인

### cron이 발동 안 함

- 해당 저장소에 60일간 활동 없으면 GitHub Actions cron이 비활성화됩니다 (무료 정책)
- 매주 PR 머지 같은 활동이 있으면 자동 유지됨

---

## 5-9. 비용 (모두 무료)

| 서비스 | 무료 한도 | 월 예상 사용량 | 잉여 |
|---|---|---|---|
| GitHub Actions (Private) | 2,000분/월 | 약 60분 (워크플로우 60회 × 1분) | 매우 충분 |
| Anthropic Claude API | 첫 가입 무료 크레딧 | 약 $0.5~$2 (14세트/주 기준) | 유료 (저렴) |
| Cloudinary | 25GB 저장 + 25GB 대역폭 | 약 0.5GB | 매우 충분 |
| Meta Graph API | 무료, 100건/24시간 | 2건/일 | 매우 충분 |

전체 운영 비용: **월 $1~3** (Anthropic API만 유료)

---

## 5-10. 다음 단계 — 운영 안정화

1. ✅ NOTIFY_WEBHOOK_URL을 슬랙 워크스페이스 웹훅으로 설정 → 실패 시 즉시 알림
2. ✅ Token Health Check 결과를 정기 점검 (월 1회 자동)
3. ✅ output/ 폴더가 너무 커지면 .gitignore 주석 해제
4. ⏭ 한 달 운영 후 콘텐츠 톤/디자인 조정
5. ⏭ 인스타 인사이트 보고 어떤 주제가 반응 좋은지 SUBTOPIC_POOL 가중치 조정
