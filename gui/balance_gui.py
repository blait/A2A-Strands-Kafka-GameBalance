#!/usr/bin/env python3
"""
Streamlit GUI for Game Balance Agent
Port: 8501
"""

import streamlit as st
import requests
import json
import re

# Agent URL
AGENT_URL = "http://localhost:9001"

st.set_page_config(
    page_title="게임 밸런스 에이전트",
    page_icon="⚖️",
    layout="wide"
)

# Add CSS to prevent horizontal scroll
st.markdown("""
<style>
    .stCodeBlock {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        max-width: 100% !important;
    }
    .stExpander {
        max-width: 100% !important;
    }
    .stExpander pre {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        max-width: 100% !important;
    }
    .stExpander code {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚖️ 게임 밸런스 에이전트")
st.caption("다른 에이전트들과 A2A 통신하여 종합 밸런스 분석 제공")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Function to parse and display content
def parse_display_content(content):
    clean = content.strip()
    json_match = re.search(r'(\{.*\})', clean, re.DOTALL)
    if json_match:
        try:
            rj = json.loads(json_match.group(1))
            if 'status' in rj and 'message' in rj:
                status = rj.get('status', 'completed')
                msg = rj.get('message', '')
                icon = {'completed': '✅', 'input_required': '❓', 'error': '❌'}.get(status, '📝')
                return f"**{icon} {status.upper()}**\n\n{msg}"
            else:
                return clean
        except json.JSONDecodeError:
            return clean
    else:
        return clean

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and "thinking" in message:
            with st.expander("🧠 사고 과정 보기", expanded=True):
                st.code(message["thinking"])
        display = parse_display_content(message["content"])
        st.markdown(display)

# Chat input
if prompt := st.chat_input("질문을 입력하세요 (예: 게임 밸런스 분석해줘)"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Send to agent with streaming
    with st.chat_message("assistant"):
        # Thinking at top - update in real-time
        with st.expander("🧠 사고 과정 (실시간)", expanded=True):
            thinking_placeholder = st.empty()
        
        # Answer below - update in real-time
        answer_md = st.empty()
        
        thinking_text = ""
        answer_text = ""
        
        answer_md.markdown("⏳ 응답 대기 중...")
        
        try:
            response = requests.post(
                f"{AGENT_URL}/ask_stream",
                json={"query": prompt},
                stream=True,
                timeout=120
            )
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        
                        if data['type'] == 'thinking':
                            thinking_text += data['content'] + "\n"
                            thinking_placeholder.code(thinking_text)
                        
                        elif data['type'] == 'answer':
                            answer_text += data['content']
                            
                            # Extract any complete <thinking> blocks from answer_text
                            thinking_matches = re.findall(r'<thinking>(.*?)</thinking>', answer_text, re.DOTALL)
                            if thinking_matches:
                                for match in thinking_matches:
                                    thinking_text += match.strip() + "\n"
                                answer_text = re.sub(r'<thinking>.*?</thinking>', '', answer_text, flags=re.DOTALL)
                                thinking_placeholder.code(thinking_text)
                            
                            clean = answer_text.strip()
                            
                            json_match = re.search(r'(\{.*\})', clean, re.DOTALL)
                            if json_match:
                                try:
                                    rj = json.loads(json_match.group(1))
                                    if 'status' in rj and 'message' in rj:
                                        status = rj.get('status', 'completed')
                                        msg = rj.get('message', '')
                                        icon = {'completed': '✅', 'input_required': '❓', 'error': '❌'}.get(status, '📝')
                                        display = f"**{icon} {status.upper()}**\n\n{msg}"
                                    else:
                                        display = clean
                                except json.JSONDecodeError:
                                    display = clean
                            else:
                                display = clean
                            
                            answer_md.markdown(display)
                        
                        elif data['type'] == 'done':
                            break
            
            # Final clean for storage
            clean = answer_text.strip()
            final_display = parse_display_content(clean)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": clean,
                "thinking": thinking_text
            })
            
            # Update the final display
            answer_md.markdown(final_display)
            
        except Exception as e:
            st.error(f"에러 발생: {str(e)}")
            st.info("에이전트가 실행 중인지 확인하세요: `python agents/game_balance_agent.py`")

# Sidebar
with st.sidebar:
    st.header("에이전트 정보")
    st.info(f"**URL**: {AGENT_URL}")
    st.info("**포트**: 8000")
    
    st.header("빠른 질문")
    if st.button("게임 밸런스 분석"):
        st.session_state.messages.append({"role": "user", "content": "게임 밸런스 분석해줘"})
        st.rerun()
    
    if st.button("테란 승률 확인"):
        st.session_state.messages.append({"role": "user", "content": "테란 승률은?"})
        st.rerun()
    
    if st.button("저그 피드백 확인"):
        st.session_state.messages.append({"role": "user", "content": "저그 피드백 보여줘"})
        st.rerun()
    
    if st.button("대화 기록 초기화"):
        st.session_state.messages = []
        st.rerun()