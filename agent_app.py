import streamlit as st
from openai import OpenAI
from datetime import datetime

# 1. 配置 Kimi API 客户端
client = OpenAI(
    api_key=st.secrets["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",
)

st.set_page_config(page_title="PIA 智能工单 Agent", page_icon="🤖", layout="wide") # 改为宽屏，方便看侧边栏
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

# ================= 🗂️ 侧边栏：历史归档区 =================
if "archives" not in st.session_state:
    st.session_state.archives = []

with st.sidebar:
    st.header("🗂️ 工单归档记录")
    st.caption("当前会话中已审核闭环的工单报告")
    st.divider()
    
    if not st.session_state.archives:
        st.info("暂无归档数据。请先完成一份工单复核。")
    else:
        # 倒序展示，最新的在最上面
        for idx, record in enumerate(reversed(st.session_state.archives)):
            with st.expander(f"✅ 报告生成时间: {record['time']}", expanded=False):
                st.markdown(record['report'])
                # 提供下载按钮
                st.download_button(
                    label="💾 下载该报告为 Markdown",
                    data=record['report'],
                    file_name=f"交付复核报告_{record['time']}.md",
                    mime="text/markdown",
                    key=f"dl_{idx}" # 确保每个按钮有唯一的 key
                )

# ================= 主页面：对话与复核区 =================
st.title("🤖 硬件交付 PIA 智能复核 Agent")
st.caption("Powered by Kimi | 只有满足现象(P)、动作交叉验证(I)、现状(A)的逻辑闭环，才会放行并归档。")
st.divider()

# 2. 注入 PIA 核心 Prompt
SYSTEM_PROMPT = """
你现在是一位资深的服务器硬件交付项目经理（PM）。你的核心任务是：作为【智能工单复核助手】，通过多轮对话，审查现场工程师提交的故障排查记录，确保其逻辑严密、证据充分，并最终生成标准化交付报告。

# Core Framework (核心审核框架：PIA 模型)
你必须严格按照以下【PIA 模型】的标准，逐一核对工程师输入的信息。任何一个环节缺失或存在逻辑断层，你都必须进行拦截并追问。
1. 【P - Phenomenon (初始现象)】必须包含明确的触发场景（如测试、上电自检）和具体的报错对象及错误码。
2. 【I - Interventions (排查动作与结果)】必须体现“控制变量法”或“交叉验证”。如果工程师申请更换了核心部件，记录中必须包含验证该部件损坏的交叉测试动作（如：对调后报错跟随部件转移）。只换件不验证必须拦截！
3. 【A - As-is (当前现状与结论)】必须明确当前机器的最新状态或最终的验收结果。

# Action Rules (执行规则)
**情况 A：信息不全或存在逻辑断层（进入“追问模式”）**
- 动作：指出缺失的环节，提出 1-2 个极具体的疑问。
- 语气：通俗、平级协作、直奔主题。不要长篇大论。

**情况 B：信息完整且逻辑闭环满足 PIA 模型（进入“生成模式”）**
- 动作：停止提问，直接输出一份结构化的最终报告。
- ⚠️ 强制规定：当你判断可以生成最终报告时，你的回复必须且只能以“【最终交付报告】”这六个字作为开头！
"""

# 3. 初始化会话状态
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    st.session_state.display_messages = [
        {"role": "assistant", "content": "你好！我是智能工单复核助手。请把现场的**排查流水账**发给我，我会基于 PIA 模型帮你查漏补缺。如果未进行交叉验证，我可是会打回来的哦！"}
    ]
    st.session_state.is_done = False

# 4. 渲染前端历史对话记录
for msg in st.session_state.display_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 5. 核心交互循环
if not st.session_state.is_done:
    if prompt := st.chat_input("请输入现场排查记录或补充回答..."):
        st.session_state.display_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Agent 正在推演 PIA 逻辑是否闭环..."):
                try:
                    response = client.chat.completions.create(
                        model="moonshot-v1-8k",
                        messages=st.session_state.messages,
                        temperature=0.2, 
                    )
                    reply = response.choices[0].message.content
                    
                    if "【最终交付报告】" in reply:
                        st.success("🎉 逻辑已完美闭环！Agent 已放行并生成标准交付报告。")
                        st.session_state.is_done = True 
                        
                    st.markdown(reply)
                    
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.session_state.display_messages.append({"role": "assistant", "content": reply})
                    
                    if st.session_state.is_done:
                        st.rerun()

                except Exception as e:
                    st.error(f"调用 API 失败，请检查网络或 Key：{e}")

# 6. 报告生成后的【一键归档】动作
if st.session_state.is_done:
    st.markdown("---")
    if st.button("📁 确认归档该报告，并处理下一个工单", type="primary", use_container_width=True):
        # 提取最后一次 AI 的回复（也就是那份最终报告）
        final_report_text = st.session_state.display_messages[-1]["content"]
        
        # 将报告和当前时间存入侧边栏的归档列表中
        st.session_state.archives.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "report": final_report_text
        })
        
        # 清空当前聊天界面的记忆，准备迎接新工单
        del st.session_state.messages
        del st.session_state.display_messages
        del st.session_state.is_done
        st.rerun()
