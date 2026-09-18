"""Persistencia de clientes emparejados en ~/.remotepad/tokens.json (F-21)."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

STATE_DIR = Path.home() / ".remotepad"
TOKENS_FILE = STATE_DIR / "tokens.json"


@dataclass(frozen=True)
class PairedClient:
    client_id: str
    client_name: str
    token: str  # hex, 64 chars (32 bytes)
    paired_at: float  # epoch seconds


class TokenStore:
    """Carga/guarda `tokens.json`. Cada instancia cachea en memoria; `_save` persiste todo el archivo."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or TOKENS_FILE
        self._clients: Dict[str, PairedClient] = self._load()

    def _load(self) -> Dict[str, PairedClient]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        clients: Dict[str, PairedClient] = {}
        for client_id, data in raw.items():
            try:
                clients[client_id] = PairedClient(**data)
            except TypeError:
                continue  # entrada corrupta: se ignora, no tira el server
        return clients

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {cid: asdict(c) for cid, c in self._clients.items()}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)  # 600 — no-op en Windows
        except OSError:
            pass

    def get(self, client_id: str) -> Optional[PairedClient]:
        return self._clients.get(client_id)

    def save(self, client: PairedClient) -> None:
        self._clients[client.client_id] = client
        self._save()

    def forget(self, client_id: str) -> None:
        if client_id in self._clients:
            del self._clients[client_id]
            self._save()

    def __len__(self) -> int:
        return len(self._clients)
