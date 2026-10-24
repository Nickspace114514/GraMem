# 2026-10-23 审查修复

针对同日代码与线上审查的发现。以下修改只在源码仓库，**尚未部署到生产**；部署流程见[部署手册](deployment.md)。

| 提交 | 内容 |
|---|---|
| Stop unresolved memory controls… | 控制分类失败不再写全局 `*` 暂停，只搁置本轮（不召回、不提取、不归档）；"别忘记 / don't forget"不再触发控制；排除变化只在有槽位被重新启用时才销毁排队证据，收紧策略则在新策略下重新提取；解析期间无关排除变化的文档重新排队，不再 blocked 并删除原件（删除类变化仍 fail closed）。 |
| Shorten and diagnose SQLite write-lock holds | 写事务记录持有者，持有超过 30 秒由 watchdog 记录线程栈，超过 2 秒记录调用位置；新增 `Store.read()`（延迟事务）用于只读路径；语音缓存文件读写与 fsync 移出写事务并使用 `O_NONBLOCK`；各会话 worker 通过 `meta.maintained_at` 共享每日 `maintain()`；实例 worker 失败指数退避（上限 120 秒）；关闭备份产生的多余连接。 |
| Treat unknown chat types as shared… | 共享会话判定改为白名单（`dm`、`direct`、`private`、`c2c` 之外都视为共享）；provider 以内容哈希为 turn 的归档在历史对账时按唯一内容摘要关联原生行，使撤销生效并避免重复归档。 |

## 验证

`tests/v2`：288 通过，4 跳过（原 263）；新增 `test_policy_epoch_scope.py`、`test_lock_contention.py`、`test_scope_and_turn_identity.py`。`ruff check` 通过。

## 已知未处理

- 写锁事故（2026-10-22 13:47 至 10-23 02:57，352 次 `database is locked`）的确切持锁线程未确认。本次增加的 watchdog 与持锁日志用于下次发生时定位；若再出现，对 Gateway 与 worker 进程使用 `py-spy dump` 并查看日志中的 `write transaction held`。
- `Store.read()` 仅用于已核实无写入的路径（`Engine.list/get/graph`、控制分类的只读查询、面板记忆分页）。其余仍使用立即写事务。
- Python 3.10 缺少 `sqlite_errorcode`，`Store` 打开数据库时的 BUSY 重试在该版本不生效；项目要求 Python 3.12 以上，不受影响。
- `network.py` 在图投影发布期间 revision 变化时可能短暂保留过期快照，直到下次同步，未改动。
