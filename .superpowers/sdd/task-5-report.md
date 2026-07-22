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
