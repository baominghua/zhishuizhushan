# Task 3 Report: Login, Logout, Session, and Password Change APIs

## Status

Implemented and verified. The human authentication API is registered alongside the existing bearer-token API and uses the existing administrator user, role, data-scope, credential, session, and audit mechanisms.

## TDD Evidence

### RED

Command:

```powershell
D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py -q -p no:cacheprovider --basetemp=D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\task-3-red
```

Result before `server/modules/human_auth.py` and its routes existed:

```text
FFFFFFFF                                                                 [100%]
8 failed in 6.04s
```

The login/session contracts received `405 Method Not Allowed` from the pre-existing static fallback rather than the new API responses. The remaining assertions failed because no session cookie or CSRF value had been issued. This established that the requested routes were absent.

### GREEN

Command:

```powershell
D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py -q -p no:cacheprovider --basetemp=D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\task-3-green-rerun
```

Result:

```text
........                                                                 [100%]
8 passed in 9.20s
```

Focused regression command:

```powershell
D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py tests/test_passwords.py tests/test_auth_store.py tests/test_auth.py tests/test_deployment_config.py -q -p no:cacheprovider --basetemp=D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\task-3-regression
```

Result:

```text
................................................                         [100%]
48 passed in 22.50s
```

## Tests

- Successful normalized-username login returns the user profile, effective roles, CSRF token, and an `HttpOnly`, `SameSite=lax` cookie.
- Production HTTP login is rejected with `426`.
- Five invalid passwords lock the account and return `423`.
- The session endpoint returns the authenticated profile and rejects an expired persisted session.
- Logout requires CSRF, revokes the current session, and clears the cookie.
- Password change requires CSRF, increments the credential version, clears the forced-change flag, preserves the current session, and revokes other sessions.
- Login and logout audit events contain no password, raw session token, raw CSRF token, or password hash.

## Files Changed

- `server/modules/human_auth.py`
- `server/modules/settings.py`
- `server/app.py`
- `tests/test_human_auth.py`
- `.superpowers/sdd/task-3-report.md`

## Self-Review

- Request payload models reject undeclared fields.
- Human sessions validate the active, non-deleted authoritative user, current credential version, idle timeout, absolute timeout, revocation state, and CSRF token hash.
- Login failure responses do not distinguish unknown, deleted, inactive, missing-credential, or incorrect-password cases.
- The session cookie is HTTP-only, `SameSite=lax`, path-scoped, and marked secure only for direct HTTPS or explicitly trusted proxy HTTPS headers.
- Passwords, password hashes, raw session tokens, and raw CSRF values are not passed to the audit helper. The existing user snapshot intentionally omits audit history from its own nested snapshots.
- Password changes update the current session's credential version and revoke all other sessions, preventing the current browser from being stranded while invalidating every other login.
- `git diff --check` reported no whitespace errors before staging.

## Concerns

- The JSON persistence path and MySQL query behavior are covered by the existing focused persistence tests, but no live MySQL server is available for end-to-end API integration in this environment.
- The full repository suite was not run; the focused authentication, password, session-store, legacy bearer-auth, and deployment-config regression set passed.
