"""
Tests for IoNetLLMClient and LLM factory functions.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from types import SimpleNamespace

from src.infrastructure.llm_client import (
    IoNetLLMClient,
    AnthropicLLMClient,
    get_llm_client,
    get_trip_chat_llm_client,
    get_macro_planning_llm_client,
)
from src.config import Settings


# Mock response objects for OpenAI client

def create_mock_completion(content: str):
    """Create a mock OpenAI completion response."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class TestIoNetLLMClient:
    """Tests for IoNetLLMClient class."""

    def test_ionet_client_initialization(self):
        """Test IoNetLLMClient initializes correctly with API key."""
        with patch("src.infrastructure.llm_client.OpenAI") as mock_openai:
            client = IoNetLLMClient(
                api_key="test-api-key",
                model="Mistral-Nemo-Instruct-2407",
                max_output_tokens=512,
                temperature=0.5,
            )

            assert client.model == "Mistral-Nemo-Instruct-2407"
            assert client.max_output_tokens == 512
            assert client.temperature == 0.5

            mock_openai.assert_called_once_with(
                api_key="test-api-key",
                base_url="https://api.intelligence.io.solutions/api/v1/",
            )

    def test_ionet_client_missing_api_key(self):
        """Test IoNetLLMClient raises error without API key."""
        with pytest.raises(ValueError, match="API key is required"):
            IoNetLLMClient(
                api_key="",
                model="Mistral-Nemo-Instruct-2407",
            )

    def test_ionet_client_build_messages_with_system(self):
        """Test message building with system prompt."""
        with patch("src.infrastructure.llm_client.OpenAI"):
            client = IoNetLLMClient(
                api_key="test-key",
                model="test-model",
            )

            messages = client._build_messages(
                prompt="Hello",
                system_prompt="You are a helpful assistant.",
            )

            assert len(messages) == 2
            assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}
            assert messages[1] == {"role": "user", "content": "Hello"}

    def test_ionet_client_build_messages_without_system(self):
        """Test message building without system prompt."""
        with patch("src.infrastructure.llm_client.OpenAI"):
            client = IoNetLLMClient(
                api_key="test-key",
                model="test-model",
            )

            messages = client._build_messages(prompt="Hello")

            assert len(messages) == 1
            assert messages[0] == {"role": "user", "content": "Hello"}

    @pytest.mark.asyncio
    async def test_ionet_generate_text(self):
        """Test generate_text returns plain text."""
        with patch("src.infrastructure.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_client.chat.completions.create.return_value = create_mock_completion(
                "Hello! How can I help you today?"
            )

            client = IoNetLLMClient(
                api_key="test-key",
                model="Mistral-Nemo-Instruct-2407",
            )

            result = await client.generate_text(
                prompt="Say hello",
                system_prompt="Be friendly",
            )

            assert result == "Hello! How can I help you today?"

    @pytest.mark.asyncio
    async def test_ionet_generate_structured_plain_json(self):
        """Test generate_structured parses plain JSON."""
        with patch("src.infrastructure.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_client.chat.completions.create.return_value = create_mock_completion(
                '{"key": "value", "number": 42}'
            )

            client = IoNetLLMClient(
                api_key="test-key",
                model="test-model",
            )

            result = await client.generate_structured(prompt="Return JSON")

            assert result == {"key": "value", "number": 42}

    @pytest.mark.asyncio
    async def test_ionet_generate_structured_json_in_code_block(self):
        """Test generate_structured parses JSON from code block."""
        with patch("src.infrastructure.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_client.chat.completions.create.return_value = create_mock_completion(
                'Here is the response:\n```json\n{"data": [1, 2, 3]}\n```\nDone!'
            )

            client = IoNetLLMClient(
                api_key="test-key",
                model="test-model",
            )

            result = await client.generate_structured(prompt="Return JSON")

            assert result == {"data": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_ionet_generate_structured_invalid_json(self):
        """Test generate_structured raises error for invalid JSON."""
        with patch("src.infrastructure.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_client.chat.completions.create.return_value = create_mock_completion(
                "This is not valid JSON at all"
            )

            client = IoNetLLMClient(
                api_key="test-key",
                model="test-model",
            )

            with pytest.raises(ValueError, match="Failed to parse JSON"):
                await client.generate_structured(prompt="Return JSON")


class TestFactoryFunctions:
    """Tests for LLM factory functions."""

    def test_get_trip_chat_client_ionet(self):
        """Test get_trip_chat_llm_client returns IoNetLLMClient for ionet provider."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-ionet-key",
            trip_chat_model="Mistral-Nemo-Instruct-2407",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            client = get_trip_chat_llm_client(app_settings=mock_settings)

            assert isinstance(client, IoNetLLMClient)
            assert client.model == "Mistral-Nemo-Instruct-2407"
            assert client.max_output_tokens == 512
            assert client.temperature == 0.5

    def test_get_macro_planning_client_ionet(self):
        """Test get_macro_planning_llm_client returns IoNetLLMClient for ionet provider."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-ionet-key",
            trip_planning_model="meta-llama/Llama-3.3-70B-Instruct",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            client = get_macro_planning_llm_client(app_settings=mock_settings)

            assert isinstance(client, IoNetLLMClient)
            assert client.model == "meta-llama/Llama-3.3-70B-Instruct"
            assert client.max_output_tokens == 2048
            assert client.temperature == 0.3

    def test_get_trip_chat_client_anthropic(self):
        """Test get_trip_chat_llm_client returns AnthropicLLMClient for anthropic provider."""
        mock_settings = Settings(
            llm_provider="anthropic",
            anthropic_api_key="test-anthropic-key",
            trip_chat_model="claude-3-5-haiku-20241022",
        )

        with patch("src.infrastructure.llm_client.AsyncAnthropic"):
            client = get_trip_chat_llm_client(app_settings=mock_settings)

            assert isinstance(client, AnthropicLLMClient)
            assert client.model == "claude-3-5-haiku-20241022"

    def test_get_macro_planning_client_anthropic(self):
        """Test get_macro_planning_llm_client returns AnthropicLLMClient for anthropic provider."""
        mock_settings = Settings(
            llm_provider="anthropic",
            anthropic_api_key="test-anthropic-key",
            trip_planning_model="claude-3-5-sonnet-20241022",
        )

        with patch("src.infrastructure.llm_client.AsyncAnthropic"):
            client = get_macro_planning_llm_client(app_settings=mock_settings)

            assert isinstance(client, AnthropicLLMClient)
            assert client.model == "claude-3-5-sonnet-20241022"

    def test_get_llm_client_ionet(self):
        """Test get_llm_client returns IoNetLLMClient for ionet provider."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-ionet-key",
            trip_planning_model="meta-llama/Llama-3.3-70B-Instruct",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            client = get_llm_client(app_settings=mock_settings)

            assert isinstance(client, IoNetLLMClient)

    def test_get_llm_client_custom_model(self):
        """Test get_llm_client with custom model override."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-ionet-key",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            client = get_llm_client(
                model="custom-model-name",
                app_settings=mock_settings,
            )

            assert isinstance(client, IoNetLLMClient)
            assert client.model == "custom-model-name"

    def test_get_trip_chat_client_missing_ionet_key(self):
        """Test get_trip_chat_llm_client raises error when ionet key is missing."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key=None,
        )

        with pytest.raises(ValueError, match="IO Intelligence API key is required"):
            get_trip_chat_llm_client(app_settings=mock_settings)

    def test_get_macro_planning_client_missing_ionet_key(self):
        """Test get_macro_planning_llm_client raises error when ionet key is missing."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key=None,
        )

        with pytest.raises(ValueError, match="IO Intelligence API key is required"):
            get_macro_planning_llm_client(app_settings=mock_settings)

    def test_get_llm_client_unknown_provider(self):
        """Test get_llm_client raises error for unknown provider."""
        mock_settings = Settings(
            llm_provider="unknown_provider",
        )

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_client(app_settings=mock_settings)


class TestIoNetModels:
    """Tests for io.net model configurations."""

    def test_trip_chat_model_config(self):
        """Test trip chat model uses cost-optimized settings."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-key",
            trip_chat_model="Mistral-Nemo-Instruct-2407",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            client = get_trip_chat_llm_client(app_settings=mock_settings)

            # Verify cost-optimized settings
            assert client.max_output_tokens == 512  # Smaller for chat
            assert client.temperature == 0.5  # Balanced for dialog

    def test_macro_planning_model_config(self):
        """Test macro planning model uses reasoning-optimized settings."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-key",
            trip_planning_model="meta-llama/Llama-3.3-70B-Instruct",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            client = get_macro_planning_llm_client(app_settings=mock_settings)

            # Verify reasoning-optimized settings
            assert client.max_output_tokens == 2048  # Larger for complex output
            assert client.temperature == 0.3  # More deterministic

    def test_default_models(self):
        """Test default model values in settings."""
        default_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-key",
        )

        assert default_settings.trip_chat_model == "Mistral-Nemo-Instruct-2407"
        assert default_settings.trip_planning_model == "meta-llama/Llama-3.3-70B-Instruct"


class TestProviderSwitching:
    """Tests for switching between providers."""

    def test_switch_to_anthropic(self):
        """Test switching provider to anthropic uses correct client."""
        mock_settings = Settings(
            llm_provider="anthropic",
            anthropic_api_key="test-anthropic-key",
            trip_chat_model="claude-3-5-haiku-20241022",
            trip_planning_model="claude-3-5-sonnet-20241022",
        )

        with patch("src.infrastructure.llm_client.AsyncAnthropic"):
            chat_client = get_trip_chat_llm_client(app_settings=mock_settings)
            planning_client = get_macro_planning_llm_client(app_settings=mock_settings)

            assert isinstance(chat_client, AnthropicLLMClient)
            assert isinstance(planning_client, AnthropicLLMClient)
            assert chat_client.model == "claude-3-5-haiku-20241022"
            assert planning_client.model == "claude-3-5-sonnet-20241022"

    def test_switch_to_ionet(self):
        """Test switching provider to ionet uses correct client."""
        mock_settings = Settings(
            llm_provider="ionet",
            ionet_api_key="test-ionet-key",
            trip_chat_model="Mistral-Nemo-Instruct-2407",
            trip_planning_model="meta-llama/Llama-3.3-70B-Instruct",
        )

        with patch("src.infrastructure.llm_client.OpenAI"):
            chat_client = get_trip_chat_llm_client(app_settings=mock_settings)
            planning_client = get_macro_planning_llm_client(app_settings=mock_settings)

            assert isinstance(chat_client, IoNetLLMClient)
            assert isinstance(planning_client, IoNetLLMClient)
            assert chat_client.model == "Mistral-Nemo-Instruct-2407"
            assert planning_client.model == "meta-llama/Llama-3.3-70B-Instruct"
