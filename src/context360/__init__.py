"""ВТБ Контекст 360 — прототип кросс-канального риск-движка «Светофор» (СБП → ДБО → банкомат)."""
from .config import Assumptions, Thresholds
from .engine import Context360Engine, LegacyRules
from .models import (ClientBehaviour, ClientProfile, Corridor, Decision, Recipient,
                     SessionContext, Transfer)
from .simulation import SimulationResult, simulate

__version__ = "0.1.0"

__all__ = [
    "Assumptions", "Thresholds",
    "Context360Engine", "LegacyRules",
    "ClientBehaviour", "ClientProfile", "Corridor", "Decision", "Recipient", "SessionContext", "Transfer",
    "SimulationResult", "simulate",
]
