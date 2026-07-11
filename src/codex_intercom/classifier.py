RESPONSE_MARKERS = (
    "please confirm",
    "please choose",
    "which do you prefer",
    "need you to choose",
    "need your answer",
    "preciso que você",
    "por favor confirme",
    "qual opção",
    "você prefere",
    "me diga",
    "responda",
)

BLOCKED_MARKERS = (
    "i am blocked",
    "i'm blocked",
    "cannot continue",
    "unable to continue",
    "blocked without",
    "estou bloqueado",
    "não consigo continuar",
    "nao consigo continuar",
    "impasse",
    "falhou sem recuperação",
    "failed without recovery",
)

RECOVERY_MARKERS = (
    "fixed",
    "resolved",
    "corrigido",
    "corrigida",
    "resolvido",
    "resolvida",
)

VERIFIED_MARKERS = (
    "pass",
    "verified",
    "verificado",
    "verificada",
    "checks green",
)


def classify_stop(message):
    tail = (message or "").strip()[-1200:]
    lowered = tail.casefold()
    recovered = (
        any(marker in lowered for marker in RECOVERY_MARKERS)
        and any(marker in lowered for marker in VERIFIED_MARKERS)
    )

    if not recovered and any(marker in lowered for marker in BLOCKED_MARKERS):
        return "blocked"
    if tail.endswith("?") or any(marker in lowered for marker in RESPONSE_MARKERS):
        return "response_required"
    return "complete"
