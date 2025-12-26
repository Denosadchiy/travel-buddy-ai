"""
Tests for Travel Time Provider Factory Function.
Tests get_travel_time_provider() behavior based on settings.
"""
import pytest
from unittest.mock import patch

from src.infrastructure.travel_time import (
    get_travel_time_provider,
    GoogleMapsTravelTimeProvider,
    SimpleHeuristicTravelTimeProvider,
)


class TestGetTravelTimeProviderFactory:
    """Tests for the get_travel_time_provider factory function."""

    def test_returns_google_provider_when_configured(self):
        """Test that factory returns GoogleMapsTravelTimeProvider when properly configured."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "google_maps"
            mock_settings.google_maps_api_key = "test_api_key_123"
            mock_settings.google_routes_base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
            mock_settings.google_routes_timeout_seconds = 10

            provider = get_travel_time_provider()

            assert isinstance(provider, GoogleMapsTravelTimeProvider)
            assert provider.api_key == "test_api_key_123"

    def test_returns_heuristic_when_google_configured_but_no_key(self):
        """Test fallback to heuristic when google_maps is configured but no API key."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "google_maps"
            mock_settings.google_maps_api_key = None  # No API key

            provider = get_travel_time_provider()

            assert isinstance(provider, SimpleHeuristicTravelTimeProvider)

    def test_returns_heuristic_when_google_configured_with_empty_key(self):
        """Test fallback to heuristic when API key is empty string."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "google_maps"
            mock_settings.google_maps_api_key = ""  # Empty key

            provider = get_travel_time_provider()

            assert isinstance(provider, SimpleHeuristicTravelTimeProvider)

    def test_returns_heuristic_when_simple_configured(self):
        """Test that factory returns SimpleHeuristicTravelTimeProvider when 'simple' is configured."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "simple"

            provider = get_travel_time_provider()

            assert isinstance(provider, SimpleHeuristicTravelTimeProvider)

    def test_returns_heuristic_for_unknown_provider(self):
        """Test that factory defaults to heuristic for unknown provider names."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "unknown_provider"

            provider = get_travel_time_provider()

            assert isinstance(provider, SimpleHeuristicTravelTimeProvider)

    def test_case_insensitive_provider_selection(self):
        """Test that provider selection is case-insensitive."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "GOOGLE_MAPS"
            mock_settings.google_maps_api_key = "test_key"
            mock_settings.google_routes_base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
            mock_settings.google_routes_timeout_seconds = 10

            provider = get_travel_time_provider()

            assert isinstance(provider, GoogleMapsTravelTimeProvider)

    def test_google_provider_uses_custom_timeout(self):
        """Test that Google provider respects custom timeout setting."""
        with patch('src.infrastructure.travel_time.settings') as mock_settings:
            mock_settings.travel_time_provider = "google_maps"
            mock_settings.google_maps_api_key = "test_key"
            mock_settings.google_routes_base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
            mock_settings.google_routes_timeout_seconds = 30

            provider = get_travel_time_provider()

            assert isinstance(provider, GoogleMapsTravelTimeProvider)
            assert provider.timeout_seconds == 30


class TestGoogleMapsTravelTimeProviderInit:
    """Tests for GoogleMapsTravelTimeProvider initialization."""

    def test_init_with_valid_key(self):
        """Test initialization with valid API key."""
        provider = GoogleMapsTravelTimeProvider(api_key="valid_key")

        assert provider.api_key == "valid_key"
        assert provider.default_mode == "DRIVE"

    def test_init_with_custom_mode(self):
        """Test initialization with custom travel mode."""
        provider = GoogleMapsTravelTimeProvider(
            api_key="valid_key",
            default_mode="WALK"
        )

        assert provider.default_mode == "WALK"

    def test_init_with_custom_base_url(self):
        """Test initialization with custom base URL."""
        custom_url = "https://custom.api.com/routes"
        provider = GoogleMapsTravelTimeProvider(
            api_key="valid_key",
            base_url=custom_url
        )

        assert provider.base_url == custom_url

    def test_init_fails_without_key(self):
        """Test that initialization fails without API key."""
        with pytest.raises(ValueError) as exc_info:
            GoogleMapsTravelTimeProvider(api_key=None)

        assert "API key" in str(exc_info.value)

    def test_init_fails_with_empty_key(self):
        """Test that initialization fails with empty API key."""
        with pytest.raises(ValueError) as exc_info:
            GoogleMapsTravelTimeProvider(api_key="")

        assert "API key" in str(exc_info.value)

    def test_has_fallback_provider(self):
        """Test that Google provider has a fallback provider."""
        provider = GoogleMapsTravelTimeProvider(api_key="test_key")

        assert provider._fallback_provider is not None
        assert isinstance(provider._fallback_provider, SimpleHeuristicTravelTimeProvider)


class TestSimpleHeuristicTravelTimeProviderInit:
    """Tests for SimpleHeuristicTravelTimeProvider initialization."""

    def test_default_constants(self):
        """Test default constants are set correctly."""
        provider = SimpleHeuristicTravelTimeProvider()

        assert provider.DEFAULT_TRAVEL_TIME_MINUTES == 15
        assert provider.AVERAGE_WALKING_SPEED_KMH == 5.0
        assert provider.AVERAGE_DRIVING_SPEED_KMH == 30.0
