import time

import anthropic
import httpx
from openai import OpenAI

from .config import get_base_url, get_model, get_provider


class APIClient:
    def __init__(self, api_key: str, model: str | None = None):
        self.model = model or get_model()
        self.provider = get_provider()
        self.api_key = api_key

        if self.provider == "openai_compatible":
            base_url = get_base_url() or "https://api.deepseek.com"
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=httpx.Client(proxy=None, timeout=120.0),
            )
        else:
            self.client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 16384,
        temperature: float = 0.7,
    ) -> str:
        if self.provider == "openai_compatible":
            return self._generate_openai(system_prompt, user_message, max_tokens, temperature)
        return self._generate_anthropic(system_prompt, user_message, max_tokens, temperature)

    def _generate_openai(
        self, system_prompt: str, user_message: str, max_tokens: int, temperature: float
    ) -> str:
        last_error = None
        for attempt in range(4):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                )
                msg = response.choices[0].message
                content = msg.content or ""
                rc = getattr(msg, "reasoning_content", None)
                if not content and rc:
                    if max_tokens < 32768:
                        return self._generate_openai(
                            system_prompt, user_message, max_tokens=32768, temperature=temperature
                        )
                return content
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "rate" in err_str or "429" in str(e):
                    if attempt < 3:
                        time.sleep(2 ** attempt)
                        continue
                    raise
                if "401" in str(e) or "auth" in err_str:
                    raise RuntimeError(
                        "Authentication failed. Check your API key — "
                        "run `user-insights config` to update it."
                    )
                if "connect" in err_str or "timeout" in err_str or "disconnect" in err_str or "protocol" in err_str:
                    if attempt < 3:
                        time.sleep(2 ** attempt)
                        continue
                    raise RuntimeError("Cannot reach the API. Check your internet connection.")
                raise RuntimeError(f"API error: {e}")
        raise last_error  # type: ignore[misc]

    def _generate_anthropic(
        self, system_prompt: str, user_message: str, max_tokens: int, temperature: float
    ) -> str:
        last_error = None
        for attempt in range(4):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                return response.content[0].text
            except anthropic.RateLimitError as e:
                last_error = e
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except anthropic.AuthenticationError:
                raise RuntimeError(
                    "Authentication failed. Check your API key — "
                    "run `user-insights config` to update it."
                )
            except anthropic.APIConnectionError:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(
                    "Cannot reach the Anthropic API. Check your internet connection."
                )
        raise last_error  # type: ignore[misc]
