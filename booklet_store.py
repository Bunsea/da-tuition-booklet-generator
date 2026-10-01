"""Private Supabase storage for reloadable theory and worksheet source data.

The public exam library stores exported PDFs. Booklet JSON lives in a separate,
private bucket so a Streamlit restart cannot erase the source material or keys.
"""

import json
from typing import Any, Dict, List

import cloud_sync


BUCKET = "booklet-data"
_bucket_ready = False


def is_configured() -> bool:
    url, key = cloud_sync.get_supabase_creds()
    return bool(url and key)


def _bucket():
    global _bucket_ready
    client = cloud_sync.get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase is not configured for permanent booklet storage.")
    if not _bucket_ready:
        buckets = client.storage.list_buckets()
        existing = next((bucket for bucket in buckets if getattr(bucket, "name", None) == BUCKET), None)
        if existing is None:
            client.storage.create_bucket(BUCKET, options={"public": False})
        elif getattr(existing, "public", False):
            raise RuntimeError("The booklet-data bucket must be private.")
        _bucket_ready = True
    return client.storage.from_(BUCKET)


def _path(kind: str, uid: str) -> str:
    if kind not in ("theory", "worksheets"):
        raise ValueError(f"Unknown booklet record type: {kind}")
    if not uid or any(ch not in "0123456789abcdef" for ch in uid):
        raise ValueError("Invalid booklet cloud identifier.")
    return f"{kind}/{uid}.json"


def put(kind: str, uid: str, record: Dict[str, Any]) -> None:
    data = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _bucket().upload(_path(kind, uid), data, {"content-type": "application/json", "upsert": "true"})


def get(kind: str, uid: str) -> Dict[str, Any]:
    data = _bucket().download(_path(kind, uid))
    record = json.loads(data.decode("utf-8"))
    if not isinstance(record, dict) or record.get("cloud_uid") != uid:
        raise ValueError(f"Invalid saved {kind} booklet record.")
    return record


def list_uids(kind: str) -> List[str]:
    _path(kind, "0")  # validate the record type
    storage = _bucket()
    result = []
    offset = 0
    while True:
        batch = storage.list(kind, {"limit": 100, "offset": offset})
        for item in batch:
            name = item.get("name", "")
            if name.endswith(".json"):
                uid = name[:-5]
                if uid and all(ch in "0123456789abcdef" for ch in uid):
                    result.append(uid)
        if len(batch) < 100:
            break
        offset += len(batch)
    return result


def remove(kind: str, uid: str) -> None:
    _bucket().remove([_path(kind, uid)])
