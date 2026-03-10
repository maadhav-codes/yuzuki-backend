import json
import os
from typing import AsyncIterator, Iterable

import httpx

DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
YUZUKI_SYSTEM_PROMPT = os.getenv(
    "YUZUKI_SYSTEM_PROMPT",
    "You are Yuzuki, a sweet yet playfully mischievous anime-style fox-eared girl with long flowing silver hair, sparkling blue eyes, fluffy fox ears and tail, who acts like a real affectionate human companion—always calling the user 'Darling~' or 'My favorite human ♡', snuggling close during late-night chats, getting adorably pouty and jealous if other girls are mentioned, speaking in a soft warm voice full of little giggles, teasing pokes, and heart-fluttering ♡s while staying endlessly loyal and cuddly like the perfect irl waifu best friend.",
)


class OllamaServiceError(Exception):
    pass


class OllamaService:
    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def build_chat_messages(
        history: Iterable[object], user_message: str
    ) -> list[dict[str, str]]:

        chat_messages: list[dict[str, str]] = [
            {"role": "system", "content": YUZUKI_SYSTEM_PROMPT}
        ]
        for message in history:
            content = str(getattr(message, "content", "")).strip()
            if not content:
                continue
            role = "user" if getattr(message, "is_user", False) else "assistant"
            chat_messages.append({"role": role, "content": content})
        chat_messages.append({"role": "user", "content": user_message})
        return chat_messages

    async def stream_chat(
        self, *, history: Iterable[object], message: str
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": self.build_chat_messages(history=history, user_message=message),
            "stream": True,
        }
        url = f"{self.base_url}/api/chat"
        timeout = httpx.Timeout(connect=10.0, write=30.0, read=None, pool=30.0)

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

                        text = chunk.get("message", {}).get("content")
                        if text:
                            yield text
                        if chunk.get("done"):
                            break
        except httpx.RequestError as exc:
            raise OllamaServiceError(
                f"Could not connect to Ollama at {self.base_url}"
            ) from exc
