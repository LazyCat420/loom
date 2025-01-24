import { StreamingTextResponse } from 'ai';

const OLLAMA_BASE_URL = "http://10.0.0.29:11434";

export async function POST(req: Request) {
  const { messages, modelConfig } = await req.json();
  
  if (modelConfig.provider === "ollama") {
    const response = await fetch(`${OLLAMA_BASE_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "llama3.2:latest",
        messages: messages.map((msg: any) => ({
          role: msg.role,
          content: msg.content
        })),
        stream: true,
      }),
    });

    // Return the streaming response
    return new StreamingTextResponse(response.body);
  }

  // ... existing code for other providers ...
} 