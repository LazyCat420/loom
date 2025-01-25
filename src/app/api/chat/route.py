from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import json
from src.components.model_config import ModelConfig

app = FastAPI()
model_config = ModelConfig()

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    messages = data["messages"]
    provider_config = data["modelConfig"]
    
    if provider_config["provider"] == "ollama":
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://10.0.0.29:11434/api/generate",
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
            
    elif provider_config["provider"] == "lmstudio":
        model_config.handle_provider_change("lmstudio")
        endpoint = model_config.endpoint
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{endpoint}/chat/completions",
                json={
                    "model": "mistral-small-22b-arliai-rpmax-v1.1",
                    "messages": [
                        {"role": "system", "content": "You are a helpful AI assistant."},
                        *messages
                    ],
                    "temperature": 0.7,
                    "max_tokens": -1,
                    "stream": True
                },
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            return StreamingResponse(
                response.aiter_bytes(),
                media_type="text/event-stream"
            ) 