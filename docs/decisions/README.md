# Architecture Decision Records

重要技术取舍按 `ADR-编号-标题.md` 记录背景、候选方案、最终选择、代价和重新评估条件。

第一批建议记录：

1. 为什么最终界面选择 Vue 3，而保留 Streamlit 作为原型；
2. 为什么第一版使用 Chroma，何时迁移 Qdrant；
3. 为什么图表由 ECharts 渲染，而不是调用生图模型；
4. 为什么业务查询必须使用数据库只读账号与 SQLGlot 双重约束。
