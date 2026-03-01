from dataclasses import dataclass
from typing import Tuple

from .discovery import EligiblePdf

@dataclass(frozen=True)
class DeterministicPaths:
    output_rel_path: str
    md_path: str
    meta_path: str

def compute_paths(e: EligiblePdf) -> DeterministicPaths:
    # §7: output_rel_path = relative path beneath Source Root with final .pdf suffix removed.
    if not e.source_path.startswith(e.root_path + "/"):
        # should not happen if eligibility correct
        raise ValueError("source_path not under root_path")
    rel_beneath = e.source_path[len(e.root_path) + 1:]  # after "root_path/"
    if not rel_beneath.endswith(".pdf"):
        raise ValueError("source_path must end with .pdf")
    output_rel_path = rel_beneath[:-4]  # remove final ".pdf"
    md_path = f"markdown/{output_rel_path}.md"
    meta_path = f"markdown/{output_rel_path}.meta.json"
    return DeterministicPaths(output_rel_path=output_rel_path, md_path=md_path, meta_path=meta_path)
