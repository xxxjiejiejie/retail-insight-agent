# v1.1 真实评测摘要

批次 ID：`v11-multiturn-resilience-20260726`  
运行日期：2026-07-26  
模型：DeepSeek V4 Pro 兼容接口  
数据：原创模拟零售数据库和制度文档  
原始 JSON：`data/runtime/evaluation_runs/v11-multiturn-resilience-20260726.json`（本地运行目录，按设计不提交 Git）

## 结果总览

| 集合 | 通过 | 总数 | 说明 |
|---|---:|---:|---|
| 正常集 | 55 | 55 | SQL 30、RAG 20、Hybrid 5 |
| 挑战集 | 12 | 12 | SQL 边界 4、RAG 库外 5、Prompt Injection 3 |
| 真实多轮 | 8 | 8 | SQL 5、RAG 2、Hybrid 1；均为双轮追问 |
| 故障恢复 | 3 | 3 | LLM 超时、LLM 格式异常、数据库超时 |

正常集分支指标：

| 分支 | 通过率 | 总 Token | 拒答率 | P50 延迟 | P95 延迟 |
|---|---:|---:|---:|---:|---:|
| SQL | 30/30 | 23,010 | 0% | 7.84s | 17.21s |
| RAG | 20/20 | 2,544 | 15% | 1.88s | 4.52s |
| Hybrid | 5/5 | 4,493 | 0% | 7.44s | 25.45s |

## 本批次验证的改动

- SQL 结果比较支持星期名称/编号归一化、两位展示精度和可选参考展示列；比较规则写在评测数据中，不按 case ID 特判。
- SQL 生成加入 Top-N、条件聚合、明细数/售出数量、平均折扣率和 `cancelled` 状态枚举约束。
- 复杂 SQL 计划输出上限提高到 2400 Token，DeepSeek 请求温度固定为 0，并支持带说明 JSON 与兼容响应格式。
- 上下文规则支持“只看/仅看”，Hybrid 追问会把追问条件同时传给 SQL 和 RAG。
- 评测页展示优化说明、批次指标变化、专项集合、历史失败和已知限制。

## 历史对比

上一批次 `v10-deterministic-fixes-20260726`：正常集 `52/55`、挑战集 `10/12`，保留 5 条失败样本。v1.1 将这些可确定的问题修复后重新运行；当前批次没有失败样本，但历史失败仍保留在本地评测页用于回归和面试演示。

## 如何复现

以下命令需要本地 MySQL、RAG 模型缓存和项目配置的 LLM API Key。真实评测会把原创问题、Schema 或制度检索片段发送至配置的模型 API：

```powershell
python scripts/evaluate_sql_smoke.py
python scripts/evaluate_rag.py
python scripts/evaluate_hybrid_live.py
python scripts/evaluate_challenges.py
python scripts/evaluate_multiturn_live.py
python scripts/evaluate_resilience.py
python scripts/archive_evaluation_run.py --run-id <unique-run-id> --label "<batch-label>"
```

`evaluate_resilience.py` 使用确定性故障注入，不调用外部模型。完整页面演示见 [INTERVIEW_DEMO.md](INTERVIEW_DEMO.md)。

## 仍存限制

- RAG 尚未使用独立裁判模型，当前指标主要验证引用覆盖、拒答和检索链路；
- 多轮目前为 8 组双轮样本，不能代表更长会话和复杂指代；
- 图表只校验类型与字段合法性，尚未评价图表是否最适合问题；
- 认证、细粒度权限、审计、限流和线上监控不在当前离线评测范围；
- 所有数字来自原创模拟数据，不能直接解释为生产环境准确率。
