import os
from uuid import uuid4

import requests
import streamlit as st

API_URL = os.getenv("RETAIL_API_URL", "http://localhost:8000/api/v1/chat")

st.set_page_config(page_title="Retail Insight Agent", layout="wide")
st.title("零售经营分析与制度知识问答智能体")
st.caption("Streamlit 仅用于验证后端链路；最终展示前端使用 Vue 3。")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())

query = st.text_input("请输入经营分析或制度问题", placeholder="例如：哪个区域的销售额最高？")

if st.button("发送", type="primary", disabled=not query.strip()):
    try:
        response = requests.post(
            API_URL,
            json={"query": query, "session_id": st.session_state.session_id},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        st.error(f"请求后端失败：{exc}")
    else:
        st.subheader("回答")
        st.write(result["answer"])
        st.caption(f"路由：{result['intent']}")

        if result.get("generated_sql"):
            st.subheader("生成的 SQL")
            st.code(result["generated_sql"], language="sql")
        if result.get("sql_result"):
            st.subheader("查询结果")
            st.dataframe(result["sql_result"])
        if result.get("citations"):
            st.subheader("引用")
            st.json(result["citations"])
        if result.get("metrics"):
            st.subheader("运行指标")
            st.json(result["metrics"])

