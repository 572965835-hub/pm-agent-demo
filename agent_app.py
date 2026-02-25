import streamlit as st
from openai import OpenAI
import sqlite3
import json
from datetime import datetime

# ================= 1. 数据库初始化 =================
def init_db():
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    # 创建工单表
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engineer_name TEXT,
            device_sn TEXT,
            product_line TEXT,
            fault_type TEXT,
            start_time TEXT,
            end_time TEXT,
            replacements TEXT, -- 存 JSON 字符串
            final_report TEXT,
            ai_critique TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= 2. Kimi API 配置 =================
client = OpenAI(
    api_key=st.secrets["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",
)

st.set_page_config(page_title="PIA 智能工单系统", page_icon="🤖", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

# ================= 3. 侧边栏：角色切换与模拟登录 =================
with st.sidebar:
    st.header("👤 用户身份")
    role = st.selectbox("请选择您的角色：", ["👨‍🔧 一线工程师 (FE)", "👔 项目经理 (PM)"])
    
    if role == "👨‍🔧 一线工程师 (FE)":
        engineer_name = st.text_input("请输入您的姓名/工号：", value="张工")
    st.divider()

# =====================================================================
#                          👨‍🔧 工程师视图 (FE View)
# =====================================================================
if role == "👨‍🔧 一线工程师 (FE)":
    st.title(f"🤖 欢迎, {engineer_name}")
    st.caption("硬件交付 PIA 智能复核 Agent | 只有逻辑闭环才能生成报告并提取表单。")
    
    # 核心 Prompt
    SYSTEM_PROMPT = """
    你是一位资深的服务器硬件交付项目经理。作为【智能工单复核助手】，通过多轮对话审查现场工程师的排查记录。
    必须严格满足【PIA 模型】：P(现象明确)、I(必须有交叉验证/对调测试动作，只换件不验证必须拦截追问)、A(现状清晰)。
    如果信息不全，请平易近人地追问。
    如果逻辑完美闭环，请停止提问，直接输出标准化报告，并且必须且只能以“【最终交付报告】”这六个字开头！
    """

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.display_messages = [{"role": "assistant", "content": "你好！我是智能复核助手。请描述现场排查流水账，我会帮你把关逻辑。如果有 SN号、换件 QN 码也请一并带上。"}]
        st.session_state.is_done = False
        st.session_state.extracted_data = None

    # 渲染聊天记录
    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 对话逻辑
    if not st.session_state.is_done:
        if prompt := st.chat_input("请输入排查记录或回答..."):
            st.session_state.display_messages.append({"role": "user", "content": prompt})
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Agent 正在推演 PIA 逻辑..."):
                    try:
                        response = client.chat.completions.create(
                            model="moonshot-v1-8k",
                            messages=st.session_state.messages,
                            temperature=0.2,
                        )
                        reply = response.choices[0].message.content
                        st.markdown(reply)
                        
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                        st.session_state.display_messages.append({"role": "assistant", "content": reply})
                        
                        if "【最终交付报告】" in reply:
                            st.session_state.is_done = True
                            st.rerun()
                    except Exception as e:
                        st.error(f"API 出错：{e}")

    # ================= 隐藏的黑科技：后台提取 JSON 结构 =================
    if st.session_state.is_done and st.session_state.extracted_data is None:
        with st.spinner("🔄 逻辑已闭环！正在为您自动提取工单表单并生成系统分析..."):
            # 让 Kimi 直接输出 JSON
            json_prompt = """
            请根据以上的完整对话历史，提取工单关键信息，并对工程师的排查逻辑进行专业点评。
            必须严格输出为合法的 JSON 格式，不要包含任何 markdown 符号（如 ```json）。
            字段如下：
            {
                "device_sn": "设备SN号，没有则填 未知",
                "product_line": "产品线/机型，没有则填 未知",
                "fault_type": "故障分类(如: GPU故障, 主板故障, 线缆故障)",
                "start_time": "维修开始时间",
                "end_time": "维修结束时间",
                "replacements": "换下件与换上件的流水描述，包含QN码和是否有效更换。如：换下内存(QN:A1)换上内存(QN:B2)，有效",
                "ai_critique": "作为顶级硬件专家，客观评价工程师的排查逻辑是否严谨、是否规范使用了交叉验证法，并给出 1-5 星的评分。限100字内。"
            }
            """
            try:
                extract_msgs = st.session_state.messages.copy()
                extract_msgs.append({"role": "user", "content": json_prompt})
                json_response = client.chat.completions.create(
                    model="moonshot-v1-8k",
                    messages=extract_msgs,
                    temperature=0.1,
                )
                raw_json = json_response.choices[0].message.content.strip().replace("```json", "").replace("```", "")
                st.session_state.extracted_data = json.loads(raw_json)
                st.session_state.final_report = st.session_state.display_messages[-1]["content"]
                st.rerun()
            except Exception as e:
                st.error(f"提取表单失败，请重试。错误: {e}")

    # ================= 工程师确认并提交表单 =================
    if st.session_state.extracted_data is not None:
        st.success("✅ 表单已自动生成，请核对后提交归档！")
        with st.form("ticket_form"):
            st.markdown("### 📝 工单结构化数据确认")
            col1, col2 = st.columns(2)
            with col1:
                device_sn = st.text_input("设备 SN 号", value=st.session_state.extracted_data.get("device_sn", ""))
                product_line = st.text_input("产品线/机型", value=st.session_state.extracted_data.get("product_line", ""))
                fault_type = st.text_input("故障类型", value=st.session_state.extracted_data.get("fault_type", ""))
            with col2:
                start_time = st.text_input("维修开始时间", value=st.session_state.extracted_data.get("start_time", ""))
                end_time = st.text_input("维修结束时间", value=st.session_state.extracted_data.get("end_time", ""))
                replacements = st.text_area("换件流水 (QN码)", value=st.session_state.extracted_data.get("replacements", ""), height=100)
            
            # AI 的点评先藏在这里，存入数据库，工程师不一定需要看
            ai_critique = st.session_state.extracted_data.get("ai_critique", "")
            
            submit_btn = st.form_submit_button("💾 确认无误，提交至工单库", type="primary", use_container_width=True)
            
            if submit_btn:
                # 写入 SQLite 数据库
                conn = sqlite3.connect('tickets.db')
                c = conn.cursor()
                c.execute('''
                    INSERT INTO tickets (engineer_name, device_sn, product_line, fault_type, start_time, end_time, replacements, final_report, ai_critique, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (engineer_name, device_sn, product_line, fault_type, start_time, end_time, replacements, st.session_state.final_report, ai_critique, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                conn.close()
                
                st.toast("提交成功！", icon="🎉")
                # 清理状态，准备下一单
                del st.session_state.messages
                del st.session_state.display_messages
                del st.session_state.is_done
                del st.session_state.extracted_data
                st.rerun()

# =====================================================================
#                          👔 项目经理视图 (PM View)
# =====================================================================
elif role == "👔 项目经理 (PM)":
    st.title("📊 全局工单管理与审计质量看板")
    st.caption("查看所有工程师提交的结构化工单，以及 AI 对每次操作的专业评分点评。")
    
    # 从数据库读取所有工单
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT id, engineer_name, device_sn, fault_type, created_at, ai_critique, final_report, replacements FROM tickets ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()

    if not rows:
        st.info("当前工单库为空，等待工程师提交。")
    else:
        # 构建一个简易的数据表格视图供 PM 快速浏览
        for row in rows:
            t_id, t_name, t_sn, t_fault, t_time, t_critique, t_report, t_reps = row
            
            # 使用 expander 作为一个独立卡片
            with st.expander(f"🎫 工单 #{t_id} | 工程师: {t_name} | 故障: {t_fault} | 提交时间: {t_time}", expanded=False):
                # 核心高亮：AI 专家点评 (给PM看的内容)
                st.info(f"**🤖 AI 专家审计点评：**\n\n{t_critique}")
                
                tab1, tab2 = st.tabs(["📝 结构化换件流水", "📄 标准交付报告"])
                with tab1:
                    st.markdown(f"**设备 SN：** {t_sn}")
                    st.markdown("**备件更换详情：**")
                    st.text(t_reps)
                with tab2:
                    st.markdown(t_report)
