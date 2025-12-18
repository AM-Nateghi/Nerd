from transformers import pipeline
import torch
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI(title="BackNerd", version="0.1.0")

app.mount("/static", StaticFiles(directory="public"))


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("public/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


def initialize_model():
    pass


pipe = pipeline(
    "image-text-to-text",
    model="google/gemma-3n-e4b-it",
    device="auto",
    torch_dtype=torch.bfloat16,
)

messages = [
    {
        "role": "system",
        "content": [{"type": "text", "text": "You are a helpful assistant."}],
    },
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "url": "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/p-blog/candy.JPG",
            },
            {"type": "text", "text": "What animal is on the candy?"},
        ],
    },
]

output = pipe(text=messages, max_new_tokens=200)
print(output[0]["generated_text"][-1]["content"])
