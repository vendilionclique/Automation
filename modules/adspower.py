"""
Small AdsPower Local API client used by harness diagnostics.
"""
import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class AdsPowerResult:
    ok: bool
    action: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class AdsPowerClient:
    def __init__(
        self,
        base_url: str = "http://local.adspower.net:50325",
        api_key: str = "",
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout

    def health(self) -> AdsPowerResult:
        return self._get("/api/v1/user/list", {"page": 1, "page_size": 1}, "health")

    def start(self, profile_id: str) -> AdsPowerResult:
        return self._get("/api/v1/browser/start", {"user_id": profile_id}, "start")

    def stop(self, profile_id: str) -> AdsPowerResult:
        return self._get("/api/v1/browser/stop", {"user_id": profile_id}, "stop")

    def update_profile_proxy(
        self,
        profile_id: str,
        proxy_host: str,
        proxy_port: str,
        proxy_type: str = "http",
        proxy_user: str = "",
        proxy_password: str = "",
    ) -> AdsPowerResult:
        proxy_config = {
            "proxy_soft": "other",
            "proxy_type": proxy_type,
            "proxy_host": proxy_host,
            "proxy_port": str(proxy_port),
        }
        if proxy_user:
            proxy_config["proxy_user"] = proxy_user
        if proxy_password:
            proxy_config["proxy_password"] = proxy_password
        payload = {
            "profile_id": profile_id,
            "user_proxy_config": proxy_config,
        }
        return self._post_json("/api/v2/browser-profile/update", payload, "update_proxy")

    def _get(self, path: str, params: Dict[str, Any], action: str) -> AdsPowerResult:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            data = json.loads(text)
        except Exception as e:
            return AdsPowerResult(ok=False, action=action, error=str(e))

        code = data.get("code")
        ok = code in (0, "0") or data.get("msg") == "Success"
        return AdsPowerResult(ok=ok, action=action, data=data, error=None if ok else data.get("msg"))

    def _post_json(self, path: str, payload: Dict[str, Any], action: str) -> AdsPowerResult:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._headers()}
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            data = json.loads(text)
        except Exception as e:
            return AdsPowerResult(ok=False, action=action, error=str(e))

        code = data.get("code")
        ok = code in (0, "0") or data.get("msg") == "Success"
        return AdsPowerResult(ok=ok, action=action, data=data, error=None if ok else data.get("msg"))

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}
