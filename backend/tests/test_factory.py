"""Unit tests for the market data provider factory."""

import os

import pytest

from market.factory import create_provider
from market.massive import MassiveProvider
from market.simulator import SimulatorProvider


class TestCreateProvider:
    def test_returns_simulator_when_no_key(self, monkeypatch):
        monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
        provider = create_provider(["AAPL", "MSFT"])
        assert isinstance(provider, SimulatorProvider)

    def test_returns_simulator_when_key_empty(self, monkeypatch):
        monkeypatch.setenv("MASSIVE_API_KEY", "")
        provider = create_provider(["AAPL"])
        assert isinstance(provider, SimulatorProvider)

    def test_returns_simulator_when_key_whitespace_only(self, monkeypatch):
        monkeypatch.setenv("MASSIVE_API_KEY", "   ")
        provider = create_provider(["AAPL"])
        assert isinstance(provider, SimulatorProvider)

    def test_returns_massive_when_key_set(self, monkeypatch):
        monkeypatch.setenv("MASSIVE_API_KEY", "real-api-key")
        provider = create_provider(["AAPL", "MSFT"])
        assert isinstance(provider, MassiveProvider)

    def test_massive_provider_receives_api_key(self, monkeypatch):
        monkeypatch.setenv("MASSIVE_API_KEY", "my-secret-key")
        provider = create_provider(["AAPL"])
        assert isinstance(provider, MassiveProvider)
        assert provider._api_key == "my-secret-key"

    def test_massive_provider_receives_tickers(self, monkeypatch):
        monkeypatch.setenv("MASSIVE_API_KEY", "key")
        tickers = ["AAPL", "MSFT", "TSLA"]
        provider = create_provider(tickers)
        assert isinstance(provider, MassiveProvider)
        assert provider._tickers == {"AAPL", "MSFT", "TSLA"}

    def test_simulator_provider_receives_tickers(self, monkeypatch):
        monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
        tickers = ["AAPL", "MSFT"]
        provider = create_provider(tickers)
        assert isinstance(provider, SimulatorProvider)
        assert provider.get_price("AAPL") is not None
        assert provider.get_price("MSFT") is not None

    def test_empty_tickers_list_accepted(self, monkeypatch):
        monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
        provider = create_provider([])
        assert isinstance(provider, SimulatorProvider)
        assert provider.get_all_prices() == {}
