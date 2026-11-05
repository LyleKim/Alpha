"""bastion.py: 가짜 ec2/ssm 클라이언트와 가짜 프로세스로 확인 (실제 AWS·프로세스 없음)."""

import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.features.assessment import bastion
from app.features.assessment.bastion import BastionError, BastionInfo, ensure_bastion, find_bastion, open_tunnel
from tests.assessment.fakes import FakeAwsError, FakeClient, FakeSession


def _inst(iid, hour, vpc="vpc-1"):
    return {"InstanceId": iid, "VpcId": vpc, "LaunchTime": datetime(2026, 1, 1, hour, tzinfo=timezone.utc)}


def _sess(instances, ping="Online"):
    ec2 = FakeClient({"describe_instances": {"Reservations": [{"Instances": instances}]}})
    ssm = FakeClient({"describe_instance_information": {"InstanceInformationList": [{"PingStatus": ping}]}})
    return FakeSession(ec2=ec2, ssm=ssm)


def test_find_none():
    assert find_bastion(_sess([]), "r", None) is None
    assert ensure_bastion(_sess([]), "r", None) == (None, "bastion 없음 (프로비저닝 미구현)")


def test_find_latest_and_filters():
    s = _sess([_inst("i-old", 1), _inst("i-new", 9)])
    info = find_bastion(s, "r", "vpc-1")
    assert info.instance_id == "i-new" and info.ssm_online
    filters = s.clients["ec2"].calls[0][1]["Filters"]
    assert {"Name": "tag:Purpose", "Values": ["alpha-assessment-bastion"]} in filters
    assert {"Name": "instance-state-name", "Values": ["running"]} in filters
    assert {"Name": "vpc-id", "Values": ["vpc-1"]} in filters
    s2 = _sess([_inst("i-1", 1)])
    find_bastion(s2, "r", None)
    assert all(f["Name"] != "vpc-id" for f in s2.clients["ec2"].calls[0][1]["Filters"])


def test_pagination():
    pages = iter([
        {"Reservations": [{"Instances": [_inst("i-a", 1)]}], "NextToken": "t"},
        {"Reservations": [{"Instances": [_inst("i-b", 5)]}]},
    ])
    ec2 = FakeClient({})
    ec2.describe_instances = lambda **kw: next(pages)
    ssm = FakeClient({"describe_instance_information": {"InstanceInformationList": [{"PingStatus": "Online"}]}})
    assert find_bastion(FakeSession(ec2=ec2, ssm=ssm), "r", None).instance_id == "i-b"


def test_not_online_and_client_error():
    info, why = ensure_bastion(_sess([_inst("i-1", 1)], ping="ConnectionLost"), "r", None)
    assert info is None and "SSM Online 아님" in why
    s = FakeSession(ec2=FakeClient({"describe_instances": FakeAwsError("UnauthorizedOperation")}))
    info, why = ensure_bastion(s, "r", None)
    assert info is None and "UnauthorizedOperation" in why and "secret-looking" not in why


# ---- open_tunnel ----
class FakeProc:
    def __init__(self, exit_code=None, err=b""):
        self.code, self.terminated, self.killed, self.pid = exit_code, False, False, 4242
        self.closed = []
        self.stderr = SimpleNamespace(read=lambda n=-1: err, close=lambda: self.closed.append("err"))
        self.stdout = SimpleNamespace(close=lambda: self.closed.append("out"))

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 0

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.code


class Creds:
    def get_frozen_credentials(self):
        return SimpleNamespace(access_key="AKIAFAKEKEY", secret_key="fakesecret", token="faketoken")


class CredSession(FakeSession):
    def get_credentials(self):
        return Creds()


INFO = BastionInfo("i-123", "vpc-1", None, True)
HOST = "db.example.amazonaws.com"


@pytest.fixture
def popen(monkeypatch):
    rec = {}
    monkeypatch.setattr(bastion.shutil, "which", lambda n: f"/bin/{n}")
    monkeypatch.setattr(bastion.time, "sleep", lambda s: None)

    def fake(cmd, **kw):
        rec["cmd"], rec["kw"], rec["proc"] = cmd, kw, rec.get("next") or FakeProc()
        return rec["proc"]

    monkeypatch.setattr(bastion.subprocess, "Popen", fake)
    rec["sigs"] = []

    def killpg(pid, sig):
        rec["sigs"].append((pid, sig))
        rec["proc"].terminated = True
        rec["proc"].code = 0

    monkeypatch.setattr(bastion.os, "killpg", killpg, raising=False)  # Windows 에도 없음
    return rec


def test_tunnel_ok(monkeypatch, popen):
    monkeypatch.setattr(bastion, "_listening", lambda p: not popen["proc"].terminated)
    with open_tunnel(CredSession(), "ap-northeast-2", INFO, HOST, 5432, local_port=15432) as hp:
        assert hp == ("localhost", 15432)
    cmd, kw = popen["cmd"], popen["kw"]
    assert cmd[:3] == ["aws", "ssm", "start-session"] and "i-123" in cmd
    assert cmd[-1] == f"host={HOST},portNumber=5432,localPortNumber=15432"
    assert kw["shell"] is False and popen["proc"].terminated
    env = kw["env"]
    assert set(env) <= {"PATH", "HOME", "LANG", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
                        "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}
    assert env["AWS_ACCESS_KEY_ID"] == "AKIAFAKEKEY"
    assert not any("AKIA" in c or "fakesecret" in c for c in cmd)


def test_tunnel_no_creds_in_env_for_fake_session(monkeypatch, popen):
    monkeypatch.setattr(bastion, "_listening", lambda p: not popen["proc"].terminated)
    with open_tunnel(FakeSession(), "ap-northeast-2", INFO, HOST, 5432):
        pass
    assert "AWS_ACCESS_KEY_ID" not in popen["kw"]["env"]


@pytest.mark.parametrize("host,port", [("a;rm -rf /", 5432), ("a b", 5432), ("", 5432), (HOST, 0), (HOST, 70000)])
def test_tunnel_rejects_injection(popen, host, port):
    with pytest.raises(BastionError):
        with open_tunnel(FakeSession(), "ap-northeast-2", INFO, host, port):
            pass
    assert "cmd" not in popen


def test_tunnel_missing_tools(monkeypatch):
    monkeypatch.setattr(bastion.shutil, "which", lambda n: None)
    with pytest.raises(BastionError, match="설치"):
        with open_tunnel(FakeSession(), "ap-northeast-2", INFO, HOST, 5432):
            pass


def test_tunnel_timeout_terminates(monkeypatch, popen):
    monkeypatch.setattr(bastion, "_listening", lambda p: False)
    with pytest.raises(BastionError, match="시간 초과"):
        with open_tunnel(FakeSession(), "ap-northeast-2", INFO, HOST, 5432, ready_timeout=0):
            pass
    assert popen["proc"].terminated


def test_tunnel_early_exit_no_secret_leak(monkeypatch, popen):
    popen["next"] = FakeProc(1, b"boom\nAKIAFAKEKEY leaked\nTargetNotConnected\nSecretAccessKey: x\n")
    monkeypatch.setattr(bastion, "_listening", lambda p: False)
    with pytest.raises(BastionError) as ei:
        with open_tunnel(FakeSession(), "ap-northeast-2", INFO, HOST, 5432):
            pass
    msg = str(ei.value)
    assert "TargetNotConnected" in msg and "AKIA" not in msg and "SecretAccessKey" not in msg


def test_stop_kills_group_even_if_proc_already_exited(monkeypatch, popen):
    # aws 가 먼저 죽었어도(poll != None) 자식 plugin 정리를 위해 그룹에 SIGTERM, SIGKILL 을 보낸다
    popen["next"] = FakeProc(1, b"boom")
    monkeypatch.setattr(bastion, "_listening", lambda p: False)
    with pytest.raises(BastionError):
        with open_tunnel(FakeSession(), "ap-northeast-2", INFO, HOST, 5432):
            pass
    import signal
    sigs = [s for _, s in popen["sigs"]]
    assert sigs == [signal.SIGTERM, getattr(signal, "SIGKILL", None)]
    assert popen["proc"].closed == ["out", "err"]  # PIPE 닫힘


@pytest.mark.parametrize("region", ["-x", "--profile", "r", "AP-northeast-2", "ap-northeast-2; ls", ""])
def test_tunnel_rejects_bad_region(popen, region):
    with pytest.raises(BastionError, match="리전"):
        with open_tunnel(FakeSession(), region, INFO, HOST, 5432):
            pass


def test_no_killpg_platform_terminates_then_kills(monkeypatch, popen):
    # Windows 처럼 killpg 가 없는 플랫폼: 그룹 신호 없이 terminate → kill, start_new_session 도 안 넘김
    monkeypatch.delattr(bastion.os, "killpg", raising=False)
    monkeypatch.setattr(bastion, "_listening", lambda p: not popen["proc"].terminated)
    with open_tunnel(FakeSession(), "ap-northeast-2", INFO, HOST, 5432, local_port=15432):
        pass
    assert "start_new_session" not in popen["kw"]
    assert popen["sigs"] == [] and popen["proc"].terminated and popen["proc"].killed
    assert popen["proc"].closed == ["out", "err"]
