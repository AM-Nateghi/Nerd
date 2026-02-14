from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union, AsyncIterator
import httpx
import uuid
from datetime import datetime
import asyncio
import logging
import os
from contextlib import asynccontextmanager
import json
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage

from tools import execute_tool

print("🔄 loading .env")
load_dotenv()

# Suppress warnings
# warnings.filterwarnings("ignore", category=FutureWarning)
# warnings.filterwarnings("ignore", category=DeprecationWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Dictionary to track active generation tasks
active_tasks: Dict[str, bool] = {}

# Load settings from environment variables
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:5836")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "2048"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are Nerd, a floating web ai guide. Answer concisely in Persian. Keep replies short and actionable. type in Markdown format",
)
STREAM_HEARTBEAT_SEC = int(os.getenv("STREAM_HEARTBEAT_SEC", "15"))
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "6"))
DB_PATH = os.getenv("CHAT_DB_PATH", "chat_history.json")
SESSION_HISTORY_LIMIT = int(os.getenv("SESSION_HISTORY_LIMIT", "20"))

FORCE_SEARCH_KEYWORDS = [
    "امروز",
    "الان",
    "جدید",
    "آپدیت",
    "update",
    "latest",
    "version",
    "release",
    "imdb",
    "قیمت",
    "سن",
    "نرخ",
    "مستندات",
    "داکیومنت",
    "documentation",
    "api",
    "changelog",
    "news",
    "os",
    "system",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Searching for information on the web and getting the full content of pages when we need up-to-date information. Or need to search for concepts such as API-Documentations, Really Instant entities like prices, ages, reports, docs, or unknown things.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string with keywords, questions, or phrases to search for.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "تعداد نتایج (پیش‌فرض: 2)",
                        "default": 2,
                    },
                },
                "required": ["query"],
            },
        },
    }
]


# Lifespan context manager (جایگزین on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting server...")
    logger.info(f"🔗 Upstream LLM base URL: {LLM_BASE_URL}")
    logger.info(f"🤖 Upstream model: {LLM_MODEL}")
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=None))
    app.state.db = TinyDB(
        DB_PATH,
        storage=JSONStorage,
        ensure_ascii=False,
        encoding="utf-8",
    )
    app.state.messages_table = app.state.db.table("messages")
    app.state.tools_table = app.state.db.table("tool_logs")
    logger.info(f"🗂️ TinyDB initialized at: {DB_PATH}")

    yield

    logger.info("🛑 Shutting down server...")
    client = getattr(app.state, "http_client", None)
    if client is not None:
        await client.aclose()
    db = getattr(app.state, "db", None)
    if db is not None:
        db.close()


# Make application FastAPI with lifespan
app = FastAPI(
    title="Nerd Agent Server",
    version="0.1.0",
    description="FastAPI backend with Gemma3n-e4b model",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    stream: Optional[bool] = None
    session_id: Optional[str] = None


# Middleware for logging requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    return response


# Health check
@app.get("/health")
async def health_check():
    return {
        "ok": True,
        "upstream_base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "timestamp": datetime.now().isoformat(),
    }


def extract_text_content(content: Union[str, List[Dict[str, Any]]]) -> str:
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    parts = []
    for part in content:
        if part.get("type") == "text":
            parts.append(part.get("text", ""))

    return " ".join(p for p in parts if p)


def should_force_search(user_text: str) -> bool:
    text = (user_text or "").lower()
    if not text:
        return False
    return any(keyword in text for keyword in FORCE_SEARCH_KEYWORDS)


def persist_message(
    app_ref: FastAPI,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    if metadata:
        payload["metadata"] = metadata
    app_ref.state.messages_table.insert(payload)


def persist_tool_log(
    app_ref: FastAPI,
    session_id: str,
    task_id: str,
    tool_name: str,
    tool_query: str,
    tool_arguments: Dict[str, Any],
    tool_result: str,
) -> None:
    app_ref.state.tools_table.insert(
        {
            "session_id": session_id,
            "task_id": task_id,
            "tool_name": tool_name,
            "tool_query": tool_query,
            "tool_arguments": tool_arguments,
            "tool_result": tool_result,
            "timestamp": datetime.now().isoformat(),
        }
    )


def load_session_history(
    app_ref: FastAPI, session_id: str, limit: int = SESSION_HISTORY_LIMIT
) -> List[Dict[str, str]]:
    session_query = Query()
    rows = app_ref.state.messages_table.search(session_query.session_id == session_id)
    rows.sort(key=lambda item: item.get("timestamp", ""))
    return [
        {"role": row.get("role", "user"), "content": row.get("content", "")}
        for row in rows[-limit:]
        if row.get("role") in ("user", "assistant") and row.get("content")
    ]


def normalize_upstream_messages(
    messages: List[Dict[str, Any]], announcement: Optional[str] = None
) -> List[Dict[str, str]]:
    system_chunks: List[str] = []
    normalized: List[Dict[str, str]] = []

    for msg in messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content and role != "assistant":
            continue
        if role == "system":
            if content:
                system_chunks.append(content)
            continue

        if role == "tool":
            tool_name = msg.get("name") or "tool"
            content = f"result of tool {tool_name}:\n{content}" if content else ""
            role = "user"

        if role not in ("user", "assistant"):
            role = "user"

        if normalized and normalized[-1]["role"] == role:
            if content:
                normalized[-1]["content"] += f"\n\n{content}"
        else:
            normalized.append({"role": role, "content": content})

    policy_block = "\n\n".join(chunk for chunk in system_chunks if chunk)
    prefix_parts = []
    if announcement:
        prefix_parts.append(announcement)
    if policy_block:
        prefix_parts.append(policy_block)
    prefix = "\n\n".join(prefix_parts).strip()

    if not normalized:
        return [{"role": "user", "content": prefix or " "}]

    if normalized[0]["role"] != "user":
        normalized.insert(0, {"role": "user", "content": prefix or " "})
    else:
        if prefix:
            normalized[0]["content"] = f"{prefix}\n\n{normalized[0]['content']}"

    return normalized


# Chat API with OpenAI-compatible upstream streaming
@app.post("/api/chat")
async def chat(request: ChatRequest, raw_request: Request):
    start_time = datetime.now()
    task_id = str(uuid.uuid4())
    session_id = (
        request.session_id
        or raw_request.headers.get("x-session-id")
        or str(uuid.uuid4())
    )
    active_tasks[task_id] = True

    logger.info(
        f"[CHAT-{task_id}] Request received - session: {session_id} - messages: {len(request.messages)}"
    )

    try:
        prompt_start = datetime.now()
        upstream_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        upstream_messages.append(
            {
                "role": "system",
                "content": (
                    "Mandatory response policy:\n"
                    "1) The final reply to the user must be in Persian only.\n"
                    "2) If the question involves up-to-date info, software/OS versions, recent changes, people, prices, ratings (e.g., IMDb), news, or documentation/API, you MUST use the search tool before answering.\n"
                    "3) If you are uncertain about coding details or docs, run search (multiple times if needed) until the result is reliable.\n"
                    "4) Never guess about fresh data without relying on search results."
                ),
            }
        )

        filtered_messages: List[ChatMessage] = []
        non_text_count = 0
        for msg in request.messages:
            if msg.role == "system":
                continue
            if msg.role not in ("user", "assistant"):
                continue
            filtered_messages.append(msg)

        db_history = load_session_history(raw_request.app, session_id)
        messages_for_prompt: List[ChatMessage] = filtered_messages
        if db_history and len(filtered_messages) <= 2:
            logger.info(
                f"[CHAT-{task_id}] Injected {len(db_history)} history item(s) from TinyDB"
            )
            for old_msg in db_history:
                upstream_messages.append(old_msg)

        for msg in messages_for_prompt:
            if msg.role not in ("user", "assistant"):
                continue

            text = extract_text_content(msg.content).strip()
            if not text:
                if isinstance(msg.content, list):
                    non_text_count += 1
                continue

            upstream_messages.append({"role": msg.role, "content": text})

        if non_text_count > 0:
            logger.warning(
                f"[CHAT-{task_id}] Ignored {non_text_count} non-text message part(s)"
            )

        if len(upstream_messages) <= 2:
            raise HTTPException(status_code=400, detail="No user content provided")

        latest_user_text = ""
        for msg in reversed(messages_for_prompt):
            if msg.role == "user":
                latest_user_text = extract_text_content(msg.content).strip()
                if latest_user_text:
                    break

        if latest_user_text:
            persist_message(raw_request.app, session_id, "user", latest_user_text)

        force_search_needed = should_force_search(latest_user_text)
        if force_search_needed:
            logger.info(
                f"[CHAT-{task_id}] Fresh-data query detected, search usage is required"
            )

        prompt_duration = (datetime.now() - prompt_start).total_seconds()
        logger.info(f"[CHAT-{task_id}] Prompt built in {prompt_duration:.2f}s")

        logger.info(f"[CHAT-{task_id}] Generation started (tool-aware loop)")

        async def generate_stream() -> AsyncIterator[str]:
            try:
                full_response = ""
                step_start = datetime.now()
                tool_logs_for_turn: List[Dict[str, Any]] = []
                search_count = 0
                force_injected = False
                yielded_session = False

                async def progress_logger() -> None:
                    while active_tasks.get(task_id, False):
                        await asyncio.sleep(STREAM_HEARTBEAT_SEC)
                        if not active_tasks.get(task_id, False):
                            break
                        elapsed = (datetime.now() - step_start).total_seconds()
                        logger.info(
                            f"[CHAT-{task_id}] Still streaming... {elapsed:.1f}s elapsed"
                        )

                progress_task = asyncio.create_task(progress_logger())

                client: httpx.AsyncClient = raw_request.app.state.http_client
                url = f"{LLM_BASE_URL}/v1/chat/completions"

                def build_status_payload(
                    status: str, detail: Optional[str] = None
                ) -> str:
                    data: Dict[str, Any] = {
                        "type": "status",
                        "status": status,
                        "done": False,
                        "session_id": session_id,
                        "task_id": task_id,
                    }
                    if detail:
                        data["detail"] = detail
                    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                conversation: List[Dict[str, Any]] = list(upstream_messages)
                for round_index in range(MAX_TOOL_CALLS + 1):
                    if not active_tasks.get(task_id, False):
                        logger.info(f"[CHAT-{task_id}] ⚠️ Task cancelled by client")
                        break
                    if await raw_request.is_disconnected():
                        logger.info(f"[CHAT-{task_id}] ⚠️ Client disconnected")
                        active_tasks[task_id] = False
                        break

                    announcement_text = (
                        "Tool status notice:\n"
                        f"- Searches completed so far: {search_count}\n"
                        f"- Search cap for this answer: {MAX_TOOL_CALLS}\n"
                        "- If fresh data or documentation is needed, use search.\n"
                        "- The final reply to the user must be in Persian only."
                    )

                    payload = {
                        "model": request.model or LLM_MODEL,
                        "messages": normalize_upstream_messages(
                            conversation, announcement=announcement_text
                        ),
                        "stream": False,
                        "temperature": TEMPERATURE,
                        "top_p": 0.75,
                        "top_k": 20,
                        "max_tokens": MAX_NEW_TOKENS,
                        "tools": TOOLS,
                        "tool_choice": "auto",
                    }

                    yield build_status_payload("thinking")

                    resp = await client.post(url, json=payload)
                    if resp.status_code != 200:
                        error_text = resp.text
                        raise RuntimeError(
                            f"Upstream error {resp.status_code}: {error_text}"
                        )

                    response_data = resp.json()
                    choices = response_data.get("choices", [])
                    if not choices:
                        raise RuntimeError("Upstream returned empty choices")

                    message = choices[0].get("message", {})
                    tool_calls = message.get("tool_calls") or []
                    assistant_content = (message.get("content") or "").strip()

                    if tool_calls:
                        logger.info(
                            f"[CHAT-{task_id}] Round {round_index + 1}: model requested {len(tool_calls)} tool call(s)"
                        )
                        conversation.append(
                            {
                                "role": "assistant",
                                "content": message.get("content") or "",
                                "tool_calls": tool_calls,
                            }
                        )

                        for tool_call in tool_calls:
                            call_id = (
                                tool_call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                            )
                            function_info = tool_call.get("function", {})
                            tool_name = function_info.get("name", "")
                            raw_args = function_info.get("arguments", "{}")

                            try:
                                tool_args = json.loads(raw_args) if raw_args else {}
                            except json.JSONDecodeError:
                                tool_args = {}

                            yield build_status_payload(
                                "searching" if tool_name == "search" else "tool",
                                str(tool_args.get("query", ""))[:200],
                            )

                            tool_result = await execute_tool(tool_name, tool_args)
                            tool_result_text = (
                                tool_result
                                if isinstance(tool_result, str)
                                else json.dumps(tool_result, ensure_ascii=False)
                            )

                            if tool_name == "search":
                                search_count += 1

                            yield build_status_payload(
                                "search_results_received"
                                if tool_name == "search"
                                else "tool_result_received"
                            )

                            tool_query = str(tool_args.get("query", ""))
                            persist_tool_log(
                                raw_request.app,
                                session_id,
                                task_id,
                                tool_name,
                                tool_query,
                                tool_args,
                                tool_result_text,
                            )
                            tool_logs_for_turn.append(
                                {
                                    "tool_name": tool_name,
                                    "tool_query": tool_query,
                                    "tool_arguments": tool_args,
                                    "tool_result": tool_result_text,
                                }
                            )

                            conversation.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": tool_name,
                                    "content": tool_result_text,
                                }
                            )
                        continue

                    if (
                        force_search_needed
                        and search_count == 0
                        and latest_user_text
                        and not force_injected
                    ):
                        logger.info(
                            f"[CHAT-{task_id}] Model skipped tool for fresh-data query, injecting mandatory search"
                        )
                        forced_args = {"query": latest_user_text, "num_results": 3}
                        yield build_status_payload("searching", latest_user_text[:200])
                        forced_result = await execute_tool("search", forced_args)
                        forced_result_text = (
                            forced_result
                            if isinstance(forced_result, str)
                            else json.dumps(forced_result, ensure_ascii=False)
                        )
                        search_count += 1
                        force_injected = True
                        yield build_status_payload("search_results_received")

                        persist_tool_log(
                            raw_request.app,
                            session_id,
                            task_id,
                            "search",
                            latest_user_text,
                            forced_args,
                            forced_result_text,
                        )
                        tool_logs_for_turn.append(
                            {
                                "tool_name": "search",
                                "tool_query": latest_user_text,
                                "tool_arguments": forced_args,
                                "tool_result": forced_result_text,
                                "injected": True,
                            }
                        )
                        conversation.append(
                            {
                                "role": "user",
                                "content": (
                                    "نتیجه جستجوی اجباری (به‌خاطر نیاز به اطلاعات به‌روز):\n"
                                    f"{forced_result_text}"
                                ),
                            }
                        )
                        continue

                    if not yielded_session:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "session_id": session_id,
                                    "task_id": task_id,
                                    "done": False,
                                },
                                ensure_ascii=False,
                            )
                            + "\n\n"
                        )
                        yielded_session = True

                    final_payload = {
                        "model": request.model or LLM_MODEL,
                        "messages": normalize_upstream_messages(
                            conversation,
                            announcement=(
                                announcement_text
                                + "\n- You are now in final answer mode. Do not call tools."
                            ),
                        ),
                        "stream": True,
                        "temperature": TEMPERATURE,
                        "top_p": 0.75,
                        "top_k": 20,
                        "max_tokens": MAX_NEW_TOKENS,
                        "tools": TOOLS,
                        "tool_choice": "none",
                    }

                    yield build_status_payload("thinking")
                    full_response = ""
                    first_token_time = None
                    async with client.stream(
                        "POST", url, json=final_payload
                    ) as final_resp:
                        if final_resp.status_code != 200:
                            error_text = (await final_resp.aread()).decode(
                                "utf-8", errors="ignore"
                            )
                            raise RuntimeError(
                                f"Upstream error {final_resp.status_code}: {error_text}"
                            )

                        async for line in final_resp.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            if await raw_request.is_disconnected():
                                logger.info(f"[CHAT-{task_id}] ⚠️ Client disconnected")
                                active_tasks[task_id] = False
                                break

                            data = line[5:].strip()
                            if data == "[DONE]":
                                break

                            try:
                                payload_chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue

                            choices_chunk = payload_chunk.get("choices", [])
                            if not choices_chunk:
                                continue

                            delta = choices_chunk[0].get("delta", {})
                            content = delta.get("content")
                            if not content:
                                continue

                            if first_token_time is None:
                                first_token_time = (
                                    datetime.now() - start_time
                                ).total_seconds()
                                logger.info(
                                    f"[CHAT-{task_id}] First final token in {first_token_time:.2f}s"
                                )
                            full_response += content
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "message": {
                                            "role": "assistant",
                                            "content": content,
                                        },
                                        "done": False,
                                        "session_id": session_id,
                                        "task_id": task_id,
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n\n"
                            )

                    break

                if not full_response:
                    full_response = "متاسفم، در تولید پاسخ نهایی مشکلی رخ داد. لطفاً دوباره تلاش کنید."

                persist_message(
                    raw_request.app,
                    session_id,
                    "assistant",
                    full_response,
                    metadata={
                        "task_id": task_id,
                        "search_count": search_count,
                        "tools": tool_logs_for_turn,
                    },
                )

                if not yielded_session:
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "session_id": session_id,
                                "task_id": task_id,
                                "done": False,
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"[CHAT-{task_id}] ✅ Response completed in {duration:.2f}s"
                )
                logger.info(
                    f'[CHAT-{task_id}] Response preview: "{full_response[:100]}..."'
                )

                final_data = {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "model": request.model or LLM_MODEL,
                    "created_at": datetime.now().isoformat(),
                    "duration_seconds": duration,
                    "session_id": session_id,
                    "task_id": task_id,
                    "search_count": search_count,
                }

                yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"[CHAT-{task_id}] ❌ Streaming error: {str(e)}")
                error_data = {
                    "error": str(e),
                    "done": True,
                    "session_id": session_id,
                    "task_id": task_id,
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            finally:
                if "progress_task" in locals():
                    progress_task.cancel()
                if task_id in active_tasks:
                    del active_tasks[task_id]

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Session-Id": session_id,
            },
        )

    except Exception as e:
        logger.error(f"[CHAT-{task_id}] ❌ Chat error: {str(e)}")
        if task_id in active_tasks:
            del active_tasks[task_id]
        raise HTTPException(
            status_code=500, detail=f"Error processing request: {str(e)}"
        )


# Cancel a chat task
@app.post("/api/chat/cancel/{task_id}")
async def cancel_chat(task_id: str):
    if task_id in active_tasks:
        active_tasks[task_id] = False
        logger.info(f"[CHAT-{task_id}] 🛑 Cancellation requested")
        return {"status": "cancelled", "task_id": task_id}
    else:
        return {"status": "not_found", "task_id": task_id}


# ─── User management ───
class RegisterUserRequest(BaseModel):
    username: str


@app.post("/api/user/register")
async def register_user(req: RegisterUserRequest, raw_request: Request):
    """Register or retrieve a user by username."""
    username = req.username.strip()
    if not username or len(username) < 2:
        raise HTTPException(
            status_code=400, detail="Username must be at least 2 characters"
        )

    users_table = raw_request.app.state.db.table("users")
    user_query = Query()
    existing = users_table.search(user_query.username == username)

    if existing:
        user = existing[0]
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "created": False,
        }

    user_id = str(uuid.uuid4())
    users_table.insert(
        {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now().isoformat(),
        }
    )
    logger.info(f"[USER] New user registered: {username} ({user_id})")
    return {"user_id": user_id, "username": username, "created": True}


@app.get("/api/user/{user_id}")
async def get_user(user_id: str, raw_request: Request):
    """Get user info by user_id."""
    users_table = raw_request.app.state.db.table("users")
    user_query = Query()
    results = users_table.search(user_query.user_id == user_id)
    if not results:
        raise HTTPException(status_code=404, detail="User not found")
    user = results[0]
    return {"user_id": user["user_id"], "username": user["username"]}


# ─── Chat history retrieval ───
@app.get("/api/history/{session_id}")
async def get_chat_history(session_id: str, raw_request: Request):
    """Retrieve chat history for a session from DB."""
    session_query = Query()
    rows = raw_request.app.state.messages_table.search(
        session_query.session_id == session_id
    )
    rows.sort(key=lambda item: item.get("timestamp", ""))
    messages = [
        {
            "role": row.get("role", "user"),
            "content": row.get("content", ""),
            "timestamp": row.get("timestamp", ""),
        }
        for row in rows
        if row.get("role") in ("user", "assistant") and row.get("content")
    ]
    return {"session_id": session_id, "messages": messages}


@app.get("/api/sessions/{user_id}")
async def get_user_sessions(user_id: str, raw_request: Request):
    """Get all sessions associated with a user."""
    sessions_table = raw_request.app.state.db.table("user_sessions")
    sq = Query()
    rows = sessions_table.search(sq.user_id == user_id)
    rows.sort(key=lambda item: item.get("last_active", ""), reverse=True)
    return {"user_id": user_id, "sessions": rows}


@app.post("/api/sessions/link")
async def link_session_to_user(raw_request: Request):
    """Link a session_id to a user_id."""
    body = await raw_request.json()
    user_id = body.get("user_id", "").strip()
    session_id = body.get("session_id", "").strip()
    if not user_id or not session_id:
        raise HTTPException(status_code=400, detail="user_id and session_id required")

    sessions_table = raw_request.app.state.db.table("user_sessions")
    sq = Query()
    existing = sessions_table.search(
        (sq.user_id == user_id) & (sq.session_id == session_id)
    )
    now = datetime.now().isoformat()
    if existing:
        sessions_table.update(
            {"last_active": now},
            (sq.user_id == user_id) & (sq.session_id == session_id),
        )
    else:
        sessions_table.insert(
            {
                "user_id": user_id,
                "session_id": session_id,
                "created_at": now,
                "last_active": now,
            }
        )
    return {"status": "ok"}


# Serve static files
app.mount("/static", StaticFiles(directory="public"), name="static")


# Main page
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("public/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Welcome to Nerd Agent Server</h1><p>Frontend files not found</p>",
            status_code=404,
        )


# Run the server
if __name__ == "__main__":
    import uvicorn

    print("╔══════════════════════════════════════════════════╗")
    print("║  🚀 Nerd Agent Server (FastAPI + Gemma3n)       ║")
    print("║  📍 http://localhost:8000                       ║")
    print("╚══════════════════════════════════════════════════╝")

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
