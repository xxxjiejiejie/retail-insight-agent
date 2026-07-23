# v0.5 架构说明

## 请求生命周期

1. Vue 将持久化在浏览器本地的 `session_id` 与 `query` 发送到 `POST /api/v1/chat/stream`。
2. FastAPI 创建 `AgentState`，LangGraph 的规则路由判断 SQL、RAG、Hybrid、Clarify 或 General。
3. SQL 分支读取真实 Schema，由 DeepSeek 返回 JSON SQL 计划，经 SQLGlot 和白名单校验后用只读账号执行。
4. RAG 分支并行执行 Chroma 向量召回与 BM25 关键词召回，经 RRF 融合出 12 个制度块；BGE Reranker 保留 5 个，再按相关度阈值筛选证据。
5. DeepSeek 只能依据筛选后的上下文回答；服务解析答案中的 `[数字]`，仅返回实际使用的引用。
6. Hybrid 分支先按“并说明/同时说明”等连接词拆分数据和制度子问题，再并行运行 SQL 与 RAG，最后合并答案、错误和指标。
7. LangGraph 在公共终止节点追加一条轻量 turn，`AsyncSqliteSaver` 将图状态写入 `data/runtime/sessions.db`。
8. FastAPI 通过 SSE 发送节点进度、心跳和统一结果；Vue 展示回答、SQL、表格、ECharts、引用、指标与最近 20 轮历史。

## 会话与 SSE

```text
Vue localStorage session_id
→ POST /chat/stream
→ LangGraph thread_id
→ route/branch/persist_turn 节点事件
→ AsyncSqliteSaver
→ SQLite sessions.db
→ SSE result/done
→ GET /sessions/{session_id} 恢复历史
```

每轮开始前会显式清空 SQL/RAG 分支临时字段，避免 Checkpointer 将上一轮 SQL、引用或澄清信息带入新分支。历史 reducer 只保留最近 20 轮，turn 不保存大体积 `sql_result`。Checkpointer 仍会保存图运行状态，因此当前 SQLite 方案定位为本地演示；生产环境应迁移到 Postgres 并增加保留策略。

SSE 使用 POST + Fetch 流式读取，事件为 `start`、`node`、`heartbeat`、`result`、`error`、`done`。Nginx 关闭代理缓冲，长节点每 10 秒发送心跳。当前 DeepSeek 客户端不是 Token 流式客户端，因此系统只承诺节点级进度，不宣称逐 Token 生成。

## Text-to-SQL

```text
读取 MySQL Schema
→ 注入数据截止日和字段说明
→ DeepSeek JSON SQL 计划
→ SQLGlot AST 解析
→ 写操作/危险函数拦截
→ 物理表字段及 CTE/派生表输出字段校验
→ LIMIT 收紧与超时
→ 只读 MySQL 执行
→ 表格与白名单 ECharts 配置
```

失败时最多纠错 2 次。传给模型的只有必要校验或数据库错误，不包含密码、连接串和内部堆栈。

## 制度 RAG

### 索引

```text
Markdown / 文本型 PDF / DOCX
→ frontmatter 或 JSON 元数据侧车
→ 标题/页码/段落感知分块
→ 稳定 chunk_id 与 paragraph_id
→ 源文件与侧车 SHA-256 清单
→ 仅删除/写入发生变化的 chunk
→ Chroma 向量索引 + BM25 语料
```

当前 8 份制度产生 24 个块。PDF 页号进入 chunk 和引用；DOCX 的 Heading 样式形成章节，表格转为文本行。扫描版 PDF 不静默降级，提取不到文字时要求先做 OCR。模型、Chroma 和 BM25 均为本地运行；DeepSeek 只负责基于证据生成答案。

增量索引清单与 BM25 语料位于 `data/runtime`，不进入 Git。正常索引比较源文件及侧车文件的 SHA-256：新建/修改文档只重新计算对应向量，删除文档会清理原 chunk。零变更运行不会加载 Embedding 模型；`--full-rebuild` 仅用于排障和索引格式迁移。

### 查询

```text
用户问题
→ Chroma 向量 Top 20 + BM25 Top 20
→ RRF(k=60) 去重融合 Top 12
→ BGE Reranker Top 5
→ relevance_score >= 0.1
→ 无证据则拒答
→ DeepSeek 带 [数字] 回答
→ 只返回答案实际使用的引用
```

阈值 0.1 来自当前固定评测：跨章节相关片段最低约 0.1096，三条无答案问题最高约 0.069。扩展评测集或更换文档后必须重新校准，不能把该值视为通用常数。

BM25 使用中文单字、相邻双字词和英文/数字词元，不依赖额外分词模型。RRF 只利用两路排名而非直接混合不可比的余弦分数和 BM25 分数。当前 17 条有答案题中，向量与融合召回均为 17/17；这只能说明没有回归，不能证明融合检索已经提高指标。

## 路由

当前使用确定性规则，因为可离线、延迟低且便于建立基线。路由测试覆盖 30 条 SQL 题、17 条有答案 RAG 题和 Hybrid 组合题。

Hybrid 仅在同时存在数据指标和明确制度/组合线索时触发，避免“门店、订单、绩效”等实体词造成误路由。未来若引入 LLM Router，必须保留规则回退并比较准确率、成本和延迟。

## 图表

LLM 不生成图片，也不执行绘图代码。后端只允许：

```json
{
  "type": "bar",
  "title": "各区域销售额",
  "x_field": "region",
  "y_field": "revenue"
}
```

字段必须存在于真实 SQL 结果中，再由 Vue 的 ECharts 渲染。

## 指标

统一响应可包含：

- LLM prompt/completion/total Token；
- LLM、SQL、检索、重排和总耗时；
- SQL 尝试次数；
- 召回数、重排数、有效证据数和引用数；
- SQL、RAG 与 Hybrid 分支耗时。

首次请求总耗时会包含本地 Embedding/Reranker 模型加载，常驻 FastAPI 后后续请求复用单例。

## 当前技术债

- 已保存会话历史，但尚未将历史摘要注入路由/提示词实现代词与省略式追问；
- PDF 当前仅支持文本型文件，扫描件尚未接入 OCR；
- Hybrid 目前合并两个分支答案，尚未增加第三次统一总结调用；
- 已提供 CPU RAG API 的完整 Compose 镜像，并从主机只读挂载模型缓存；GPU 推理仍通过主机 Python 环境运行，尚未提供 NVIDIA Container Toolkit 版镜像；
- Vue 主包仍有约 732KB gzip 的分包优化空间；
- 当前评测规模仍小，需要扩展到 50～100 条综合用例。
