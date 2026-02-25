import streamlit as st
import time

# 设置页面配置（宽屏模式，看起来更舒展）
st.set_page_config(page_title="故障单智能复核 Agent", page_icon="🤖", layout="centered")

# 隐藏右上角的 Streamlit 默认菜单，看起来更像独立产品
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# 初始化 Session State
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'initial_input' not in st.session_state:
    st.session_state.initial_input = ""

st.title("🤖 硬件交付工单智能复核")
st.caption("AI 自动识别逻辑断层，引导补充规范数据，一键生成交付报告。")
st.divider()

# ================= 阶段 1：输入与分析 =================
if st.session_state.step == 1:
    with st.chat_message("assistant"):
        st.write("你好！我是工单复核助手。请把现场的**排查流水账**发给我，我来帮你查漏补缺。")
    
    initial_input = st.text_area(
        "📝 粘贴现场排查记录：", 
        height=150, 
        placeholder="例如：2月13日：rack-mfgdiag-st(ct)-test pass..."
    )
    
    if st.button("开始智能分析 ✨", type="primary", use_container_width=True):
        if initial_input.strip() == "":
            st.warning("请先输入排查记录哦！")
        else:
            st.session_state.initial_input = initial_input
            with st.spinner('AI 正在推演排查逻辑，寻找信息断层...'):
                time.sleep(1.5) # 模拟大模型思考的真实感
            st.session_state.step = 2
            st.rerun()

# ================= 阶段 2：逐条追问与补充 =================
elif st.session_state.step == 2:
    # 将原始记录折叠起来，保持页面清爽
    with st.expander("查看原始排查记录", expanded=False):
        st.info(st.session_state.initial_input)

    with st.chat_message("assistant"):
        st.write("我分析完了。记录里有几个关键逻辑没闭环，为了顺利结单，麻烦补充一下这几个细节：")
        
    st.markdown("### 🔍 信息补充")
    
    # 【UI优化核心】：将大段文本拆分成独立的问题卡片和输入框
    st.markdown("**第一部分：关于“最初故障现象是什么？”**")
    ans1 = st.text_input("1. 13号进场跑 mfgdiag 最开始报错的具体信息是什么？（请提供截图或日志）")
    ans2 = st.text_input("2. 发现该故障时，是否对当前的交付进度产生了阻塞？")
    
    st.markdown("**第二部分：关于“排查动作及依据”**")
    ans3 = st.text_input("3. 13号排除了CT和ST后，为什么当天没有继续测CC？（备件/时间原因？）")
    ans4 = st.text_input("4. 14号再次跑 rack-mfgdiag 的具体结果是 pass 还是 fail？")
    ans5 = st.text_input("5. 16号换上新CC后报错位置改变，当时有没有把旧CC插到别的槽位交叉验证DOA？")
    ans6 = st.text_input("6. 16号 mfgdiag fail 的具体失败项是什么？")
    
    st.markdown("**第三部分：关于“验收结果”**")
    ans7 = st.text_input("7. 18号换第二个CC通过后，有没有对整机完整运行一次健康度检查？")

    st.markdown("---")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("返回上一步", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("生成标准化报告 📝", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

# ================= 阶段 3：输出最终报告 =================
elif st.session_state.step == 3:
    st.success("🎉 报告已生成！逻辑已闭环，符合 PM 审计标准。")
    
    # 使用卡片式风格展示最终报告
    report_container = st.container(border=True)
    with report_container:
        st.markdown("### 🟢 最终结构化排查报告 (可直接归档)")
        st.markdown("""
        **一、 初始故障现象**
        2月13日进场执行交付阶段硬件自检时，触发 Nvlmapper 结果异常。（附：初始报错日志）。该异常阻塞了后续交付验收流程。

        **二、 排查过程与逻辑闭环**
        * **2月13日：** 运行测试通过。发现 `CT02-CC0-ST4` 链路质量差。对调后报错位置不变，初步排除 CT 与 ST。当天受限于现场条件未继续排查 CC。
        * **2月14日：** 针对 CC 进行对调测试，报错位置跟随 CC 转移，锁定 CC。申请备件。
        * **2月16日：** 更换首个新 CC 后，依然报错且位置变化，`mfgdiag` 变为 fail。经交叉验证判定该新备件 DOA（到货即损），再次追加备件。

        **三、 最终结果与验收确认**
        * **2月18日：** 更换第二个新 CC 备件后，Nvlmapper 测试通过。
        * **验收结论：** 已完成整机全量复测，整机健康度达标，故障消除，准予结单。
        """)
    
    if st.button("✨ 处理下一个工单", type="primary"):
        st.session_state.step = 1
        st.rerun()