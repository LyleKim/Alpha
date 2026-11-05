"""refs: db_admin_ref → 자격 증명. 비밀번호 센티널이 사유·예외에 새지 않는지도 확인합니다."""

import json
import sys
import types

import pytest

from app.features.assessment import refs

PW = "SENTINEL-pw-9f3a"


def _secrets(monkeypatch, fn):
    m = types.ModuleType("app.core.secrets")
    m.resolve = fn
    monkeypatch.setitem(sys.modules, "app.core.secrets", m)


def _clean(creds, why):
    assert PW not in repr(why)
    return creds, why


def test_secret_dict_and_json_and_username_alias(monkeypatch):
    _secrets(monkeypatch, lambda r: {"user": "admin", "password": PW})
    assert refs.resolve_db_admin("secret://a") == ({"user": "admin", "password": PW}, None)
    _secrets(monkeypatch, lambda r: json.dumps({"username": "u", "password": PW}))
    assert refs.resolve_db_admin("secret://a") == ({"user": "u", "password": PW}, None)


def test_secret_missing_key_has_no_secret(monkeypatch):
    _secrets(monkeypatch, lambda r: {"user": "admin"})
    c, why = _clean(*refs.resolve_db_admin("secret://a"))
    assert c is None and "password" in why


def test_secret_exceptions_only_class_name(monkeypatch):
    def boom(r):
        raise KeyError(PW)
    _secrets(monkeypatch, boom)
    c, why = _clean(*refs.resolve_db_admin("secret://a"))
    assert c is None and "KeyError" in why
    _secrets(monkeypatch, lambda r: "not json " + PW)
    c, why = _clean(*refs.resolve_db_admin("secret://a"))
    assert c is None and "JSONDecodeError" in why


def test_secret_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "app.core.secrets", None)  # import 시 ImportError
    c, why = refs.resolve_db_admin("secret://a")
    assert c is None and "미구현" in why


def test_env_ok_empty_bad_prefix(monkeypatch):
    monkeypatch.setenv("SRC_USER", "admin")
    monkeypatch.setenv("SRC_PASSWORD", PW)
    assert refs.resolve_db_admin("env://SRC") == ({"user": "admin", "password": PW}, None)
    monkeypatch.setenv("SRC_PASSWORD", "")
    c, why = _clean(*refs.resolve_db_admin("env://SRC"))
    assert c is None and "SRC_PASSWORD" in why and "SRC_USER" not in why
    c, why = refs.resolve_db_admin("env://src-x")
    assert c is None and "PREFIX" in why


@pytest.mark.parametrize("ref", [None, "", "plain", "ssm://x"])
def test_bad_refs(ref):
    c, why = refs.resolve_db_admin(ref)
    assert c is None and why


class FakeSM:
    def __init__(self, pages, secret=None, exc=None):
        self.pages, self.secret, self.exc, self.got = pages, secret, exc, None

    def list_secrets(self, **kw):
        i = int(kw.get("NextToken", 0))
        out = {"SecretList": [{"Name": n} for n in self.pages[i]]}
        if i + 1 < len(self.pages):
            out["NextToken"] = str(i + 1)
        return out

    def get_secret_value(self, SecretId):
        if self.exc:
            raise self.exc
        self.got = SecretId
        return {"SecretString": json.dumps(self.secret)}


class FakeSession:
    def __init__(self, sm):
        self.sm = sm

    def client(self, name, region_name=None):
        assert name == "secretsmanager"
        return self.sm


SEC = {"username": "admin", "password": PW, "dbInstanceIdentifier": "db-1"}


def test_asm_one_candidate_across_pages():
    sm = FakeSM([[], ["rds-db-credentials/db-X/a"]], SEC)
    c, why = refs.lookup_db_admin_from_asm(FakeSession(sm), "db-X", "db-1")
    assert (c, why) == ({"user": "admin", "password": PW}, None)
    assert sm.got == "rds-db-credentials/db-X/a"


@pytest.mark.parametrize("pages", [[[]], [["a"], ["b"]]])
def test_asm_zero_or_many(pages):
    c, why = _clean(*refs.lookup_db_admin_from_asm(FakeSession(FakeSM(pages, SEC)), "db-X", "db-1"))
    assert c is None and "후보" in why


def test_asm_instance_mismatch():
    sm = FakeSM([["n"]], SEC)
    c, why = _clean(*refs.lookup_db_admin_from_asm(FakeSession(sm), "db-X", "other"))
    assert c is None and "다름" in why


def test_asm_client_error_code_only():
    class CE(Exception):
        response = {"Error": {"Code": "AccessDenied", "Message": PW}}
    sm = FakeSM([["n"]], SEC, exc=CE(PW))
    c, why = _clean(*refs.lookup_db_admin_from_asm(FakeSession(sm), "db-X", "db-1"))
    assert c is None and "CE" in why and "AccessDenied" in why


def test_db_admin_for_gate(monkeypatch):
    sm = FakeSM([["n"]], SEC)
    s = FakeSession(sm)
    monkeypatch.setenv("SRC_USER", "")  # ref 가 있고 틀리면 폴백하지 않음
    c, why = refs.db_admin_for("env://SRC", s, "db-X", "db-1", allow_asm_fallback=True)
    assert c is None and sm.got is None
    c, why = refs.db_admin_for(None, s, "db-X", "db-1")
    assert c is None and "db_admin_ref 없음" in why and sm.got is None
    c, why = refs.db_admin_for(None, s, "db-X", "db-1", allow_asm_fallback=True)
    assert c == {"user": "admin", "password": PW}
