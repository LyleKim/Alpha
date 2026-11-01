# infra

플랫폼이 사용하는 IaC·배포 설정 모음입니다. 아직 실제 자원 정의는 없습니다.

| 경로 | 용도 | 사용 모듈 |
| --- | --- | --- |
| `terraform/gcp/` | GCP 목적지 앱·DB 인프라 | `provisioning` |
| `db_migration/terraform/` | CDC 실행 서버·네트워크·저장소 | `db_migration` |
| `db_migration/deployment/` | Kafka·Kafka Connect 실행·배포 설정 | `db_migration` |
| `db_migration/connectors/` | Debezium PostgreSQL Source·JDBC Sink 템플릿 | `db_migration` |

- 목적지 인프라와 CDC 인프라는 자원 소유 범위와 Terraform 상태를 **분리**합니다.
- 상태 파일(`*.tfstate`)과 실제 변수 파일(`*.tfvars`)은 커밋하지 않습니다. 예시는 `*.tfvars.example`로 둡니다.
- `.terraform.lock.hcl`은 커밋합니다.
