from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from pydantic import BaseModel

from app.core.config import get_settings
from app.rag.runtime import get_policy_reranker, get_policy_retriever
from app.tools.models import RenderAnalysisReportArgs, SearchPolicyEvidenceArgs

REPORT_STYLE = """
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #eef2f0;
  color: #1d2925;
  font-family: Arial, "Microsoft YaHei", sans-serif;
  line-height: 1.7;
}
main {
  width: min(1040px, calc(100% - 40px));
  margin: 36px auto;
  padding: 44px 52px;
  border-top: 6px solid #176b4d;
  background: #fff;
  box-shadow: 0 12px 32px rgba(25, 48, 39, 0.1);
}
header { padding-bottom: 24px; border-bottom: 1px solid #d9e2de; }
h1 { margin: 0 0 12px; font-size: 30px; line-height: 1.3; letter-spacing: 0; }
h2 { margin: 30px 0 10px; font-size: 18px; letter-spacing: 0; }
.meta, .muted { color: #63726c; font-size: 13px; }
.tag {
  display: inline-block;
  padding: 3px 9px;
  border-radius: 4px;
  background: #e8f3ee;
  color: #176b4d;
  font-size: 12px;
}
.table-wrap { overflow: auto; border: 1px solid #d9e2de; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td {
  padding: 9px 11px;
  border-bottom: 1px solid #e7ecea;
  text-align: left;
  white-space: nowrap;
}
th { background: #f4f7f5; color: #31443d; }
.chart { padding: 18px; border: 1px solid #d9e2de; }
.chart-row {
  display: grid;
  grid-template-columns: minmax(90px, 1fr) 3fr 90px;
  gap: 12px;
  align-items: center;
  margin: 10px 0;
  font-size: 13px;
}
.chart-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chart-track { height: 12px; background: #e8eeeb; }
.chart-bar { display: block; height: 100%; background: #2f8062; }
.chart-row strong { text-align: right; }
.evidence { padding-left: 22px; }
.evidence li { margin: 12px 0; }
code {
  display: block;
  padding: 14px;
  border-left: 3px solid #7b8f87;
  background: #f4f7f5;
  font-size: 12px;
  white-space: pre-wrap;
}
footer {
  margin-top: 36px;
  padding-top: 18px;
  border-top: 1px solid #d9e2de;
  color: #63726c;
  font-size: 12px;
}
@media print {
  body { background: #fff; }
  main { width: 100%; margin: 0; box-shadow: none; }
}
"""


def _citation_payload(item: Any) -> dict[str, Any]:
    chunk = item.chunk
    return {
        "source": chunk.title,
        "section": chunk.section,
        "page": chunk.page,
        "excerpt": chunk.content[:400],
        "document_id": chunk.document_id,
        "version": chunk.version,
        "paragraph_id": chunk.paragraph_id,
        "chunk_id": chunk.chunk_id,
        "relevance_score": round(item.score, 6),
    }


async def search_policy_evidence(raw_args: BaseModel, context: Any) -> dict[str, Any]:
    if not isinstance(raw_args, SearchPolicyEvidenceArgs):
        raise TypeError("unexpected tool arguments")
    settings = get_settings()
    retriever = get_policy_retriever()
    reranker = get_policy_reranker()
    candidates = await retriever.retrieve(
        raw_args.query,
        top_k=settings.rag_retrieval_top_k,
    )
    ranked = await reranker.rerank(
        raw_args.query,
        candidates,
        top_k=raw_args.limit,
    )
    evidence = [
        _citation_payload(item)
        for item in ranked
        if item.score >= settings.rag_min_relevance_score
    ][: raw_args.limit]
    context.policy_evidence = evidence
    return {"count": len(evidence), "evidence": evidence}


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _render_table(sql_result: dict[str, Any] | None) -> str:
    if not sql_result:
        return '<p class="muted">本报告没有附带结构化数据表。</p>'
    columns = [str(column) for column in sql_result.get("columns", [])]
    rows = list(sql_result.get("rows", []))
    if not columns or not rows:
        return '<p class="muted">查询没有返回可展示的数据行。</p>'
    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(_format_value(row.get(column)))}</td>" for column in columns
        )
        + "</tr>"
        for row in rows[:100]
        if isinstance(row, dict)
    )
    truncated = ""
    row_count = int(sql_result.get("row_count", len(rows)))
    if row_count > len(rows) or len(rows) > 100:
        truncated = f'<p class="muted">报告展示前 {min(len(rows), 100)} 行，共 {row_count} 行。</p>'
    return (
        f'{truncated}<div class="table-wrap"><table><thead><tr>{header}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _render_chart(
    sql_result: dict[str, Any] | None,
    chart_spec: dict[str, Any] | None,
) -> str:
    if not sql_result or not chart_spec:
        return ""
    rows = [row for row in sql_result.get("rows", []) if isinstance(row, dict)][:12]
    x_field = str(chart_spec.get("x_field", ""))
    y_field = str(chart_spec.get("y_field", ""))
    plotted: list[tuple[str, float]] = []
    for row in rows:
        value = row.get(y_field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            plotted.append((_format_value(row.get(x_field)), float(value)))
    if not plotted:
        return ""
    maximum = max((abs(value) for _, value in plotted), default=0) or 1
    bars = "".join(
        '<div class="chart-row">'
        f'<span class="chart-label">{escape(label)}</span>'
        '<span class="chart-track">'
        f'<span class="chart-bar" style="width:{max(2, abs(value) / maximum * 100):.1f}%"></span>'
        "</span>"
        f'<strong>{escape(_format_value(value))}</strong>'
        "</div>"
        for label, value in plotted
    )
    title = escape(str(chart_spec.get("title") or "数据对比"))
    return (
        f"<section><h2>{title}</h2>"
        f'<div class="chart" role="img" aria-label="{title}">{bars}</div></section>'
    )


def _render_evidence(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return ""
    items = "".join(
        "<li>"
        f'<strong>{escape(str(item.get("source") or "制度文档"))}</strong>'
        f' · {escape(str(item.get("version") or "未标注版本"))}'
        f'<p>{escape(str(item.get("section") or "相关章节"))}：'
        f'{escape(str(item.get("excerpt") or ""))}</p>'
        "</li>"
        for item in evidence
    )
    return f"<section><h2>制度引用</h2><ol class=\"evidence\">{items}</ol></section>"


def _report_html(
    args: RenderAnalysisReportArgs,
    *,
    source_turn: dict[str, Any],
    evidence: list[dict[str, Any]],
    created_at: datetime,
) -> str:
    sections = "".join(
        f"<section><h2>{escape(section.heading)}</h2>"
        f"<p>{escape(section.content).replace(chr(10), '<br>')}</p></section>"
        for section in args.sections
    )
    sql_result = source_turn.get("sql_result")
    chart = _render_chart(sql_result, source_turn.get("chart_spec")) if args.include_chart else ""
    sql = escape(str(source_turn.get("generated_sql") or "未提供"))
    query = escape(str(source_turn.get("query") or "未提供"))
    source_turn_id = escape(str(source_turn.get("turn_id") or ""))
    report_type = "经营分析报告" if args.report_type == "analysis" else "管理层简报"
    generated_at = created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    table = _render_table(sql_result)
    evidence_html = _render_evidence(evidence)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(args.title)}</title>
<style>{REPORT_STYLE}</style>
</head>
<body><main>
<header>
<span class="tag">{report_type}</span>
<h1>{escape(args.title)}</h1>
<p class="meta">生成时间：{generated_at}</p>
</header>
{sections}
{chart}
<section><h2>数据明细</h2>{table}</section>
{evidence_html}
<section><h2>数据来源</h2>
<p><strong>原始问题：</strong>{query}</p>
<p><strong>来源轮次：</strong>{source_turn_id}</p>
<code>{sql}</code>
</section>
<footer>
本报告由 Retail Insight Agent 根据已执行的查询结果生成。
结论仅覆盖报告中列出的数据范围。
</footer>
</main></body>
</html>"""


async def render_analysis_report(raw_args: BaseModel, context: Any) -> dict[str, Any]:
    if not isinstance(raw_args, RenderAnalysisReportArgs):
        raise TypeError("unexpected tool arguments")
    source_turn = context.source_turn
    if not source_turn.get("sql_result"):
        raise ValueError("source analysis has no structured result")

    settings = get_settings()
    output_dir = Path(settings.report_output_path).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = str(uuid4())
    created_at = datetime.now(UTC)
    artifact = {
        "report_id": report_id,
        "title": raw_args.title,
        "format": "html",
        "download_url": (
            f"{settings.api_prefix}/reports/{report_id}?"
            + urlencode({"session_id": context.session_id})
        ),
        "source_turn_id": str(source_turn["turn_id"]),
        "created_at": created_at.isoformat(),
    }
    html = _report_html(
        raw_args,
        source_turn=source_turn,
        evidence=context.policy_evidence,
        created_at=created_at,
    )
    (output_dir / f"{report_id}.html").write_text(html, encoding="utf-8")
    metadata = {**artifact, "session_id": context.session_id}
    (output_dir / f"{report_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"count": 1, "artifact": artifact}
