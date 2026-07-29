# Scripts

## 数据库与 SQL

- `generate_seed_data.py`：固定随机种子生成零售模拟数据。
- `verify_database.py`：用只读账号检查 Schema、数据量和聚合查询。
- `verify_deepseek.py`：执行一次最小 DeepSeek 请求，不输出 Key 或正文。
- `verify_sql_references.py`：执行 30 条参考 SQL，不调用 LLM。
- `evaluate_sql_smoke.py`：比较 DeepSeek SQL 与参考 SQL 的数据库执行结果；`--reuse-generated` 不产生新模型调用。

## RAG

RAG corpus and ablation workflow:

- `generate_policy_corpus.py` keeps the eight seed policies and creates 92 original synthetic retail SOPs, producing 100 documents across 10 domains.
- `validate_policy_corpus.py` checks metadata, stable IDs, duplicate bodies, chunk counts, and domain distribution.
- `build_rag_ground_truth.py` creates 80 chunk-level cases (70 answerable, 10 out-of-corpus) without using retrieval rankings as labels.
- `evaluate_rag_ablation.py` compares Vector, BM25, RRF, and RRF + BGE Reranker with Hit@5, MRR@5, nDCG@5, P50/P95 latency, and failure samples. It is local-only and does not call an LLM, LangSmith, or a database.

- `index_policies.py`：解析 Markdown/PDF/DOCX 制度，按文件哈希增量更新 Chroma 与 BM25 语料；`--full-rebuild` 可强制全量重建。
- `verify_ocr.py`：临时生成一页无敏感内容的图片型 PDF，通过完整文档加载链路验证 Qwen3.7 Plus OCR 回退；会产生一次外部模型调用，不读取制度目录。
- `verify_langsmith.py`：发送脱敏隐私探针并读回 Trace；`--live-llm` 额外验证一次真实 DeepSeek LLM Span。
- `verify_rag_stack.py [query]`：验证 CUDA、BM25 + 向量融合 Top 12 召回和 Top 5 重排。
- `verify_rag_answer.py [question]`：执行一条真实带引用 RAG 问答。
- `evaluate_rag_retrieval.py`：运行 20 条本地召回/拒答评测，并比较纯向量与融合召回，不调用 LLM。
- `evaluate_rag.py`：运行 20 条真实 DeepSeek RAG 评测。
- `verify_api_e2e.py`：通过 FastAPI ASGI 接口验证一条真实 Hybrid 请求。

## 会话与 SSE

- `verify_session_stream.py --reset`：经公开 API 验证 SSE 事件顺序、最终结果和 SQLite 会话落库；默认使用 General 问题，不调用付费模型。
- `evaluate_report_agent.py --live`：连续验证分析查询与报告追问，检查受控 ReAct 工具选择、报告产物和最大两次工具调用；默认拒绝运行，需明确外发授权。

## 综合评测

- `evaluate_comprehensive.py --quick`：运行 50 项路由、Hybrid 拆分和 SQL 安全检查，不连接模型或数据库。
- `evaluate_comprehensive.py`：增加 30 条真实 MySQL 参考 SQL 和 20 条本地 RAG 检索，共 100 项；不调用付费 LLM。
- `evaluate_hybrid_live.py`：默认运行 5 条真实 DeepSeek Hybrid 抽样，同时比较 SQL 执行结果和制度引用；会产生付费模型调用。使用 `--case-id HYBRID-003` 聚焦重跑时写入独立报告，不覆盖默认五题基线。
- `evaluate_challenges.py`：运行 4 条 SQL 边界、5 条 RAG 库外问题和 3 条 Prompt Injection 挑战；结果写入独立的 `challenge_eval_report.json`，失败样本会保留，不混入正常集主指标。
- `evaluate_multiturn_live.py`：运行 8 组真实双轮 SQL/RAG/Hybrid 追问，校验上下文是否使用、路由、SQL 结果和制度引用；会产生付费模型调用。
- `evaluate_resilience.py`：注入 LLM 超时、格式异常和数据库超时，验证安全降级与自动重试；不调用外部模型。
- `archive_evaluation_run.py`：将当前 SQL/RAG/Hybrid、多轮和故障报告归档为不可覆盖的历史批次，附带数据集哈希、Git 状态、失败诊断、优化说明和剩余限制；不调用模型。

报告写入 Git 忽略的 `data/runtime`。脚本不得输出 Key，也不得把本机绝对路径写入可提交配置。

## v0.8 前端联调

- 真实模式启动后，页面会分别请求 `/api/v1/health`、`/api/v1/metadata/schema` 和 `/api/v1/metadata/policies`，用于展示 API、经营数据库和制度知识库状态。
- 访问 `http://localhost:8080/?demo=1` 可进入无网络、无数据库、零 Token 的演示模式；演示历史只保留在当前页面。
- 历史结果回放通过 `/api/v1/sessions/{session_id}` 恢复，不会重新调用模型或重新执行 SQL。历史 SQL 快照最多包含前 100 行。
- 评测结果页通过 `/api/v1/evaluation/runs` 和 `/api/v1/evaluation/runs/{run_id}` 读取批次。运行评测后执行 `python scripts/archive_evaluation_run.py --run-id <唯一批次名>`，再刷新页面的“评测结果”导航。
- 前端 E2E 使用已安装的 Microsoft Edge，不下载浏览器二进制。启动 Docker Compose 后在 `frontend` 目录执行 `npm.cmd run test:e2e`，覆盖评测批次、失败样本、Schema 滚动、制度正文和新建会话历史。
