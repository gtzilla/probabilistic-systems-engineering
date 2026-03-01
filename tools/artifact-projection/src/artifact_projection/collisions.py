from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from .errors import FailedPolicy
from .util import ascii_case_fold

@dataclass(frozen=True)
class DtsPaths:
    all_paths: List[str]  # includes md and meta
    md_paths: List[str]
    meta_paths: List[str]

def evaluate_collisions(dts: DtsPaths, unmanaged: Set[str]) -> None:
    # 11.1 DTS internal collisions
    seen: Set[str] = set()
    for p in dts.all_paths:
        if p in seen:
            raise FailedPolicy(f"DTS exact path collision: {p}")
        seen.add(p)

    fold_map: Dict[str, str] = {}
    for p in dts.all_paths:
        f = ascii_case_fold(p)
        prev = fold_map.get(f)
        if prev is not None and prev != p:
            raise FailedPolicy(f"DTS ASCII case-fold collision: {prev} vs {p}")
        fold_map[f] = p

    # 11.2 DTS vs Unmanaged
    for p in dts.all_paths:
        if p in unmanaged:
            raise FailedPolicy(f"DTS path collides with Unmanaged path: {p}")

    # 11.3 DTS vs LRS: handled by not treating MR paths as unmanaged; LRS not passed here
