from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, collection: str) -> Path:
        return self.data_dir / f"{collection}.json"

    def read(self, collection: str, default: Any) -> Any:
        path = self.path_for(collection)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, collection: str, data: Any) -> None:
        path = self.path_for(collection)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)
