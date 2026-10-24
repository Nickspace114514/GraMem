# LLM 自动审批

现行 GraMem 2.4.1 / schema 7，核对日期 2026-10-04；自 2.1.1 起默认 `auto_approve=true`，生产同样显式启用。不再要求逐条手工批准身份、职业、当前位置或其他候选。

## 工作流程

- 会话提取：LLM 在提取事实、评分、冲突和关系时一并完成最终审核；通过证据/权限校验的事实直接激活，包含身份等原确认类型。合并也复用生成合并内容的 LLM 调用，不追加审批调用。
- 历史候选、默认导入、显式 `confirmed=false` 候选：常驻后台自动审核，每批仅一个身份，最多 `max_items` 条，输入不超过 `extraction_input_tokens`；批准后可召回，关系进入独立 FalkorDB。
- 管理员明确保存的事实保留原有可信写入语义，原件知识分块仍按授权资料归档；不为每个分块新增模型调用。
- 批准同时更新事实状态、全文索引、画像失效标记和图同步队列。`confirmation_types` 仅在显式关闭自动审批的传统模式中要求手工确认。

自动审批不等于把任何文本强制变成有效记忆。LLM 可以拒绝缺少证据的事实；程序继续阻止秘密、越权、已遗忘内容与过时更新。寒暄、低置信/无未来价值提取仍会过滤。过时或缺少来源的旧候选自动拒绝，不替用户编造依据。不能取消遗忘或恢复旧资料。

## 接口与观测

`gramem --home <HERMES_HOME> review`：处理一个就绪候选批次，返回 `review_processed` 和 `graph_synced`。主 worker、Hermes provider 与本实例常驻知识 worker 自动执行，不需要定时手工调用。管理 API 的 `/operation`，`action=worker` 也返回 `review_processed`。

`Engine.review_one()` 返回是否处理了工作，true 不表示所有候选都获批准。`Engine.status()` 提供 `automatic_approval` 与 `review_jobs`。通过 list/get 或管理面板详情查看：

- 候选 `lifecycle=auto_review`，`metadata.auto_review` 包含 attempts、retry_at、error 与持久租约；旧 awaiting_confirm/review 同样自动处理。
- 完成 `metadata.approval` 包含 mode=llm、stage（extraction/consolidation/candidate_review）、approved、model、at。后台事件 AUTO_APPROVE/AUTO_REJECT 与 AUTO_REVIEW_BATCH 可审计；批次事件记录数字 usage。
- 模型请求或 JSON 校验失败时不激活，保留候选并自动退避重试，最长间隔一小时。模型不可用时等待恢复；不会退回要求用户手工批准。

跨进程使用持久租约，崩溃后租约到期恢复。审核提交时重新核对候选/目标版本、来源、排除 epoch；审核期间遗忘或修改的记录不能由旧审核结果复活。不同身份不混在同一次模型请求中。

控制台显示“自动审核中”，移除逐条确认按钮；管理员显式拒绝与原 confirm/reject API 保留兼容。配置更新后须重启 gateway、控制台和常驻 worker。真实模型判断仍有语义误判风险，没有承诺固定 token 节省比例。

## 2026-10-03 验收

服务器隔离回归 177 项通过，包含真实独立 FalkorDB。生产实际 qwen3.8-flash 验证：identity、occupation、current_location 自动提取直接 active；另 3 条 identity/occupation/health 旧式候选由后台自动批准。自动提取任务记录 1 次 Chat + 3 次 embedding、input_tokens=872、output_tokens=397；没有逐条追加审批 Chat。实际后台进程领取的审批用量不计入测试 Engine 的进程用量。测试范围隔离，结束后清理测试事实。

部署前真实 Owner 有 2 条 awaiting_confirm；后台自动审核后 1 条批准、1 条拒绝，Owner 待审为 0。自动审核可以拒绝，不等于无条件激活。gateway、控制台、常驻 worker 已重启；15 条会话缓存通过 Hermes 原生接口刷新，769 条历史消息与非缓存字段一致。配置显式 auto_approve=true，事实库 schema 4 保留，未备份或导入旧系统记忆。

另经 Hermes 原生 MemoryManager 回调与真实模型验证：identity/preference/skill/project/relationship/episodic/knowledge/temporary 八类均为 active，跨联系人隔离与真实独立图通过。两条任务合计 input_tokens=1848、output_tokens=1325，2 次 Chat + 8 次 embedding，身份不再进入人工确认。
