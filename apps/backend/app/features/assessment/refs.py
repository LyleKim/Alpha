"""db_admin_ref(원본 RDS 마스터 계정 이름표) → PG 접속용 자격 증명.

- `secret://…`(core/secrets) 와 `env://PREFIX`(PREFIX_USER/PREFIX_PASSWORD) 를 지원합니다. 환경변수는 읽기만 합니다.
- 비밀번호는 반환 값(자격 증명 dict)에만 있고 사유 문장·예외·로그에는 절대 넣지 않습니다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.features.assessment.aws import error_code

Creds = dict[str, str]
Result = tuple[Creds | None, str | None]

_PREFIX = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _from_mapping(data: Any) -> Result:
    if not isinstance(data, dict):
        return None, "DB 관리자 이름표의 값이 JSON 객체가 아님"
    user = data.get("user") or data.get("username")
    password = data.get("password")
    missing = [k for k, v in (("user", user), ("password", password)) if not v]
    if missing:
        return None, f"DB 관리자 이름표의 값에 키가 없음: {missing}"
    return {"user": str(user), "password": str(password)}, None


def resolve_db_admin(ref: str | None) -> Result:
    """(자격 증명, 실패 사유). 사유는 gaps 에 넣을 한국어 한 문장이며 비밀 값을 담지 않습니다."""
    if not ref or not isinstance(ref, str):
        return None, "db_admin_ref 가 비어 있음"
    if ref.startswith("secret://"):
        try:
            from app.core.secrets import resolve  # 지연 import: 미구현 환경에서도 모듈이 로드되게
        except ImportError:
            return None, "DB 관리자 이름표를 풀 수 없음 (core/secrets 미구현)"
        try:
            data = resolve(ref)
            if isinstance(data, str):
                data = json.loads(data)
        except Exception as e:  # 메시지에 값이 섞일 수 있어 클래스명만 남깁니다
            return None, f"DB 관리자 이름표를 풀지 못함: {type(e).__name__}"
        return _from_mapping(data)
    if ref.startswith("env://"):
        prefix = ref[len("env://"):]
        if not _PREFIX.match(prefix):
            return None, "env:// 이름표의 PREFIX 형식이 올바르지 않음 (대문자·숫자·밑줄만 허용)"
        names = (f"{prefix}_USER", f"{prefix}_PASSWORD")
        empty = [n for n in names if not os.environ.get(n)]
        if empty:
            return None, f"환경변수가 설정되지 않음: {empty}"
        return {"user": os.environ[names[0]], "password": os.environ[names[1]]}, None
    return None, "지원하지 않는 db_admin_ref 형식 (secret:// 또는 env:// 만 허용)"


def lookup_db_admin_from_asm(
    session: Any,
    db_resource_id: str | None,
    instance_id: str | None,
    secret_id: str | None = None,
) -> Result:
    """개발 전용 폴백: RDS 가 만든 Secrets Manager 시크릿에서 마스터 계정을 찾습니다(읽기 전용, 환경변수 미사용)."""
    if not secret_id and not db_resource_id:
        return None, "secret_id 또는 db_resource_id 가 없어 시크릿을 찾을 수 없음"
    try:
        sm = session.client("secretsmanager", region_name=None)
        if not secret_id:
            prefix = f"rds-db-credentials/{db_resource_id}/"
            names: list[str] = []
            kwargs: dict[str, Any] = {"Filters": [{"Key": "name", "Values": [prefix]}]}
            while True:
                page = sm.list_secrets(**kwargs)
                names += [s["Name"] for s in page.get("SecretList", [])]
                if not page.get("NextToken"):
                    break
                kwargs["NextToken"] = page["NextToken"]
            if len(names) != 1:
                return None, f"{prefix} 시크릿 후보가 {len(names)}개라 하나로 정할 수 없음"
            secret_id = names[0]
        raw = sm.get_secret_value(SecretId=secret_id).get("SecretString")
    except Exception as e:  # ClientError·BotoCoreError 등: 본문 대신 클래스명+코드만
        return None, f"Secrets Manager 호출 실패: {type(e).__name__} {error_code(e)}"
    if not raw:
        return None, "SecretString 이 없음 (binary 시크릿은 지원 안 함)"
    try:
        data = json.loads(raw)
    except ValueError:
        return None, "SecretString 이 JSON 이 아님"
    if not isinstance(data, dict):
        return None, "SecretString JSON 이 객체가 아님"
    sec_inst = data.get("dbInstanceIdentifier")
    if instance_id and sec_inst and instance_id != sec_inst:
        return None, "시크릿의 dbInstanceIdentifier 가 대상 인스턴스와 다름"
    return _from_mapping(data)


def db_admin_for(
    ref: str | None,
    session: Any,
    db_resource_id: str | None,
    instance_id: str | None,
    allow_asm_fallback: bool = False,
) -> Result:
    """ref 가 있으면 그것만 씁니다(틀려도 폴백 금지). ref 가 없고 허용된 때만 ASM 폴백."""
    if ref:
        return resolve_db_admin(ref)
    if allow_asm_fallback:
        return lookup_db_admin_from_asm(session, db_resource_id, instance_id)
    return None, "db_admin_ref 없음 (ASM 폴백은 개발 전용이라 꺼져 있음)"
