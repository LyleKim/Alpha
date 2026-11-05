"""app_hint.py: 가짜 ECS 클라이언트로 확인 (AWS 호출 없음). 호스트는 예시 값입니다."""

from app.features.assessment import app_hint

from .fakes import FakeAwsError, FakeClient, FakeSession

HOST = "db-example.abcdefghijkl.ap-northeast-2.rds.amazonaws.com"
PW = "PW-SENTINEL-9f3a"


def _env(host=HOST, db="appdb"):
    return [{"name": "PGHOST", "value": host}, {"name": "PGDATABASE", "value": db},
            {"name": "PGPASSWORD", "value": PW}]


def _sess(containers, services=("arn:svc/a",), **extra):
    task = {"taskDefinition": {"containerDefinitions": containers}}
    ecs = FakeClient({
        "list_clusters": {"clusterArns": ["arn:cluster/c"]},
        "list_services": {"serviceArns": list(services)},
        "describe_services": {"services": [{"taskDefinition": "td:1"} for _ in services]},
        "describe_task_definition": task, **extra,
    })
    return FakeSession(ecs=ecs), ecs


def test_hint_found():
    s, _ = _sess([{"environment": _env()}])
    assert app_hint.pg_database_hint(s, "ap-northeast-2", HOST) == "appdb"


def test_other_host_or_no_host_is_none():
    s, _ = _sess([{"environment": _env(host="other.example.com")}])
    assert app_hint.pg_database_hint(s, "ap-northeast-2", HOST) is None
    assert app_hint.pg_database_hint(s, "ap-northeast-2", None) is None


def test_two_different_values_is_none():
    s, _ = _sess([{"environment": _env(db="a")}, {"environment": _env(db="b")}])
    assert app_hint.pg_database_hint(s, "ap-northeast-2", HOST) is None


def test_same_value_twice_ok():
    s, _ = _sess([{"environment": _env()}, {"environment": _env()}])
    assert app_hint.pg_database_hint(s, "ap-northeast-2", HOST) == "appdb"


def test_secrets_field_ignored():
    c = {"environment": [{"name": "PGHOST", "value": HOST}],
         "secrets": [{"name": "PGDATABASE", "valueFrom": "arn:secret:x"}]}
    s, _ = _sess([c])
    assert app_hint.pg_database_hint(s, "ap-northeast-2", HOST) is None


def test_ecs_error_swallowed():
    s = FakeSession(ecs=FakeClient({"list_clusters": FakeAwsError("AccessDenied")}))
    assert app_hint.pg_database_hint(s, "ap-northeast-2", HOST) is None


def test_given_cluster_service_skips_listing_and_no_password_returned():
    s, ecs = _sess([{"environment": _env()}])
    out = app_hint.pg_database_hint(s, "ap-northeast-2", HOST, "arn:cluster/c", "arn:svc/a")
    assert out == "appdb" and PW not in out
    assert [n for n, _ in ecs.calls] == ["describe_services", "describe_task_definition"]


def test_limits():
    s, ecs = _sess([{"environment": _env()}], services=[f"arn:svc/{i}" for i in range(80)])
    app_hint.pg_database_hint(s, "ap-northeast-2", HOST)
    described = sum(len(k["services"]) for n, k in ecs.calls if n == "describe_services")
    assert described == app_hint.MAX_SERVICES
