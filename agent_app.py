import streamlit as st
from openai import OpenAI
import sqlite3
import json
from datetime import datetime

from prompts import AGENT_SYSTEM_PROMPT, CRITIQUE_PROMPT

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

# ================= 2. API 与 Tools 配置 =================
client = OpenAI(
    api_key=st.secrets["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",
)

# 工具 1：供一线复核 Agent 结单使用
ticket_tools = [{
    "type": "function",
    "function": {
        "name": "submit_resolved_ticket",
        "description": "当工程师提供的流水账信息完整，逻辑闭环（满足现象、动作、现状全覆盖），不需要再追问时，调用此工具提取结构化数据并结单。",
        "parameters": {
            "type": "object",
            "properties": {
                "device_sn": {"type": "string", "description": "设备SN号，若无填 '未知'"},
                "product_line": {"type": "string", "description": "产品线/机型，若无填 '未知'"},
                "fault_type": {"type": "string", "description": "故障分类(如: GPU故障, 主板故障, 线缆故障)"},
                "start_time": {"type": "string", "description": "维修开始时间"},
                "end_time": {"type": "string", "description": "维修结束时间"},
                "final_report": {"type": "string", "description": "代入一线工程师的第一人称视角，撰写的最终标准化现场处理描述报告。"},
                "replacements": {
                    "type": "array",
                    "description": "换件流水，如果没有换件则为空数组",
                    "items": {
                        "type": "object",
                        "properties": {
                            "replace_time": {"type": "string", "description": "更换时间"},
                            "action_info": {"type": "string", "description": "更换信息/原因描述"},
                            "new_type": {"type": "string", "description": "换上件类型"},
                            "new_qn": {"type": "string", "description": "换上件QN"},
                            "old_type": {"type": "string", "description": "换下件类型"},
                            "old_qn": {"type": "string", "description": "换下件QN"}
                        }
                    }
                }
            },
            "required": ["fault_type", "final_report", "replacements"]
        }
    }
}]

# 工具 2：供技术总监 Agent 结构化打分使用
audit_tools = [{
    "type": "function",
    "function": {
        "name": "submit_audit_critique",
        "description": "基于工单内容提交结构化的审计点评与风险评估",
        "parameters": {
            "type": "object",
            "properties": {
                "risk_level": {"type": "string", "enum": ["Low", "Medium", "High"], "description": "工单操作风险等级 (Low: 标准合规, Medium: 存在瑕疵, High: 违反物理护栏或盲目换件)"},
                "overall_score": {"type": "integer", "description": "综合评分 (0-100)"},
                "sop_violation": {"type": "boolean", "description": "是否违反SOP"},
                "critique_text": {"type": "string", "description": "专业的 Markdown 点评正文，必须包含一句话定性、核心逻辑诊断、纠偏指导"}
            },
            "required": ["risk_level", "overall_score", "sop_violation", "critique_text"]
        }
    }
}]

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
        # 稳健的 Session State 初始化
        if "messages" not in st.session_state:
            st.session_state.messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
            st.session_state.display_messages = [{"role": "assistant", "content": "你好！请描述现场排查流水账。如果有 SN号、换件 QN 码也请一并带上。"}]
            st.session_state.is_done = False
            st.session_state.extracted_data = None
            st.session_state.ai_critique = None
            st.session_state.final_report = None

        messages_container = st.container(height=450)
        with messages_container:
            for msg in st.session_state.display_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if getattr(st.session_state, 'is_done', False) is False:
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
                                    tools=ticket_tools,
                                    tool_choice="auto"
                                )
                                response_msg = response.choices[0].message
                                
                                # 判断是追问，还是调用工具结单
                                if response_msg.tool_calls:
                                    tool_call = response_msg.tool_calls[0]
                                    if tool_call.function.name == "submit_resolved_ticket":
                                        arguments = json.loads(tool_call.function.arguments)
                                        st.session_state.is_done = True
                                        st.session_state.extracted_data = arguments
                                        st.session_state.final_report = arguments.get("final_report", "未生成最终报告")
                                        
                                        final_reply = f"### 📄 最终交付报告\n\n{st.session_state.final_report}"
                                        st.markdown(final_reply)
                                        
                                        # 【修复核心：严格遵守 API 的 Tool Call 闭环规范】
                                        # 1. 先把大模型的工具调用请求存入历史
                                        st.session_state.messages.append(response_msg)
                                        # 2. 立即补充一条 role="tool" 的消息作为反馈，告诉 API 工具已经执行完毕
                                        st.session_state.messages.append({
                                            "role": "tool",
                                            "tool_call_id": tool_call.id,
                                            "name": tool_call.function.name,
                                            "content": "{\"status\": \"success\", \"message\": \"工单数据已成功提取\"}"
                                        })
                                        
                                        st.session_state.display_messages.append({"role": "assistant", "content": final_reply})
                                        st.rerun()

        # 后台单路专家审计：强制 JSON 工具输出
        if st.session_state.is_done and st.session_state.ai_critique is None:
            with st.spinner("🧠 顶尖技术总监正在进行高危审计与复盘..."):
                try:
                    crit_msgs = st.session_state.messages.copy()
                    context = f"提取的工单数据：\n{json.dumps(st.session_state.extracted_data, ensure_ascii=False)}\n\n"
                    crit_msgs.append({"role": "user", "content": context + CRITIQUE_PROMPT})
                    
                    crit_res = client.chat.completions.create(
                        model="moonshot-v1-8k",
                        messages=crit_msgs, 
                        temperature=0.3,
                        tools=audit_tools,
                        tool_choice={"type": "function", "function": {"name": "submit_audit_critique"}}
                    )
                    
                    audit_msg = crit_res.choices[0].message
                    if audit_msg.tool_calls:
                        audit_data = json.loads(audit_msg.tool_calls[0].function.arguments)
                        # 将结构化的字典序列化存入数据库
                        st.session_state.ai_critique = json.dumps(audit_data, ensure_ascii=False)
                    else:
                        st.session_state.ai_critique = json.dumps({"risk_level": "Medium", "overall_score": 0, "sop_violation": False, "critique_text": "未按预期生成点评。"}, ensure_ascii=False)
                except Exception as e:
                    st.error(f"生成点评失败: {e}")
                    st.session_state.ai_critique = json.dumps({"risk_level": "High", "overall_score": 0, "sop_violation": True, "critique_text": f"系统解析错误：{e}"}, ensure_ascii=False)
                st.rerun()

        # 工程师核对表单并提交
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
                st.markdown("### 🔧 换件流水")
                reps = st.session_state.extracted_data.get("replacements", [])
                if not reps:
                    reps = [{}] 

                final_reps_data = []
                for i, rep in enumerate(reps):
                    st.markdown(f"**第 {i+1} 次更换**")
                    c1, c2, c3 = st.columns(3)
                    t_val = c1.text_input(f"更换时间", value=rep.get("replace_time", ""), key=f"t_{i}")
                    i_val = c2.text_area(f"更换信息描述", value=rep.get("action_info", ""), key=f"i_{i}", height=68)
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
                    # 清理状态，准备接下一单
                    for key in ['messages', 'display_messages', 'is_done', 'extracted_data', 'ai_critique', 'final_report']:
                        if key in st.session_state:
                            del st.session_state[key]
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
                    try:
                        reps_list = json.loads(h_reps) if h_reps else []
                        if reps_list:
                            st.table(reps_list)
                    except:
                        pass

# =====================================================================
#                          👔 交付总监/PM 视图 (Dashboard View)
# =====================================================================
elif role == "👔 交付总监/PM":

    @st.dialog("🎫 工单详细审计报告", width="large")
    def show_ticket_dialog(t_id, t_name, t_sn, t_fault, t_time, t_critique_data, t_report, t_reps):
        st.subheader(f"工单 #{t_id} | 责任人: {t_name}")
        st.caption(f"设备SN: {t_sn} | 故障类型: {t_fault} | 提交时间: {t_time}")
        
        # 结构化展示总监打分
        r_level = t_critique_data.get("risk_level", "Unknown")
        r_color = "🔴" if r_level == "High" else "🟡" if r_level == "Medium" else "🟢"
        
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("质量总分", f"{t_critique_data.get('overall_score', 0)} 分")
        sc2.metric("操作风险等级", f"{r_color} {r_level}")
        sc3.metric("违规 SOP", "是" if t_critique_data.get("sop_violation") else "否")
        
        st.warning(f"**🧠 AI 技术总监深度点评：**\n\n{t_critique_data.get('critique_text', '无具体点评内容')}")
        
        tab1, tab2 = st.tabs(["📝 结构化换件流水", "📄 原始闭环报告"])
        with tab1:
            try:
                reps_list = json.loads(t_reps) if t_reps else []
                if reps_list: st.table(reps_list) 
                else: st.write("无换件记录")
            except:
                st.write("数据解析异常")
        with tab2:
            st.markdown(t_report)

    st.title("📊 全局交付审计与技术总监看板")
    st.caption("全局视野：掌控工单流转，基于结构化 AI 打分进行质量管控。")
    
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT id, engineer_name, device_sn, fault_type, created_at, ai_critique, final_report, replacements FROM tickets ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()

    if not rows:
        st.info("当前工单库为空，等待工程师提交。")
    else:
        # PM 列表渲染
        hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([1, 1.5, 2, 2, 1.5, 1.5])
        hc1.write("**ID**")
        hc2.write("**责任人**")
        hc3.write("**故障类型**")
        hc4.write("**时间**")
        hc5.write("**质控预警**")
        hc6.write("**操作**")
        st.markdown("---")
        
        for row in rows:
            t_id, t_name, t_sn, t_fault, t_time, t_critique_str, t_report, t_reps = row
            
            # 解析存储的结构化 JSON 评价
            try:
                critique_data = json.loads(t_critique_str) if t_critique_str else {}
            except:
                critique_data = {"risk_level": "Unknown"}
                
            risk = critique_data.get("risk_level", "Unknown")
            risk_badge = "🔴 高危" if risk == "High" else "🟡 瑕疵" if risk == "Medium" else "🟢 规范"
            
            c1, c2, c3, c4, c5, c6 = st.columns([1, 1.5, 2, 2, 1.5, 1.5])
            c1.write(f"#{t_id}")
            c2.write(t_name)
            c3.write(t_fault)
            c4.caption(t_time[5:16]) # 只显示日期和时间简写
            c5.write(risk_badge)
            
            if c6.button("复盘详情", key=f"btn_{t_id}"):
                show_ticket_dialog(t_id, t_name, t_sn, t_fault, t_time, critique_data, t_report, t_reps)
