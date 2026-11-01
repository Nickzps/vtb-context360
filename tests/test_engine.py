"""Сценарии из кейса как тесты: кейс Никиты (FP), кейс бабушки (TP), флаг в банкоматы."""
import pytest

from context360 import (ClientBehaviour, ClientProfile, Context360Engine, Corridor, LegacyRules,
                        Recipient, SessionContext, Transfer, simulate)


def client(age=30, typical=30_000, vuln=3, cid=1):
    return ClientProfile(cid, age, typical, vuln, whitelist={100, 101})


def clean_recipient(rid=999):
    return Recipient(rid, in_cbr_db=False, account_age_days=1500, unique_senders_24h=1)


def session(**kw):
    base = dict(active_call=False, screen_sharing=False, phone_changed_hours=None, me2me_in_24h=0.0, new_device=False)
    base.update(kw)
    return SessionContext(**base)


@pytest.fixture
def engine():
    return Context360Engine()


def test_regular_transfer_to_known_recipient_is_green(engine):
    t = Transfer(1, client(), clean_recipient(rid=100), 5_000, session())
    d = engine.decide(t)
    assert d.corridor is Corridor.GREEN
    assert d.passed and not d.manual_review


def test_nikita_bicycle_goes_yellow_and_passes_by_qr(engine):
    """Сменил номер за сутки + крупная сумма новому продавцу → жёлтый, снимается QR-хэндшейком."""
    t = Transfer(2, client(), clean_recipient(), 85_000, session(phone_changed_hours=20),
                 ClientBehaviour(can_qr_handshake=True))
    d = engine.decide(t)
    assert d.corridor is Corridor.YELLOW
    assert d.passed
    assert "Радар сделки" in d.resolved_by
    assert any("Признак №9" in r for r in d.reasons)


def test_legacy_blocks_nikita(engine):
    t = Transfer(2, client(), clean_recipient(), 85_000, session(phone_changed_hours=20))
    assert LegacyRules().blocks(t)


def test_grandmother_under_dictation_is_red_and_flags_atm(engine):
    """Активный звонок + новый получатель + крупная сумма → жёсткий стоп и лимит в АТМ на 48 ч."""
    granny = client(age=78, typical=20_000, vuln=8, cid=7)
    t = Transfer(3, granny, clean_recipient(), 400_000, session(active_call=True))
    d = engine.decide(t, now_h=10)
    assert d.corridor is Corridor.RED
    assert not d.passed and d.manual_review
    assert engine.atm_limit(7, now_h=11) == 50_000
    assert engine.atm_limit(7, now_h=10 + 48.5) is None   # флаг снимается после охлаждения


def test_recipient_in_cbr_database_is_hard_red(engine):
    r = Recipient(5, in_cbr_db=True, account_age_days=1000, unique_senders_24h=0)
    d = engine.decide(Transfer(4, client(), r, 1_000, session()))
    assert d.corridor is Corridor.RED


def test_safe_account_choice_turns_yellow_into_red(engine):
    t = Transfer(5, client(), clean_recipient(), 85_000, session(phone_changed_hours=20),
                 ClientBehaviour(picks_safe_account=True))
    d = engine.decide(t)
    assert d.corridor is Corridor.RED
    assert not d.passed


def test_vulnerable_client_needs_trusted_contact(engine):
    old = client(age=70, vuln=8)
    t = Transfer(6, old, clean_recipient(), 100_000, session(),
                 ClientBehaviour(trusted_contact_confirms=False))
    d = engine.decide(t)
    assert d.corridor is Corridor.RED      # жёлтый не снят: доверенное лицо отклонило
    assert not d.passed
    assert "Защита близких 2.0" in " ".join(d.reasons)


def test_simulation_is_reproducible_and_beats_legacy():
    a = simulate(n_transfers=20_000, n_clients=2_000, seed=1, measure_latency=False)
    b = simulate(n_transfers=20_000, n_clients=2_000, seed=1, measure_latency=False)
    assert a.new.fp_manual == b.new.fp_manual and a.new.loss == b.new.loss
    assert a.new.fp_manual < a.legacy.fp_manual
    assert a.new.loss < a.legacy.loss
