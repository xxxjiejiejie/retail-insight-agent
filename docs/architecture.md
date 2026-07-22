# 基础架构说明

## 请求生命周期

1. Vue 或 Streamlit 将 `query` 和 `session_id` 发送给 FastAPI。
2. FastAPI 创建初始 `AgentState` 并调用 LangGraph。
3. `route` 节点执行第一版确定性分类。
4. 条件边将请求送入 SQL、RAG、Hybrid、Clarify 或 General 节点。
5. 当前 SQL/RAG 服务只定义稳定接口，后续分别替换为真实实现。
6. FastAPI 返回统一结构，前端不依赖具体 Agent 内部实现。

## 为什么先使用规则路由

基础框架阶段使用规则路由有三个目的：

- 不配置 LLM 也能验证图结构和 API；
- 为后续 LLM 路由提供可比较的基线；
- 先建立路由评测集，再决定是否需要更复杂模型。

它不是最终方案。新增 LLM Router 时必须保留确定性回退，并用固定评测集对比准确率、延迟和成本。

## SQL 分支后续节点

```text
schema_retrieval
→ sql_generation
→ ast_validation
→ read_only_execution
→ result_interpretation
→ chart_spec_validation
```

## RAG 分支后续节点

```text
query_rewrite
→ hybrid_retrieval
→ rerank
→ evidence_check
→ cited_answer
```

## 图表原则

LLM 不生成图片，也不执行任意绘图代码。后端只输出白名单图表配置：

```json
{
  "type": "bar",
  "title": "各区域销售额",
  "x_field": "region",
  "y_field": "revenue"
}
```

后端验证字段来自真实查询结果后，由 Vue 中的 ECharts 渲染。

## 当前技术债

- 尚未接入 Checkpointer；
- 尚未实现真实 Schema 检索；
- SQL 校验器需要补充更多危险函数和方言测试；
- Hybrid 分支暂为顺序执行；
- 前端尚未实现 SSE 和完整表格组件；
- Docker Compose 使用本地演示密码。

