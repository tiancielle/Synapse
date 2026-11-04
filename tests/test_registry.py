from core.registry import Decision, Risk, check_consistency, decide, policy_for


def test_read_tools_are_automatic():
    assert decide("calendar", "lister_evenements") == Decision.AUTO


def test_write_tool_notifies():
    assert decide("calendar", "creer_evenement") == Decision.NOTIFY


def test_destructive_tool_requires_confirmation():
    assert decide("calendar", "supprimer_evenement") == Decision.CONFIRM


def test_unknown_tool_is_denied_by_default():
    policy = policy_for("calendar", "formater_le_disque")
    assert policy.risk == Risk.FORBIDDEN
    assert decide("calendar", "formater_le_disque") == Decision.DENY


def test_unknown_server_is_denied():
    assert decide("inconnu", "lister_evenements") == Decision.DENY


class _T:
    def __init__(self, name, read_only=None, destructive=None):
        self.name = name
        self.annotations = type("A", (), {"read_only_hint": read_only, "destructive_hint": destructive})()


def test_consistency_detects_unregistered_tool():
    tools = [_T("lister_evenements", True, False), _T("outil_surprise", True, False)]
    problems = check_consistency("calendar", tools)
    assert any("outil_surprise" in p and "NON enregistré" in p for p in problems)


def test_consistency_detects_mislabelled_read_only():
    tools = [_T("creer_evenement", read_only=True, destructive=False)]
    problems = check_consistency("calendar", tools)
    assert any("creer_evenement" in p and "read-only" in p for p in problems)