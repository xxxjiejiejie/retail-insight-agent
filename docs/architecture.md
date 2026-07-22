# v0.3 架构说明

## 请求生命周期

1. Vue 将 `query` 和 `session_id` 发送到 `POST /api/v1/chat`。
2. FastAPI 创建 `AgentState`，LangGraph 的规则路由判断 SQL、RAG、Hybrid、Clarify 或 General。
3. SQL 分支读取真实 Schema，由 DeepSeek 返回 JSON SQL 计划，经 SQLGlot 和白名单校验后用只读账号执行。
4. RAG 分支从 Chroma 召回 12 个制度块，BGE Reranker 保留 5 个，再按相关度阈值筛选证据。
5. DeepSeek 只能依据筛选后的上下文回答；服务解析答案中的 `[数字]`，仅返回实际使用的引用。
6. Hybrid 分支先按“并说明/同时说明”等连接词拆分数据和制度子问题，再并行运行 SQL 与 RAG，最后合并答案、错误和指标。
7. FastAPI 返回统一响应，Vue 展示回答、SQL、表格、ECharts 图表、引用和运行指标。

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
原创 Markdown 制度
→ frontmatter 元数据
→ 标题/段落感知分块
→ 稳定 chunk_id 与 paragraph_id
→ BGE Small 中文向量
→ Chroma 持久化索引
```

当前 8 份制度产生 24 个块。模型与 Chroma 均为本地运行；DeepSeek只负责基于证据生成答案。

### 查询

```text
用户问题
→ Chroma Top 12
→ BGE Reranker Top 5
→ relevance_score >= 0.1
→ 无证据则拒答
→ DeepSeek 带 [数字] 回答
→ 只返回答案实际使用的引用
```

阈值 0.1 来自当前固定评测：跨章节相关片段最低约 0.1096，三条无答案问题最高约 0.069。扩展评测集或更换文档后必须重新校准，不能把该值视为通用常数。

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

- 尚未实现 LangGraph Checkpointer、会话持久化和 SSE；
- 文档仅支持 Markdown，尚未加入 PDF/DOCX；
- 尚未实现 BM25 混合召回和增量索引；
- Hybrid 目前合并两个分支答案，尚未增加第三次统一总结调用；
- GPU RAG API 尚未打入完整 Docker 镜像；
- Vue 主包仍有约 732KB gzip 的分包优化空间；
- 当前评测规模仍小，需要扩展到 50～100 条综合用例。
