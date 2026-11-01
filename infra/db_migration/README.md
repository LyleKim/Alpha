# db_migration (infra)

`db_migration` 모듈이 사용하는 CDC 실행 환경 자산입니다.
CDC 실행 환경은 FastAPI와 별도로 동작하고, FastAPI는 이를 구축·제어합니다.

```
원본 DB → Debezium Source → Kafka → JDBC Sink → 목적지 DB
```

- `terraform/`: CDC 실행 서버·네트워크·저장소
- `deployment/`: Kafka·Kafka Connect 실행·배포 설정
- `connectors/`: 커넥터 설정 템플릿

CDC 서버를 어느 클라우드에 둘지는 아직 정하지 않았습니다 (합의 필요).
