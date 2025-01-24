from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import json

OLLAMA_BASE_URL = "http://10.0.0.29:11434"

app = FastAPI()

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    messages = data["messages"]
    model_config = data["modelConfig"]
    
    if model_config["provider"] == "ollama":
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": messages[-1]["content"],
                    "stream": True,
                    "temperature": 0.7,
                    "top_p": 0.9
                },
                headers={"Content-Type": "application/json"},
            )
            
            return StreamingResponse(
                response.aiter_bytes(),
                media_type="text/event-stream"
            ) 