import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from typing import Any

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]

class SecureTokenStore:
    """Windows-user-bound encrypted token storage using DPAPI."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_tokens.secure"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            raise RuntimeError("SecureTokenStore requires Windows DPAPI")

    @staticmethod
    def _protect(value: str) -> str:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        raw = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        source = _DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        target = _DATA_BLOB()
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        )
        if not ok:
            raise ctypes.WinError()
        try:
            protected = ctypes.string_at(target.pbData, target.cbData)
            return base64.b64encode(protected).decode("ascii")
        finally:
            kernel32.LocalFree(target.pbData)

    @staticmethod
    def _unprotect(value: str) -> str:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        protected = base64.b64decode(value.encode("ascii"))
        buffer = ctypes.create_string_buffer(protected)
        source = _DATA_BLOB(
            len(protected),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        target = _DATA_BLOB()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        )
        if not ok:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(target.pbData)

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, str]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def set(self, provider: str, payload: dict[str, Any]) -> None:
        data = self._load()
        data[str(provider).lower()] = self._protect(
            json.dumps(payload, separators=(",", ":"), sort_keys=True)
        )
        self._save(data)

    def get(self, provider: str) -> dict[str, Any] | None:
        encrypted = self._load().get(str(provider).lower())
        if not encrypted:
            return None
        return json.loads(self._unprotect(encrypted))

    def delete(self, provider: str) -> None:
        data = self._load()
        data.pop(str(provider).lower(), None)
        self._save(data)

    def has(self, provider: str) -> bool:
        return bool(self._load().get(str(provider).lower()))
