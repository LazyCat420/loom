from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ModelOption:
    label: str
    value: str
    models: List[str]

class ModelConfig:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.endpoint: Optional[str] = None
        
        self.model_options = [
            ModelOption(
                label="OpenAI",
                value="openai",
                models=["davinci-002", "gpt-3.5-turbo", "gpt-4"]
            ),
            ModelOption(
                label="Ollama",
                value="ollama",
                models=["llama3.2:latest"]
            ),
            ModelOption(
                label="LM Studio",
                value="lmstudio",
                models=["mistral-small-22b-arliai-rpmax-v1.1"]
            )
        ]
    
    def handle_provider_change(self, provider: str):
        if provider == "ollama":
            self.api_key = None
            self.endpoint = "http://10.0.0.29:11434"
        elif provider == "openai":
            self.endpoint = "https://api.openai.com/v1"
        elif provider == "lmstudio":
            self.api_key = None
            self.endpoint = "http://127.0.0.1:80/v1" 