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

## Third Independent Review Follow-up

- `promote-standby.sh` now reads and validates `SHOW REPLICA STATUS` before any write-permission change, requires the SQL thread to be running with an empty `Last_SQL_Error`, then stops only the IO thread to freeze `Retrieved_Gtid_Set`. It waits for that exact set with `WAIT_FOR_EXECUTED_GTID_SET`, verifies `GTID_SUBSET(..., @@GLOBAL.gtid_executed)`, and only then stops replication and disables read-only mode. It deliberately no longer runs `RESET REPLICA ALL`, preserving replication metadata for incident evidence and later rebuilds.
- GTID convergence proves only that transactions already received by the standby were applied. The runbook now requires an explicit source-side RPO decision for transactions that were not transferred before the IO thread was frozen.
- Before any database change, promotion validates TLS certificate/key existence, validity, and matching public keys when TLS is enabled. It also verifies required standby directories and the app, GeoServer, and Nginx images before starting failover services.
- Break-glass rotation now always requires a new `--token-output-file`; it never prints a secret to stdout. The handoff file is created and synced before the environment replacement, and is removed if replacement fails. Primary-environment upgrade validates an existing break-glass profile (user, admin role, and global project/area scopes), revokes a broken pointed profile, and uses the same handoff-before-environment ordering when a replacement is required.
- `make-standby-env.sh` now backs up and rolls back both the environment and satellite config if either atomic move or the post-move validation fails, avoiding a mixed pair. The runbook and `ops/README.md` now conditionally use the TLS Compose overlay only when TLS is enabled, document the auth=0 confirmation exception, and include the failover image prerequisites.

## Third Follow-up Verification

- Added regression coverage for GTID convergence/no-reset policy, TLS certificate-key public-key matching, required handoff files, invalid break-glass pointer replacement, and standby pair rollback contracts.
- The first new focused test run had one failed assertion because the test expected `unlink()` while the implementation correctly uses `unlink(missing_ok=True)`. After correcting that assertion, the first deployment-contract run exposed an obsolete expectation that promotion reset replication metadata. Updating it introduced an indentation error during pytest collection; that test-only error was corrected. These failures are not counted as passing results.
- Final targeted deployment/configuration verification: `55 passed in 11.67s` for `tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py`, with isolated Task 9 `--basetemp` and `-p no:cacheprovider`.
- Full pytest verification: `779 passed in 192.70s (0:03:12)` using `REMOTE_SENSING_DATA_DIR`, an isolated Task 9 `--basetemp`, and `-p no:cacheprovider`.
- `bash -n` passed for all 15 tracked shell scripts. Python compilation passed for the two credential lifecycle scripts and the deployment regression module.

## Fourth Independent Review Follow-up

- `promote-standby.sh` is now a resumable, protected-file state machine. `/srv/smart-bamboo-dr/config/promotion-state` records `preflight`, `draining`, `commit-intent`, `database-promoted`, `services-started`, or an explicit `recovery-failed` condition together with the immutable release commit.
- Once `STOP REPLICA IO_THREAD` succeeds, an EXIT recovery trap performs a best-effort `START REPLICA IO_THREAD` on every pre-commit failure and reports whether recovery succeeded. The trap is cancelled at the persisted `commit-intent` boundary, immediately before the database write-permission transition.
- A retry always repeats the confirmation and primary-unavailability gates. A `draining` or `recovery-failed` marker first resumes the IO thread before new preflight. A `commit-intent` marker inspects `read_only` and `super_read_only`: it fail-forwards to database promotion only when the state is unambiguously both writable or both read-only; mixed values fail closed. Service-start failures after database promotion are resumed from `database-promoted` rather than being rejected because the SQL thread is intentionally stopped.
- The role-override file is prepared before the irreversible transition and installed by same-directory atomic rename only after `database-promoted`. Temporary override files are cleaned on both normal and error exits.
- Promotion and TLS activation no longer `source` Docker environment files. New `read-protected-env.py` parses only requested `KEY=VALUE` entries as data, rejects duplicate requested keys and malformed/multiline values, and never evaluates shell syntax. `read-replica-status.py` requires exactly one requested field, rejecting duplicate fields and unsupported multi-channel status instead of selecting the last value.
- The runbook documents the state phases and the same-gate rerun command. It prohibits manually deleting the marker, resetting replication metadata, or changing database read-only flags during recovery.

## Fourth Follow-up Verification

- Added executable regressions proving that `$()`, backticks, and semicolon-containing dotenv values are returned as inert data without creating the embedded marker file, and that multi-channel/duplicate `SHOW REPLICA STATUS` fields are rejected. Source-order regressions cover the pre-commit IO recovery trap, state transitions, fail-forward branches, and the absence of `source`.
- Final targeted deployment/configuration verification: `58 passed in 11.64s` for `tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py`, with isolated Task 9 `--basetemp` and `-p no:cacheprovider`.
- Final full pytest verification: `782 passed in 181.19s (0:03:01)` using `REMOTE_SENSING_DATA_DIR`, an isolated Task 9 `--basetemp`, and `-p no:cacheprovider`.
- `bash -n` passed for all 15 tracked shell scripts. Python compilation passed for `read-protected-env.py`, `read-replica-status.py`, the credential lifecycle scripts, and the deployment regression module.

## Fifth Independent Review Follow-up

- Added `durable-atomic-write.py` for protected promotion-state and role-override writes. It writes and fsyncs a same-directory temporary file, atomically replaces the target, and fsyncs the parent directory on the Linux deployment target. Promotion calls it for both the `0600` marker and `0640` role override.
- The irreversible sequence is now durable at each boundary: `commit-intent` marker, database `STOP REPLICA` plus read-only disable, durable role override installation, durable `database-promoted` marker, then failover services. Power loss at each transition is therefore distinguishable on retry.
- `draining` and `recovery-failed` retries inspect the database role before touching replication. Only `1,1` resumes and verifies IO; `0,0` treats the marker as stale, never starts IO, durably installs the override, marks database-promoted, and fails forward. Mixed values fail closed. `database-promoted` follows the same database-role logic, including reboot recovery from an explicit `1,1` state.
- IO recovery now reads `SHOW REPLICA STATUS` after `START REPLICA IO_THREAD`, accepts only IO `Yes` or `Connecting` with SQL `Yes` and no `Last_SQL_Error`, and records `recovery-failed` otherwise.
- The progress ledger records a Minor: the non-executing protected dotenv parser intentionally supports a constrained grammar rather than every Docker Compose env-file edge case. Current generated protected env values remain within that controlled grammar.

## Fifth Follow-up Verification

- Added power-loss/stale-marker/reboot branch regressions, durable-write order assertions, post-restart IO-status assertions, and an executable durable atomic-writer replacement test.
- The first durable-writer test failed on Windows because opening a directory handle for fsync is not supported by that platform. The helper now safely skips that platform-specific operation only off POSIX; its Linux path still requires directory fsync. This failure is not counted as passing. Focused rerun: `3 passed in 0.13s`.
- Final targeted deployment/configuration verification: `60 passed in 11.62s` for `tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py`, with isolated Task 9 `--basetemp` and `-p no:cacheprovider`.
- Final full pytest verification: `784 passed in 185.03s (0:03:05)` using `REMOTE_SENSING_DATA_DIR`, an isolated Task 9 `--basetemp`, and `-p no:cacheprovider`.
- `bash -n` passed for all 15 tracked shell scripts. Python compilation passed for the durable writer, protected-env and replication-status helpers, and deployment regressions.

## Sixth Independent Review Follow-up

- `role-override.cnf` contains no secret and is now durably installed with mode `0644`, matching the initial data-disk file convention so the MySQL container user can read it after restart.
- `durable-atomic-write.py` now applies the requested mode through `os.fchmod` on the temporary file before file flush/fsync. The atomic rename and parent-directory fsync follow, so file content and permission metadata share the same durable write boundary.

## Sixth Follow-up Verification

- Updated regression assertions verify the `0644` role override and the ordering `fchmod -> file fsync -> rename -> parent-directory fsync`. Focused durability verification: `2 passed in 0.20s`.
- Final targeted deployment/configuration verification: `60 passed in 11.72s` for `tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py`, with isolated Task 9 `--basetemp` and `-p no:cacheprovider`.
- Final full pytest verification: `784 passed in 174.26s (0:02:54)` using `REMOTE_SENSING_DATA_DIR`, an isolated Task 9 `--basetemp`, and `-p no:cacheprovider`. `bash -n` passed for all 15 tracked shell scripts.
- Actual MySQL container restart and the cloud-host bind-mounted role-override readability remain cloud-host release gates; they were not claimed as completed locally.
