"""Модели данных: что лежит в ночном кэше, что снимает сенсор сессии, что выдаёт ядро."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Corridor(str, Enum):
    GREEN = "GREEN"    # бесшовно, клиент проверку не замечает
    YELLOW = "YELLOW"  # Self-Service в приложении: QR, биометрия, доверенное лицо
    RED = "RED"        # жёсткий стоп по 161-ФЗ: пауза 48 ч + флаг в банкоматы


@dataclass
class ClientProfile:
    """Блок 1. Batch Profile Store: считается ночью (лаг данных до 24 ч), лежит в быстром кэше."""
    client_id: int
    age: int
    typical_limit: float          # Typical_Limit: типичный максимальный перевод
    vulnerability_index: int      # Vulnerability_Index: 1..10
    whitelist: set[int] = field(default_factory=set)   # «белые» получатели


@dataclass
class Recipient:
    rid: int
    in_cbr_db: bool               # база ЦБ / ФинЦЕРТ / МВД
    account_age_days: int
    unique_senders_24h: int       # сетевой признак дропа: сколько разных людей прислали деньги


@dataclass
class SessionContext:
    """Блок 2. Real-Time Edge Sensor: Live_Session_Context, снимается в момент клика."""
    active_call: bool
    screen_sharing: bool
    phone_changed_hours: float | None   # Признак №9: часов назад сменили номер (None — не меняли)
    me2me_in_24h: float                 # Признак №11: сумма Me2Me за 24 ч
    new_device: bool


@dataclass
class ClientBehaviour:
    """Как клиент поведёт себя на экране Self-Service (нужно только для симуляции)."""
    can_qr_handshake: bool = False         # продавец рядом и показывает QR
    biometric_ok: bool = True
    picks_safe_account: bool = False       # выбирает «Безопасный счёт / спецслужбы»
    trusted_contact_confirms: bool = False # доверенное лицо подтверждает перевод


@dataclass
class Transfer:
    tx_id: int
    client: ClientProfile
    recipient: Recipient
    amount: float
    session: SessionContext
    behaviour: ClientBehaviour = field(default_factory=ClientBehaviour)
    scenario: str = "manual"
    is_fraud: bool = False


@dataclass
class Score:
    value: int
    reasons: list[str]
    hard_stop: bool
    mule_points: int


@dataclass
class Decision:
    corridor: Corridor
    score: int
    reasons: list[str]
    passed: bool           # деньги ушли получателю
    resolved_by: str       # чем закрыт кейс
    manual_review: bool    # нужен ручной разбор (КЦ / антифрод / офис)
