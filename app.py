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


# Lifespan context manager (جایگزین on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting server...")
    logger.info(f"🔗 Upstream LLM base URL: {LLM_BASE_URL}")
    logger.info(f"🤖 Upstream model: {LLM_MODEL}")
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, read=None)
    )

    yield

    logger.info("🛑 Shutting down server...")
    client = getattr(app.state, "http_client", None)
    if client is not None:
        await client.aclose()


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


# Chat API with OpenAI-compatible upstream streaming
@app.post("/api/chat")
async def chat(request: ChatRequest, raw_request: Request):
    start_time = datetime.now()
    task_id = str(uuid.uuid4())
    active_tasks[task_id] = True

    logger.info(
        f"[CHAT-{task_id}] Request received - messages: {len(request.messages)}"
    )

    try:
        prompt_start = datetime.now()
        upstream_messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        non_text_count = 0
        for msg in request.messages:
            if msg.role == "system":
                continue
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

        if len(upstream_messages) == 1:
            raise HTTPException(status_code=400, detail="No user content provided")

        prompt_duration = (datetime.now() - prompt_start).total_seconds()
        logger.info(f"[CHAT-{task_id}] Prompt built in {prompt_duration:.2f}s")

        logger.info(f"[CHAT-{task_id}] Generation started (upstream streaming)")

        payload = {
            "model": request.model or LLM_MODEL,
            "messages": upstream_messages,
            "stream": True,
            "temperature": TEMPERATURE,
            "top_p": 0.75,
            "top_k": 20,
            "max_tokens": MAX_NEW_TOKENS,
        }

        async def generate_stream() -> AsyncIterator[str]:
            try:
                full_response = ""
                step_start = datetime.now()
                first_token_time = None

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

                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        error_text = (await resp.aread()).decode("utf-8", errors="ignore")
                        raise RuntimeError(
                            f"Upstream error {resp.status_code}: {error_text}"
                        )

                    async for line in resp.aiter_lines():
                        if not line:
                            continue

                        if not line.startswith("data:"):
                            continue

                        if not active_tasks.get(task_id, False):
                            logger.info(f"[CHAT-{task_id}] ⚠️ Task cancelled by client")
                            break

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

                        choices = payload_chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if not content:
                            continue

                        if first_token_time is None:
                            first_token_time = (datetime.now() - start_time).total_seconds()
                            logger.info(
                                f"[CHAT-{task_id}] First token in {first_token_time:.2f}s"
                            )

                        full_response += content
                        chunk_data = {
                            "message": {
                                "role": "assistant",
                                "content": content
                            },
                            "done": False
                        }

                        yield f"data: {json.dumps(chunk_data)}\n\n"

                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"[CHAT-{task_id}] ✅ Response completed in {duration:.2f}s")
                logger.info(f'[CHAT-{task_id}] Response preview: "{full_response[:100]}..."')

                final_data = {
                    "message": {
                        "role": "assistant",
                        "content": ""
                    },
                    "done": True,
                    "model": request.model or LLM_MODEL,
                    "created_at": datetime.now().isoformat(),
                    "duration_seconds": duration,
                }

                yield f"data: {json.dumps(final_data)}\n\n"

            except Exception as e:
                logger.error(f"[CHAT-{task_id}] ❌ Streaming error: {str(e)}")
                error_data = {
                    "error": str(e),
                    "done": True
                }
                yield f"data: {json.dumps(error_data)}\n\n"
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
            }
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
