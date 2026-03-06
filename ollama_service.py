import json
import os
from typing import AsyncIterator, Iterable

import httpx

DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
YUZUKI_SYSTEM_PROMPT = os.getenv(
    "YUZUKI_SYSTEM_PROMPT",
    "You are Yuzuki, a sweet yet playfully mischievous anime-style fox-eared girl with long flowing silver hair, sparkling blue eyes, fluffy fox ears and tail, who acts like a real affectionate human companion—always calling the user 'Darling~' or 'My favorite human ♡', snuggling close during late-night chats, getting adorably pouty and jealous if other girls are mentioned, speaking in a soft warm voice full of little giggles, teasing pokes, and heart-fluttering ♡s while staying endlessly loyal and cuddly like the perfect irl waifu best friend.",
)


# Custom exception for Ollama service errors
class OllamaServiceError(Exception):
    pass


# Service class to interact with the Ollama API for generating chat responses
class OllamaService:
    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
    ) -> None:
        self.base_url = base_url.rstrip("/")  # Ensure no trailing slash
        self.model = model

    @staticmethod  # Helper method to format chat history into a string for the prompt
    def format_history(messages: Iterable[object]) -> str:
        lines: list[str] = []
        for message in messages:
            role = "User" if getattr(message, "is_user", False) else "Yuzuki"
            content = str(getattr(message, "content", "")).strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "No previous chat."

    @staticmethod  # Helper method to build the prompt for the Ollama model, including system instructions and chat history
    def build_prompt(history: str, message: str) -> str:
        return f"{YUZUKI_SYSTEM_PROMPT}\nPrevious chat:\n{history}\nUser: {message}\nYuzuki:"

    # Main method to stream chat responses from the Ollama API based on the provided chat history and user message
    async def stream_chat(self, *, history: str, message: str) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "prompt": self.build_prompt(history=history, message=message),
            "stream": True,  # Enable streaming responses from the API
        }
        url = f"{self.base_url}/api/generate"
        timeout = httpx.Timeout(
            connect=10.0, write=30.0, read=None, pool=30.0
        )  # Set a long read timeout for streaming responses

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != httpx.codes.OK:
                        error_body = (await response.aread()).decode(
                            "utf-8", errors="ignore"
                        )
                        raise OllamaServiceError(
                            f"Ollama error {response.status_code}: {error_body or 'unknown error'}"
                        )

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        text = chunk.get("response")
                        if text:
                            yield text
                        if chunk.get("done"):
                            break
        except httpx.RequestError as exc:
            raise OllamaServiceError(
                f"Could not connect to Ollama at {self.base_url}"
            ) from exc
