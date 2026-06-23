# FInk single-main public-repository addendum

This addendum overrides branch and GitHub instructions in the original
automation manual.

## Git policy

- Remote name: `origin`
- Only branch: `main`
- Do not create or use `master`, `develop`, or `auto/<TASK_ID>`.
- The automated loop commits accepted work directly to local `main`.
- The loop does not push automatically.
- The operator pushes with `git push origin main` after inspection.

## Public repository preflight

```bash
source "$HOME/fai/fink-env.sh"
cd "$REPO_ROOT"

bash scripts/public_repo_preflight.sh
```

## Create and push the public repository

```bash
FINK_PUBLIC_CONFIRM=YES \
  bash scripts/create_public_repo.sh
```

Expected repository:

```text
https://github.com/seonukkim/fink
```

## After the public repository exists

Run the Master Spec build and audit exactly as described in the original
manual. Then replace the original loop-bootstrap prompts with the two prompt
files in this patch before running Codex and Claude.

Each successful checkpoint is pushed manually:

```bash
git status --short
git log --oneline -n 5
git push origin main
```
