# Scripts

- `generate_seed_data.py`：使用固定随机种子生成可重复的零售模拟数据，并输出到 `data/seed/demo_data.sql`。
- `verify_database.py`：使用应用的只读账号检查 Schema、数据量和一条真实聚合查询。
- `verify_deepseek.py`：执行一次最小 DeepSeek 联网验证，不输出密钥或模型正文。
- `evaluate_sql_smoke.py`：运行 5 条真实 Text-to-SQL 冒烟评测，并将报告写入 `data/runtime`；调整评测逻辑后可加 `--reuse-generated` 复用上次生成 SQL，仅重跑本地数据库比对，避免重复消耗 API 额度。
- 后续将增加文档索引、评测运行和结果导出脚本。

脚本必须支持重复运行，禁止在源码中写入真实密钥或本机绝对路径。
