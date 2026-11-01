# backend

클라우드 이전 플랫폼의 FastAPI 백엔드입니다.

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

- `GET /health`: API 프로세스 생존 확인 (클라우드·DB·Kafka 연결 상태와 무관)
- `GET /docs`: OpenAPI 문서

## 구조

- `app/main.py`: 앱 생성·라우터 등록
- `app/core/`: 공통 설정(`config.py`)·로그(`logging.py`). 업무 로직은 두지 않습니다.
- `app/features/<모듈>/`: 모듈별 구현. 각 폴더의 README에 책임·입출력·미정 사항이 있습니다.
- `tests/`: 테스트

## 규칙

- 기능 라우터는 실제 동작이 구현된 뒤에 `main.py`에 등록합니다. 미구현 기능의 가짜 성공 응답은 만들지 않습니다.
- 새 의존성(DB, 작업 큐, 인증, 에이전트 프레임워크 등)은 팀에서 합의한 뒤 추가합니다.
