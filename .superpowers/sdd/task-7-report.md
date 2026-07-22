# Task 7 Report: Session-aware Admin Shell and Password Security

## Delivered

- Reworked `admin-common.js` around the cookie-backed `/api/auth/me` profile. `initShell()` now gates business API work until the effective permissions and menus are available.
- Removed persistent human/service-token handling from the shared admin shell. All shared and raw admin requests use `credentials: "include"`; mutating human-session requests receive `X-CSRF-Token` from session storage.
- Added same-origin login return paths, server-first logout, session-state cleanup, and public `AdminCommon.refreshSession()` / `AdminCommon.logout()` APIs.
- Added a focused forced-password-change dialog that blocks normal admin content, handles a backend `403 Password change required`, validates confirmation, clears password fields in `finally`, and refreshes the session after success.
- Added separate row and detail actions for temporary passwords and session revocation. Temporary passwords use only the security endpoint payload and are cleared immediately after submission.
- Routed download, health, and upload fetches in every independent admin page through `AdminCommon.fetchWithSession()` so they cannot bypass session gating, cookie credentials, CSRF, 401 redirects, or forced password change handling.

## Tests

- `node --test tests/admin_shell_behavior.test.js tests/admin_users_security_behavior.test.js` - 5 passed
- `D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_admin_login_ui.py tests/test_admin_separation.py tests/test_auth.py tests/test_auth_store.py tests/test_human_auth.py -q -p no:cacheprovider --basetemp .tmp\\task7-final2` - 210 passed
- `Get-ChildItem -Filter 'admin-*.js' | ForEach-Object { node --check $_.FullName }` - passed
- `git diff --check` - passed

## Residual Risk

- Browser-level visual interaction was not exercised against a live server in this worktree. The focused VM/DOM tests cover request, redirect, forced-change, logout, and password-action behavior; end-to-end deployment verification remains appropriate for the actual cookie and HTTPS configuration.

## Review Follow-up

- `sessionReadyPromise` is now a real business-request gate. A forced password change keeps it pending; the internal `authApi()` bypasses that gate only for `/api/auth/me` and password change, and the post-change profile refresh releases queued page loaders.
- Startup and successful logout remove the legacy `smartBambooAdminToken` and `smartBambooAdminTokenPersistent` keys from both browser storage areas. Failed logout keeps the live session/profile, renders a Chinese retry status, and does not redirect; a `401` remains an idempotent completed logout.
- The dashboard health function is covered through the real shared gate: no health request starts while forced change is active, and it resumes automatically after password change succeeds.
- The user ledger now reserves stable desktop and mobile space for its five icon actions, retains horizontal scrolling, and awaits/catches session-revocation failures in both row and detail handlers.

## Review Verification

- `node --test tests/admin_shell_behavior.test.js tests/admin_users_security_behavior.test.js` - 8 passed
- `D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe -m pytest tests/test_admin_login_ui.py tests/test_admin_separation.py tests/test_auth.py tests/test_auth_store.py tests/test_human_auth.py -q -p no:cacheprovider --basetemp .tmp\\task7-review-final2` - 211 passed
- All `admin-*.js` syntax checks and `git diff --check` passed.
