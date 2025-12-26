"""
Provider-agnostic LLM client abstraction.
Supports multiple providers: IO Intelligence (io.net) and Anthropic Claude.
"""
from abc import ABC, abstractmethod
from typing import Optional
import json

import anyio
from openai import OpenAI
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from src.config import settings, Settings


class LLMResponse(BaseModel):
    """Standardized LLM response."""
    text: str
    structured_output: Optional[dict] = None


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Generate plain text response."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> dict:
        """Generate structured JSON response."""
        pass


class IoNetLLMClient(LLMClient):
    """
    IO Intelligence (io.net) implementation of LLM client.
    Uses OpenAI-compatible API with custom base_url.

    Supported models:
    - Mistral-Nemo-Instruct-2407 (cheap, fast - for chat)
    - meta-llama/Llama-3.3-70B-Instruct (strong reasoning - for planning)
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int = 1024,
        temperature: float = 0.3,
        base_url: str = "https://api.intelligence.io.solutions/api/v1/",
    ):
        """
        Initialize IO Intelligence client.

        Args:
            api_key: IO Intelligence API key
            model: Model name (e.g., "Mistral-Nemo-Instruct-2407")
            max_output_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-1.0)
            base_url: API base URL
        """
        if not api_key:
            raise ValueError("IO Intelligence API key is required. Set IONET_API_KEY environment variable.")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        """Build OpenAI-style messages list."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return messages

    def _sync_chat_completion(self, messages: list[dict], max_tokens: int) -> str:
        """Synchronous chat completion call."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_completion_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """
        Generate plain text response using IO Intelligence.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response

        Returns:
            Generated text string
        """
        messages = self._build_messages(prompt, system_prompt)

        # Run sync OpenAI client in thread to avoid blocking
        response_text = await anyio.to_thread.run_sync(
            lambda: self._sync_chat_completion(messages, max_tokens)
        )

        return response_text

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Generate structured JSON response using IO Intelligence.

        Args:
            prompt: User prompt (should request JSON output)
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response

        Returns:
            Parsed JSON as dict

        Raises:
            ValueError: If JSON parsing fails
        """
        messages = self._build_messages(prompt, system_prompt)

        # Run sync OpenAI client in thread to avoid blocking
        text_response = await anyio.to_thread.run_sync(
            lambda: self._sync_chat_completion(messages, max_tokens)
        )

        # Parse JSON from response
        try:
            # Look for JSON in code blocks or raw text
            if "```json" in text_response:
                json_start = text_response.find("```json") + 7
                json_end = text_response.find("```", json_start)
                json_text = text_response[json_start:json_end].strip()
            elif "```" in text_response:
                json_start = text_response.find("```") + 3
                json_end = text_response.find("```", json_start)
                json_text = text_response[json_start:json_end].strip()
            else:
                json_text = text_response.strip()

            return json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON from IO Intelligence response: {e}\n"
                f"Model: {self.model}\n"
                f"Response: {text_response[:500]}..."
            )


class AnthropicLLMClient(LLMClient):
    """
    Anthropic Claude implementation of LLM client.
    Uses async Anthropic SDK.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key (defaults to settings)
            base_url: Base URL for API (defaults to settings)
            model: Model name (defaults to settings)
        """
        self.api_key = api_key or settings.anthropic_api_key
        self.base_url = base_url or settings.anthropic_base_url
        self.model = model or settings.anthropic_model

        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable.")

        self.client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Generate plain text response using Claude."""
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=messages,
        )

        return response.content[0].text

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Generate structured JSON response using Claude.
        Expects the prompt to request JSON output and the model to comply.
        """
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=messages,
        )

        text_response = response.content[0].text

        # Try to parse JSON from response
        try:
            # Look for JSON in code blocks or raw text
            if "```json" in text_response:
                json_start = text_response.find("```json") + 7
                json_end = text_response.find("```", json_start)
                json_text = text_response[json_start:json_end].strip()
            elif "```" in text_response:
                json_start = text_response.find("```") + 3
                json_end = text_response.find("```", json_start)
                json_text = text_response[json_start:json_end].strip()
            else:
                json_text = text_response.strip()

            return json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from LLM response: {e}\nResponse: {text_response}")


# Factory functions to get LLM clients

def get_llm_client(
    model: Optional[str] = None,
    app_settings: Optional[Settings] = None,
) -> LLMClient:
    """
    Factory function to create LLM client instance.
    Uses the configured provider (io.net or Anthropic).

    Args:
        model: Optional model override
        app_settings: Optional settings override (for testing)
    """
    s = app_settings or settings

    if s.llm_provider == "ionet":
        if not s.ionet_api_key:
            raise ValueError(
                "IO Intelligence API key is required. "
                "Set IONET_API_KEY environment variable."
            )
        return IoNetLLMClient(
            api_key=s.ionet_api_key,
            model=model or s.trip_planning_model,
            max_output_tokens=2048,
            temperature=0.3,
            base_url=s.ionet_base_url,
        )
    elif s.llm_provider == "anthropic":
        return AnthropicLLMClient(model=model)
    else:
        raise ValueError(f"Unknown LLM provider: {s.llm_provider}. Use 'ionet' or 'anthropic'.")


def get_trip_chat_llm_client(app_settings: Optional[Settings] = None) -> LLMClient:
    """
    Factory function for trip chat LLM client (optimized for cost).
    Uses cheaper/faster model for conversational updates.

    io.net: Mistral-Nemo-Instruct-2407 (max 512 tokens, temp 0.5)
    Anthropic: claude-3-5-haiku-20241022

    Args:
        app_settings: Optional settings override (for testing)
    """
    s = app_settings or settings

    if s.llm_provider == "ionet":
        if not s.ionet_api_key:
            raise ValueError(
                "IO Intelligence API key is required. "
                "Set IONET_API_KEY environment variable."
            )
        return IoNetLLMClient(
            api_key=s.ionet_api_key,
            model=s.trip_chat_model,
            max_output_tokens=512,  # Cost-optimized: smaller response
            temperature=0.5,  # Good balance for dialog + structured updates
            base_url=s.ionet_base_url,
        )
    elif s.llm_provider == "anthropic":
        return AnthropicLLMClient(model=s.trip_chat_model)
    else:
        raise ValueError(f"Unknown LLM provider: {s.llm_provider}. Use 'ionet' or 'anthropic'.")


def get_macro_planning_llm_client(app_settings: Optional[Settings] = None) -> LLMClient:
    """
    Factory function for macro planning LLM client.
    Uses more powerful model for complex itinerary generation.

    io.net: meta-llama/Llama-3.3-70B-Instruct (max 2048 tokens, temp 0.3)
    Anthropic: claude-3-5-sonnet-20241022

    Args:
        app_settings: Optional settings override (for testing)
    """
    s = app_settings or settings

    if s.llm_provider == "ionet":
        if not s.ionet_api_key:
            raise ValueError(
                "IO Intelligence API key is required. "
                "Set IONET_API_KEY environment variable."
            )
        return IoNetLLMClient(
            api_key=s.ionet_api_key,
            model=s.trip_planning_model,
            max_output_tokens=2048,  # Larger for complex itineraries
            temperature=0.3,  # More deterministic structure
            base_url=s.ionet_base_url,
        )
    elif s.llm_provider == "anthropic":
        return AnthropicLLMClient(model=s.trip_planning_model)
    else:
        raise ValueError(f"Unknown LLM provider: {s.llm_provider}. Use 'ionet' or 'anthropic'.")
