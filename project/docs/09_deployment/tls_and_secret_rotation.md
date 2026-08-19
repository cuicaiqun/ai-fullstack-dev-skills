# P0-3：本地自签 TLS 与密钥轮换 / 回滚演练

- 文档路径：`project/docs/09_deployment/tls_and_secret_rotation.md`
- 最后更新：2026-08-19
- 范围：本地 / 单机演示；正式 KMS/集群 Ingress 仍属后续

---

## 1. 本地 HTTPS（自签）

### 生成证书

```bash
cd project/code
bash scripts/gen_selfsigned_tls.sh
```

产物：`tls/server.crt`、`tls/server.key`（勿提交私钥到公开仓库）。

### 启动 TLS 终止（Nginx → API:8080）

```bash
cd project/code
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.tls.yml \
  --env-file python/.env up -d tls
curl -k https://127.0.0.1:8443/api/health
```

验收：

- [x] `https://127.0.0.1:8443/api/health` 返回 JSON（允许自签警告）— **08-19 已验证**
- [ ] 数据面端口策略仍按生产 compose：仅网关对外（本机 dev overlay 可例外）

回滚：`docker compose ... stop tls` 后继续只用 `http://127.0.0.1:8080`。

---

## 2. JWT 密钥轮换演练

前置：API 已启用 `AUTH_ENABLED=true`。

### 步骤

1. 记录当前 `JWT_SECRET`（备份到私密处，勿入库）。
2. 用当前密钥登录，保存 `access_token`。
3. 生成新密钥（示例）：`openssl rand -hex 32`。
4. 更新 `python/.env` 中 `JWT_SECRET=<新值>`。
5. 重启 API（及 ingest-worker）：  
   `docker compose ... up -d api ingest-worker`
6. 用**旧** token 调 `/api/auth/me` → 期望 **401**。
7. 重新登录拿到新 token → `/api/auth/me` **200**。

### 回滚

1. 把 `JWT_SECRET` 改回备份值。
2. 重启 API/worker。
3. 旧会话仍可能因 `jti` 撤销列表或 `token_version` 失效；以重新登录为准。

验收清单：

- [x] 轮换后旧 JWT 立即不可用 — **08-19 `drill_jwt_rotation.sh` 验证**
- [x] 新登录可用 — **08-19 验证**
- [x] 回滚后可用备份密钥重新签发 — **08-19 验证**

自动化：

```bash
cd project/code/python
bash scripts/drill_jwt_rotation.sh
```

---

## 3. 数据库口令轮换（Neo4j / Postgres）摘要

1. 在库内改密码（或重建用户）。
2. 同步更新 `.env`：`NEO4J_PASSWORD` / `POSTGRES_PASSWORD` 与 DSN。
3. 滚动重启依赖这些口令的容器。
4. `/api/health` 中对应 `*_live` 为 ok。

失败回滚：改回旧口令并重启；保留旧连接串备份至演练结束。

---

## 4. 生产边界提醒（本版不做但必须知道）

- 正式环境用公网证书（Let’s Encrypt / 公司 PKI）+ Secret Manager，而不是仓库内私钥。
- 生产 compose 仅发布 API/TLS 端口；Neo4j/Chroma/Postgres/Redis/Kafka 不映射宿主机。
- `APP_ENV=production` + `REQUIRE_STRONG_SECRETS=true` 下弱密钥应拒绝启动（见 `scripts/check_p0_3_deploy.py`）。
