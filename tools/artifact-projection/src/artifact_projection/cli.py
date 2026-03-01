import argparse
from pathlib import Path

from .converge import run_convergence
from .errors import FailedPolicy, FailedOperational, FailedRepresentation

def main():
    p = argparse.ArgumentParser(description="Artifact Projection (Contract v2.3.1)")
    p.add_argument("--config", required=True, help="Path to config JSON")
    args = p.parse_args()

    repo_root = Path(".").resolve()
    try:
        outcome = run_convergence(repo_root=repo_root, config_path=Path(args.config))
        print(outcome)
    except FailedPolicy as e:
        print(f"FAILED_POLICY: {e}")
        raise SystemExit(1)
    except FailedOperational as e:
        print(f"FAILED_OPERATIONAL: {e}")
        raise SystemExit(2)
    except FailedRepresentation as e:
        print(f"FAILED_REPRESENTATION: {e}")
        raise SystemExit(3)
    except Exception as e:
        print(f"FAILED_OPERATIONAL: {e}")
        raise SystemExit(2)
