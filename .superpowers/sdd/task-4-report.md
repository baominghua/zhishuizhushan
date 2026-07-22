# Task 4 Report: Unified Session and Service Authentication

## RED

1. Added compatibility tests for mixed auth configuration, human-session `/api/auth/me`, forced password change blocking, browser CSRF validation, and service-token response metadata.
2. Ran `tests/test_auth.py tests/test_human_auth.py` with the required virtual environment, `-p no:cacheprovider`, and a Task 4 base temp directory.
3. Observed the expected feature failures: bearer-only config, missing `authType`, session treated as a development request, no forced-change restriction, and no global CSRF restriction.
4. Tightened the CSRF test to send an incorrect token and observed the missing `token_hash` dependency as a `NameError` before the final fix.

## GREEN

- `tests/test_auth.py tests/test_human_auth.py -q -p no:cacheprovider`: 19 passed.
- `tests/test_auth.py tests/test_admin_roles.py -q -p no:cacheprovider`: 83 passed.

All test runs used `D:\Users\MECHREUO\Documents\New project\.venv\Scripts\python.exe` and isolated `REMOTE_SENSING_DATA_DIR` and `--basetemp` paths under `D:\Users\MECHREUO\Documents\武夷福森报销助手\.tmp`.

## Self Review

- `request_context()` resolves a valid human session before evaluating the existing bearer-token flow; when no session is valid, the bearer and development-header behavior is unchanged.
- Browser sessions require a matching `X-CSRF-Token` on POST, PUT, PATCH, and DELETE. Service bearer tokens never enter that browser-only check.
- Sessions marked `mustChangePassword` are limited to the four required auth endpoints before authorization handlers execute.
- `/api/auth/config` exposes the required session-or-bearer capability fields.
- `/api/auth/me` adds session metadata without changing the existing effective roles, permissions, menus, or data-scope payload.
- `git diff --check` is run as the final whitespace gate before commit.

## Review Remediation

### RED

1. Added a legacy `server/app.py` cache-route regression. A forced-change session received `200` from `GET /api/cache/tiles`; after clearing forced change, an unsafe cache delete also bypassed CSRF.
2. Added forced-session tests for `/api/auth/config` and `/api/auth/login`. Both returned `200` before the remediation, while anonymous requests remained expected to work.
3. Added a development-mode request with an unconfigured bearer string. `/api/auth/me` incorrectly reported `authenticated: true`.
4. Added a forced-session public API test. It exposed a stale health payload reference to removed legacy auth globals, and demonstrated that public API routes needed a common session policy gate.

### GREEN

- The legacy `server/app.py` context is now an adapter over the unified `server.modules.auth.request_context`; legacy routes receive the same human-session, CSRF, forced-change, bearer, and development-header decisions.
- An application-level `/api/*` session-policy gate protects routes that do not declare an auth dependency. It leaves anonymous and bearer requests unblocked by browser CSRF logic.
- `/api/auth/config` and `/api/auth/login` enforce the optional existing-session policy, so anonymous access remains available while a forced-change session receives `403 Password change required`.
- `/api/auth/me` gets `authType` and `authenticated` from the context actually resolved by `request_context`, not from an arbitrary authorization header.
- Health auth status reads the unified settings and service-token profile source.
- `tests/test_auth.py tests/test_human_auth.py tests/test_admin_roles.py -q -p no:cacheprovider`: 106 passed.

## Legacy Bearer Compatibility Remediation

### RED

1. A JSON string profile, `{"legacy-token": "legacy-user"}`, was resolved as `admin` with global scopes. The new regression showed that it could not preserve the legacy no-role/no-scope context.
2. A compact profile, `token=user|roles|projects|areas`, returned `401` because the unified parser treated the full record as a token rather than parsing its fields.

### GREEN

- JSON string profiles now retain only the legacy username. Omitted roles and scopes remain empty, and the regression proves the token cannot pass the imagery scene-delete permission check.
- Compact profiles now retain the legacy record separator and field separator semantics, including multiple roles, projects, areas, and empty fields.
- `tests/test_auth.py tests/test_human_auth.py tests/test_admin_roles.py tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py -q -p no:cacheprovider`: 147 passed.

### Deferred Minor

- The application middleware and route dependency can both read a valid human session during one request. The shared request state prevents policy disagreement, but the duplicate refresh remains noted for a later low-risk consolidation rather than changing this security boundary during the compatibility fix.
