# Scripts

## 数据库与 SQL

- `generate_seed_data.py`：固定随机种子生成零售模拟数据。
- `verify_database.py`：用只读账号检查 Schema、数据量和聚合查询。
- `verify_deepseek.py`：执行一次最小 DeepSeek 请求，不输出 Key 或正文。
- `verify_sql_references.py`：执行 30 条参考 SQL，不调用 LLM。
- `evaluate_sql_smoke.py`：比较 DeepSeek SQL 与参考 SQL 的数据库执行结果；`--reuse-generated` 不产生新模型调用。

## RAG

- `index_policies.py`：解析 8 份 Markdown 制度并重建 Chroma 索引。
- `verify_rag_stack.py [query]`：验证 CUDA、Top 12 召回和 Top 5 重排。
- `verify_rag_answer.py [question]`：执行一条真实带引用 RAG 问答。
- `evaluate_rag_retrieval.py`：运行 20 条本地召回/拒答评测，不调用 LLM。
- `evaluate_rag.py`：运行 20 条真实 DeepSeek RAG 评测。
- `verify_api_e2e.py`：通过 FastAPI ASGI 接口验证一条真实 Hybrid 请求。

报告写入 Git 忽略的 `data/runtime`。脚本不得输出 Key，也不得把本机绝对路径写入可提交配置。
