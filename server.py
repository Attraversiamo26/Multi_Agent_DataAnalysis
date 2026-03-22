import argparse
import asyncio
import json
import logging
import os
import platform
from typing import List, cast
from uuid import uuid4

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.config.loader import load_yaml_config
from src.graph.builder import build_graph
from src.utils.similar_questions import get_similar_questions
from src.utils.tag_manager import TagFilter
from src.utils.session_manager import get_session_manager
from src.utils.storage_manager import get_storage_manager
from src.utils.execution_monitor import get_execution_monitor
from src.entity.enhanced_models import PlanStatus, StepStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# Pydantic models for request/response
class ChatMessage(BaseModel):
    role: str = Field(..., description="The role of the message sender (user or assistant)")
    content: str = Field(..., description="The text content of the message")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(
        default_factory=list,
        description="History of messages between the user and the assistant"
    )
    session_id: str = Field(
        default="__default__",
        description="A specific conversation identifier"
    )


# Create FastAPI app
app = FastAPI(
    title="Data Agent API",
    description="API for Data Agent",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Build workflow graph
graph = build_graph()

# Get system type
system = platform.system()

# Load configuration
config = load_yaml_config("conf.yaml")
default_locale = config.get("app", {}).get("locale", "zh-CN")
workspace_base_dir = config.get("app", {}).get("workspace_directory", {})
workspace_dir_mac = workspace_base_dir.get("macOS", "/Users/qiweideng/Desktop/数据分析大模型/代码库/DataAgent-main")
workspace_dir_windows = workspace_base_dir.get("windows", "D:/tmp")

# Track interrupt state for each conversation session
interrupt_flags: dict[str, bool] = {}


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chat responses for a conversation session.
    Generates a new session_id if not provided.
    """
    session_id = request.session_id
    if session_id == "__default__":
        session_id = str(uuid4())
    return StreamingResponse(
        _astream_workflow_generator(
            request.model_dump()["messages"],
            session_id
        ),
        media_type="text/event-stream",
    )


class SimilarQuestionsRequest(BaseModel):
    user_question: str = Field(..., description="The user's current question")
    context: List[ChatMessage] = Field(default_factory=list, description="Previous conversation messages")


@app.post("/api/similar-questions")
async def get_similar_questions_endpoint(request: SimilarQuestionsRequest):
    """
    Generate similar questions based on the user's current question and context.
    """
    # Convert context to the expected format
    context_formatted = [msg.model_dump() for msg in request.context]
    
    # Generate similar questions
    similar_questions = await get_similar_questions(
        request.user_question, 
        context_formatted
    )
    
    return {
        "similar_questions": similar_questions
    }


class SessionCreateRequest(BaseModel):
    user_id: str = Field(default="default", description="User ID for the session")
    metadata: dict = Field(default_factory=dict, description="Additional metadata for the session")


@app.post("/api/sessions")
async def create_session(request: SessionCreateRequest):
    """
    Create a new conversation session.
    """
    session_manager = get_session_manager()
    session_id = session_manager.create_session(request.user_id, request.metadata)
    return {"session_id": session_id}


@app.get("/api/sessions")
async def list_sessions():
    """
    List all available sessions.
    """
    session_manager = get_session_manager()
    sessions = session_manager.list_all_sessions()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """
    Get a specific session by ID.
    """
    storage = get_storage_manager()
    session = storage.load_session(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    return {"session": session.model_dump()}


@app.get("/api/sessions/{session_id}/statistics")
async def get_session_statistics(session_id: str):
    """
    Get statistics for a specific session.
    """
    storage = get_storage_manager()
    stats = storage.get_session_statistics(session_id)
    if not stats:
        return {"error": "Session not found"}, 404
    return {"statistics": stats}


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, keyword: str = None):
    """
    Get messages from a session, optionally filtered by keyword.
    """
    storage = get_storage_manager()
    session = storage.load_session(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    
    if keyword:
        messages = storage.query_messages_by_keyword(session_id, keyword)
    else:
        messages = session.messages
    
    return {"messages": [msg.model_dump() for msg in messages]}


@app.get("/api/sessions/{session_id}/plans")
async def get_session_plans(session_id: str, status: str = None):
    """
    Get plans from a session, optionally filtered by status.
    """
    storage = get_storage_manager()
    session = storage.load_session(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    
    if status:
        try:
            plan_status = PlanStatus(status)
            plans = storage.query_plans_by_status(session_id, plan_status)
        except ValueError:
            return {"error": "Invalid status"}, 400
    else:
        plans = session.plans
    
    return {"plans": [plan.model_dump() for plan in plans]}


@app.post("/api/sessions/{session_id}/backup")
async def backup_session(session_id: str):
    """
    Backup a specific session.
    """
    storage = get_storage_manager()
    backup_path = storage.backup_session(session_id)
    if not backup_path:
        return {"error": "Session not found"}, 404
    return {"backup_path": backup_path}


@app.post("/api/archive")
async def archive_old_sessions(days_old: int = 30):
    """
    Archive sessions older than specified days.
    """
    storage = get_storage_manager()
    archived_count = storage.archive_old_sessions(days_old)
    return {"archived_count": archived_count}


@app.get("/api/execution/current")
async def get_current_execution_status():
    """
    Get current execution status of plan and step.
    """
    monitor = get_execution_monitor()
    plan_status = monitor.get_current_plan_status()
    step_status = monitor.get_current_step_status()
    return {
        "plan": plan_status,
        "step": step_status
    }


@app.get("/api/analytics/all-sessions")
async def get_all_sessions_analytics():
    """
    Get analytics data for all sessions.
    """
    storage = get_storage_manager()
    analytics = storage.get_all_sessions_statistics()
    return {"analytics": analytics}


async def _astream_workflow_generator(
        messages: List[ChatMessage],
        session_id: str
):
    """
    Generate streaming workflow responses for the chat.
    Creates workspace directory and handles conversation state.
    """
    logger.info(f"[Workflow Generator] ===== Started =====")
    logger.info(f"[Workflow Generator] Session ID: {session_id}")
    logger.info(f"[Workflow Generator] Messages received: {len(messages)}")
    
    # Create workspace directory for this session
    base_dir = workspace_dir_windows if system == "Windows" else workspace_dir_mac
    workspace_directory = f"{base_dir}/{session_id}"
    if not os.path.exists(workspace_directory):
        os.makedirs(workspace_directory)
        logger.info(f"[Workflow Generator] Created workspace directory: {workspace_directory}")
    else:
        logger.info(f"[Workflow Generator] Workspace directory already exists: {workspace_directory}")

    # Get the latest user message
    user_question = messages[-1].get("content")
    logger.info(f"[Workflow Generator] User question: {user_question}")

    # Handle interrupt/resume flow
    if interrupt_flags.get(session_id):
        logger.info(f"[Workflow Generator] Handling interrupt/resume")
        interrupt_flags[session_id] = False
        _input = Command(resume={"data": user_question})
    else:
        logger.info(f"[Workflow Generator] Creating new workflow input")
        _input = {
            "user_question": user_question,
            "executed_steps": [],
            "current_plan": None,
            "ask_user_question": None,
            "retrieved_info": "",
            "locale": default_locale,
            "need_replan": True,
            "workspace_directory": workspace_directory
        }

    # Stream workflow execution
    logger.info(f"[Workflow Generator] About to call graph.astream()")
    logger.info(f"[Workflow Generator] Input: {_input}")
    
    try:
        node_count = 0
        logger.info(f"[Workflow Generator] ===== Starting graph.astream() iteration =====")
        
        # 不使用 subgraphs=True，简化事件处理
        async for event in graph.astream(
                input=_input,
                config={
                    "thread_id": session_id
                },
                stream_mode="messages",  # 不使用 subgraphs，简化处理
        ):
            node_count += 1
            logger.info(f"[Workflow Generator] ===== Node {node_count} =====")
            logger.info(f"[Workflow Generator] Event type: {type(event)}")
            
            # 处理 interrupt 事件
            if isinstance(event, dict) and "__interrupt__" in event:
                interrupt_items = event.get("__interrupt__") or []
                if interrupt_flags.get(session_id):
                    continue
                interrupt_flags[session_id] = True
                interrupt_message = {
                    "session_id": session_id,
                    "id": f"interrupt_{interrupt_items[0].id}",
                    "role": "assistant",
                    "content": f"❔{interrupt_items[0].value}",
                }
                yield _make_event("message_chunk", interrupt_message)
                continue
            
            # 处理消息事件 - 支持 2 元组和 3 元组格式
            if isinstance(event, tuple) and len(event) >= 2:
                # 根据长度解构
                if len(event) == 3:
                    namespace, message_chunk, metadata = event
                elif len(event) == 2:
                    message_chunk, metadata = event
                    namespace = ()
                else:
                    continue
                
                # 跳过没有 message_chunk 的情况
                if message_chunk is None:
                    continue
                
                logger.info(f"[Workflow Generator] Processing message from namespace: {namespace}")
                
                # 获取 content
                content_piece = ""
                if hasattr(message_chunk, 'content'):
                    content_piece = message_chunk.content
                elif isinstance(message_chunk, str):
                    content_piece = message_chunk
                else:
                    content_piece = str(message_chunk)
                
                # Skip internal thinking and empty content
                if "think" in content_piece or "\n\n" == content_piece or '' == str(content_piece).strip():
                    logger.info(f"[Workflow Generator] Skipping empty/thinking content")
                    continue
                
                # Skip ALL report template sections (should only appear in full analysis reports)
                report_section_headers = [
                    "### 1. Executive Summary",
                    "### 2. Key Findings",
                    "### 3. Detailed Analysis",
                    "### 4. Recommendations",
                    "### 5. Conclusion",
                    "## Executive Summary",
                    "## Key Findings",
                    "## Detailed Analysis",
                    "## Recommendations",
                    "## Conclusion",
                    "##### 1. Executive Summary",
                    "##### 2. Key Findings",
                    "##### 3. Detailed Analysis",
                    "##### 4. Recommendations",
                    "##### 5. Conclusion",
                    "This analysis",  # Report introduction phrases
                    "Final status:",  # Status summaries
                    "Root cause:",    # Root cause analysis
                    "Next step:",     # Next steps
                ]
                
                # Check if this is a report section header (should be filtered out for simple queries)
                is_report_header = any(header in content_piece for header in report_section_headers)
                if is_report_header:
                    logger.info(f"[Workflow Generator] Skipping report section header (data-only mode): {content_piece[:50]}...")
                    continue
                
                # Mark Agent reasoning/analysis process content as collapsible thinking
                # These are internal monologue that should be hidden by default
                reasoning_patterns = [
                    "Agent analyzing and determining next action",
                    "Reasoning:",
                    "Preparing tool:",
                    "Tool parameters:",
                    "Tool execution completed:",
                    "I need to use the",
                    "I should call",
                    "Let me check",
                    "Now I will",
                    "Next step is to",
                ]
                
                # Patterns that indicate actual response content (should NOT be marked as thinking)
                response_patterns = [
                    "### ",  # Markdown headers
                    "## ",
                    "**",    # Bold text
                    "✅",    # Success indicators
                    "📊",    # Chart indicators
                    "🔹",    # Bullet points
                    "|",     # Table content
                    "共有",   # Chinese result indicators
                    "统计",   # Statistics
                    "结果",   # Results
                ]
                
                is_reasoning = any(pattern in content_piece for pattern in reasoning_patterns)
                is_response = any(pattern in content_piece for pattern in response_patterns)
                
                if is_reasoning and not is_response:
                    # Mark it as thinking content for frontend to handle
                    content_piece = f"__THINKING_START__{content_piece}__THINKING_END__"
                    logger.info(f"[Workflow Generator] Marked as thinking content: {content_piece[:50]}...")
                else:
                    # This is actual response content, log it
                    logger.info(f"[Workflow Generator] Response content: {content_piece[:50]}...")

                # 获取 message_id
                message_id = ""
                if hasattr(message_chunk, 'id'):
                    message_id = message_chunk.id
                else:
                    message_id = f"msg_{node_count}"

                # Stream message chunk to client
                event_stream_message = {
                    "session_id": session_id,
                    "id": message_id,
                    "role": "assistant",
                    "content": content_piece,
                }
                yield _make_event("message_chunk", event_stream_message)
            else:
                logger.info(f"[Workflow Generator] Unexpected event format: {type(event)} - {event}")
                
    except Exception as e:
        logger.error(f"[Workflow Generator] Error in workflow execution: {e}", exc_info=True)
        error_message = {
            "session_id": session_id,
            "id": f"error_{str(uuid4())}",
            "role": "assistant",
            "content": f"抱歉，执行过程中出现错误：{str(e)}",
        }
        yield _make_event("message_chunk", error_message)


def _make_event(event_type: str, data: dict[str, any]):
    """
    Format data as Server-Sent Event (SSE).
    Removes empty content fields.
    """
    if data.get("content") == "":
        data.pop("content")
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    # Set event loop policy for Windows compatibility
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the data agent server")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (default: False, not recommended on Windows)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=10000,
        help="Port to bind the server to (default: 10000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info)",
    )

    args = parser.parse_args()

    # Determine reload setting
    reload = args.reload

    logger.info(f"Starting data agent server on {args.host}:{args.port}")
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=reload,
        log_level=args.log_level,
    )