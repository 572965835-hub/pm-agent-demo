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
                            "action_info": {"type
