from dotenv import load_dotenv

print("🔄 loading .env")
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
from transformers import pipeline
import torch
import base64
import io
from PIL import Image
import httpx
import uuid
from datetime import datetime, timedelta
import asyncio
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
import warnings

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

# Temporary storage for images in memory
image_store: Dict[str, Dict[str, Any]] = {}

# Gemma3n model
pipe = None


# function for expanding home directory path
def expand_path(path: str) -> str:
    """Convert ~ to full home directory path"""
    return str(Path(path).expanduser().resolve())


# Load settings from environment variables
MODEL_PATH = os.getenv("MODEL_PATH", "google/gemma-3n-e4b-it")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "2048"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))

# If local path, expand it
if MODEL_PATH.startswith("~") or MODEL_PATH.startswith("/"):
    MODEL_PATH = expand_path(MODEL_PATH)
    logger.info(f"📂 Local model path: {MODEL_PATH}")


# Lifespan context manager (جایگزین on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global pipe
    logger.info("🚀 Loading Gemma3n-e4b model...")

    try:
        # Check CUDA availability
        cuda_available = torch.cuda.is_available()
        device = "cuda" if cuda_available else "cpu"
        logger.info(f"🔍 CUDA available: {cuda_available}")
        logger.info(f"📊 Using device: {device}")
        if cuda_available:
            logger.info(f"🎮 GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"💾 GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
        
        # Check if local path exists
        if os.path.exists(MODEL_PATH):
            logger.info(f"✅ مدل از مسیر لوکال بارگذاری می‌شود: {MODEL_PATH}")
        else:
            logger.info(f"📥 مدل از Hugging Face Hub دانلود می‌شود: {MODEL_PATH}")

        pipe = pipeline(
            "image-text-to-text",
            model=MODEL_PATH,
            device=device,
            torch_dtype=torch.float16 if cuda_available else torch.float32,
        )
        logger.info("✅ model was successfully loaded!")
    except Exception as e:
        logger.error(f"❌ خطا در بارگذاری مدل: {e}")
        logger.error(f"💡 مسیر مورد استفاده: {MODEL_PATH}")
        logger.error(
            f"💡 برای استفاده از مسیر لوکال، متغیر محیطی MODEL_PATH را تنظیم کنید"
        )
        pipe = None

    yield

    # Shutdown
    logger.info("🛑 shutdown server...")


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
class ImageUploadRequest(BaseModel):
    image: str  # base64 string


class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = "gemma3n-e4b"
    tools: Optional[List[Dict[str, Any]]] = None


# Middleware for logging requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    return response


# Health check
@app.get("/health")
async def health_check():
    model_status = "loaded" if pipe is not None else "not_loaded"
    return {
        "ok": True,
        "model": "gemma3n-e4b",
        "model_status": model_status,
        "timestamp": datetime.now().isoformat(),
    }


# upload image endpoint
@app.post("/api/upload-image")
async def upload_image(request: ImageUploadRequest):
    try:
        if not request.image:
            raise HTTPException(status_code=400, detail="No image provided")

        # ساخت ID یونیک
        image_id = str(uuid.uuid4())

        # ذخیره تصویر با اطلاعات اضافی
        image_store[image_id] = {
            "data": request.image,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(hours=1),
        }

        # پاک کردن خودکار بعد از 1 ساعت
        asyncio.create_task(cleanup_image(image_id))

        image_url = f"/api/images/{image_id}"
        logger.info(f"[IMAGE] تصویر آپلود شد: {image_id}")

        return {"url": image_url, "id": image_id}

    except Exception as e:
        logger.error(f"[IMAGE] خطا در آپلود: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Image cleanup function after 1 hour
async def cleanup_image(image_id: str):
    await asyncio.sleep(3600)  # 1 ساعت
    if image_id in image_store:
        del image_store[image_id]
        logger.info(f"[IMAGE] تصویر پاک شد: {image_id}")


# serve image endpoint
@app.get("/api/images/{image_id}")
async def get_image(image_id: str):
    if image_id not in image_store:
        raise HTTPException(status_code=404, detail="Image not found")

    image_data = image_store[image_id]["data"]

    # حذف prefix اگر وجود داره
    if "," in image_data:
        image_data = image_data.split(",")[1]

    try:
        # تبدیل base64 به bytes
        image_bytes = base64.b64decode(image_data)
        return Response(content=image_bytes, media_type="image/png")

    except Exception as e:
        logger.error(f"[IMAGE] خطا در decode: {str(e)}")
        raise HTTPException(status_code=500, detail="Error decoding image")


# Helper function to fetch image from URL
async def fetch_image_as_base64(url: str) -> Optional[str]:
    try:
        # If the URL is our local one, get directly from store
        if "/api/images/" in url:
            image_id = url.split("/")[-1]
            if image_id in image_store:
                data = image_store[image_id]["data"]
                # Remove prefix
                if "," in data:
                    return data.split(",")[1]
                return data

        # Otherwise, download it
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            image_bytes = response.content
            return base64.b64encode(image_bytes).decode("utf-8")

    except Exception as e:
        logger.error(f"[IMAGE] Error downloading image: {str(e)}")
        return None


# Function to convert base64 to PIL Image
def base64_to_pil(base64_str: str) -> Image.Image:
    # Remove prefix if exists
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]

    image_bytes = base64.b64decode(base64_str)
    image = Image.open(io.BytesIO(image_bytes))
    return image


# Chat API
@app.post("/api/chat")
async def chat(request: ChatRequest):
    start_time = datetime.now()
    logger.info(
        f"[CHAT] Chat request received - number of messages: {len(request.messages)}"
    )

    if pipe is None:
        raise HTTPException(
            status_code=503, detail="Model is not loaded yet. Please wait."
        )

    try:
        # Convert message format for Gemma
        formatted_messages = []

        for msg in request.messages:
            formatted_msg = {"role": msg.role, "content": []}

            if isinstance(msg.content, str):
                # فرمت قدیمی - فقط متن
                formatted_msg["content"].append({"type": "text", "text": msg.content})

            elif isinstance(msg.content, list):
                # فرمت جدید - استخراج متن و تصاویر
                for part in msg.content:
                    if part.get("type") == "text":
                        formatted_msg["content"].append(
                            {"type": "text", "text": part.get("text", "")}
                        )

                    elif part.get("type") == "image":
                        image_url = part.get("url", "")
                        logger.info(f"[CHAT] دانلود تصویر از: {image_url}")

                        # دانلود و تبدیل تصویر
                        base64_image = await fetch_image_as_base64(image_url)

                        if base64_image:
                            # تبدیل به PIL Image
                            try:
                                pil_image = base64_to_pil(base64_image)
                                formatted_msg["content"].append(
                                    {"type": "image", "image": pil_image}
                                )
                                logger.info("[CHAT] تصویر با موفقیت پردازش شد")
                            except Exception as e:
                                logger.error(f"[CHAT] خطا در پردازش تصویر: {e}")

            formatted_messages.append(formatted_msg)

        logger.info("[CHAT] Sending to Gemma3n model...")

        # Call the model
        output = pipe(
            text=formatted_messages,
            max_new_tokens=2048,
            do_sample=True,
            temperature=1.0,
        )

        # استخراج پاسخ
        generated_text = output[0]["generated_text"][-1]["content"]

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"[CHAT] ✅ Response received in {duration:.2f}s")
        logger.info(f'[CHAT] Content: "{generated_text[:100]}..."')

        # Build response in Ollama-like format
        response_data = {
            "message": {"role": "assistant", "content": generated_text},
            "model": request.model,
            "created_at": datetime.now().isoformat(),
            "done": True,
            "duration_seconds": duration,
        }

        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"[CHAT] ❌ Error in chat: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error processing request: {str(e)}"
        )


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
    print("║  🤖 Model: google/gemma-3n-e4b-it               ║")
    print("╚══════════════════════════════════════════════════╝")

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
