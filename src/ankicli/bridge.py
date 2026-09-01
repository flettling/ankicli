import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


class BridgeError(RuntimeError):
    pass


class BridgeClient:
    def __init__(self, *, port: int, token: str, timeout: int = 900):
        self.port = int(port)
        self.token = token
        self.timeout = timeout

    @classmethod
    def discover(cls, base: Path) -> Optional["BridgeClient"]:
        state_path = base / "ankicli-bridge.json"
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            if int(payload.get("protocol", 0)) != 1:
                return None
            return cls(port=int(payload["port"]), token=str(payload["token"]))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/health")

    def import_apkg(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/v1/import-apkg", payload)

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer %s" % self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(body).get("error", body)
            except json.JSONDecodeError:
                message = body
            raise BridgeError("Anki bridge rejected request: %s" % message) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise BridgeError("Anki bridge is unavailable: %s" % exc) from exc
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BridgeError("Anki bridge returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise BridgeError("Anki bridge returned an invalid response")
        return result
