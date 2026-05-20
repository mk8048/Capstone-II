# Dashboard / NATS 테스트 정리

## 현재 구현된 파일

### `dashboard_app.py`
- Flask 기반 대시보드 웹 앱
- NATS 구독자 역할 수행
- 기본 NATS URL: `nats://127.0.0.1:4222`
- 수신 토픽:
  - `cs.vision.control.detected`
  - `cs.llm.control.update`
- 수신 메시지를 메모리에 보관하고 화면에 실시간 표시
- MediaMTX 스트림 URL 입력 폼 제공
- NATS 연결 상태를 화면에 표시

### `send_nats_test.py`
- 테스트용 NATS 메시지 발행 스크립트
- 로컬 NATS에 메시지 발행 후 `dashboard_app.py`가 수신하도록 설계
- 실행 시 `cs.vision.control.detected` 메시지 전송

## 지금까지 진행한 흐름

1. 로컬에서 NATS가 올라와 있는지 확인
   - `Test-NetConnection -ComputerName 127.0.0.1 -Port 4222`
   - `TcpTestSucceeded : True`가 되어야 함

2. `dashboard_app.py` 실행
   - `cd C:\cs\Capstone-II\dashboard`
   - `python dashboard_app.py`
   - 브라우저에서 `http://127.0.0.1:5001/` 열기
   - 페이지 상단에 `NATS 상태: connected` 확인

3. `send_nats_test.py`로 테스트 메시지 발행
   - 같은 폴더에서 `python send_nats_test.py`
   - 페이지 새로고침 후 메시지 표시 확인

4. 현재 확인된 결과
   - NATS 연결 성공
   - 테스트 메시지 발행 후 대시보드에 표시됨
   - `keypairsw.pem`은 SSH 로그인 키이며, 로컬 NATS와 직접 관련 없음

## 중요한 점
- 현재 테스트는 로컬 NATS 서버(`127.0.0.1:4222`)를 대상으로 함.
- 팀 공통 NATS를 사용하려면 `NATS_URL`을 VM의 공통 주소로 변경해야 함.

## `send_nats_test.py` 예시 메시지

```python
msg = {
    "event_id": "evt_test_002",
    "camera_id": "cam01",
    "event_type": "person_detected",
    "source": "vision",
    "timestamp": "2026-05-19T12:00:00+09:00",
    "data": {
        "object_count": 1,
        "max_confidence": 0.88,
        "image_key": "events/test.jpg",
        "objects": [
            {
                "class_name": "person",
                "confidence": 0.88,
                "bbox": [100, 120, 80, 180],
                "track_id": None,
            }
        ],
    },
}
``` 해당식으로 수정 가능 

## 앞으로 할 것

- 실제 Vision 서버가 보내는 메시지 토픽과 스키마에 맞게 메시지 파이프라인 확장
- MediaMTX 스트림 URL을 실제 영상 소스로 연결
- 대시보드에 메시지 필터/요약 기능 추가
- 실시간성 확인 가능하도록 추가적인 기능 보안 필요

---
