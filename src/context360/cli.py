"""Командная строка: python -m context360 [--transfers N] [--green-max X] ..."""
from __future__ import annotations

import argparse
from dataclasses import replace

from .config import Assumptions, Thresholds
from .report import to_json, to_text
from .simulation import simulate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="context360",
        description="ВТБ Контекст 360: симуляция риск-движка «Светофор» против жёстких правил.",
    )
    p.add_argument("--transfers", type=int, default=300_000, help="число переводов (по умолчанию 300 000)")
    p.add_argument("--clients", type=int, default=20_000, help="число клиентов (по умолчанию 20 000)")
    p.add_argument("--seed", type=int, default=42, help="seed генератора, чтобы результаты повторялись")
    p.add_argument("--green-max", type=int, help="порог зелёного коридора (по умолчанию 35)")
    p.add_argument("--yellow-max", type=int, help="порог жёлтого коридора (по умолчанию 70)")
    p.add_argument("--fraud-share", type=float, help="доля мошеннических переводов (по умолчанию 0.004)")
    p.add_argument("--json", action="store_true", help="вывести результат в JSON")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    th = Thresholds()
    if args.green_max is not None:
        th = replace(th, green_max=args.green_max)
    if args.yellow_max is not None:
        th = replace(th, yellow_max=args.yellow_max)
    a = Assumptions()
    if args.fraud_share is not None:
        a = replace(a, fraud_share=args.fraud_share)

    result = simulate(args.transfers, args.clients, args.seed, th, a)
    print(to_json(result) if args.json else to_text(result))


if __name__ == "__main__":
    main()
