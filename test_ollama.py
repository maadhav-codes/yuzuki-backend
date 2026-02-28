import requests
import json

url = "http://localhost:11434/api/generate"

payload = {"model": "nova:latest", "prompt": "Why is the sky blue?", "stream": True}

try:
    response = requests.post(url, json=payload, stream=True, timeout=5)

    if response.status_code == 200:
        print("Connection Successful. Streaming Response: \n")

        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))

                if "response" in chunk:
                    print(chunk["response"], end="", flush=True)

                if chunk.get("done"):
                    print("\n\n--- Generation Complete ---")
    else:
        print(f"Ollama Error ({response.status_code}): {response.text}")

except requests.exceptions.ConnectionError:
    print("Error: Could not connect to Ollama. Is the server running on port 11434?")
except requests.exceptions.Timeout:
    print("Error: The request timed out.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
