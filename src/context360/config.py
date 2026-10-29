"""Пороги движка и допущения симуляции.

Пороги (`Thresholds`) — это то, что в реальном внедрении калибрует департамент антифрода
на пилоте (A/B на 5% трафика СБП). Допущения (`Assumptions`) описывают поведение жертв
и мошенников в синтетике: их нельзя выдавать за факт, их нужно проговаривать.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    # Маршрутизация «Светофор»
    green_max: int = 35            # score < green_max  -> GREEN
    yellow_max: int = 70           # score <= yellow_max -> YELLOW, выше -> RED

    # Признаки ЦБ (Приказ № ОД-2506)
    phone_change_hours: float = 48         # Признак №9: смена номера за N часов
    me2me_threshold_rub: float = 200_000   # Признак №11: Me2Me за 24 ч

    # Перевод под диктовку: активный звонок + новый получатель + крупная сумма
    call_amount_share: float = 0.5         # доля от Typical_Limit
    call_amount_floor_rub: float = 30_000

    # Сетевые признаки дропа у получателя
    mule_account_age_days: int = 30
    mule_unique_senders_24h: int = 5

    # Уязвимость клиента (Vulnerability_Index из ночного профиля)
    vulnerable_index: int = 7
    vulnerable_multiplier: float = 1.2

    # Блок 5: охлаждение и кросс-канальный флаг в АТМ
    cooling_hours: float = 48
    atm_limit_rub: float = 50_000


@dataclass(frozen=True)
class Assumptions:
    fraud_share: float = 0.004               # доля мошеннических переводов в потоке
    manual_review_cost_rub: float = 180      # стоимость ручного разбора (из финмодели решения)
    callcenter_fraud_leak: float = 0.35      # «наследие»: жертва под диктовку уговаривает КЦ снять блок
    red_pause_fraud_leak: float = 0.05       # после паузы 48 ч + звонка спецгруппы жертва всё равно переводит
    atm_redirect_after_block: float = 0.50   # после отказа в онлайне жертву ведут в банкомат
