"""
Data Agent Streamlit Frontend
A beautiful chat interface for the Data Agent API
"""

import streamlit as st
import requests
import json
from datetime import datetime
from typing import Generator, Dict, Any
import time
import re
import ast
import os
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="邮政数据分析智能体",
    page_icon="📮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI - inspired by reference design
st.markdown("""
<style>
    /* Main container */
    .main-container {
        display: flex;
        height: 100vh;
        background-color: #f5f5f5;
    }
    
    /* Sidebar navigation */
    .sidebar {
        width: 200px;
        background-color: white;
        border-right: 1px solid #e0e0e0;
        padding: 20px;
        box-shadow: 2px 0 5px rgba(0,0,0,0.05);
    }
    
    .sidebar-header {
        display: flex;
        align-items: center;
        margin-bottom: 30px;
        padding-bottom: 15px;
        border-bottom: 1px solid #f0f0f0;
    }
    
    .sidebar-logo {
        width: 40px;
        height: 50px;
        margin-right: 5px;
        object-fit: contain;
    }
    
    .sidebar-title {
        font-size: 20px;
        font-weight: 600;
        color: black;
        line-height: 1.2;
    }
    
    .nav-item {
        display: flex;
        align-items: center;
        padding: 12px 15px;
        margin: 5px 0;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.3s ease;
        color: #666;
        text-decoration: none;
    }
    
    .nav-item:hover {
        background-color: #f0f8ff;
        color: #1a73e8;
    }
    
    .nav-item.active {
        background-color: #e3f2fd;
        color: #1a73e8;
        font-weight: 500;
    }
    
    .nav-icon {
        margin-right: 10px;
        font-size: 18px;
    }
    
    /* Main content area */
    .main-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }
    
    /* Top bar */
    .top-bar {
        background-color: white;
        padding: 15px 30px;
        border-bottom: 1px solid #e0e0e0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .search-box {
        display: flex;
        align-items: center;
        background-color: #f5f5f5;
        border-radius: 20px;
        padding: 8px 15px;
        width: 300px;
    }
    
    .search-box input {
        border: none;
        background: transparent;
        outline: none;
        flex: 1;
        margin-left: 10px;
    }
    
    .user-profile {
        display: flex;
        align-items: center;
    }
    
    .user-avatar {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background-color: #e3f2fd;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-left: 15px;
    }
    
    /* Welcome section */
    .welcome-section {
        text-align: center;
        padding: 40px 20px;
        background-color: #fafafa;
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    
    .welcome-title {
        font-size: 28px;
        font-weight: 600;
        color: #333;
        margin-bottom: 20px;
    }
    
    .welcome-subtitle {
        font-size: 16px;
        color: #666;
        margin-bottom: 40px;
    }
    
    .logo-container {
        margin: 20px 0;
    }
    
    .main-logo {
        width: 200px;
        height: 200px;
        object-fit: contain;
    }
    
    /* Background header */
    .background-header {
        background-image: url('frontend_assets/抬头图片.png');
        background-size: cover;
        background-position: center;
        border-radius: 12px;
        padding: 40px;
        width: 100%;
        max-width: 800px;
        margin: 0 auto 20px auto;
        text-align: center;
        color: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    .header-title {
        font-size: 24px;
        font-weight: 600;
        margin: 0;
    }
    
    /* Upload area */
    .upload-area {
        background-color: white;
        border-radius: 12px;
        padding: 30px;
        width: 100%;
        max-width: 600px;
        margin: 0 auto;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        color: #000000;
    }
    
    .upload-header {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }
    
    .upload-icon {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background-color: #4CAF50;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 15px;
    }
    
    .upload-title {
        font-size: 18px;
        font-weight: 600;
        color: #000000;
        margin: 0;
    }
    
    .upload-description {
        background-color: #f5f5f5;
        border-radius: 8px;
        padding: 20px;
        min-height: 100px;
        margin-bottom: 20px;
        text-align: center;
    }
    
    .upload-description p {
        color: #000000;
        margin: 0;
    }
    
    .upload-content {
        display: flex;
        flex-direction: column;
        gap: 15px;
    }
    
    .drag-drop-area {
        border: 2px dashed #4CAF50;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
    }
    
    .drag-drop-text {
        color: #000000;
        margin: 0;
    }
    
    .input-area {
        display: flex;
        gap: 10px;
    }
    
    .input-field {
        flex: 1;
        padding: 15px;
        border: 1px solid #000000;
        border-radius: 20px;
        outline: none;
        color: #000000;
    }
    
    .input-field::placeholder {
        color: #666666;
    }
    
    .send-button {
        background-color: #4CAF50;
        color: white;
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    /* Chat area */
    .chat-area {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 20px;
        overflow: hidden;
    }
    
    .chat-messages {
        flex: 1;
        overflow-y: auto;
        margin-bottom: 20px;
    }
    
    .chat-input-area {
        display: flex;
        gap: 10px;
        padding: 10px;
        background-color: white;
        border-radius: 10px;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
    }
    
    .chat-input {
        flex: 1;
        border: 1px solid #e0e0e0;
        border-radius: 20px;
        padding: 12px 20px;
        outline: none;
    }
    
    /* Message styles */
    .message {
        margin-bottom: 15px;
        max-width: 70%;
    }
    
    .user-message {
        margin-left: auto;
        background-color: #e3f2fd;
        border-radius: 18px 18px 4px 18px;
        padding: 12px 16px;
    }
    
    .assistant-message {
        margin-right: auto;
        background-color: white;
        border-radius: 18px 18px 18px 4px;
        padding: 12px 16px;
        border: 1px solid #e0e0e0;
    }
    
    /* Data preview */
    .data-preview {
        background-color: white;
        border-radius: 10px;
        padding: 20px;
        margin-top: 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .sidebar {
            width: 180px;
        }
        
        .upload-area {
            width: 90%;
        }
        
        .background-header {
            width: 90%;
        }
    }
</style>
""", unsafe_allow_html=True)


class DataAgentClient:
    """Client for Data Agent API"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.chat_endpoint = f"{self.base_url}/api/chat/stream"
    
    def check_server_status(self) -> bool:
        """Check if server is running"""
        try:
            response = requests.get(self.base_url, timeout=2)
            return True
        except requests.exceptions.RequestException:
            return False
    
    def chat_stream(self, user_input: str, session_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Send chat request and stream response
        
        Args:
            user_input: User's question
            session_id: Session ID for maintaining context
            
        Yields:
            Event dictionaries parsed from SSE stream:
            {
              "type": str,          # SSE event type or 'message'
              "id": str,            # message id (changes across LLM/tool phases)
              "content": str        # text chunk
            }
            Additionally emits {"type": "separator"} when message id changes.
        """
        messages = [{
            "role": "user",
            "content": user_input
        }]
        
        payload = {
            "messages": messages,
            "session_id": session_id
        }
        
        try:
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=180
            )
            
            if response.status_code != 200:
                yield {"type": "error", "content": f"❌ Error: HTTP {response.status_code}", "id": ""}
                return
            
            # Parse SSE (Server-Sent Events) stream
            last_message_id = None
            current_event_type = None
            for line in response.iter_lines(decode_unicode=True):
                if not line or line.strip() == "":
                    continue
                
                if line.startswith("event:"):
                    current_event_type = line.split(":", 1)[1].strip()
                    continue
                
                if line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(data_str)
                        content = data.get("content", "")
                        message_id = data.get("id", "")
                        
                        if isinstance(content, str) and content:
                            # Emit a separator when message id changes (new phase)
                            if last_message_id and message_id != last_message_id:
                                yield {"type": "separator", "id": message_id, "content": ""}
                            yield {
                                "type": current_event_type or "message",
                                "id": message_id or "",
                                "content": content
                            }
                            if message_id:
                                last_message_id = message_id
                    except json.JSONDecodeError:
                        continue
        
        except requests.exceptions.Timeout:
            yield {"type": "error", "content": "❌ Request timeout. Please try again.", "id": ""}
        except requests.exceptions.ConnectionError:
            yield {"type": "error", "content": "❌ Cannot connect to server. Please make sure the server is running.", "id": ""}
        except Exception as e:
            yield {"type": "error", "content": f"❌ Error: {str(e)}", "id": ""}


def initialize_session_state():
    """Initialize Streamlit session state"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if "server_url" not in st.session_state:
        st.session_state.server_url = "http://localhost:10000"
    if "client" not in st.session_state:
        st.session_state.client = DataAgentClient(st.session_state.server_url)
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"
    if "uploaded_file" not in st.session_state:
        st.session_state.uploaded_file = None


def render_sidebar():
    """Render sidebar with navigation"""
    with st.sidebar:
        # Logo and title
        col1, col2 = st.columns([1, 3])
        with col1:
            st.image("frontend_assets/公司图标.png", width=40)
        with col2:
            st.markdown("<div class='sidebar-title'>邮政数据分析智能体</div>", unsafe_allow_html=True)
        
        # Navigation items
        nav_items = [
            {"icon": "🏠", "label": "首页", "page": "home"},
            {"icon": "📊", "label": "数据分析", "page": "analysis"},
            {"icon": "📄", "label": "我的文档", "page": "documents"},
            {"icon": "🧠", "label": "知识库", "page": "knowledge"},
            {"icon": "📚", "label": "历史会话", "page": "history"}
        ]
        
        for item in nav_items:
            if st.button(f"{item['icon']} {item['label']}", use_container_width=True):
                st.session_state.current_page = item["page"]
                st.rerun()
        
        # Session management
        st.markdown("""
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #f0f0f0;">
            <div style="font-size: 14px; color: #666; margin-bottom: 10px;">分析会话管理</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🔄 新会话", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.rerun()
        
        if st.button("🗑️ 清除聊天", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


def render_home_page():
    """Render home page with welcome screen"""
    # Main title with background
    try:
        # Check if the image file exists
        if os.path.exists('frontend_assets/抬头图片.png'):
            # Create a container with the image
            col1, col2, col3 = st.columns([1, 8, 1])
            with col2:
                # Use st.image to display the image
                st.image("frontend_assets/抬头图片.png", width="150%", caption="")
                # Add text overlay
                st.markdown("""
                <div style='position: absolute; top: 50%; left: 50%; transform: translate(-75%, -75%); text-align: center; background-color: rgba(0,0,0,0); padding: 20px; border-radius: 8px;'>
                    <h1 style='font-size: 36px; font-weight: 700; margin: 0; color: black;'>欢迎使用邮政数据分析智能体——您的数据分析小助手</h1>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style='background-color: white; border-radius: 12px; padding: 60px; width: 100%; max-width: 800px; margin: 0 auto 20px auto; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.2);'>
                <h1 style='font-size: 36px; font-weight: 700; margin: 0; width: 75%; margin: 0 auto; color: black;'>欢迎使用邮政数据分析智能体</h1>
            </div>
            """, unsafe_allow_html=True)
    except Exception as e:
        st.markdown("""
        <div style='background-color: #4CAF50; border-radius: 12px; padding: 60px; width: 100%; max-width: 800px; margin: 0 auto 20px auto; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.2);'>
            <h1 style='font-size: 36px; font-weight: 700; margin: 0; width: 75%; margin: 0 auto; color: black;'>欢迎使用邮政数据分析智能体</h1>
        </div>
        """, unsafe_allow_html=True)
    
    # Actual file upload functionality
    st.markdown("### 📁 数据上传")
    uploaded_file = st.file_uploader(
        "上传您的数据文件",
        type=["csv", "xlsx", "xls"],
        help="支持的格式：CSV、Excel"
    )
    
    if uploaded_file is not None:
        # Create csv_files directory if it doesn't exist
        os.makedirs("csv_files", exist_ok=True)
        
        # Save the uploaded file
        file_path = os.path.join("csv_files", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # Update conf.yaml to add the uploaded file to data_sources
        import subprocess
        result = subprocess.run(["python", "update_csv_config.py"], capture_output=True, text=True)
        if "Updated" in result.stdout:
            st.success(f"✅ 文件已保存：{uploaded_file.name}，并已添加到配置中")
        else:
            st.success(f"✅ 文件已保存：{uploaded_file.name}")
        
        st.session_state.uploaded_file = uploaded_file
        
        # Show file preview
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            
            st.subheader("📊 文件预览")
            st.dataframe(df.head(), use_container_width=True)
            st.text(f"数据形状：{df.shape[0]} 行 × {df.shape[1]} 列")
            st.text(f"列名：{', '.join(df.columns.tolist())}")
        except Exception as e:
            st.error(f"❌ 读取文件时出错：{str(e)}")
    
    # Chat input
    st.markdown("### 💬 对话分析")
    user_input = st.chat_input("请输入您的分析需求...")
    
    # Process user input
    if user_input:
        # Check server connection first
        if not st.session_state.client.check_server_status():
            st.error("❌ 无法连接到服务器。请检查服务器URL并确保服务器正在运行。")
            return
        
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Get assistant response
        with st.chat_message("assistant"):
            full_response = ""
            for event in st.session_state.client.chat_stream(
                user_input,
                st.session_state.session_id
            ):
                content_chunk = event.get("content", "")
                if content_chunk:
                    full_response += content_chunk
                    st.markdown(full_response + "▌")
            
            # Finalize response
            st.markdown(full_response)
            
            # Check if response contains visualization results
            if "```python" in full_response and ("matplotlib" in full_response or "seaborn" in full_response or "plotly" in full_response):
                st.info("📊 检测到可视化代码，您可以在后端执行完整的可视化分析")
            
            # Check if response contains chart data
            if "chart_data" in full_response:
                st.info("📊 检测到图表数据，您可以在前端查看可视化结果")
            
            st.session_state.messages.append({"role": "assistant", "content": full_response})


def render_analysis_page():
    """Render analysis page with file upload and chat"""
    # File upload section
    st.markdown("### 📁 数据上传")
    uploaded_file = st.file_uploader(
        "上传您的数据文件",
        type=["csv", "xlsx", "xls"],
        help="支持的格式：CSV、Excel"
    )
    
    if uploaded_file is not None:
        # Create csv_files directory if it doesn't exist
        os.makedirs("csv_files", exist_ok=True)
        
        # Save the uploaded file
        file_path = os.path.join("csv_files", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # Update conf.yaml to add the uploaded file to data_sources
        import subprocess
        result = subprocess.run(["python", "update_csv_config.py"], capture_output=True, text=True)
        if "Updated" in result.stdout:
            st.success(f"✅ 文件已保存：{uploaded_file.name}，并已添加到配置中")
        else:
            st.success(f"✅ 文件已保存：{uploaded_file.name}")
        
        st.session_state.uploaded_file = uploaded_file
        
        # Show file preview
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            
            st.subheader("📊 文件预览")
            st.dataframe(df.head(), use_container_width=True)
            st.text(f"数据形状：{df.shape[0]} 行 × {df.shape[1]} 列")
            st.text(f"列名：{', '.join(df.columns.tolist())}")
        except Exception as e:
            st.error(f"❌ 读取文件时出错：{str(e)}")
    
    # Chat section
    st.markdown("### 💬 对话分析")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    user_input = st.chat_input("请输入您的分析需求...")
    
    # Process user input
    if user_input:
        # Check server connection first
        if not st.session_state.client.check_server_status():
            st.error("❌ 无法连接到服务器。请检查服务器URL并确保服务器正在运行。")
            return
        
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Get assistant response
        with st.chat_message("assistant"):
            full_response = ""
            for event in st.session_state.client.chat_stream(
                user_input,
                st.session_state.session_id
            ):
                content_chunk = event.get("content", "")
                if content_chunk:
                    full_response += content_chunk
                    st.markdown(full_response + "▌")
            
            # Finalize response
            st.markdown(full_response)
            
            # Check if response contains visualization results
            if "```python" in full_response and ("matplotlib" in full_response or "seaborn" in full_response or "plotly" in full_response):
                st.info("📊 检测到可视化代码，您可以在后端执行完整的可视化分析")
            
            # Check if response contains chart data
            if "chart_data" in full_response:
                st.info("📊 检测到图表数据，您可以在前端查看可视化结果")
            
            st.session_state.messages.append({"role": "assistant", "content": full_response})


def render_documents_page():
    """Render documents page"""
    st.markdown("### 📄 我的文档")
    st.info("文档管理功能正在开发中...")


def render_knowledge_page():
    """Render knowledge page"""
    st.markdown("### 🧠 知识库")
    st.info("知识库功能正在开发中...")


def render_history_page():
    """Render history page"""
    st.markdown("### 📚 历史会话")
    st.info("历史会话功能正在开发中...")


def main():
    """Main application"""
    initialize_session_state()
    
    # Sidebar
    render_sidebar()
    
    # Main content
    if st.session_state.current_page == "home":
        render_home_page()
    elif st.session_state.current_page == "analysis":
        render_analysis_page()
    elif st.session_state.current_page == "documents":
        render_documents_page()
    elif st.session_state.current_page == "knowledge":
        render_knowledge_page()
    elif st.session_state.current_page == "history":
        render_history_page()


if __name__ == "__main__":
    main()
