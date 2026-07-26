# Retail Insight Agent

> 面向零售经营分析的 AI 应用工程项目：自然语言查经营数据库、查询制度知识库，并通过 LangGraph 完成 SQL、RAG、Hybrid 路由与可审计结果展示。

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Frontend-Vue%203-42B883?logo=vuedotjs&logoColor=white)
![Tests](https://img.shields.io/badge/tests-99%20passed%20%7C%203%20skipped-2ea44f)

当前真实评测批次：`v11-multiturn-resilience-20260726`。正常集 `55/55`、挑战集 `12/12`、真实多轮 `8/8`、故障恢复 `3/3`。评测结果不等同于生产环境准确率，数据为原创模拟零售场景。可提交的指标摘要见 [v1.1 评测摘要](docs/EVALUATION_V11.md)。

面向中小零售企业的经营分析与制度知识问答智能体。用户可以用自然语言查询 MySQL 中的经营数据，也可以查询原创模拟制度；LangGraph 将问题路由到 SQL、RAG、Hybrid、Clarify 或 General 分支。

## 30 秒了解项目

这个项目解决的是一个典型 AI 应用问题：企业用户不想写 SQL，也不想在制度文件里翻页，但答案又必须可验证、可追溯、可拒答。

- **SQL 分析**：自然语言生成只读 SQL，经过 Schema/字段白名单、SQLGlot AST、危险节点拦截、LIMIT、超时和最多 2 次纠错后执行。
- **RAG 问答**：Markdown/PDF/DOCX 制度经标题感知分块，使用向量 + BM25 + RRF + Reranker 检索，只返回答案实际使用的引用；证据不足时拒答。
- **Hybrid 联查**：将经营数据问题和制度问题拆分并行执行，合并为带数据库结果和制度依据的答案。
- **工程闭环**：SSE 进度流、SQLite 会话历史、Schema/制度只读抽屉、CSV/SQL 导出、评测批次对比和演示模式。
- **可验证性**：保留正常集、挑战集、多轮集、故障恢复集及历史失败样本，不只展示成功截图。

## 页面截图

页面截图：分析工作台使用零 Token 演示模式；评测页、Schema 和制度抽屉来自真实本地运行模式，数据和评测报告均来自原创模拟环境：

| 分析工作台 | v1.1 评测结果 |
|---|---|
| ![分析工作台](docs/screenshots/workbench-demo.png) | ![v1.1 评测结果](docs/screenshots/evaluation-v11.png) |

| Schema 抽屉 | 制度知识库抽屉 |
|---|---|
| ![经营数据库 Schema](docs/screenshots/schema-drawer.png) | ![制度知识库](docs/screenshots/policy-drawer.png) |

完整演示顺序见 [5 分钟面试演示流程](docs/INTERVIEW_DEMO.md)。访问 `http://localhost:8080/?demo=1` 可进入零 Token 演示模式。

## 当前版本：v1.1

当前版本在 v0.8 的交互闭环基础上，补齐了真实评测、失败分析、多轮追问和故障恢复证据：

- FastAPI `POST /api/v1/chat` 与 LangGraph 条件路由；
- DeepSeek V4 Pro Anthropic 兼容客户端；
- 安全 Text-to-SQL：Schema 注入、JSON 计划、SQLGlot AST、表字段白名单、危险函数拦截、LIMIT、超时、只读执行及最多 2 次纠错；
- MySQL 8.4 模拟零售库：12 家门店、60 个商品、4000 笔订单、10005 条订单明细；
- Markdown/PDF/DOCX 统一制度加载、标题感知分块、PDF 页码和稳定段落编号；
- 文件 SHA-256 清单驱动的 Chroma 增量更新，未变更文档不重复计算 Embedding；
- `BAAI/bge-small-zh-v1.5` 向量召回 + 中文字符/双字词 BM25，通过 RRF 融合后保留 Top 12；
- `BAAI/bge-reranker-base` Top 5 重排、0.1 证据阈值及低相关度拒答；
- DeepSeek 基于证据生成答案，只返回答案中实际使用的 `[数字]` 引用；
- Hybrid 问题拆分为数据与制度子问题并行执行；
- Vue 3 + TypeScript + Element Plus + ECharts 展示型分析工作台，包含深色导航、示例问题、SSE 进度、结果分区和响应式布局；
- 分析结果按“结论、数据与图表、制度依据、运行轨迹”组织，支持 CSV 导出、SQL 复制、会话快速复用以及引用位置与相关度展示；
- Element Plus 按需注册、ECharts 模块化注册与异步加载；首屏主 JS 从 2197.88KB 降至 384.28KB，CSS 从 359.49KB 降至 89.27KB；
- CPU 版 FastAPI、Vue 与 MySQL 的完整 Docker Compose 部署；BGE 模型从主机缓存只读挂载并离线加载；
- LangGraph `AsyncSqliteSaver` Checkpointer、最近 20 轮轻量会话记录、查询与清空接口；
- `POST /api/v1/chat/stream` SSE 节点进度流，含 10 秒心跳、最终结果与安全错误事件；
- Vue 将会话 ID 保存在浏览器本地，刷新后从 SQLite 恢复历史，并可清空后创建新会话；
- 基础上下文追问解析：将“那华东呢”“换成五月”“只看未达标门店”“这个制度的申诉期限呢”等短追问与最近一次分析问题组合，不增加额外 LLM 调用；Hybrid 追问会同时传给 SQL 与 RAG 子分支；
- 统一 100 项本地评测：30 条 SQL 参考执行、20 条 RAG 召回/拒答、25 条路由、10 条 Hybrid 拆分和 15 条 SQL 安全边界；
- SSE 内部失败返回统一安全错误，不向页面暴露连接信息或堆栈；
- Python 3.12、102 个 pytest 用例（99 个通过、3 个按环境跳过）、Ruff、MyPy 和可重复评测脚本。

前端与演示闭环：

- Checkpointer 保存每轮轻量结果快照，历史会话可恢复对应回答、SQL、表格、图表、引用和指标；SQL 历史行数最多保存前 100 行并保留原始总行数；
- “经营数据库”和“制度知识库”提供只读元数据抽屉，分别查看真实表字段和 8 份制度目录；
- `?demo=1` 进入前端演示模式，使用内置 SQL/RAG/Hybrid 样例，不调用 DeepSeek、不访问真实数据库、不写入真实会话；
- 页面启动时实际检查 API、经营数据库和制度知识库状态，并提供检查中、正常、异常和演示四类提示。

当前真实评测结果：

- 30/30 条参考 SQL 可通过安全校验并在真实 MySQL 执行；
- 完整 30 条真实 DeepSeek Text-to-SQL 通过 30/30，包含 Top-N、聚合、状态枚举和复杂 CTE 场景；
- 20/20 条本地 RAG 召回/拒答评测通过；
- 17 条有答案题中纯向量与混合召回均为 17/17，当前小型题集尚未体现召回增益；
- 100/100 项完整本地综合评测通过，两次运行约 23～28 秒，付费 LLM 调用为 0；
- 20/20 条真实 DeepSeek RAG 评测通过，其中 17 条有答案题返回制度引用，3 条库外问题零引用拒答；本批次使用 2,544 Token；
- 5/5 条真实 DeepSeek Hybrid 问题通过数据库结果与制度引用双重校验，本批次使用 4,493 Token；
- 8/8 组真实双轮追问通过：SQL 5 组、RAG 2 组、Hybrid 1 组；
- 3/3 故障恢复演示通过：LLM API 超时、LLM 格式异常、数据库超时；
- 12/12 挑战集通过：SQL 边界、RAG 库外问题和 Prompt Injection；
- Docker 页面真实验收通过：评测页展示正常/挑战/多轮/故障专项、优化说明、历史失败和已知限制；E2E `11 passed, 1 skipped`。

评测集较小且全部为原创模拟场景，这些数字不能等同于生产环境准确率。

已知限制：

- 扫描版 PDF 的 OCR；
- RAG 尚未使用独立裁判模型，当前指标验证引用覆盖、拒答和检索链路，不等同于逐句事实一致性；
- 多轮真实评测目前为 8 组双轮问题，不能代表更长会话、跨天追问和复杂指代；
- 图表目前校验类型和字段合法性，尚未评价图表类型是否最适合问题；
- 认证、细粒度权限、审计、限流和线上监控不在当前离线评测范围；
- GPU RAG API 镜像仍未单独发布，Compose 使用 CPU 版保证可移植部署。

## 架构

```mermaid
flowchart LR
    Vue["Vue 3"] --> API["FastAPI"]
    API --> Graph["LangGraph Router"]
    Graph --> SQL["安全 Text-to-SQL"]
    Graph --> RAG["制度 RAG"]
    Graph --> Hybrid["Hybrid 拆分与并行"]
    SQL --> MySQL[("MySQL 只读账号")]
    RAG --> Vector["BGE Small + Chroma"]
    RAG --> BM25["中文 BM25"]
    Vector --> RRF["RRF 融合"]
    BM25 --> RRF
    RRF --> Reranker["BGE Reranker Base"]
    Reranker --> Answer["DeepSeek 带引用回答"]
    SQL --> Answer
    Hybrid --> SQL
    Hybrid --> RAG
```

详细调用链见 [docs/architecture.md](docs/architecture.md)。

## 目录

```text
app/
├── api/                 FastAPI 路由与响应模型
├── core/                配置、日志和异常
├── database/            MySQL Engine 与 Schema
├── graph/               LangGraph 路由、节点和状态
├── llm/                 DeepSeek 兼容客户端
├── rag/                 文档、检索、重排、引用
└── sql_agent/           SQL 生成、校验和执行
data/
├── documents/           Markdown/PDF/DOCX 制度与二进制文档元数据侧车
├── eval/                SQL 与 RAG 固定评测集
└── runtime/             本地索引和报告，Git 忽略
frontend/                Vue 3 前端
prototype/               Streamlit 早期原型
docs/
├── architecture.md      架构与调用链
├── EVALUATION_V11.md     可提交的真实评测摘要
├── INTERVIEW_DEMO.md     5 分钟面试演示流程
└── screenshots/          GitHub 页面截图
scripts/                 数据、索引、验证和评测脚本
tests/                   单元与集成测试
```

## 本地安装

### 1. Python 3.12 环境

```powershell
conda create --prefix .\.venv python=3.12 pip -y
conda activate .\.venv
python -m pip install -e ".[dev,prototype]"
Copy-Item .env.example .env
```

不要把依赖安装到系统 Python，也不要提交 `.env`。

### 2. GPU RAG 依赖

下面的首次下载可能达到数 GB；开始前应确认磁盘空间和网络流量。

```powershell
python -m pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install --no-cache-dir -e ".[rag]"
```

本机已验证的组合为 Python 3.12、PyTorch 2.11.0+cu128、CUDA 12.8 和 RTX 4060 Laptop GPU 8GB。

### 3. 配置

```dotenv
LLM_PROVIDER=deepseek_anthropic
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com/anthropic
LLM_API_KEY=仅在本机填写新密钥
DATA_AS_OF_DATE=2026-06-30

MODEL_CACHE_PATH=./data/runtime/model_cache
HOST_MODEL_CACHE_PATH=./data/runtime/model_cache
MODEL_LOCAL_FILES_ONLY=false
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RERANKER_MODEL=BAAI/bge-reranker-base
LEXICAL_CORPUS_PATH=./data/runtime/bm25_corpus.json
RAG_VECTOR_TOP_K=20
RAG_BM25_TOP_K=20
RAG_RRF_K=60
```

首次索引/模型验证完成后可把 `MODEL_LOCAL_FILES_ONLY` 改为 `true`，避免已缓存模型启动时仍访问 Hugging Face。模型缓存也可以放到仓库外的其他磁盘目录。

如果 Key 曾出现在聊天、截图、日志或 Git 历史中，必须撤销并重新生成。

## 运行

### MySQL

```powershell
python scripts/generate_seed_data.py
docker compose up -d mysql
python scripts/verify_database.py
```

主机端口为 `3307`，容器内仍为 `3306`。应用账号 `retail_readonly` 仅拥有 SELECT 权限。

### 制度索引

Markdown 直接在 YAML frontmatter 中声明元数据。PDF/DOCX 需要同目录、同完整文件名的侧车文件，例如 `return_policy.pdf.metadata.json`：

```json
{
  "document_id": "POL-RETURN-002",
  "title": "退换货补充制度",
  "version": "1.0",
  "effective_date": "2026-07-01"
}
```

PDF 必须包含可复制文本；扫描件会明确提示先做 OCR。DOCX 按 Heading 样式分节，表格按文本行进入索引。

```powershell
python scripts/index_policies.py
python scripts/verify_rag_stack.py
```

默认命令按源文件及侧车文件 SHA-256 增量更新，同时生成 Git 忽略的 Chroma 索引清单和 BM25 语料。文档新增、修改、删除都会同步；需要排障时可执行 `python scripts/index_policies.py --full-rebuild` 强制全量重建。

模型已缓存且启用离线模式时，可额外设置：

```powershell
$env:HF_HUB_OFFLINE="1"
```

### FastAPI

```powershell
uvicorn app.main:app --reload
```

- 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>

### 完整 Docker Compose（CPU RAG）

先确保两个 BGE 模型已下载，并在本机 `.env` 中将 `HOST_MODEL_CACHE_PATH` 指向 Hugging Face 缓存根目录。例如：

```dotenv
HOST_MODEL_CACHE_PATH=E:/AIModels/huggingface
```

随后运行：

```powershell
docker compose --progress plain build api
docker compose up -d --force-recreate api frontend
docker compose ps
```

Compose 将模型缓存只读挂载到容器 `/models`，并启用 Hugging Face/Transformers 离线模式，不会在每次启动时重新下载模型。访问 <http://localhost:8080>；API 为 <http://localhost:8000>。v0.6 CPU API 镜像实测约 494MB，冷启动首个 RAG 请求约 15 秒，模型预热后同类页面请求约 2.5 秒。当前 Docker 依赖分层的新缓存首次构建约 317.3 秒，紧接着的零变更构建全部命中缓存，约 2.7 秒完成；该数据仅代表同机热缓存场景。

`data/runtime` 挂载到容器内同名目录，SQLite 会话数据库因此能跨 API 容器重启保留。会话只保留最近 20 轮轻量记录；当前路由和回答仍以本轮问题为主，尚未把历史摘要注入模型完成指代消解。

### Vue

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

访问 <http://localhost:5173>。图表由后端白名单 `chart_spec` 和真实 SQL 结果驱动，不使用生图模型。

## 测试与评测

```powershell
python -m ruff check app tests scripts
python -m mypy app scripts
python -m pytest

$env:RUN_DB_TESTS="1"
python -m pytest tests/integration/test_database.py
```

需要真实 API 额度的脚本：

```powershell
python scripts/verify_deepseek.py
python scripts/evaluate_sql_smoke.py
python scripts/verify_rag_answer.py
python scripts/evaluate_rag.py
python scripts/evaluate_hybrid_live.py
python scripts/verify_api_e2e.py
python scripts/verify_session_stream.py --reset
```

不调用付费模型的脚本：

```powershell
python scripts/verify_sql_references.py
python scripts/evaluate_sql_smoke.py --reuse-generated
python scripts/evaluate_rag_retrieval.py
python scripts/evaluate_comprehensive.py --quick
python scripts/evaluate_comprehensive.py
```

`--quick` 只运行 50 项路由、Hybrid 拆分和 SQL 安全检查；完整模式连接真实 MySQL 并加载本地 BGE，共运行 100 项，但不会调用 DeepSeek。报告写入 `data/runtime/comprehensive_eval_report.json`。

评测报告写入已被 Git 忽略的 `data/runtime`，不会保存 Key。

推荐验证顺序：

```powershell
# 不调用付费模型：固定 SQL、检索、安全和综合门禁
python scripts/verify_sql_references.py
python scripts/evaluate_rag_retrieval.py
python scripts/evaluate_comprehensive.py

# 不调用外部模型：故障恢复演示
python scripts/evaluate_resilience.py

# 真实模型评测：需要明确的 API Key 和外发授权
python scripts/evaluate_sql_smoke.py
python scripts/evaluate_rag.py
python scripts/evaluate_hybrid_live.py
python scripts/evaluate_challenges.py
python scripts/evaluate_multiturn_live.py

# 归档当前报告，run_id 必须唯一且不可覆盖
python scripts/archive_evaluation_run.py --run-id <unique-run-id> --label "<batch-label>"
```

真实评测会把原创模拟问题、Schema 或制度检索片段发送至配置的模型 API；默认开发测试不调用付费模型。完整的 5 分钟讲解顺序见 [docs/INTERVIEW_DEMO.md](docs/INTERVIEW_DEMO.md)。

## API 示例

```http
POST /api/v1/chat
Content-Type: application/json

{
  "query": "2026年6月哪些门店没有完成销售目标？并说明销售目标完成率在绩效中的权重。",
  "session_id": "demo-session"
}
```

响应会根据分支返回 `resolved_query`、`context_used`、`generated_sql`、`sql_result`、`chart_spec`、`citations`、`errors` 和 `metrics`。引用包含制度名、版本、章节、PDF 页码（如有）、段落编号、原文片段和相关度。

流式接口为 `POST /api/v1/chat/stream`，依次发送 `start`、`node`、可选 `heartbeat`、`result` 和 `done` 事件。这里的“流式”是可观测的 LangGraph 节点进度与最终结果，不是伪造的逐 Token 输出。

会话接口：

- `GET /api/v1/sessions/{session_id}`：读取最近 20 轮；
- `DELETE /api/v1/sessions/{session_id}`：删除指定会话，不影响其他会话。

评测接口：

- `GET /api/v1/evaluation/runs`：读取历史评测批次摘要；
- `GET /api/v1/evaluation/runs/{run_id}`：读取指定批次的分支指标、专项评测、优化说明、限制、失败样本和来源报告。

运行 `python scripts/archive_evaluation_run.py --run-id <唯一批次名>` 可将当前 SQL/RAG/Hybrid、多轮和故障报告归档到 `data/runtime/evaluation_runs`。前端“评测结果”页面展示准确率、拒答率、Token、P50/P95 延迟、专项指标、优化说明、失败样本和批次对比；当前报告覆盖数量会原样显示，不会补写缺失样本。

## 安全边界

- 数据库使用只读账号；
- 只允许单条 SELECT/CTE；
- SQLGlot 校验物理表、物理字段以及 CTE/派生表输出字段；
- 拒绝写操作、危险函数、未知表字段和超大 LIMIT；
- 查询设置超时和最大返回行数；
- SQL 错误纠错最多 2 次，不向模型发送密码、连接串或内部堆栈；
- RAG 低证据拒答，只返回答案实际引用的片段；
- PDF/DOCX 使用显式元数据侧车，扫描版 PDF 不会被误建为空索引；
- `.env`、Chroma 索引、模型缓存和评测报告不进入 Git。

## 开源与归属

项目采用 MIT License。参考项目、保留内容与重写原则见 [NOTICE.md](NOTICE.md)。制度文档和模拟经营数据为本项目公开演示用途，不包含真实企业隐私。
## v1.0 确定性失败修复回归

当前可验证的第三批次为 `v10-deterministic-fixes-20260726`，使用与第二批次相同的数据集原样回归：

- 正常集 55 条：SQL 30 条（27/30）、RAG 20 条（20/20）、Hybrid 5 条（5/5），合计 52/55，准确率 94.55%。
- 挑战集 12 条：SQL 边界 4 条、RAG 库外 5 条、Prompt Injection 3 条，合计 10/12；挑战集不混入正常集主准确率。
- `RAG-CH-004` 从“明确拒答但携带无关引用”变为零引用拒答并通过；`SQL-CH-002` 原有的 `GROUP BY` 投影别名白名单误判已消失，SQL 可直接执行。
- 本次 `SQL-CH-002` 仍因 `DAYNAME` 与参考查询 `DAYOFWEEK` 的表示差异未通过值比对；`SQL-CH-004` 因未返回过滤条件中恒为 0 的库存展示列未通过比对。两条新失败均如实保留，没有修改题目或参考答案。
- 评测页会单独展示正常集、挑战集、已知限制和历史批次；运行 `scripts/evaluate_challenges.py` 后，再用 `scripts/archive_evaluation_run.py --run-id <唯一批次名>` 归档。

此前的 `v08-baseline-20260724` 和 `v09-expanded-challenges-20260724` 仍保留为历史批次，不能用新报告覆盖。

## v1.1 SQL 稳定性与多轮故障回归

当前可验证的第四批次为 `v11-multiturn-resilience-20260726`：

详细指标、Token、限制和复现命令见 [docs/EVALUATION_V11.md](docs/EVALUATION_V11.md)。

- 正常集 55 条：SQL 30/30、RAG 20/20、Hybrid 5/5，合计 55/55；
- 挑战集 12 条：SQL 边界 4/4、RAG 库外 5/5、Prompt Injection 3/3；
- 真实双轮追问 8/8：SQL 5 组、RAG 2 组、Hybrid 1 组，单独统计，不混入正常集；
- 故障恢复演示 3/3：LLM API 超时安全降级、LLM 格式异常自动重试、数据库超时安全失败；
- 当前批次没有失败样本，但上一批次 `v10-deterministic-fixes-20260726` 的 5 条失败仍可在历史对比中查看；
- 评测页新增优化说明、当前/对比批次指标变化、多轮和故障专项、已知限制详细描述。
