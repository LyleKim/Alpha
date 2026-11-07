from types import SimpleNamespace

from app.features.workflows import runners, target_adapters
from app.features.workflows.schemas import MigrationRequest, TargetInfraConfig
from app.features.provisioning.onprem import service
from app.features.db_migration.schemas import DbMigrationInput

SOURCE = {
    "account_id": "123456789012",
    "region": "ap-northeast-2",
    "db": {"host": "rds.internal", "database": "postgres"},
    "network": {
        "vpc_id": "vpc-test",
        "cidr": "172.31.0.0/16",
        "route_table_ids": ["rtb-test"],
    },
    "app": {"db_user": "app"},
    "tables": ["public.work_items", "alpha_cdc.cutover_marker"],
    "credentials_ref": {"cloud": "secret://aws", "db_admin": "secret://admin"},
}
TARGET = {
    "cloud": "onprem",
    "region": "local",
    "project_id": None,
    "network": {},
    "db": {
        "instance": "local",
        "private_ip": "127.0.0.1",
        "port": 15432,
        "database": "appdb",
    },
    "app": {"url": None, "db_user": "app"},
    "credentials_ref": {"cloud": "secret://config", "admin": "secret://admin"},
}


def test_registered_adapter_forwards_existing_arguments_and_reference(monkeypatch):
    called = {}
    monkeypatch.setattr(
        service, "provision", lambda **kw: called.update(kw) or {"target": TARGET}
    )
    cfg = TargetInfraConfig(
        provider="onprem", extra_params={"onprem_config_ref": "secret://config"}
    )
    request = MigrationRequest(
        service_name="app", aws_region="ap-northeast-2", target_infra=cfg
    )
    adapter = target_adapters.adapter_for(request)
    assert adapter.provider == "onprem"
    assert adapter.provision("run-1", {}, cfg, None) == {"target": TARGET}
    assert called["config_ref"] == "secret://config"


def test_runner_passes_target_unchanged_and_selects_onprem_vpn(monkeypatch):
    from app.features.db_migration import service as db_service

    captured = {}

    def run(inp, ctx):
        captured.update(inp)
        DbMigrationInput.model_validate(inp)
        return {"state": "streaming", "phase": "streaming", "job_id": "run_1"}

    monkeypatch.setattr(db_service, "run", run)
    monkeypatch.setattr(runners, "_agent_is_simulated", lambda: False)
    request = MigrationRequest(
        service_name="app",
        aws_region="ap-northeast-2",
        target_infra={
            "provider": "onprem",
            "extra_params": {"onprem_config_ref": "secret://config"},
        },
    )
    run = SimpleNamespace(
        run_id="run-1",
        request=request,
        outputs={"planning": {"source": SOURCE}, "provisioning": {"target": TARGET}},
    )
    result = runners.run_db_migration(run, None, poll_interval_s=0.001, timeout_s=1)
    assert result["state"] == "streaming"
    assert captured["target"] == TARGET
    assert captured["options"] == {"pass_onprem": True}
    assert captured["source"]["tables"] == ["public.work_items"]
