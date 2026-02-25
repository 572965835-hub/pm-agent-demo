import json
# ... 其他引入保持不变 ...

# 在文件顶部或适合的位置定义工具 Schema
ticket_tools = [
    {
        "type": "function",
        "function": {
            "name": "submit_resolved_ticket",
            "description": "当工程师提供的现场排查流水账信息完整，逻辑闭环（满足现象、动作、现状全覆盖），不需要再追问时，调用此工具结单并提取结构化数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_sn": {
                        "type": "string",
                        "description": "设备SN号，若无请填 '未知'"
                    },
                    "product_line": {
                        "type": "string",
                        "description": "产品线/机型，若无请填 '未知'"
                    },
                    "fault_type": {
                        "type": "string",
                        "description": "故障分类(如: GPU故障, 主板故障, 线缆故障)"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "维修开始时间"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "维修结束时间"
                    },
                    "final_report": {
                        "type": "string",
                        "description": "代入一线工程师的第一人称视角，撰写的最终标准化现场处理描述报告。"
                    },
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
    }
]

# ... 初始化与界面代码保持不变 ...

# 修改对话逻辑部分
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
                        # API 调用，加入 tools 参数
                        response = client.chat.completions.create(
                            model="moonshot-v1-8k",
                            messages=st.session_state.messages,
                            temperature=0.2,
                            tools=ticket_tools, # 注入工具
                            tool_choice="auto"  # 让大模型自己决定是对话还是调用工具
                        )
                        
                        response_message = response.choices[0].message

                        # 【核心逻辑分流】：判断模型是选择了对话，还是选择了调用工具结单
                        if response_message.tool_calls:
                            # 1. 模型决定结单！
                            tool_call = response_message.tool_calls[0]
                            if tool_call.function.name == "submit_resolved_ticket":
                                # 解析大模型输出的 JSON 参数
                                arguments = json.loads(tool_call.function.arguments)
                                
                                st.session_state.is_done = True
                                st.session_state.extracted_data = arguments
                                st.session_state.final_report = arguments.get("final_report", "未生成最终报告")
                                
                                final_reply = f"### 📄 最终交付报告\n\n{st.session_state.final_report}"
                                st.markdown(final_reply)
                                
                                # 将工具调用的结果加入消息历史，保持上下文完整
                                st.session_state.messages.append(response_message)
                                st.session_state.display_messages.append({"role": "assistant", "content": final_reply})
                                
                                st.rerun()
                        else:
                            # 2. 模型认为信息不足，继续追问
                            reply = response_message.content
                            st.markdown(reply)
                            st.session_state.messages.append({"role": "assistant", "content": reply})
                            st.session_state.display_messages.append({"role": "assistant", "content": reply})
                            
                    except Exception as e:
                        st.error(f"API 出错或 JSON 解析失败：{e}")

# ================= 后台提取逻辑精简 =================
# 原先的 JSON 表单提取代码可以【全部删除】，因为上面的 Function Calling 已经把数据拿到了！
# 你现在只需要保留“技术总监点评”的代码即可。

if st.session_state.is_done and st.session_state.ai_critique is None:
    with st.spinner("🧠 全球顶尖技术总监正在撰写深度复盘报告..."):
        try:
            crit_msgs = st.session_state.messages.copy()
            # 将最终提取的 JSON 作为上下文塞给总监，让他点评得更精准
            crit_context = f"以下是最终提取的工单结构化数据：\n{json.dumps(st.session_state.extracted_data, ensure_ascii=False)}\n\n"
            crit_msgs.append({"role": "user", "content": crit_context + CRITIQUE_PROMPT})
            
            crit_res = client.chat.completions.create(
                model="moonshot-v1-8k", messages=crit_msgs, temperature=0.3
            )
            st.session_state.ai_critique = crit_res.choices[0].message.content
        except Exception as e:
            st.error(f"生成点评失败: {e}")
            st.session_state.ai_critique = "点评生成失败。"
        st.rerun()
