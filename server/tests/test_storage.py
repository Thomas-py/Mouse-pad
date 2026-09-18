from pathlib import Path

from remotepad_server.storage import PairedClient, TokenStore


def _client(client_id: str = "iphone-1") -> PairedClient:
    return PairedClient(client_id=client_id, client_name="iPhone de prueba", token="ab" * 32, paired_at=1.0)


def test_save_and_get(tmp_path: Path) -> None:
    store = TokenStore(path=tmp_path / "tokens.json")
    store.save(_client())
    assert store.get("iphone-1") == _client()


def test_get_missing_returns_none(tmp_path: Path) -> None:
    store = TokenStore(path=tmp_path / "tokens.json")
    assert store.get("nope") is None


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    TokenStore(path=path).save(_client())
    reloaded = TokenStore(path=path)
    assert reloaded.get("iphone-1") == _client()


def test_forget_removes_client(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    store = TokenStore(path=path)
    store.save(_client())
    store.forget("iphone-1")
    assert store.get("iphone-1") is None
    assert TokenStore(path=path).get("iphone-1") is None


def test_forget_missing_client_is_noop(tmp_path: Path) -> None:
    store = TokenStore(path=tmp_path / "tokens.json")
    store.forget("nope")  # no debe lanzar


def test_recovers_from_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("no es json", encoding="utf-8")
    store = TokenStore(path=path)
    assert len(store) == 0
    store.save(_client())
    assert store.get("iphone-1") is not None


def test_recovers_from_malformed_entry(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text('{"c1": {"client_id": "c1"}}', encoding="utf-8")  # faltan campos
    store = TokenStore(path=path)
    assert len(store) == 0


def test_creates_parent_dir(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "tokens.json"
    store = TokenStore(path=path)
    store.save(_client())
    assert path.exists()
