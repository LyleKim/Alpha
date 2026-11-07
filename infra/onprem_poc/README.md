# 온프렘 목적지 PoC

CDC 목적지를 "온프렘"으로 흉내 내는 한 호스트 구성입니다. 클라우드 목적지(Cloud SQL 등) 대신 이 PostgreSQL 로 복제하고 전환하는 흐름을 시험합니다. 운영용이 아닙니다.

- `postgres`: PostgreSQL 16 (`wal_level=logical`, `ssl=on` 자체 서명). `back` 네트워크(internal)에만 있어 밖에서 직접 붙을 수 없습니다.
- `cloudflared`: Cloudflare Tunnel. DB와 외부(`front`)를 잇는 유일한 컨테이너입니다. CDC 노드는 사이드카의 `cloudflared access tcp` 로 이 터널을 지나 DB에 붙습니다.
- `compose.was.yml`: 이후 단계용 WAS 컨테이너(선택). 가져온 이미지와 `.was.env` 가 필요합니다.

## 실행
1. `.env.example` 을 `.env` 로 복사하고 값을 채웁니다. `PG_PASSWORD` 는 직접 만든 비밀번호(예: `openssl rand -base64 24`)이고, `TUNNEL_TOKEN` 은 Cloudflare 터널 토큰입니다. 비워 두면 `docker compose` 가 시작을 막습니다. 예시 값으로 띄우지 마세요: Access 를 설정하기 전에는 호스트 이름과 DB 비밀번호만으로 인터넷에서 접속됩니다.
2. `certs/server.crt`, `certs/server.key` 를 만듭니다(자체 서명, 예: `openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=postgres" -keyout certs/server.key -out certs/server.crt`).
3. `docker compose up -d --wait` (PG 가 준비될 때까지 기다린 뒤 cloudflared 가 뜹니다)

## WAS 추가 (선택)
`compose.was.yml` 은 `compose.yml` 의 `back`·`front` 네트워크를 쓰므로 반드시 함께 지정합니다.

```
docker compose -f compose.yml -f compose.was.yml up -d
```

- 이미지: 원본 앱 이미지(ECR 의 `target-app`, 다이제스트로 고정)를 `linux/amd64` 로 가져와 `alpha-target-app:onprem-<다이제스트 앞 12자리>` 로 태그해 둡니다. 이 태그는 `compose.was.yml` 의 `image:` 와 같아야 합니다. 이미지 아카이브(`*.docker.tar`)는 git 에 올리지 않습니다.
- `.was.env`(git 제외)에 들어갈 키: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSSLMODE`, `APP_ENV`, `PORT`, `WORKER_SECRET`, `REQUIRE_WORKER_SECRET`. 값은 이 레포에 두지 않습니다.
- WAS 는 호스트의 `127.0.0.1:18081` 로만 공개됩니다.

## 알려진 한계
- 접근 보호(Cloudflare Access)는 따로 설정해야 합니다. 설정 전에는 호스트 이름과 DB 비밀번호만으로 접속됩니다.
- `cloudflared` 는 `2026.10.7` 로 고정했습니다. 올리려면 태그를 바꾸세요.
- 자체 서명 인증서라 `sslmode=require` 는 연결을 암호화만 하고 서버 인증서를 검증하지 않습니다(PoC 용). 검증이 필요하면 CA 를 배포하고 `verify-full` 을 쓰세요.
- 이 PR 은 compose 파일만입니다. 플랫폼 코드와는 연결되어 있지 않습니다(`db_migration` 의 `pass_onprem` 옵션과 사이드카는 별도).
