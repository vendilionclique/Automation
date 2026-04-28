"""
Proxy pool diagnostics.

The first implementation is deliberately vendor-neutral: it can fetch one or
more proxies from a configured URL, or validate a manually supplied proxy.
Provider-specific parsing can be added after the real supplier format is known.
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProxyProbeResult:
    ok: bool
    proxy: Optional[str]
    exit_ip: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None
    healthcheck_url: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class ProxyPoolClient:
    def __init__(
        self,
        provider_url: str = "",
        healthcheck_url: str = "https://api.ipify.org?format=json",
        timeout: float = 10.0,
    ):
        self.provider_url = provider_url.strip()
        self.healthcheck_url = healthcheck_url.strip() or "https://api.ipify.org?format=json"
        self.timeout = timeout

    def fetch(self) -> List[str]:
        if not self.provider_url:
            return []

        with urllib.request.urlopen(self.provider_url, timeout=self.timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()

        return self._parse_provider_response(text)

    def fetch_with_raw(self) -> Dict[str, Any]:
        if not self.provider_url:
            return {"proxies": [], "raw_response": "", "error": None}

        try:
            with urllib.request.urlopen(self.provider_url, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace").strip()
            return {
                "proxies": self._parse_provider_response(text),
                "raw_response": text[:5000],
                "error": None,
            }
        except Exception as e:
            return {"proxies": [], "raw_response": "", "error": str(e)}

    def probe(self, proxy: Optional[str] = None) -> ProxyProbeResult:
        proxy = (proxy or "").strip() or None
        try:
            opener = self._build_opener(proxy)
            with opener.open(self.healthcheck_url, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace").strip()
            return ProxyProbeResult(
                ok=True,
                proxy=proxy,
                exit_ip=self._extract_ip(text),
                raw_response=text[:1000],
                healthcheck_url=self.healthcheck_url,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return ProxyProbeResult(
                ok=False,
                proxy=proxy,
                error=str(e),
                healthcheck_url=self.healthcheck_url,
            )

    def _build_opener(self, proxy: Optional[str]):
        if not proxy:
            return urllib.request.build_opener()

        proxy_url = proxy if "://" in proxy else f"http://{proxy}"
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        return urllib.request.build_opener(handler)

    def _parse_provider_response(self, text: str) -> List[str]:
        if not text:
            return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return self._parse_text_proxies(text)

        if isinstance(data, list):
            return self._dedupe([self._proxy_from_item(item) for item in data])

        if isinstance(data, dict):
            direct = self._proxy_from_item(data)
            if direct:
                return [direct]

            for key in ("proxies", "data", "items", "result", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    return self._dedupe([self._proxy_from_item(item) for item in value])
                if isinstance(value, str):
                    return self._parse_text_proxies(value)
                if isinstance(value, dict):
                    nested = self._proxy_from_item(value)
                    if nested:
                        return [nested]

        return []

    def _parse_text_proxies(self, text: str) -> List[str]:
        candidates = []
        for part in re.split(r"[\r\n,;\s]+", text):
            value = part.strip()
            if value and self._looks_like_proxy(value):
                candidates.append(value)
        return self._dedupe(candidates)

    def _proxy_from_item(self, item) -> str:
        if isinstance(item, str):
            return item.strip() if self._looks_like_proxy(item.strip()) else ""
        if not isinstance(item, dict):
            return ""
        host = item.get("host") or item.get("ip") or item.get("server")
        port = item.get("port")
        username = item.get("username") or item.get("user")
        password = item.get("password") or item.get("pass")
        if host and port:
            auth = f"{username}:{password}@" if username and password else ""
            scheme = item.get("scheme") or item.get("protocol") or ""
            prefix = f"{scheme}://" if scheme else ""
            return f"{prefix}{auth}{host}:{port}"
        for key in ("proxy", "addr", "address", "url"):
            value = item.get(key)
            if value and self._looks_like_proxy(str(value)):
                return str(value).strip()
        return ""

    def _extract_ip(self, text: str) -> Optional[str]:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data.get("ip") or data.get("origin")
        except json.JSONDecodeError:
            pass
        return text.strip() or None

    def _looks_like_proxy(self, value: str) -> bool:
        if not value:
            return False
        value = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", value)
        if "@" in value:
            value = value.rsplit("@", 1)[1]
        if ":" not in value:
            return False
        host, port = value.rsplit(":", 1)
        return bool(host.strip()) and port.isdigit()

    def _dedupe(self, proxies: List[str]) -> List[str]:
        seen = set()
        result = []
        for proxy in proxies:
            proxy = (proxy or "").strip()
            if not proxy or proxy in seen:
                continue
            seen.add(proxy)
            result.append(proxy)
        return result
