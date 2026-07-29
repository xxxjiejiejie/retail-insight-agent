# v1.2 RAG 检索消融评测

批次 ID：`v12-rag-ablation-20260729`  
运行日期：2026-07-29  
执行方式：本地 BGE Embedding、Chroma、BM25 与 BGE Reranker  
外部调用：0（不调用 DeepSeek、Qwen、LangSmith 或业务数据库）  
数据说明：全部为原创模拟零售制度/SOP，不包含真实企业制度或客户数据

## 评测目标

本批次用于回答三个问题：

1. 制度库从 8 份扩展到约 100 份后，检索链路能否定位到实际包含答案的 chunk；
2. Vector、BM25、RRF 与 RRF + BGE Reranker 四种 Pipeline 的效果和延迟差异如何；
3. 在大量结构相似、主题接近的模拟 SOP 中，Reranker 是否能纠正召回阶段的章节级排序噪声。

![v1.2 RAG 检索消融实验](screenshots/rag-ablation-v12.png)

## 语料与 Ground Truth

| 项目 | 数量/版本 | 说明 |
|---|---:|---|
| 制度文档 | 100 | 8 份种子制度 + 92 份新增原创模拟制度 |
| 业务域 | 10 | 售后、促销、库存、会员、隐私、绩效、定价、订单、门店运营、采购物流 |
| Chunk | 484 | 标题/段落感知分块，使用稳定 `chunk_id` 和 `paragraph_id` |
| 评测问题 | 80 | 60 条直接事实、10 条跨文档、10 条库外问题 |
| 可回答问题 | 70 | 用于 Hit@5、MRR@5、nDCG@5 |
| 库外问题 | 10 | 单独作为诊断集，不混入排序指标 |
| Dev / Test | 28 / 52 | 固定划分，用于后续调参与独立复测 |
| 语料版本 | `9e21449fa587121a` | 根据源文件内容生成 |
| 数据集版本 | `7cec2109a05bd900` | 根据 Ground Truth 生成 |

Ground Truth 直接依据制度编写结构绑定相关 `chunk_id`，没有根据任一检索器的排名反向填写。直接答案 chunk 标记为相关度 2；库外问题不设置相关 chunk。语料校验结果为 100 个唯一 `document_id`、484 个唯一 `chunk_id`、484 个唯一 `paragraph_id`，完全重复正文为 0。

## 指标口径

- **Hit@5**：前 5 个结果中只要出现一个相关 chunk 即记为命中。
- **MRR@5**：第一个相关 chunk 排名的倒数，越接近 1 表示答案出现得越靠前。
- **nDCG@5**：考虑相关度和排序位置的折损累计增益，越接近 1 越好。
- **P50/P95 延迟**：80 条问题在本机本地 Pipeline 上的中位数和尾部延迟。
- **失败样本**：可回答问题的 Top 5 中没有相关 chunk；同一问题可能在多个 Pipeline 下分别产生失败记录。

库外题不计入 Hit@5、MRR@5 和 nDCG@5。裸检索器返回候选不等于系统最终作答，端到端拒答能力继续由真实 RAG 问答评测衡量。

## 四组 Pipeline

1. **Vector**：`BAAI/bge-small-zh-v1.5` + Chroma，取 Top 5。
2. **BM25**：中文字符、连续中文片段与双字词分词，取 Top 5。
3. **RRF**：Vector Top 20 与 BM25 Top 20，以 `k=60` 融合后取 Top 5。
4. **RRF + BGE Reranker**：RRF 候选 Top 12，经 `BAAI/bge-reranker-base` 重排后取 Top 5。

## 结果

| Pipeline | Hit@5 | MRR@5 | nDCG@5 | P50 | P95 | 失败样本 |
|---|---:|---:|---:|---:|---:|---:|
| Vector | 71.43% | 47.31% | 52.54% | 13.25ms | 22.35ms | 20 |
| BM25 | 32.86% | 9.31% | 15.05% | 6.09ms | 8.75ms | 47 |
| RRF | 51.43% | 21.50% | 28.99% | 13.34ms | 22.49ms | 34 |
| **RRF + BGE Reranker** | **84.29%** | **82.50%** | **82.36%** | 191.40ms | 203.46ms | **11** |

相对纯 Vector，RRF + BGE Reranker 的 Hit@5 提高 12.86 个百分点、MRR@5 提高 35.19 个百分点、nDCG@5 提高 29.82 个百分点。代价是 P50 延迟增加约 178ms；在当前离线知识库规模下，这一延迟换取了明显更稳定的答案 chunk 排序。

## 结果分析

### 为什么 BM25 和纯 RRF 较低

新增语料有意保留大量相似 SOP 结构，用来形成接近真实制度库的 hard negatives。问题通常包含制度标题和具体规则，但同一制度的“操作流程”“记录与复盘”等章节也包含相同主题词。BM25 容易把同文档错误章节或相似制度排到前列，导致 chunk 级 Ground Truth 不命中。

RRF 只融合排名，不理解问题与段落的语义对应关系。因此词法召回中的章节噪声会进入融合排名，当前结果低于纯 Vector。这个结果说明“增加一种召回器”并不必然提升最终 Top 5，融合效果必须通过消融实验验证。

### Reranker 带来的改善

BGE Reranker 对“问题—候选 chunk”成对打分，将真正包含发起角色、时限或审批门槛的段落重新排到前列。最终失败从 Vector 的 20 条降到 11 条，其中直接事实题失败 3 条、跨文档题失败 8 条。

跨文档问题仍是主要难点：当前 Hit/MRR/nDCG 只要求命中任一相关 chunk，尚未衡量两个目标文档是否都被覆盖。后续若继续优化评测，应优先增加跨文档 `Document Recall@5` 或覆盖率，而不是继续扩大文档数量。

## 如何复现

以下流程只使用本地语料和本地模型，不调用外部 API：

```powershell
python scripts/generate_policy_corpus.py
python scripts/validate_policy_corpus.py
python scripts/index_policies.py
python scripts/build_rag_ground_truth.py
python scripts/evaluate_rag_ablation.py
python scripts/archive_evaluation_run.py `
  --run-id v12-rag-ablation-20260729 `
  --label "v1.2 RAG 100 份语料与消融评测"
```

主要可提交资产：

- `data/eval/rag_ground_truth.json`：固定 chunk 级 Ground Truth；
- `scripts/evaluate_rag_ablation.py`：四组 Pipeline 与指标实现；
- `app/evaluation/rag_ablation.py`：Hit/MRR/nDCG 计算；
- `frontend/src/components/RAGAblationChart.vue`：前端可视化；
- `docs/screenshots/rag-ablation-v12.png`：真实本地评测页面截图。

`data/runtime` 中的 Chroma/BM25 索引、原始报告和历史批次按设计被 Git 忽略，不包含 API Key。

## 限制与结论边界

- 100 份制度全部为原创模拟语料，数量增加不代表已达到生产企业知识库规模或复杂度；
- Ground Truth 由制度编写结构确定，尚未经过双人独立标注和一致性仲裁；
- 当前指标评价检索排序，不评价最终答案的逐句事实一致性；
- 10 条库外问题只用于诊断，不用于比较裸检索器的“拒答准确率”；
- 延迟来自单机本地环境，不能直接外推到云端、GPU 或高并发场景；
- 跨文档问题尚缺少完整文档覆盖率指标。

因此，本批次可以证明当前模拟语料上的四组检索差异以及 Reranker 的排序增益，但不能解释为生产环境准确率、通用 RAG 基准或真实企业制度问答效果。
