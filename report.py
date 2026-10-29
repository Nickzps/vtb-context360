"""Текстовый и JSON-отчёт по результатам симуляции."""
from __future__ import annotations

import json
from dataclasses import asdict

from .models import Corridor
from .simulation import SideMetrics, SimulationResult

EXAMPLE_KEYS = [
    "purchase_in_person/YELLOW",
    "safe_account/RED",
    "account_takeover/RED",
    "me2me_then_purchase/YELLOW",
]


def _n(x: float, fmt: str = ",.0f") -> str:
    return format(x, fmt).replace(",", " ")


def _rows(cost: float) -> list[tuple[str, callable]]:
    return [
        ("Полнота выявления фрода (Recall)", lambda m: f"{m.recall:.1%}"),
        ("Потери клиентов, млн ₽", lambda m: f"{m.loss / 1e6:.1f}"),
        ("Доля спасённых средств", lambda m: f"{m.saved_share:.1%}"),
        ("Ложные блоки с ручным разбором, шт.", lambda m: _n(m.fp_manual)),
        ("Доля ложных блоков среди честных", lambda m: f"{m.fp_rate:.2%}"),
        ("Честные, прошедшие Self-Service, шт.", lambda m: _n(m.legit_selfservice)),
        ("Стоимость ручного разбора FP, тыс. ₽", lambda m: _n(m.fp_manual * cost / 1e3)),
    ]


def to_text(r: SimulationResult) -> str:
    out: list[str] = []
    p = out.append
    p("=" * 72)
    p("ВТБ Контекст 360 — прогон прототипа на синтетике")
    p(f"Переводов: {_n(r.n_transfers)} | клиентов: {_n(r.n_clients)} | мошеннических: {_n(r.new.fraud_cnt)}")
    p("=" * 72)

    p("\nРаспределение по коридорам:")
    for c in Corridor:
        p(f"  {c.value:<7} {r.corridor_share(c):6.2%}")

    if r.latencies_us:
        lat = sorted(r.latencies_us)
        p(f"\nЗадержка решения (Python, без сети): p50 {lat[len(lat) // 2]:.1f} мкс, "
          f"p99 {lat[int(len(lat) * 0.99)]:.1f} мкс")

    p(f"\n  {'Метрика':<42}{'Наследие':>13}{'Контекст 360':>15}")
    for name, f in _rows(r.assumptions.manual_review_cost_rub):
        p(f"  {name:<42}{f(r.legacy):>13}{f(r.new):>15}")

    p(f"\nИтог: ручных разборов FP −{r.fp_reduction:.0%}, потерь клиентов −{r.loss_reduction:.0%}")

    p("\nКак закрываются жёлтые и красные кейсы:")
    for how, cnt in r.resolved.most_common(8):
        p(f"  {_n(cnt):>7}  {how}")

    p("\nПримеры решений (для слайдов CJM):")
    for key in EXAMPLE_KEYS:
        if key not in r.examples:
            continue
        t, d = r.examples[key]
        p(f"\n  [{key}] {_n(t.amount)} ₽, клиент {t.client.age} лет, score {d.score}")
        for reason in d.reasons:
            p(f"     • {reason}")
        p(f"     → {d.resolved_by}")

    p(f"\nДопущения: {asdict(r.assumptions)}")
    return "\n".join(out)


def to_dict(r: SimulationResult) -> dict:
    def side(m: SideMetrics) -> dict:
        return {**asdict(m), "recall": m.recall, "saved_share": m.saved_share, "fp_rate": m.fp_rate}

    return {
        "n_transfers": r.n_transfers,
        "n_clients": r.n_clients,
        "corridors": {c.value: r.corridor_share(c) for c in Corridor},
        "legacy": side(r.legacy),
        "context360": side(r.new),
        "fp_reduction": r.fp_reduction,
        "loss_reduction": r.loss_reduction,
        "thresholds": asdict(r.thresholds),
        "assumptions": asdict(r.assumptions),
    }


def to_json(r: SimulationResult) -> str:
    return json.dumps(to_dict(r), ensure_ascii=False, indent=2)
