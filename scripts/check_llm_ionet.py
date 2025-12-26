#!/usr/bin/env python3
"""
Integration check for LLM / IO.NET connectivity.
Tests that the LLM client can successfully communicate with the configured provider.

Usage:
    python -m scripts.check_llm_ionet
    or
    make check-llm

Exit codes:
    0: Success - LLM is working correctly
    1: Failure - LLM request failed or response invalid
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.llm_client import get_trip_chat_llm_client
from src.config import settings


async def check_llm_connectivity():
    """Check LLM connectivity with a minimal test request."""

    # Check configuration
    if settings.llm_provider == "ionet" and not settings.ionet_api_key:
        print("❌ LLM / IO.NET check: FAILED")
        print("   Reason: IONET_API_KEY not configured")
        print("   Set the IONET_API_KEY environment variable")
        return False

    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        print("❌ LLM / Anthropic check: FAILED")
        print("   Reason: ANTHROPIC_API_KEY not configured")
        print("   Set the ANTHROPIC_API_KEY environment variable")
        return False

    try:
        # Get LLM client (uses trip_chat model for cost efficiency)
        client = get_trip_chat_llm_client()

        print(f"🔄 Testing LLM connectivity...")
        print(f"   Provider: {settings.llm_provider}")
        if settings.llm_provider == "ionet":
            print(f"   Model: {settings.trip_chat_model}")
            print(f"   Base URL: {settings.ionet_base_url}")
        else:
            print(f"   Model: {settings.trip_chat_model}")

        # Make a minimal test request
        system_prompt = "You are a test assistant. Follow instructions exactly."
        user_prompt = "Respond with exactly this string and nothing else: PING_OK"

        response = await client.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=32,  # Very small to minimize cost
        )

        # Validate response
        response_clean = response.strip()

        if "PING_OK" in response_clean:
            print(f"✅ LLM / {settings.llm_provider.upper()} check: OK")
            print(f"   Response: {response_clean[:100]}")
            return True
        else:
            print(f"❌ LLM / {settings.llm_provider.upper()} check: FAILED")
            print(f"   Reason: Response doesn't contain expected 'PING_OK'")
            print(f"   Got: {response_clean[:200]}")
            return False

    except ValueError as e:
        print(f"❌ LLM / {settings.llm_provider.upper()} check: FAILED")
        print(f"   Reason: Configuration error - {str(e)}")
        return False
    except Exception as e:
        print(f"❌ LLM / {settings.llm_provider.upper()} check: FAILED")
        print(f"   Reason: {type(e).__name__}: {str(e)}")
        return False


def main():
    """Main entry point."""
    success = asyncio.run(check_llm_connectivity())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
