"""Мост между страницей и движком: принимает JSON из браузера, возвращает JSON."""
import json
from dataclasses import replace

from context360 import (Assumptions, ClientBehaviour, ClientProfile, Context360Engine,
                        LegacyRules, Recipient, SessionContext, Thresholds, Transfer, simulate)
from context360.report import to_dict

RID = 555


def decide(payload: str) -> str:
    p = json.loads(payload)
    th = Thresholds()
    client = ClientProfile(1, p["age"], p["typical_limit"], p["vulnerability_index"],
                           {RID} if p["known_recipient"] else set())
    recipient = Recipient(RID, p["in_cbr_db"], p["account_age_days"], p["unique_senders_24h"])
    session = SessionContext(p["active_call"], p["screen_sharing"],
                             p["phone_changed_hours"] if p["phone_changed"] else None,
                             p["me2me_in_24h"], p["new_device"])
    behaviour = ClientBehaviour(p["can_qr_handshake"], p["biometric_ok"],
                                p["picks_safe_account"], p["trusted_contact_confirms"])
    t = Transfer(1, client, recipient, p["amount"], session, behaviour)

    d = Context360Engine(th).decide(t)
    return json.dumps({
        "corridor": d.corridor.value,
        "score": d.score,
        "reasons": d.reasons,
        "passed": d.passed,
        "resolved_by": d.resolved_by,
        "manual_review": d.manual_review,
        "legacy_blocks": LegacyRules(th).blocks(t),
    }, ensure_ascii=False)


def run_simulation(payload: str) -> str:
    p = json.loads(payload)
    th = replace(Thresholds(), green_max=p["green_max"], yellow_max=p["yellow_max"])
    a = replace(Assumptions(), fraud_share=p["fraud_share"])
    n = p["transfers"]
    r = simulate(n, max(2_000, n // 15), p["seed"], th, a, measure_latency=False)
    out = to_dict(r)
    out["resolved"] = r.resolved.most_common(8)
    return json.dumps(out, ensure_ascii=False)
