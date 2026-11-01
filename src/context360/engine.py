"""Блоки 3–5: ядро 161-ФЗ, Self-Service и протокол охлаждения.

Context360Engine — решение «Светофор»:
    score()        признаки ЦБ + поведенческий скоринг + сетевые признаки дропа
    route()        GREEN / YELLOW / RED
    self_service() снятие подозрения самим клиентом (Радар сделки, биометрия, Защита близких 2.0)
    decide()       полный путь; при RED ставит флаг ATM_Limit_50k на cooling_hours

LegacyRules — «как сейчас»: любой сработавший признак = блок ДБО и звонок в КЦ,
а банкоматы о блоке не знают.
"""
from __future__ import annotations

from .config import Thresholds
from .models import Corridor, Decision, Score, Transfer


class Context360Engine:
    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.th = thresholds or Thresholds()
        self._atm_flags: dict[int, float] = {}   # client_id -> до какого момента (в часах) действует флаг

    # ------------------------------------------------------------- Блок 3: скоринг
    def score(self, t: Transfer) -> Score:
        th, c, r, s = self.th, t.client, t.recipient, t.session
        new_recipient = r.rid not in c.whitelist

        # Жёсткие стопы: красный коридор без вариантов
        if r.in_cbr_db:
            return Score(100, ["Получатель в базе ЦБ / ФинЦЕРТ"], True, 0)
        if s.screen_sharing:
            return Score(100, ["Демонстрация экрана / удалённый доступ"], True, 0)
        big = t.amount >= max(th.call_amount_share * c.typical_limit, th.call_amount_floor_rub)
        if s.active_call and new_recipient and big:
            return Score(100, ["Перевод под диктовку: активный звонок + новый получатель + крупная сумма"], True, 0)

        value, reasons = 0, []
        if new_recipient:
            value += 20
            reasons.append("Новый получатель")

        ratio = t.amount / c.typical_limit
        if ratio > 3:
            value += 25
            reasons.append(f"Сумма в {ratio:.1f}× выше типичной")
        elif ratio > 1.5:
            value += 15
            reasons.append(f"Сумма в {ratio:.1f}× выше типичной")

        if s.phone_changed_hours is not None and s.phone_changed_hours <= th.phone_change_hours:
            value += 25
            reasons.append(f"Признак №9: смена номера ≤{th.phone_change_hours:.0f} ч")
        if s.me2me_in_24h >= th.me2me_threshold_rub and new_recipient:
            value += 30
            reasons.append("Признак №11: Me2Me >200 тыс. ₽ и новый получатель")
        if s.new_device:
            value += 15
            reasons.append("Новое устройство")

        mule = 0
        if r.account_age_days < th.mule_account_age_days:
            mule += 15
        if r.unique_senders_24h >= th.mule_unique_senders_24h:
            mule += 25
        if mule:
            value += mule
            reasons.append(f"Сетевые признаки дропа у получателя (+{mule})")

        if c.vulnerability_index >= th.vulnerable_index:
            value = int(value * th.vulnerable_multiplier)
            reasons.append(f"Повышенная уязвимость клиента (×{th.vulnerable_multiplier:g})")

        return Score(min(value, 99), reasons, False, mule)

    def route(self, sc: Score) -> Corridor:
        if sc.hard_stop or sc.value > self.th.yellow_max:
            return Corridor.RED
        return Corridor.GREEN if sc.value < self.th.green_max else Corridor.YELLOW

    # ------------------------------------------------------------- Блок 4: Self-Service
    def self_service(self, t: Transfer, mule_points: int) -> tuple[bool, str]:
        b = t.behaviour
        if b.picks_safe_account:
            return False, "Клиент выбрал «Безопасный счёт / спецслужбы» → RED"
        if b.can_qr_handshake:
            return True, "Радар сделки: QR-хэндшейк, продавец рядом"
        if t.client.vulnerability_index >= self.th.vulnerable_index:
            ok = b.trusted_contact_confirms
            return ok, "Защита близких 2.0: доверенное лицо " + ("подтвердило" if ok else "отклонило")
        if b.biometric_ok and mule_points < 25:
            return True, "Биометрия, получатель без признаков дропа"
        return False, "Self-Service не пройден → RED"

    # ------------------------------------------------------------- полный путь
    def decide(self, t: Transfer, now_h: float = 0.0) -> Decision:
        sc = self.score(t)
        corridor = self.route(sc)
        reasons = list(sc.reasons)

        if corridor is Corridor.GREEN:
            return Decision(corridor, sc.value, reasons, True, "Бесшовно", False)

        if corridor is Corridor.YELLOW:
            ok, how = self.self_service(t, sc.mule_points)
            if ok:
                return Decision(corridor, sc.value, reasons, True, how, False)
            reasons.append(how)
            corridor = Corridor.RED

        # Блок 5: охлаждение + синхронный флаг во все банкоматы
        self._atm_flags[t.client.client_id] = now_h + self.th.cooling_hours
        return Decision(corridor, sc.value, reasons, False,
                        f"Пауза {self.th.cooling_hours:.0f} ч + флаг ATM_Limit_{self.th.atm_limit_rub/1000:.0f}k", True)

    def atm_limit(self, client_id: int, now_h: float) -> float | None:
        """Лимит снятия в АТМ для клиента или None, если флага нет."""
        expires = self._atm_flags.get(client_id)
        return self.th.atm_limit_rub if expires is not None and expires > now_h else None


class LegacyRules:
    """«Как сейчас»: сработал любой признак → блок ДБО и звонок в КЦ. Звонок мошенника движок не видит."""

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.th = thresholds or Thresholds()

    def blocks(self, t: Transfer) -> bool:
        th, c, r, s = self.th, t.client, t.recipient, t.session
        new_recipient = r.rid not in c.whitelist
        return any([
            r.in_cbr_db,
            s.phone_changed_hours is not None and s.phone_changed_hours <= th.phone_change_hours,
            s.me2me_in_24h >= th.me2me_threshold_rub and new_recipient,
            new_recipient and t.amount > 3 * c.typical_limit,
            s.new_device and new_recipient,
        ])
