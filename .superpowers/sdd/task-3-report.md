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

## Review Repair Evidence

### RED

Command:

```powershell
D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py -q -p no:cacheprovider --basetemp=D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\task-3-review-red-final
```

Result before the repair:

```text
.F.F.........                                                            [100%]
2 failed, 11 passed in 10.28s
```

The casefolded login returned `401` instead of `200`, and production HTTP login with `SMART_BAMBOO_AUTH_REQUIRE_HTTPS=0` returned `200` instead of `426`. The trusted-proxy Secure-cookie test plus the new successful-login reset and password-change audit secrecy tests already passed, confirming those existing paths while documenting their contracts.

### GREEN

Targeted command:

```powershell
D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py -q -p no:cacheprovider --basetemp=D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\task-3-review-green
```

Result:

```text
.............                                                            [100%]
13 passed in 13.15s
```

Focused regression command:

```powershell
D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py tests/test_passwords.py tests/test_auth_store.py tests/test_auth.py tests/test_deployment_config.py tests/test_admin_roles.py -q -p no:cacheprovider --basetemp=D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp\task-3-review-regression-rerun
```

Result:

```text
........................................................................ [ 54%]
.............................................................            [100%]
133 passed in 76.45s (0:01:16)
```

### Repair Details

- Usernames use one `trim + lower` canonical form. New or normalized users persist it; JSON lookup compares canonical values; MySQL and PostGIS lookups use matching `LOWER(username) = %s` predicates so the login path resolves the same authoritative user across backends before loading credentials by user id.
- Production mode always requires HTTPS for password login. `SMART_BAMBOO_AUTH_REQUIRE_HTTPS` remains available in development/test, but cannot weaken production. With explicit trusted proxy headers, a production HTTPS login emits a `Secure` session cookie.
- Added explicit coverage for successful-login failure-count reset and for password-change audit secrecy, including both passwords, old/new password hashes, raw session token, and raw CSRF token.
- Updated the existing PostGIS duplicate-user query assertion to the canonical lookup predicate.
