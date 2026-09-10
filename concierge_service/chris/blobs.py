"""Atomic content-addressed evidence, deliberately no implicit deletion."""
import hashlib
import os
import re
import tempfile
from pathlib import Path
from .contracts import canonical, require

class Blobs:
    def __init__(self, database):
        path = Path(database)
        require(path.is_absolute(), "absolute_storage_required")
        self.root = path.parent / "chris-blobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, value):
        raw = canonical(value)
        require(len(raw) <= 512 * 1024, "blob_too_large")
        key = hashlib.sha256(raw).hexdigest()
        target = self.root / key
        with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as out:
            temporary = out.name
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, target)
        return key

    def get(self, key):
        require(isinstance(key, str) and re.fullmatch("[a-f0-9]{64}", key), "invalid_blob")
        raw = (self.root / key).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == key, "blob_corrupt", 503)
        import json
        return json.loads(raw)
