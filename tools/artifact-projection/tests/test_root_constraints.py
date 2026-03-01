import json
from pathlib import Path
import pytest

from artifact_projection.config import load_config

def test_root_overlap_rejected(tmp_path: Path):
    cfg = {
        "engine_id": "x",
        "roots": [
            {"root_id":"a","root_path":"pdf","recursive":True},
            {"root_id":"b","root_path":"pdf/sub","recursive":True},
        ]
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        load_config(p)
