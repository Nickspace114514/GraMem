# 2026-10-31 空闲轮询与写锁

多个 Hermes profile 共用一个宿主进程时，每个被激活的 provider 都会起一个后台轮询线程。这些线程在没有任务时也每秒申请一次写锁，数量一多，真正的写入和新 provider 的初始化就排不上队。以下修改只在源码仓库；线上是手工合入的子集，见末尾。

## 现象与证据

- 某个 profile 在 20 分钟内记录了约 1800 次 provider 激活（每分钟 110 到 140 次），每次都新建 Engine 并启动轮询线程。
- 同一时段 `database is locked` 与 "background work failed" 的日志每分钟从 255 条升到约 1400 条；`BEGIN IMMEDIATE` 探测 3 秒拿不到锁。
- `/proc/locks` 显示同机的管理面板进程持有该库 WAL 的写锁，重启该面板后锁释放。
- 持锁线程的确切调用栈没有拿到：当时线上版本没有写事务看门狗（2026-10-23 的 `Store` 看门狗只在仓库里）。因此本次修改降低的是争用，不是对持锁原因的证明。

## 修改

| 位置 | 内容 |
|---|---|
| `Store.__init__` | `user_version` 已是当前版本时不再开写事务做迁移/建表。版本号与建表在同一个事务里设置，所以版本匹配即表示无事可做 |
| `engine.process_one`、`approval.review_one`、`chats.process_one`、`chat_backfill.step`、`relations.process_one`、`knowledge.process_one` | 先用只读查询判断有没有待处理项，没有就直接返回，不再申请写锁。探测是实际选择条件的超集，不会漏掉任务 |
| `knowledge.embed_one` | 候选选择改用 `Store.read()` 快照，嵌入模型调用不在写事务内 |
| `gramem/polling.py`（新） | `poll_delay()`：1 秒基础间隔加最多 50% 抖动，连续失败按指数退避，上限 45 秒 |
| `hermes.py` `_run` | 使用 `poll_delay`；失败日志只记第一次的完整栈，之后每 60 秒一条汇总，不再每秒每个 provider 一条 |

显式传入 `principal` 或 `job_id` 的 `chats.process_one` 调用不走探测，权限错误行为不变。

## 验证

- `tests/v2`：298 通过，4 跳过（此前 288）；新增 `test_idle_polling.py` 共 10 项，其中 9 项在旧代码上失败。`ruff check` 通过。
- 进程内模拟：60 个空闲轮询器加一个真实写入者，写入最长等待从 665 ms 降到 3 ms，同一窗口轮询次数从 3879 增到 6587。这不是对原事故（跨进程、持续数分钟）的复现。

## 已知限制

- 永远无法处理的记忆（例如含密钥而被跳过）会让 `relations` 的探测一直为真，仍会周期性申请写锁。
- 激活风暴本身（为什么一个 profile 会在几分钟内激活上千次 provider）在宿主一侧，本次没有定位。
- 线上是旧版引擎加手工合入的上述修改，不是整体升级；2026-10-23 的审查修复仍未部署。再次出现 `database is locked` 时，应先部署看门狗读取持锁栈。
