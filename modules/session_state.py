"""
Session and safety budget helpers for visual collection.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict


HEALTHY = "healthy"
LOGIN_REQUIRED = "login_required"
CAPTCHA_REQUIRED = "captcha_required"
POPUP_BLOCKED = "popup_blocked"
RISK_SUSPECTED = "risk_suspected"
COOLING_DOWN = "cooling_down"
LOCKED = "locked"


@dataclass
class SessionPolicy:
    daily_keyword_budget: int = 20
    hourly_keyword_budget: int = 5
    cooldown_minutes: int = 60
    max_consecutive_abnormal: int = 2

    def to_dict(self):
        return asdict(self)


def session_policy_from_settings(config) -> SessionPolicy:
    return SessionPolicy(
        daily_keyword_budget=config.getint("SESSION", "daily_keyword_budget", fallback=20),
        hourly_keyword_budget=config.getint("SESSION", "hourly_keyword_budget", fallback=5),
        cooldown_minutes=config.getint("SESSION", "cooldown_minutes", fallback=60),
        max_consecutive_abnormal=config.getint("SESSION", "max_consecutive_abnormal", fallback=2),
    )


def initial_session_state(policy: SessionPolicy) -> Dict:
    return {
        "status": HEALTHY,
        "policy": policy.to_dict(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_today": 0,
        "processed_this_hour": 0,
        "consecutive_abnormal": 0,
    }
