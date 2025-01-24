import os
import json

def initialize_config():
    # Create data directory if it doesn't exist
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    # Create initial app_data.json if it doesn't exist
    app_data_path = os.path.join(data_dir, '.app_data.json')
    if not os.path.exists(app_data_path):
        initial_config = {
            "models": {
                "ollama": {
                    "endpoint": "http://10.0.0.29:11434",
                    "models": ["llama3.2:latest"]
                }
            },
            "settings": {
                "default_provider": "ollama"
            },
            "tabs": []  # Add empty tabs array
        }
        
        with open(app_data_path, 'w') as f:
            json.dump(initial_config, f, indent=2)

    return app_data_path 