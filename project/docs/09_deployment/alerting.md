# P1-3：可观测性告警（health + metrics）

- 文档路径：`project/docs/09_deployment/alerting.md`
- 最后更新：2026-08-19

## 1. 本地门禁脚本

```bash
cd project/code/python
python scripts/check_alerts.py
# 或指定 API
API_BASE=http://127.0.0.1:8080 python scripts/check_alerts.py
```

检查项：

- `/api/health` 非 503 degraded（核心依赖 vector + state 须 ok）
- `/metrics` 中 `dependency_up{name="vector_store|knowledge_graph|state_store"}` 不为 0

退出码 0 = 无告警；1 = 存在告警（可接 cron / CI）。

## 2. Prometheus 规则

示例规则：`project/code/prometheus/alerts.yml`

- `AgentHubDependencyDown` — `dependency_up == 0`
- `AgentHubHigh5xxRate` — HTTP 5xx 比例

Scrape 配置示例：

```yaml
scrape_configs:
  - job_name: agenthub
    static_configs:
      - targets: ["api:8080"]
    metrics_path: /metrics
```

Health 黑盒探测（可选）：

```yaml
  - job_name: agenthub-health
    metrics_path: /api/health
    static_configs:
      - targets: ["api:8080"]
```

## 3. 验收清单

- [ ] `check_alerts.py` 在依赖正常时 exit 0
- [ ] stop Chroma 后 `check_alerts.py` exit 1（或 health 503）
- [ ] Prometheus 能 scrape `/metrics` 并加载 `alerts.yml`

## 4. 仍缺（下一版）

- Alertmanager 路由 / on-call
- 业务 SLO 与 RTO/RPO 演练 runbook
