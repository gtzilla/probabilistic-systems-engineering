# Artifact Projection (Contract v2.4.1)

Projects eligible PDFs under configured Source Roots into `markdown/` as deterministic `.md` + `.meta.json` pairs.

## Environment variables
- `ARTIFACT_PROJECTION_ALLOW_DELETIONS`
  - If exactly `"true"`, Managed Residue (LRS) under `markdown/` may be deleted.
  - Otherwise, any non-empty LRS results in `FAILED_POLICY`.

## Fixtures
Fixtures live at `tools/artifact-projection/fixtures/<fixture_id>/`.
CI runs fixture validation with deletions disabled, and a separate job validates deletion-enabled behavior.
