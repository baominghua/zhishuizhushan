# Task 5 Report: Account Password Administration and Bootstrap

## RED

- Added backend tests for independent password-reset and session-revocation permissions, credential-version updates, lock clearing, session invalidation, and audit secret exclusion.
- Added bootstrap tests for the MySQL-only default, explicit JSON development opt-in, one-time generated password output, no on-disk password persistence, and restoration of a soft-deleted matching user.
- Observed expected failures before implementation: missing `set-password` route returned `405`; the bootstrap command was absent; the soft-deleted bootstrap case initially created a duplicate user.

## GREEN

- Added `system.users.setPassword` and `system.users.revokeSessions` to the permission catalog, API-scope map, and only the existing `system.users.manage` implication closure.
- Added `POST /api/admin/users/{user_id}/set-password` and `POST /api/admin/users/{user_id}/revoke-sessions` with independent authorization.
- Temporary-password reset validates the existing password policy, stores only the Argon2id hash, increments an existing credential version, requires a change, clears lock state, revokes sessions, and records only changed field names in audit data.
- Added `ops/scripts/bootstrap-admin-password.py`. It rejects non-MySQL storage unless `--allow-json-development` is supplied, supports `--password-stdin`, generates a policy-compliant 20-character temporary password when no input is supplied, writes it only to stdout once, and restores/updates a same-name administrator without duplicating a soft-deleted account.

## Verification

- RED: `python -m pytest tests/test_admin_roles.py::test_password_reset_requires_independent_permission_and_revokes_sessions tests/test_bootstrap_admin_password.py -q -p no:cacheprovider --basetemp $TASK_TMP/task-5-red` -> 3 expected failures.
- GREEN focused: 5 passed.
- Task brief suite: `python -m pytest tests/test_admin_roles.py tests/test_bootstrap_admin_password.py -q -p no:cacheprovider --basetemp $TASK_TMP/task-5-brief` -> 84 passed.
- Related authentication and permission regression: `python -m pytest tests/test_passwords.py tests/test_auth_store.py tests/test_human_auth.py tests/test_auth.py tests/test_admin_roles.py tests/test_bootstrap_admin_password.py -q -p no:cacheprovider --basetemp $TASK_TMP/task-5-regression` -> 126 passed.
- `git diff --check` completed with no output.

## Self-review

- Verified that the new audit event contains only changed field names and normal user metadata; tests assert that password text, password hashes, and session tokens are absent.
- Verified that existing permission implications remain unchanged except for the two new actions added to `system.users.manage`.
- Residual risk: MySQL behavior uses the existing storage helpers and was covered by the established authentication-store tests, but this task did not run against a live MySQL instance.

## Review Remediation

### RED

- Reproduced that `SMART_BAMBOO_STORAGE_BACKEND=mysql` without a database URL completed bootstrap by silently writing JSON.
- Reproduced that bootstrap did not create an `admin` role record and left user/credential writes non-atomic when credential persistence failed.
- Reproduced that password reset and session revocation persisted credential or session changes before an audit failure.

### GREEN

- Bootstrap now uses `use_mysql()` for its fail-closed production gate. A missing MySQL URL exits non-zero before any JSON path is created.
- Bootstrap writes the canonical administrator role, user-role association, credential, session revocation, and audit entry in one MySQL connection/transaction. It rolls back on any exception and checks the persisted role association before commit.
- JSON development operations use a process lock plus byte-for-byte multi-file snapshots. Any failure restores users, roles, credentials, and sessions to their prior state.
- Account-security endpoints use the same MySQL transaction pattern and the JSON snapshot transaction, so audit failures cannot leave a reset password or revoked session behind.

### Verification

- Review RED suite: 5 expected failures covering fail-closed MySQL configuration, missing admin role, bootstrap credential failure rollback, and both endpoint rollback paths.
- Review GREEN focused suite: 5 passed; MySQL bootstrap mock transaction: 1 passed.
- Regression suite: 131 passed in 81.66 seconds.

### Residual Risk

- The MySQL transaction path is exercised with a deterministic mock. A live MySQL integration environment is still required to validate server-side constraint and isolation behavior under concurrent production load.

## Final Storage Boundary Remediation

- `--allow-json-development` now permits only an actual JSON backend; PostGIS is rejected before any read or write.
- Password administration rejects PostGIS with `501` and the stable detail `Human credential administration requires MySQL or JSON development storage` before user lookup.
- JSON users, roles, credentials, sessions, and multi-file recovery share the public `database.JSON_STORE_LOCK` reentrant lock.
- Added direct MySQL audit-failure mock coverage asserting rollback occurs without commit.
- Final focused verification: 5 passed; `git diff --check` passed. The preceding Task 5/auth-store/admin-role/bootstrap regression run reached 103 passing tests before the reload-safe lock reference correction.

## Reload-Safe Lock Remediation

- `database.JSON_STORE_LOCK` now survives `importlib.reload(database)` through a globals guard.
- `auth_store`, `admin_users`, and `admin_roles` dynamically resolve the lock through the `database` module rather than caching an imported alias.
- RED reproduced a changed RLock after reload. Green reload and write-path tests passed; a broader regression initially exposed one remaining session-revocation alias, which was removed.
- Final focused verification: 10 passed and `git diff --check` passed. The broad related suite reached 128 passed before that last stale alias was identified.
