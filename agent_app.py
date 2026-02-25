import streamlit as st
from openai import OpenAI
import sqlite3
import json
from datetime import datetime

from prompts import AGENT_SYSTEM_PROMPT, JSON_EXTRACTION_PROMPT, CRITIQUE_PROMPT

# ================= 1. 数据库初始化 =================
def init_db():
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engineer_name TEXT,
            device_sn TEXT,
            product_line TEXT,
            fault_type TEXT,
            start_time TEXT,
            end_time TEXT,
            replacements TEXT, 
            final_report TEXT,
            ai_critique TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= 2. API 配置 =================
client = OpenAI(
    api_key=st.secrets["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",
)

st.set_page_config(page_title="PIA 智能交付与审计系统", page_icon="🤖", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

# ================= 3. 侧边栏：角色路由 =================
with st.sidebar:
    st.header("👤 用户身份")
    role = st.selectbox("请选择您的角色：", ["👨‍🔧 一线工程师 (FE)", "👔 交付总监/PM"])
    
    if role == "👨‍🔧 一线工程师 (FE)":
        engineer_name = st.text_input("请输入您的姓名/工号：", value="张工")
    st.divider()

# =====================================================================
#                          👨‍🔧 工程师视图 (FE View)
# =====================================================================
if role == "👨‍🔧 一线工程师 (FE)":
    st.title(f"🤖 欢迎, {engineer_name}")
    st.caption("硬件交付 PIA 智能复核 Agent | 只有逻辑闭环才能结单。")
    
    tab_work, tab_history = st.tabs(["💬 当前工单处理", "🗂️ 我的历史工单 (只读)"])
    
    with tab_work:
        if "messages" not in st.session_state:
            st.session_state.messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
            st.session_state.display_messages = [{"role": "assistant", "content": "你好！请描述现场排查流水账。如果有 SN号、换件 QN 码也请一并带上。"}]
            st.session_state.is_done = False
            st.session_state.extracted_data = None
            st.session_state.ai_critique = None

        messages_container = st.container(height=450)
        with messages_container:
            for msg in st.session_state.display_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if not st.session_state.is_done:
            if prompt := st.chat_input("请输入现场排查流水账..."):
                st.session_state.display_messages.append({"role": "user", "content": prompt})
                st.session_state.messages.append({"role": "user", "content": prompt})
                
                with messages_container:
                    with st.chat_message("user"):
                        st.markdown(prompt)

                    with st.chat_message("assistant"):
                        with st.spinner("Agent 正在推演逻辑..."):
                            try:
                                response = client.chat.completions.create(
                                    model="moonshot-v1-8k",
                                    messages=st.session_state.messages,
                                    temperature=0.2,
                                )
                                reply = response.choices[0].message.content
                                
                                # 【顶级防误
