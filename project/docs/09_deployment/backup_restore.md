# P1-4：备份与恢复演练

- 文档路径：`project/docs/09_deployment/backup_restore.md`
- 最后更新：2026-08-19

## 1. 备份

```bash
cd project/code
bash scripts/backup.sh
# 产出：code/backups/<timestamp>/knowledge.dump [+ neo4j/]
```

## 2. 校验演练（推荐，非破坏性）

```bash
cd project/code
bash scripts/drill_backup_restore.sh
```

验证：`knowledge.dump` 非空 + `pg_restore --list` 可读。

## 3. Postgres 恢复（破坏性，需确认）

```bash
cd project/code
RESTORE_FROM=backups/<timestamp> RESTORE_CONFIRM=1 bash scripts/restore.sh
```

或在演练脚本中：

```bash
DRILL_RESTORE=1 bash scripts/drill_backup_restore.sh
```

## 4. 验收清单

- [x] `drill_backup_restore.sh` exit 0 — **08-19 已验证**
- [ ] （可选）`DRILL_RESTORE=1` 后 `psql` 可查询 public 表
- [ ] Neo4j 手工 load 步骤已文档化（自动 load 仍延后）

## 5. 仍缺

- Chroma / Redis / 上传原件一致快照
- 按 doc 彻底删除证明
- 空环境全栈时间点恢复 + 检索一致性 E2E
