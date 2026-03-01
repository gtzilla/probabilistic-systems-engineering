from .fixture_harness import run_fixtures

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--allow-deletions", action="store_true")
    args = p.parse_args()
    raise SystemExit(run_fixtures(allow_deletions=args.allow_deletions))

if __name__ == "__main__":
    main()
