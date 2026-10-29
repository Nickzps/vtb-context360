"""Синтетический поток переводов и сравнение «Контекст 360» с «наследием».

Данные полностью синтетические. Сценарии мошенничества повторяют схемы из docs/sbp_research.md:
«безопасный счёт» под диктовку, фейковый продавец, захват аккаунта, «инвестиции».
"""
from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass, field

from .config import Assumptions, Thresholds
from .engine import Context360Engine, LegacyRules
from .models import (ClientBehaviour, ClientProfile, Corridor, Decision, Recipient,
                     SessionContext, Transfer)


# ---------------------------------------------------------------- генерация
def make_clients(rng: random.Random, n: int) -> list[ClientProfile]:
    clients = []
    for cid in range(n):
        age = rng.choices([rng.randint(18, 35), rng.randint(36, 59), rng.randint(60, 85)],
                          [0.35, 0.45, 0.20])[0]
        vuln = min(10, max(1, int(rng.gauss(3, 1.5)) + (4 if age >= 60 else 0)))
        whitelist = {cid * 100 + k for k in range(rng.randint(3, 15))}
        clients.append(ClientProfile(cid, age, rng.lognormvariate(10.1, 0.6), vuln, whitelist))
    return clients


def _clean_recipient(rng: random.Random, rid: int) -> Recipient:
    return Recipient(rid, False, rng.randint(100, 5000), rng.randint(0, 3))


def _mule_recipient(rng: random.Random, rid: int, p_db: float) -> Recipient:
    return Recipient(
        rid,
        rng.random() < p_db,
        rng.randint(1, 29) if rng.random() < 0.7 else rng.randint(30, 400),
        rng.randint(5, 40) if rng.random() < 0.6 else rng.randint(0, 4),
    )


def make_transfer(rng: random.Random, tx_id: int, c: ClientProfile, fraud_share: float) -> Transfer:
    def sess(call=0.02, phone=0.01, me2me=0.0, dev=0.03, screen=0.0) -> SessionContext:
        return SessionContext(
            active_call=rng.random() < call,
            screen_sharing=rng.random() < screen,
            phone_changed_hours=rng.uniform(1, 47) if rng.random() < phone else None,
            me2me_in_24h=rng.uniform(200_000, 900_000) if rng.random() < me2me else 0.0,
            new_device=rng.random() < dev,
        )

    new_rid = 10**9 + tx_id

    if rng.random() < fraud_share:
        kind = rng.choices(["safe_account", "fake_seller", "account_takeover", "investment"],
                           [0.45, 0.25, 0.20, 0.10])[0]
        if kind == "safe_account":
            return Transfer(tx_id, c, _mule_recipient(rng, new_rid, 0.25), rng.uniform(100_000, 1_500_000),
                            sess(call=0.8, me2me=0.5, screen=0.1),
                            ClientBehaviour(False, True, rng.random() < 0.15, rng.random() < 0.15), kind, True)
        if kind == "fake_seller":
            return Transfer(tx_id, c, _mule_recipient(rng, new_rid, 0.20), rng.uniform(10_000, 80_000),
                            sess(call=0.05), ClientBehaviour(False, True, False, rng.random() < 0.4), kind, True)
        if kind == "account_takeover":
            return Transfer(tx_id, c, _mule_recipient(rng, new_rid, 0.20), rng.uniform(30_000, 400_000),
                            sess(phone=0.7, dev=0.9, call=0.0),
                            ClientBehaviour(False, False, False, rng.random() < 0.05), kind, True)
        return Transfer(tx_id, c, _mule_recipient(rng, new_rid, 0.15), rng.uniform(50_000, 300_000),
                        sess(call=0.2), ClientBehaviour(False, True, False, rng.random() < 0.3), kind, True)

    kind = rng.choices(["regular", "purchase_in_person", "new_recipient_remote", "me2me_then_purchase"],
                       [0.80, 0.08, 0.10, 0.02])[0]
    if kind == "regular":
        rid = rng.choice(sorted(c.whitelist)) if rng.random() < 0.85 else new_rid
        return Transfer(tx_id, c, _clean_recipient(rng, rid), c.typical_limit * rng.uniform(0.05, 1.2),
                        sess(), ClientBehaviour(False, True, False, True), kind)
    if kind == "purchase_in_person":   # кейс стажёра Никиты с велосипедом
        return Transfer(tx_id, c, _clean_recipient(rng, new_rid), rng.uniform(20_000, 200_000),
                        sess(phone=0.05), ClientBehaviour(rng.random() < 0.85, True, False, rng.random() < 0.95), kind)
    if kind == "new_recipient_remote":
        return Transfer(tx_id, c, _clean_recipient(rng, new_rid), c.typical_limit * rng.uniform(0.1, 2.5),
                        sess(), ClientBehaviour(False, True, False, rng.random() < 0.95), kind)
    return Transfer(tx_id, c, _clean_recipient(rng, new_rid), rng.uniform(300_000, 2_000_000),
                    sess(me2me=1.0), ClientBehaviour(rng.random() < 0.6, True, False, rng.random() < 0.95), kind)


# ---------------------------------------------------------------- результаты
@dataclass
class SideMetrics:
    fraud_cnt: int = 0
    fraud_vol: float = 0.0
    tp: int = 0
    loss: float = 0.0
    legit_cnt: int = 0
    fp_manual: int = 0
    legit_selfservice: int = 0

    @property
    def recall(self) -> float:
        return self.tp / self.fraud_cnt if self.fraud_cnt else 0.0

    @property
    def saved_share(self) -> float:
        return 1 - self.loss / self.fraud_vol if self.fraud_vol else 0.0

    @property
    def fp_rate(self) -> float:
        return self.fp_manual / self.legit_cnt if self.legit_cnt else 0.0


@dataclass
class SimulationResult:
    n_transfers: int
    n_clients: int
    thresholds: Thresholds
    assumptions: Assumptions
    corridors: Counter = field(default_factory=Counter)
    resolved: Counter = field(default_factory=Counter)
    new: SideMetrics = field(default_factory=SideMetrics)
    legacy: SideMetrics = field(default_factory=SideMetrics)
    latencies_us: list[float] = field(default_factory=list)
    examples: dict[str, tuple[Transfer, Decision]] = field(default_factory=dict)

    @property
    def fp_reduction(self) -> float:
        return 1 - self.new.fp_manual / max(1, self.legacy.fp_manual)

    @property
    def loss_reduction(self) -> float:
        return 1 - self.new.loss / max(1.0, self.legacy.loss)

    def corridor_share(self, c: Corridor) -> float:
        return self.corridors[c] / max(1, sum(self.corridors.values()))


# ---------------------------------------------------------------- прогон
def simulate(n_transfers: int = 300_000, n_clients: int = 20_000, seed: int = 42,
             thresholds: Thresholds | None = None, assumptions: Assumptions | None = None,
             measure_latency: bool = True) -> SimulationResult:
    th = thresholds or Thresholds()
    a = assumptions or Assumptions()
    rng = random.Random(seed)
    clients = make_clients(rng, n_clients)
    engine, legacy = Context360Engine(th), LegacyRules(th)
    res = SimulationResult(n_transfers, n_clients, th, a)

    for tx_id in range(n_transfers):
        now_h = tx_id / n_transfers * 24 * 30          # поток растянут на месяц
        t = make_transfer(rng, tx_id, rng.choice(clients), a.fraud_share)

        t0 = time.perf_counter()
        d = engine.decide(t, now_h)
        if measure_latency:
            res.latencies_us.append((time.perf_counter() - t0) * 1e6)

        res.corridors[d.corridor] += 1
        if d.corridor is not Corridor.GREEN or t.is_fraud:
            label = "Фрод прошёл зелёным (пропуск)" if d.resolved_by == "Бесшовно" else d.resolved_by.split(":")[0]
            res.resolved[label] += 1
        res.examples.setdefault(f"{t.scenario}/{d.corridor.value}", (t, d))

        # --- Контекст 360
        n = res.new
        if t.is_fraud:
            n.fraud_cnt += 1
            n.fraud_vol += t.amount
            if d.passed:
                n.loss += t.amount
            else:
                n.tp += 1
                if rng.random() < a.red_pause_fraud_leak:
                    n.loss += t.amount
                elif rng.random() < a.atm_redirect_after_block:
                    limit = engine.atm_limit(t.client.client_id, now_h)
                    n.loss += min(t.amount, limit) if limit is not None else t.amount
        else:
            n.legit_cnt += 1
            if d.manual_review:
                n.fp_manual += 1
            elif d.corridor is Corridor.YELLOW:
                n.legit_selfservice += 1

        # --- «Наследие»
        o = res.legacy
        blocked = legacy.blocks(t)
        if t.is_fraud:
            o.fraud_cnt += 1
            o.fraud_vol += t.amount
            if not blocked:
                o.loss += t.amount
            else:
                o.tp += 1
                if rng.random() < a.callcenter_fraud_leak:
                    o.loss += t.amount
                elif rng.random() < a.atm_redirect_after_block:
                    o.loss += t.amount        # банкомат сигнала не получил
        else:
            o.legit_cnt += 1
            if blocked:
                o.fp_manual += 1

    return res
