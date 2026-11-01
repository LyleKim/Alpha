# terraform/gcp

GCP 목적지 앱·DB 인프라를 생성하는 Terraform 코드 자리입니다. `provisioning` 모듈이 실행합니다.

- 자원 정의는 아직 작성하지 않았습니다.
- CDC 인프라(`infra/db_migration/terraform/`)와 상태를 공유하지 않습니다.

## 미정 사항 (합의 필요)
- 목적지 자원 구성 (앱 실행 환경, DB 종류 등)
- 원격 상태(backend) 위치
- 변수·출력 규격 (`provisioning` 계약과 연결)
