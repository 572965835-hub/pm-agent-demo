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
                        with st.spinner("Agent 正在严苛审视排查逻辑..."):
                            try:
                                response = client.chat.completions.create(
                                    model="moonshot-v1-8k",
                                    messages=st.session_state.messages,
                                    temperature=0.1, # 极其理性的温度，避免随机发散
                                )
                                reply = response.choices[0].message.content
                                
                                # 【极度强硬的路由判定器】
                                if "<FINAL_REPORT>" in reply:
                                    st.session_state.is_done = True
                                    reply = reply.replace("<FINAL_REPORT>", "### 📄 最终交付报告\n\n").strip()
                                else:
                                    # 如果 AI 没有给出完结信号，强制剥离内部追问标签
                                    reply = reply.replace("[打回追问]", "").strip()
                                
                                st.markdown(reply)
                                
                                st.session_state.messages.append({"role": "assistant", "content": reply})
                                st.session_state.display_messages.append({"role": "assistant", "content": reply})
                                
                            except Exception as e:
                                st.error(f"API 出错：{e}")
                
                # 【终极状态同步】无论走到哪个分支，立刻刷新前端保持状态完全一致
                st.rerun()

        # ================= 后台双路提取：JSON 表单 + 技术总监点评 =================
        if st.session_state.is_done and st.session_state.extracted_data is None:
            with st.spinner("🔄 逻辑已闭环！正在提取表单数据..."):
                try:
                    extract_msgs = st.session_state.messages.copy()
                    extract_msgs.append({"role": "user", "content": JSON_EXTRACTION_PROMPT})
                    json_res = client.chat.completions.create(
                        model="moonshot-v1-8k", messages=extract_msgs, temperature=0.1
                    )
                    raw_json = json_res.choices[0].message.content.strip().replace("```json", "").replace("```", "")
                    st.session_state.extracted_data = json.loads(raw_json)
                except Exception as e:
                    st.error(f"提取表单失败: {e}")
                    st.session_state.extracted_data = {"replacements": []}

            with st.spinner("🧠 全球顶尖技术总监正在撰写深度复盘报告..."):
                try:
                    crit_msgs = st.session_state.messages.copy()
                    crit_msgs.append({"role": "user", "content": CRITIQUE_PROMPT})
                    crit_res = client.chat.completions.create(
                        model="moonshot-v1-8k", messages=crit_msgs, temperature=0.3
                    )
                    st.session_state.ai_critique = crit_res.choices[0].message.content
                    st.session_state.final_report = st.session_state.display_messages[-1]["content"]
                except Exception as e:
                    st.error(f"生成点评失败: {e}")
                    st.session_state.ai_critique = "点评生成失败。"
                st.rerun()

        # ================= 工程师核对表单并提交 =================
        if st.session_state.extracted_data is not None:
            st.success("✅ 逻辑验证通过！请核对结构化流水后归档（提交后不可修改）。")
            with st.form("ticket_form"):
                st.markdown("### 📝 基础信息")
                col1, col2 = st.columns(2)
                device_sn = col1.text_input("设备 SN 号", value=st.session_state.extracted_data.get("device_sn", ""))
                product_line = col2.text_input("产品线/机型", value=st.session_state.extracted_data.get("product_line", ""))
                fault_type = col1.text_input("故障类型", value=st.session_state.extracted_data.get("fault_type", ""))
                start_time = col2.text_input("维修开始时间", value=st.session_state.extracted_data.get("start_time", ""))
                end_time = col1.text_input("维修结束时间", value=st.session_state.extracted_data.get("end_time", ""))
                
                st.divider()
                st.markdown("### 🔧 换件流水 (动态分离展示)")
                reps = st.session_state.extracted_data.get("replacements", [])
                if not reps:
                    reps = [{}] 

                final_reps_data = []
                for i, rep in enumerate(reps):
                    st.markdown(f"**第 {i+1} 次更换**")
                    c1, c2, c3 = st.columns(3)
                    t_val = c1.text_input(f"更换时间", value=rep.get("replace_time", ""), key=f"t_{i}")
                    i_val = c2.text_area(f"更换信息描述", value=rep.get("action_info", ""), key=f"i_{i}", height=100)
                    nt_val = c3.text_input(f"换上件类型", value=rep.get("new_type", ""), key=f"nt_{i}")
                    
                    c4, c5, c6 = st.columns(3)
                    nq_val = c4.text_input(f"换上件QN", value=rep.get("new_qn", ""), key=f"nq_{i}")
                    ot_val = c5.text_input(f"换下件类型", value=rep.get("old_type", ""), key=f"ot_{i}")
                    oq_val = c6.text_input(f"换下件QN", value=rep.get("old_qn", ""), key=f"oq_{i}")
                    st.markdown("---")
                    
                    final_reps_data.append({
                        "更换时间": t_val, "更换信息": i_val, 
                        "换上件类型": nt_val, "换上件QN": nq_val, 
                        "换下件类型": ot_val, "换下件QN": oq_val
                    })
                
                submit_btn = st.form_submit_button("💾 确认无误，提交至工单库", type="primary", use_container_width=True)
                
                if submit_btn:
                    reps_json = json.dumps(final_reps_data, ensure_ascii=False)
                    conn = sqlite3.connect('tickets.db')
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO tickets (engineer_name, device_sn, product_line, fault_type, start_time, end_time, replacements, final_report, ai_critique, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (engineer_name, device_sn, product_line, fault_type, start_time, end_time, reps_json, st.session_state.final_report, st.session_state.ai_critique, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    
                    st.toast("工单已锁定并归档！", icon="🔒")
                    del st.session_state.messages
                    del st.session_state.display_messages
                    del st.session_state.is_done
                    del st.session_state.extracted_data
                    del st.session_state.ai_critique
                    st.rerun()

    with tab_history:
        conn = sqlite3.connect('tickets.db')
        c = conn.cursor()
        c.execute('SELECT id, device_sn, fault_type, created_at, final_report, replacements FROM tickets WHERE engineer_name = ? ORDER BY id DESC', (engineer_name,))
        history_rows = c.fetchall()
        conn.close()
        
        if not history_rows:
            st.info("您还没有提交过历史工单。")
        else:
            for row in history_rows:
                h_id, h_sn, h_fault, h_time, h_report, h_reps = row
                with st.expander(f"🔒 历史工单 #{h_id} | SN: {h_sn} | 时间: {h_time}"):
                    st.markdown(h_report)
                    
                    reps_list = []
                    if h_reps:
                        try:
                            reps_list = json.loads(h_reps)
                        except Exception:
                            reps_list = [{"历史文本记录": h_reps}]
                            
                    if reps_list:
                        st.markdown("**换件流水：**")
                        st.table(reps_list) 

# =====================================================================
#                          👔 交付总监/PM 视图 (Dashboard View)
# =====================================================================
elif role == "👔 交付总监/PM":

    @st.dialog("🎫 工单详细审计报告", width="large")
    def show_ticket_dialog(t_id, t_name, t_sn, t_fault, t_time, t_critique, t_report, t_reps):
        st.subheader(f"工单 #{t_id} | 责任人: {t_name}")
        st.caption(f"设备SN: {t_sn} | 故障类型: {t_fault} | 提交时间: {t_time}")
        
        st.warning(f"**🧠 AI 技术总监审计点评：**\n\n{t_critique}")
        
        tab1, tab2 = st.tabs(["📝 结构化换件流水", "📄 原始闭环报告"])
        with tab1:
            reps_list = []
            if t_reps:
                try:
                    reps_list = json.loads(t_reps)
                except Exception:
                    reps_list = [{"历史文本记录": t_reps}]
                    
            if reps_list:
                st.table(reps_list) 
            else:
                st.write("无换件记录")
        with tab2:
            st.markdown(t_report)

    st.title("📊 全局交付审计与技术总监看板")
    st.caption("全局视野：掌控工单流转，快速审核 AI 专家提供的交付动作复盘。")
    
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT id, engineer_name, device_sn, fault_type, created_at, ai_critique, final_report, replacements FROM tickets ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()

    if not rows:
        st.info("当前工单库为空，等待工程师提交。")
    else:
        total_tickets = len(rows)
        replaced_count = 0
        for r in rows:
            try:
                reps = json.loads(r[7])
                if reps and len(reps) > 0 and "更换时间" in reps[0]: 
                    replaced_count += 1
            except:
                pass

        col1, col2, col3 = st.columns(3)
        col1.metric(label="今日工单总数", value=total_tickets)
        col2.metric(label="涉及换件单数", value=replaced_count)
        col3.metric(label="智能审计覆盖率", value="100%")
        
        st.divider()
        st.markdown("### 📋 工单数据流转中心")

        hc1, hc2, hc3, hc4, hc5 = st.columns([1, 2, 2, 3, 2])
        hc1.write("**工单ID**")
        hc2.write("**责任人**")
        hc3.write("**故障类型**")
        hc4.write("**提交时间**")
        hc5.write("**操作**")
        st.markdown("---")
        
        for row in rows:
            t_id, t_name, t_sn, t_fault, t_time, t_critique, t_report, t_reps = row
            c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 3, 2])
            c1.write(f"#{t_id}")
            c2.write(t_name)
            c3.write(t_fault)
            c4.write(t_time)
            
            if c5.button("查看详情", key=f"btn_{t_id}"):
                show_ticket_dialog(t_id, t_name, t_sn, t_fault, t_time, t_critique, t_report, t_reps)
