# Scripts

- `generate_seed_data.py`：使用固定随机种子生成可重复的零售模拟数据，并输出到 `data/seed/demo_data.sql`。
- `verify_database.py`：使用应用的只读账号检查 Schema、数据量和一条真实聚合查询。
- 后续将增加文档索引、评测运行和结果导出脚本。

脚本必须支持重复运行，禁止在源码中写入真实密钥或本机绝对路径。
