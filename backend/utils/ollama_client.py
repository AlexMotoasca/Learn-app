from flask import current_app
import httpx
import json

def call_ollama_generate(prompt: str, max_tokens: int | None = None):
    url = current_app.config["OLLAMA_URL"]
    model = current_app.config["OLLAMA_MODEL"]

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192
        }
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)

    try:
        r = httpx.post(url, json=payload, timeout=300)  # 5 min
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Ollama request failed: {e}")

    data = r.json()
    output = (data.get("response") or "").strip()

    # protecții mici
    if output.startswith("```"):
        output = output.strip("`").strip()
    if output.startswith('"') and output.endswith('"'):
        try:
            output = json.loads(output)
        except:
            pass

    return output or "<<<ERROR>>> Empty response from model."

