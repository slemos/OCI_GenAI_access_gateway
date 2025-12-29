# Oracle Cloud Infrastructure (OCI) Generative AI Service

## Overview
The **OCI Generative AI Service** is a fully managed service that integrates versatile language models for various applications. This service allows developers to leverage powerful AI capabilities without the complexity of managing infrastructure.

## Key Features
- **Easy Integration**: Use the provided SDK to easily call OCI Generative AI services.
- **OpenAI Compatibility**: The service supports OpenAI API formats, enabling quick integration with existing applications.
- **Model Support**: Supports multiple models including Grok, Llama 4, Whisper, Oracle, and Gemini, among others.

## Change Log
- **2025-12-29**: Support for AI Speech Realtime service. See [Oracle Speech API](https://docs.oracle.com/en-us/iaas/api/#/EN/speech/20220101/)
- **2025-12-23**: Support for imported models. See [Oracle Documentation](https://docs.oracle.com/en-us/iaas/Content/generative-ai/imported-models.htm).
- **2025-12-09**: Added support for **Gemini** models from Google.
- **2025-10-11**: Deployed the app on OCI OKE. [Refer here for more](deployments/readme.md).
- **2025-09-25**: Introduced **Easy Mode** for environment variable configuration.

## Prerequisites

1. **Install Python Packages**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Authentication**:
   - **API Key**: Create an OCI API key and configure `~/.oci/config`. Set `AUTH_TYPE = "API_KEY"` in `config.py`.
   - **Instance Principal**: For OCI-hosted deployments, set `AUTH_TYPE = "INSTANCE_PRINCIPAL"`.
   - **Create a config.py file**: Copy config-sample.py to config.py and edit content as needed.

3. **Configure Models**:
   - Use environment variables for simple setup (e.g., `OCI_REGION`, `OCI_COMPARTMENT`).
   - For advanced configurations, edit `models.yaml` to specify models by region and compartment.

## Deployment

### Local Development
- **Run with Uvicorn**:
  ```bash
  cd app && python app.py
  ```
- **Run with Gunicorn** (Linux only):
  ```bash
  gunicorn app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --timeout 600 --bind 0.0.0.0:8088
  ```

### Docker Deployment
1. **Build the Image**:
   ```bash
   docker build -t oci_genai_gateway .
   ```
2. **Run the Container**:
   ```bash
   docker run -p 8088:8088 -v ~/.oci:/root/.oci -it oci_genai_gateway
   ```

### OCI OKE Deployment
Refer to [deployments/readme.md](deployments/readme.md) for deploying on Oracle Kubernetes Engine.

## Testing

Use the provided [endpoint_test.ipynb](endpoint_test.ipynb) notebook to test all endpoints with the OpenAI client. Set the base URL to `http://127.0.0.1:8088/v1/` and use `ocigenerativeai` as the API key.

## API Endpoints

The OCI Generative AI Access Gateway provides OpenAI-compatible endpoints for interacting with OCI Generative AI services. Below is a list of all available endpoints:

### 1. Models
- **GET /v1/models**: List all available models.
- **GET /v1/models/{model_id}**: Retrieve information about a specific model.

### 2. Chat Completions
- **POST /v1/chat/completions**: Generate chat completions using supported models.

#### Example Request (Non-Streaming):
```python
from openai import OpenAI

client = OpenAI(
    api_key="ocigenerativeai",
    base_url="http://127.0.0.1:8088/v1/",
    max_retries=0
)

completion = client.chat.completions.create(
    model="cohere.command-latest",
    messages=[{"role": "user", "content": "Hello! 你好！"}],
    max_tokens=1024,
    temperature=0.7
)
print(completion.choices[0].message.content)
```

#### Example Request (Streaming):
```python
response = client.chat.completions.create(
    model="cohere.command-latest",
    messages=[{"role": "user", "content": "Hello! 你好！"}],
    max_tokens=1024,
    stream=True
)
for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')
```

### 3. Embeddings
- **POST /v1/embeddings**: Generate embeddings for text inputs.

#### Example Request:
```python
embeddings = client.embeddings.create(
    input=["Hello, world!", "How are you?"],
    model="cohere.embed-english-v3.0"
)
print(embeddings.data)
```

### 4. Audio Transcriptions
- **POST /v1/audio/transcriptions**: Transcribe audio files.

#### Example Requests:

**Using Whisper Model:**
```bash
curl -X POST "http://127.0.0.1:8088/v1/audio/transcriptions" \
  -H "Authorization: Bearer ocigenerativeai" \
  -F "file=@audio.pcm" \
  -F "model=WHISPER" \
  -F "language=es" \
  -F "response_format=json" \
```

**Using Oracle Model:**
```bash
curl -X POST "http://127.0.0.1:8088/v1/audio/transcriptions" \
  -H "Authorization: Bearer ocigenerativeai" \
  -F "file=@audio.pcm" \
  -F "model=ORACLE" \
  -F "language=es-ES" \
  -F "response_format=json" \
  -F "region=us-ashburn-1" \
```

**Note**: Audio is sent in PCM format at 16000Hz by default.

## Conclusion
The OCI Generative AI Service provides a robust platform for integrating AI capabilities into applications. With its easy setup and extensive model support, developers can quickly harness the power of AI in their projects.
