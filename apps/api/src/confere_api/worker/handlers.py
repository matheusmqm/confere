"""Registra os handlers de job. O pipeline mora em `orquestrador.py` (CF-107)."""

from confere_api.worker import orquestrador

__all__ = ["orquestrador"]
