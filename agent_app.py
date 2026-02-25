import streamlit as st
import time
import google.generativeai as genai

# 配置 Gemini API（安全地从 Streamlit Secrets 中读取）
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# 初始化模型 (使用适合文本处理的模型)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="故障单智能复核 Agent", page_icon="🤖", layout="centered")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

if 'step' not in st.session_state:
    st.session_state.step = 1
if 'initial_input' not in st.session_state:
    st.session_state.initial_input = ""

st.title("🤖 硬件交付工单智能复核")
st.caption("AI 自动识别逻辑断层，引导补充规范数据，一键生成交付报告。")
st.divider()

# ================= 真实调用大模型生成追问 =================
def generate_dynamic_questions(initial_record):
    # 这里嵌入了我们之前精心打磨的“智能工单复核机器人” Prompt
    prompt = f"""
    你现在是一个部署在服务器交付与运维工单系统中的【智能工单复核机器人】。
    你的核心任务是：自动审阅现场工程师提交的故障排查记录，识别其中的逻辑断层和信息缺失，并生成结构化的追问清单。

    【必须遵守的规则】：
    1. 只能问现场工程师能回答的操作细节（如：拔插、对调、脚本测试结果、初始报错截图）。严禁提问研发/供应链问题。
    2. 机器处于交付上架测试阶段，尚未上线。严禁提问线上业务问题。
    3. 保持客观、专业的 AI 助手语调。不要带有情绪化指责。

    【输出格式】：
    请输出 3 到 5 个最核心的追问，直接以问题呈现，不要输出额外的寒暄和解释。问题要细化到具体的排查动作或结果。
    
    以下是工程师的实际排查记录，请分析并生成追问：
    {initial_record}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"调用 AI 模型时出错啦，请检查 API Key 或网络：{e}"

# ================= 真实调用大模型生成最终报告 =================
def generate_dynamic_report(initial_record, answers):
    prompt = f"""
    你是一位资深的服务器交付项目经理。请根据工程师最初提供的排查记录，以及他刚刚补充的详细解答，
    融合撰写一份结构化、逻辑严密、符合项目交付审计标准的最终故障排查报告。

    初始排查记录：
    {initial_record}

    工程师补充的详细解答：
    {answers}

    请直接输出报告正文，包含“初始故障现象”、“排查过程与逻辑闭环”、“最终结果与验收确认”三个标准段落。不要有其他废话。
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"生成报告时出错啦：{e}"

# ================= UI 流程控制 =================
if st.session_state.step == 1:
    with st.chat_message("assistant"):
        st.write("你好！我是工单复核助手。请把现场的**排查流水账**发给我，我来帮你查漏补缺。")
    
    initial_input = st.text_area("📝 粘贴现场排查记录：", height=150)
    
    if st.button("开始智能分析 ✨", type="primary", use_container_width=True):
        if initial_input.strip() == "":
            st.warning("请先输入排查记录哦！")
        else:
            st.session_state.initial_input = initial_input
            with st.spinner('AI 正在推演排查逻辑，寻找信息断层...'):
                # 真正调用 AI 接口！
                st.session_state.dynamic_questions = generate_dynamic_questions(initial_input)
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    with st.expander("查看原始排查记录", expanded=False):
        st.info(st.session_state.initial_input)

    with st.chat_message("assistant"):
        st.write("我分析完了，基于你提供的记录，你需要补充以下关键细节才能闭环：")
        
    st.markdown("### 🔍 AI 智能追问")
    # 展示大模型真实思考后生成的追问
    st.markdown(st.session_state.dynamic_questions)
    
    st.markdown("---")
    answers_input = st.text_area("请在此逐条回复上述问题（AI 将自动为您整合）：", height=200)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("返回上一步", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("生成标准化报告 📝", type="primary", use_container_width=True):
            if answers_input.strip() == "":
                st.warning("请填写补充信息！")
            else:
                with st.spinner('AI 正在撰写标准排查报告...'):
                    # 真正调用 AI 接口！
                    st.session_state.final_report = generate_dynamic_report(
                        st.session_state.initial_input, 
                        answers_input
                    )
                st.session_state.step = 3
                st.rerun()

elif st.session_state.step == 3:
    st.success("🎉 报告已由 AI 融合生成！逻辑已闭环，符合 PM 审计标准。")
    report_container = st.container(border=True)
    with report_container:
        # 展示大模型生成的最终报告
        st.markdown(st.session_state.final_report)
    
    if st.button("✨ 处理下一个工单", type="primary"):
        st.session_state.step = 1
        st.rerun()
