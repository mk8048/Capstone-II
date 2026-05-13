# 팀원 개발 환경 세팅 가이드

본 문서는 **capstone-llm-cctv** 프로젝트 개발 환경을 본인 PC에 세팅하기 위한 가이드이다.
모든 팀원이 이 문서대로 진행하면 동일한 개발 환경이 갖춰진다.

---

# 📋 0. 작업 전 준비물

다음 정보를 main-server 담당자에게 받아야 한다.

| 항목 | 받는 방법 |
|------|----------| 
| VM 공인 IP | 담당자에게 직접 전달받음 |
| VM SSH 키 (`keypairsw.pem`) | 담당자에게 직접 전달받음 (USB 권장) |
| `.env` 파일 비밀번호 | 담당자에게 직접 전달받음 |
| GitHub repo 접근 권한 | 본인 GitHub 사용자명을 알려주면 collaborator로 등록 |

---

# 1. PowerShell 관리자 권한 실행

Windows 검색창에서 다음과 같이 진행한다.

```
PowerShell 검색 → 마우스 오른쪽 클릭 → 관리자 권한으로 실행
```

그 다음 아래 명령어를 입력한다.

```powershell
wsl --install -d Ubuntu
```

또는 기본 Ubuntu만 설치하려면 다음과 같이 입력한다.

```powershell
wsl --install
```

설치가 끝나면 **PC를 재부팅**한다.

---

# 2. Ubuntu 첫 실행

재부팅 후 Windows 시작 메뉴에서 **Ubuntu**를 검색해서 실행한다.

처음 실행하면 다음과 같이 계정을 만들라고 나온다.

```
Enter new UNIX username:
New password:
Retype new password:
```

예시:

```
username: capstone
password: 본인이 사용할 비밀번호
```

비밀번호 입력할 때 화면에 아무것도 안 보이는 것이 정상이다. 그냥 입력하고 Enter를 누르면 된다.

---

# 3. WSL2로 설치됐는지 확인

PowerShell에서 확인한다.

```powershell
wsl -l -v
```

정상이라면 다음과 같이 나와야 한다.

```
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

`VERSION`이 `2`이면 WSL2 설치가 완료된 것이다.

만약 `VERSION`이 `1`로 나오면 아래 명령어를 실행한다.

```powershell
wsl --set-version Ubuntu 2
```

앞으로 설치되는 배포판을 기본적으로 WSL2로 쓰려면 다음 명령어를 입력한다.

```powershell
wsl --set-default-version 2
```

---

# 4. Ubuntu 기본 업데이트

Ubuntu 터미널에서 아래 명령어를 실행한다.

```bash
sudo apt update && sudo apt upgrade -y
```

개발에 필요한 기본 패키지를 설치한다.

```bash
sudo apt install -y \
  git \
  curl \
  wget \
  vim \
  unzip \
  build-essential \
  python3 \
  python3-pip \
  python3-venv \
  postgresql-client \
  ffmpeg
```

설치 확인:

```bash
python3 --version
pip3 --version
git --version
```

---

# 5. Git 설정

Ubuntu 터미널에서 각자 본인 GitHub 계정 정보로 설정한다.

```bash
git config --global user.name "본인 이름"
git config --global user.email "본인 GitHub 이메일"
git config --global init.defaultBranch main
```

확인:

```bash
git config --global --list
```

---

# 6. SSH 키 생성 (GitHub용 + VM용)

## 6-1. GitHub용 SSH 키 만들기

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github -C "본인이름-pc"
```

비밀번호 묻는 부분은 빈 칸으로 두고 Enter를 3번 누른다.

공개키 확인:

```bash
cat ~/.ssh/github.pub
```

출력된 한 줄(`ssh-ed25519 AAAA...`)을 복사한다.

브라우저에서 다음 순서대로 진행한다.

1. github.com → 우상단 프로필 → **Settings**
2. 좌측 메뉴 → **SSH and GPG keys** → **New SSH key**
3. Title: `본인이름-pc`
4. Key: 위에서 복사한 공개키 붙여넣기
5. **Add SSH key**

## 6-2. VM 접속용 키 등록

main-server 담당자에게 받은 `keypairsw.pem`을 Windows의 Downloads 폴더에 둔 다음, WSL2로 복사한다.

```bash
mkdir -p ~/.ssh
cp /mnt/c/Users/<Windows사용자명>/Downloads/keypairsw.pem ~/.ssh/
chmod 400 ~/.ssh/keypairsw.pem
```

> `<Windows사용자명>`은 본인 Windows 사용자명으로 교체한다.

확인:

```bash
ls -l ~/.ssh/keypairsw.pem
# -r-------- 1 ... ← 권한 400이면 OK
```

---

# 7. SSH config 작성

```bash
vi ~/.ssh/config
```

`i`를 눌러 입력 모드로 진입한 후 다음 내용을 붙여넣는다.

```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github

Host capstone-vm
    HostName 210.109.82.57
    User ubuntu
    IdentityFile ~/.ssh/keypairsw.pem
    ServerAliveInterval 60
    ServerAliveCountMax 3

    LocalForward 5432 localhost:5432
    LocalForward 9000 localhost:9000
    LocalForward 9001 localhost:9001
    LocalForward 4222 localhost:4222
    LocalForward 8222 localhost:8222
    LocalForward 8000 localhost:8000
```

> VM IP가 다르면 담당자에게 받은 값으로 교체한다.

저장: `Esc` → `:wq` → Enter

권한 설정:

```bash
chmod 600 ~/.ssh/config
```

---

# 8. 연결 테스트

## 8-1. GitHub 연결

```bash
ssh -T git@github.com
```

다음 메시지가 뜨면 성공이다.

```
Hi <username>! You've successfully authenticated...
```

## 8-2. VM 연결 (포트 포워딩 포함)

```bash
ssh capstone-vm
```

`ubuntu@host-...:~$` 프롬프트가 뜨면 성공이다. **확인 후 즉시 종료**한다.

```bash
exit
```

---

# 9. 포트 충돌 점검

본인 PC에 이미 PostgreSQL이나 MinIO가 깔려서 동작 중이면 SSH 터널이 충돌한다.

## 9-1. 점유 확인

```bash
ss -tlnp | grep -E '5432|9000|9001|4222|8000'
```

뭔가 출력되면 해당 포트가 다른 프로세스에 의해 사용 중이다.

## 9-2. 해결

### Windows에 PostgreSQL이 깔려 있는 경우

Windows CMD **관리자 권한**으로 실행한다.

```cmd
net stop postgresql-x64-XX
```

(`XX`는 본인 PostgreSQL 버전: 14, 15, 16, 17, 18)

자동 시작 비활성화:

```cmd
sc config postgresql-x64-XX start=disabled
```

### Windows에 MinIO를 띄워둔 경우

```cmd
taskkill /F /IM minio.exe
```

### 기존 SSH 터널이 떠 있는 경우

```bash
ps aux | grep "ssh -fN"
pkill -f "ssh -fN capstone-vm"
```

---

# 10. 프로젝트 폴더 만들기

프로젝트는 **WSL 내부에 두는 것이 좋다.**

```bash
mkdir -p ~/projects
cd ~/projects
git clone git@github.com:<org>/Capstone-II.git
cd Capstone-II
```

> `<org>`는 실제 GitHub 조직/계정명으로 교체한다. SSH 방식이라 비밀번호를 묻지 않는다.

확인:

```bash
ls -la
# docker-compose.yml, .env.example, docs/, infra/ 가 보여야 한다.
```

주의할 점:

```
추천:   ~/projects/Capstone-II
비추천: /mnt/c/Users/...
```

`/mnt/c` 아래는 Windows 파일시스템이라 Python, Node 개발 시 속도가 느려진다.

---

# 11. `.env` 파일 만들기

```bash
cp .env.example .env
vi .env
```

`i`로 입력 모드로 진입한 후, main-server 담당자에게 받은 비밀번호 부분만 수정한다.

```bash
POSTGRES_USER=capstone2
POSTGRES_PASSWORD=<받은_비밀번호>
POSTGRES_DB=capstone2
POSTGRES_PORT=5432

MINIO_ROOT_USER=minio_admin
MINIO_ROOT_PASSWORD=<받은_비밀번호>
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

NATS_PORT=4222
NATS_MONITOR_PORT=8222
```

저장: `Esc` → `:wq`

> ⚠️ **`.env`는 절대 git에 커밋하지 않는다.** `.gitignore`에 등록되어 자동으로 제외된다.

---

# 12. SSH 터널 띄우기 + 인프라 접속 테스트

## 12-1. SSH 터널 백그라운드로 띄우기

```bash
ssh -fN capstone-vm
```

> `Address already in use` 에러가 뜨면 9-2의 포트 충돌 점검을 다시 진행한다.

## 12-2. 터널 작동 확인

```bash
nc -zv localhost 5432
nc -zv localhost 9001
nc -zv localhost 4222
```

각각 `succeeded!`가 나오면 OK이다.

## 12-3. PostgreSQL 접속

```bash
psql -h localhost -p 5432 -U capstone2 -d capstone2 -c "\dt"
# 비밀번호 입력
```

테이블 4개가 보여야 한다.

- cameras
- detected_objects
- detection_events
- llm_analysis

## 12-4. MinIO 콘솔 (브라우저)

본인 PC 브라우저에서 다음 주소로 접속한다.

```
http://localhost:9001
```

로그인 정보:

- Username: `minio_admin`
- Password: `.env`의 `MINIO_ROOT_PASSWORD` 값

MinIO 대시보드가 뜨면 성공이다.

---

# 13. VS Code에서 WSL 연결

Windows에 VS Code를 설치한 뒤, VS Code 확장에서 아래를 설치한다.

```
WSL  (Microsoft 공식)
```

Ubuntu 터미널에서 프로젝트 폴더로 이동한 다음 실행한다.

```bash
cd ~/projects/Capstone-II
code .
```

처음 실행하면 VS Code가 WSL 서버를 자동으로 설치하고, 이후부터는 WSL Ubuntu 환경에서 바로 개발할 수 있다.

좌측 하단에 `WSL: Ubuntu` 표시가 있는지 확인한다.

## 추천 확장

- Python
- Pylance
- Docker
- GitLens
- DotENV

---

# 14. 설치가 안 될 때 확인할 것

## 14-1. Windows 버전 확인

`Win + R`을 누르고 다음을 입력한다.

```
winver
```

Windows 10이면 **버전 2004 이상, 빌드 19041 이상**이어야 `wsl --install` 명령을 사용할 수 있다.

## 14-2. 설치 가능한 Ubuntu 목록 확인

```powershell
wsl --list --online
```

특정 버전 설치:

```powershell
wsl --install -d Ubuntu-22.04
```

## 14-3. 0.0%에서 멈추는 경우

웹 다운로드 방식 설치를 시도한다.

```powershell
wsl --install --web-download -d Ubuntu
```

---

# 15. 자주 쓰는 명령어 치트시트

## SSH 터널 관리

```bash
# 터널 띄우기
ssh -fN capstone-vm

# 터널 떠 있는지 확인
ps aux | grep "ssh -fN"

# 터널 종료
pkill -f "ssh -fN capstone-vm"
```

## Git

```bash
git status              # 변경사항 확인
git add .               # 전체 stage
git commit -m "메시지"   # 커밋
git push                # 푸시
git pull                # 최신 받기
git checkout <브랜치명>  # 브랜치 전환
git branch              # 현재 branch 확인 (현재 branch 앞에 `*` 표시가 붙음)
```

## Docker (VM에서만 사용 — 본인 PC에서는 안 함)

```bash
docker compose ps                       # 컨테이너 상태
docker compose logs <서비스명>           # 로그 확인
docker compose restart <서비스명>        # 재시작
docker compose down                     # 정지
docker compose up -d                    # 시작
```

## PostgreSQL

```bash
psql -h localhost -p 5432 -U capstone2 -d capstone2

# psql 안에서
\dt           # 테이블 목록
\d cameras    # 테이블 구조
\q            # 종료
```

---

# 16. 브랜치 작업 규칙

## 16-1. 브랜치 구조

```
main                    ← 안정 버전 (시연/제출용)
└── dev                 ← 통합 개발 브랜치
    ├── fea/vision-server     ← Vision 담당
    ├── fea/main-server       ← Main Server 담당
    ├── fea/llm-server        ← LLM 담당
    └── fea/dashboard         ← Dashboard 담당
```

모든 브랜치는 미리 생성되어 있다. 각자 본인 영역의 `feature/*` 브랜치로 전환해서 작업한다.

## 16-2. 담당별 브랜치명

| 담당 | 브랜치명 |
|------|---------|
| Vision Server | `fea/vision-server` |
| Main Server   | `fea/main-server`   |
| LLM Server    | `fea/llm-server`    |
| Dashboard     | `fea/dashboard`     |

## 16-3. 본인 브랜치로 전환 (clone 직후 1회)

```bash
# 원격 브랜치 목록 가져오기
git fetch --all

# 본인 브랜치로 전환 (원격 브랜치로부터 자동 추적)
git checkout fea/<본인영역>
```

## 16-4. 터미널 프롬프트에 현재 브랜치 표시 (선택)

매번 `git branch`로 현재 브랜치를 확인하기 번거로우면 프롬프트에 자동 표시되도록 설정한다.

`~/.bashrc` 끝에 다음 내용을 추가한다.

```bash
vi ~/.bashrc
```

파일 맨 아래에 `i`로 입력 모드 진입 후 붙여넣는다.

​```bash
parse_git_branch() {
    git branch 2>/dev/null | grep '^*' | sed 's/* //'
}
PS1='\u@\h:\w\[\033[33m\] $(parse_git_branch)\[\033[0m\]\$ '
​```

저장: `Esc` → `:wq`

적용:

```bash
source ~/.bashrc
```

이후 프롬프트가 다음과 같이 표시된다.

```
ubuntu@ubuntu:~/projects/Capstone-II fea/main-server$
```

## 16-5. 평소 작업 흐름
자신이 작업하고 있는 경로에서 `code .` 명령어를 입력 후 vscode를 실행하여 vscode 내에서 작업 및 git push & pull을 진행한다.
아래 명령어는 CLI 환경에서의 git 명령어들이다.

```bash
# 1. 작업 시작 전, dev의 최신 변경 받기
git checkout dev
git pull

# 2. 본인 브랜치로 돌아가서 dev 변경 반영
git checkout feature/<본인영역>
git merge dev

# 3. 작업 → 커밋 → 푸시
git add .
git commit -m "메시지"
git push

# 4. 어느 정도 완성되면 dev에 머지
git checkout dev
git pull
git merge feature/<본인영역>
git push
```

## 16-6. 규칙

- `main` 브랜치에 직접 push 금지 (시연 직전에만 머지)
- 본인 영역 외 폴더 수정 시 팀원들에게 사전 공유
- 인프라 파일(`docker-compose.yml`, `init.sql`, `.env.example` 등) 수정은 main-server 담당자와 협의
- 커밋 메시지는 영문 또는 한글 자유. 한 줄로 간결하게 작성
- 충돌(conflict) 발생 시 본인이 해결 후 push / 해결 어려울 시 팀원들과 공유 및 논의

## 16-7. 커밋 메시지 권장 형식

```
<타입>: <간단 설명>

예시:
feat: /events 엔드포인트 추가
fix: NATS 구독자 재연결 버그 수정
docs: onboarding 문서 업데이트
chore: 의존성 버전 업데이트
refactor: DB 모델 구조 정리
```

타입 종류:
- `feat`: 새 기능
- `fix`: 버그 수정
- `docs`: 문서 변경
- `chore`: 빌드/설정 등 잡일
- `refactor`: 기능 변경 없는 코드 정리
- `test`: 테스트 코드

---

# 📅 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-05-13 | WSL2 + SSH + 인프라 접속 + 브랜치 규칙 통합 (초안) |
