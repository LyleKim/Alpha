"""앱이 쓰는 DB 이름(PGDATABASE) 보조 힌트. app.py 와 별개의 보조 힌트입니다.

ECS 읽기 전용 호출(ListClusters/ListServices/DescribeServices/DescribeTaskDefinition)로
태스크 정의 컨테이너의 평문 `environment` 중 `PGHOST == db_host` 인 컨테이너의 `PGDATABASE` 만 읽습니다.
`secrets` 와 다른 환경변수 값은 읽지도 반환하지도 않습니다.
조회 실패는 전부 삼키고 None 을 돌려줍니다 (ECS 실패는 app.py 가 자기 gap 으로 알리므로 중복 gap 을 만들지 않음).
"""

from __future__ import annotations

from typing import Any

MAX_CLUSTERS = 5
MAX_SERVICES = 50


def pg_database_hint(
    session: Any, region: str, db_host: str | None,
    ecs_cluster: str | None = None, ecs_service: str | None = None,
) -> str | None:
    """PGHOST 가 db_host 인 컨테이너의 PGDATABASE. 없거나 서로 다른 값이 둘 이상이면 None."""
    if not db_host:
        return None
    try:
        ecs = session.client("ecs", region_name=region)
        clusters = [ecs_cluster] if ecs_cluster else ecs.list_clusters().get("clusterArns", [])[:MAX_CLUSTERS]
        found: set[str] = set()
        for cluster in clusters:
            if ecs_service:
                services = [ecs_service]
            else:
                services = ecs.list_services(cluster=cluster, maxResults=MAX_SERVICES).get("serviceArns", [])[:MAX_SERVICES]
            for i in range(0, len(services), 10):  # DescribeServices 는 한 번에 10개까지
                res = ecs.describe_services(cluster=cluster, services=services[i:i + 10])
                for svc in res.get("services", []):
                    task = ecs.describe_task_definition(taskDefinition=svc["taskDefinition"]).get("taskDefinition", {})
                    for c in task.get("containerDefinitions", []):
                        env = {e.get("name"): e.get("value") for e in c.get("environment") or []}
                        if env.get("PGHOST") == db_host and env.get("PGDATABASE"):
                            found.add(env["PGDATABASE"])
    except Exception:  # ClientError·BotoCoreError 등 전부: 보조 힌트라 조용히 포기
        return None
    return found.pop() if len(found) == 1 else None
