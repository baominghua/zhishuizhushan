# Task 9 Report: Verification and Password Authentication Runbook

Baseline: `44d501e05b7b3b7ad08ea821d2ff6451fa45ddd6`

## Changes

- Added `docs/admin-password-authentication-runbook.md` with the primary/standby Compose paths, backup, migration, bootstrap, HTTPS activation, validation, token revocation, and non-destructive rollback procedure.
- Updated `docs/smart-bamboo-production-checklist.md` with the password-authentication release gate and the cloud-host-only Docker requirement.

## Verification

- Focused backend suite:
  `REMOTE_SENSING_DATA_DIR=D:\\Users\\MECHREUO\\Documents\\武夷福森报销助手\\.tmp\\task-9-focused\\remote-sensing`
  with `--basetemp D:\\Users\\MECHREUO\\Documents\\武夷福森报销助手\\.tmp\\task-9-focused\\pytest -p no:cacheprovider`:
  `158 passed in 77.64s`.
- Full pytest suite with its own `task-9-full` data directory, `--basetemp`, and `-p no:cacheprovider`:
  `771 passed in 196.77s`.
- All 19 root `*.js` files: `node --check` passed.
- Existing Node behavior tests: 20 passed, 0 failed.
- All 14 existing `*.sh` scripts: `D:\\Program Files\\Git\\bin\\bash.exe -n` passed.
- Docker CLI: unavailable locally (`docker=NOT_FOUND`), so `docker compose config` is documented as a primary/standby cloud-host release gate and was not claimed locally.

## True Environment Failures Before Valid Runs

1. The worktree has no `./.venv/Scripts/python.exe`; the valid test invocation used the existing `D:\\Users\\MECHREUO\\Documents\\New project\\.venv\\Scripts\\python.exe` environment.
2. The first focused pytest invocation used a not-yet-created `--basetemp` parent and ended with `7 passed, 151 errors` caused by `FileNotFoundError` creating the basetemp path. After creating the required `task-9-*` parents, the focused and full runs above completed successfully.
3. An initial parallel verification group terminated when the Docker availability probe returned exit code 2. Its other commands were rerun independently; only the results above are counted as verification.

## Deferred to Controller

- Desktop and mobile browser screenshots and interactive acceptance.
- Cloud-host deployment, primary/standby `docker compose config`, HTTPS activation, and post-release verification.
- No push was performed.

## Independent Review Follow-up

The independent review found the first runbook did not close several production deployment paths. This follow-up adds real deployment files and updates the documentation rather than treating them as wording-only changes:

- `ops/compose.tls.yml`, `ops/nginx/smart-bamboo-tls.conf`, and `ops/scripts/enable-tls.sh` provide the certificate-gated HTTPS Nginx overlay. The repository still does not contain a domain, certificate, or private key.
- `generate-primary-env.sh` now creates a separately stored break-glass administrator service token and records the full immutable release commit. `make-standby-env.sh` checks that authentication, TLS, break-glass, and token configuration are copied to the standby environment.
- `verify-cluster.sh primary --allow-human-auth-pending` accepts only the single expected `human_auth_pending_https` warning while password authentication is off. Normal primary verification still requires `ready` with no warnings.
- `promote-standby.sh` uses the synchronized authentication state, requires `CONFIRM_HUMAN_AUTH_ENABLED=1` when that state is enabled, and applies the TLS Compose overlay. It no longer assumes a permanently disabled standby login path.
- `ops/scripts/rotate-break-glass-token.py` provides a console-only recovery mechanism that replaces only the break-glass profile, stores the new token in the protected env file, and outputs it once. The runbook requires immediate encrypted standby synchronization.
- The runbook now pins an approved full commit before deployment, verifies it with `git rev-parse HEAD`, puts TLS before password login, keeps a break-glass token during rollback, delays legacy-token revocation until an observation period, uses `system.users.setPassword` and `system.users.revokeSessions`, and names `admin_user_credentials`.

## Follow-up Verification

- New deployment regression: `tests/test_cloud_dual_host_deployment.py::test_human_auth_rollout_has_tls_token_sync_and_failover_guards` first failed because `ops/compose.tls.yml` did not exist; it now passes.
- `ops/scripts/rotate-break-glass-token.py` compiled with the project Python environment. A functional temporary-env run confirmed it preserves the dashboard profile, replaces only the old break-glass profile, and emits one new token. A BOM-prefixed env fixture exposed a real duplicate-key issue; the script now reads `utf-8-sig`, and the executable pytest regression passes.
- Final targeted suites: `49 passed in 10.52s` for `tests/test_cloud_dual_host_deployment.py` and `tests/test_deployment_config.py`, using isolated Task 9 temp paths and `-p no:cacheprovider`.
- Final syntax checks: `bash -n` passed for all 15 shell scripts; PyYAML parsed primary, standby, and TLS Compose files; the break-glass recovery script compiled successfully.

## Second Independent Review Follow-up

The second review identified operational safety gaps in the first follow-up. The following implementation and documentation changes close them:

- All deployment-time Compose validation now uses `docker compose ... config --quiet`; no command writes rendered configuration (and its secrets) to a predictable `/tmp` path.
- `promote-standby.sh` completes reversible preflight checks before `STOP REPLICA`, read-only changes, or reset: immutable commit and tag, protected environment fields, required data directories, the built image, and `docker compose config --quiet`. When TLS is enabled it also requires the standby-only `/srv/smart-bamboo-dr/tls` certificate/key paths, validates both files and certificate lifetime, and applies `ops/compose.tls.yml` whether human authentication is enabled or disabled.
- `make-standby-env.sh` now writes a private same-directory temporary file, validates every copied release/authentication/TLS/token field, sets its mode, and atomically replaces the destination only after all checks succeed. It rewrites TLS paths to `/srv/smart-bamboo-dr/tls`.
- `generate-primary-env.sh` refuses to overwrite an existing protected environment by default. Replacement requires both `--replace` and `CONFIRM_REPLACE_PRIMARY_ENV=YES`. New `upgrade-primary-env.py` idempotently fills missing immutable release, TLS, and initial break-glass fields without rotating existing database or service credentials.
- Break-glass rotation now removes both the token named by `SMART_BAMBOO_BREAK_GLASS_TOKEN` and every `user=break_glass` token profile before adding one new profile. It supports a create-new-only `--token-output-file` created with mode `0600`; the runbook limits stdout to an interactive, non-logged console and requires a private output file for systemd, CI, or redirected execution.
- `enable-tls.sh` is primary-only. A standby starts TLS Nginx only through the failover promotion path. Role parsing in verification scripts is strict, and `ops/README.md` now reflects the confirmation variable and TCP 443 security-group rule.
- The runbook distinguishes application readiness from TLS verification: `/api/health` does not prove a TLS handshake, so external `openssl s_client` and HTTPS `curl` remain separate release gates.

## Second Follow-up Verification

- Added executable regressions for the second review. They prove the primary-env upgrade is idempotent and leaves MySQL credentials unchanged, and prove rotation revokes the exact current break-glass token plus all old `user=break_glass` profiles.
- The first execution of those new regressions failed twice on Windows because POSIX mode bits for an `os.open(..., 0o600)` file are not represented by Windows `stat`. The scripts already create the file with `O_EXCL` and `0600`; the test now checks that contract and asserts actual mode bits only on POSIX. Rerun result: `52 passed in 11.69s` for `tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py`.
- Initial full pytest run timed out at the tool's 124-second limit and is not counted as passing. A second run with a 600-second limit completed: `776 passed in 191.82s (0:03:11)` using `REMOTE_SENSING_DATA_DIR`, an isolated Task 9 `--basetemp`, and `-p no:cacheprovider`.
- `bash -n` passed for the operational shell scripts; `py_compile` passed for both token lifecycle scripts; PyYAML parsed all four Compose files (`docker-compose.yml`, primary, standby, and TLS). The deployment contract test suite covers the Compose environment contract.
- Node `--check` passed for all 28 tracked JavaScript files. All three existing Node behavior files passed (21 assertions total).
- Docker CLI remains unavailable locally. Actual `docker compose ... config --quiet`, image availability, certificate placement, TLS handshake, and cloud-host promotion remain explicit cloud-host release gates. Browser desktop/mobile screenshots and interactive cloud acceptance remain deferred to the controller.

## Controller Browser Acceptance

Controller acceptance was completed after `d735f08` and passed `19/19`. The controller verified that no legacy token field is exposed; the lockout flow returns four `401` responses followed by `423`; forced password change reaches the admin shell; disabling an account works; a viewer can be created; temporary-password and session-revocation actions work; the viewer receives `403` for both security actions; logout clears the session and redirects; and the 390px mobile viewport has no horizontal overflow. No passwords, tokens, cookies, or other credential values are recorded here. Browser artifacts are stored outside the repository at `D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\smart-bamboo-auth-e2e-artifacts`.
