# LINUX PC HANDOFF — dashboard 이미지 프록시 + LLM Server 반영

> 임시 전달 파일. **읽고 적용한 뒤 이 파일은 삭제**하세요.
> (Vision PC에서 작업한 내용을 git으로 넘기기 위한 노트)

## 무엇이 바뀌었나

`fea/llm-server` 브랜치에 두 가지가 추가됨:

1. **LLM Server 신규 구현** (`llm-server/`) — Vision 탐지 이벤트를 받아 MinIO 프레임을
   LLaVA로 요약 → `cs.llm.control.update` 발행. (Vision PC에서 e2e 검증 완료,
   main-server까지 도달 확인됨)
2. **dashboard MinIO 이미지 프록시** (`dashboard/dashboard_app.py`) — 탐지 카드에
   `thumb.jpg`가 LLM 요약과 함께 뜨도록 추가. **← 이게 Linux PC에서 검증할 대상.**

dashboard 변경 요약:
- `GET /image/<path:image_key>` 라우트 추가 → MinIO `get_object`를 `image/jpeg`로 스트리밍
- `image_key` 수신 시 `image_src = "/image/" + image_key` 자동 세팅
- `dashboard/requirements.txt`에 `minio>=7.2` 추가

## Linux PC에서 할 일

### 1. 코드 받기
```bash
git fetch origin
git checkout fea/llm-server      # 이미 이 브랜치면 생략
git pull origin fea/llm-server
```
> dev 등 다른 브랜치에서 dashboard를 돌린다면, fea/llm-server를 거기에 머지해야 반영됨.

### 2. 새 의존성 설치 (minio 추가됨)
```bash
pip install -r dashboard/requirements.txt
```

### 3. MinIO 환경변수 export (중요)
dashboard는 dotenv를 안 쓰고 `os.environ`을 직접 읽습니다. **`.env`는 git에 안 올라오므로**
실행 전 직접 export 해야 이미지 프록시가 동작합니다.
```bash
export MINIO_SECRET_KEY='<팀 MinIO 비밀번호>'   # 보안상 이 파일엔 값 미기재
# 기본값으로 충분한 것들 (필요 시에만 변경):
#   MINIO_ENDPOINT=localhost:9000   (이 PC는 이미 9000 터널 있음)
#   MINIO_ACCESS_KEY=minio_admin
#   MINIO_BUCKET=capstone2
#   MINIO_SECURE=false
```

### 4. 실행
```bash
cd dashboard && python dashboard_app.py     # http://127.0.0.1:5001
```
전제: main-server 실행 중 + NATS(4222)/MinIO(9000) 터널 up.

### 5. 검증
- 탐지를 한 번 발생시키고, dashboard 이벤트 카드에 **thumb.jpg 이미지가 표시**되는지 확인.
  - 라이브 이벤트: 이미지 + bbox 오버레이 + (잠시 뒤) LLM 요약까지
  - main-server `/events`에서 불러온 과거 이벤트: 이미지는 뜨지만 objects가 없어 bbox는 없음 (정상)
- 프록시 단독 확인:
  ```bash
  curl -I "http://127.0.0.1:5001/image/events/<event_id>/thumb.jpg"   # 200 + image/jpeg면 OK
  ```
- 안 뜨면 dashboard 콘솔 로그 확인 (503=minio 미설치, 404=fetch 실패/키 오류).

## 결과 회신
검증 결과(성공/이슈)를 Vision PC 쪽에 알려주면, 이슈는 거기서 수정합니다.
그리고 **이 파일은 삭제**하고 커밋하세요.
