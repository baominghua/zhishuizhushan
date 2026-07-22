# Smart Bamboo Admin Authentication and Domain Forms Design

**Status:** Approved design  
**Date:** 2026-07-22  
**Scope:** Human authentication, action permissions, metadata-driven CRUD forms, and normalized relationships for all business modules.

## 1. Context

The platform already has separate forest-block and forest-rights ledgers, an admin user/role/permission foundation, 25 business modules, and MySQL-compatible relationship tables. The current production acceptance login still asks a human user to paste an API token. Most business create/edit forms expose only a few shallow fields, accept linked block/right codes as comma-separated text, and expose raw JSON as a normal input.

The next release turns these foundations into a formal administration system:

- people sign in with an account and password tied to the existing user and role system;
- machine/dashboard access continues to use separately managed service tokens;
- every module has an explicit field schema, validation rules, status vocabulary, and relation definitions;
- forest blocks, forest rights, farmers, cooperatives, enterprises, devices, materials, and other records are selected from existing ledgers;
- list, detail, create, edit, delete, and export remain separate actions and permission boundaries.

## 2. Goals

1. Replace human token entry with secure username/password authentication.
2. Preserve current roles, menu permissions, data scopes, and service-token access.
3. Build one reusable form and relation-selector system for all 25 business modules.
4. Store relationships as normalized record links, not unchecked text codes.
5. Keep forest blocks and forest-rights archives independent while allowing bidirectional navigation.
6. Make every create/edit operation auditable and permission-aware.

## 3. Non-goals

- Complex multi-step approval engines are not included in this release.
- Public self-registration and password recovery by email/SMS are not included.
- Automatic organization synchronization with an external identity provider is not included.
- Domain-specific mobile apps are not included; the APIs and schemas will remain reusable by them.

## 4. Authentication Architecture

### 4.1 Human and service identities

Human users authenticate with username/password. Dashboard and integration clients authenticate with service tokens. The two credential types are deliberately separate:

- Human identity: `admin_users` + `admin_user_credentials` + `admin_sessions`.
- Service identity: the existing environment-backed token registry, later migratable to a service-account table.

A service token cannot be used by the admin login form. A human session cannot be copied into dashboard configuration.

### 4.2 Credential storage

Add `admin_user_credentials` as a one-to-one secret table:

| Column | Purpose |
| --- | --- |
| `user_id` | Foreign key to `admin_users.id`, unique |
| `password_hash` | Argon2id encoded hash |
| `password_changed_at` | Last successful password change |
| `must_change_password` | Forces first-login password replacement |
| `failed_login_count` | Consecutive failed attempts |
| `locked_until` | Temporary lock expiry |
| `credential_version` | Revokes old sessions after a password reset |
| `created_at`, `updated_at` | Audit timestamps |

Secret columns never appear in user list/detail serializers. Passwords are never logged or returned.

### 4.3 Sessions

Add `admin_sessions`:

| Column | Purpose |
| --- | --- |
| `id` | Session identifier |
| `user_id` | Authenticated user |
| `token_hash` | SHA-256 hash of a random opaque session token |
| `csrf_token_hash` | Hash used to validate mutating requests |
| `credential_version` | Invalidates sessions after password reset |
| `issued_at`, `last_seen_at`, `expires_at` | Session lifetime |
| `revoked_at` | Explicit logout/revocation |
| `ip_address`, `user_agent` | Security audit context |

The browser receives the opaque session token in an `HttpOnly`, `SameSite=Lax` cookie. Production cookies use `Secure`. Mutating requests also send an in-memory CSRF token in `X-CSRF-Token`. Sessions expire after eight hours of inactivity and no later than 24 hours after issue.

### 4.4 Login policy

- Username matching is normalized and case-insensitive.
- Disabled or soft-deleted users cannot sign in.
- Five consecutive failures lock the account for 15 minutes.
- A successful login resets the failure counter and records `last_login_at`.
- First login and administrator password reset set `must_change_password=true`.
- Password policy: at least 10 characters and at least three of uppercase, lowercase, number, and symbol.
- Password change revokes all other sessions.
- Login, failure, lock, logout, password change, reset, and session revocation produce audit events.

### 4.5 Authentication APIs

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/auth/session`
- `POST /api/auth/change-password`
- `POST /api/admin/users/{id}/set-password`
- `POST /api/admin/users/{id}/revoke-sessions`

The existing bearer-token path remains available for service identities. `request_context()` resolves either a valid human session or a valid service token into the same authorization context.

### 4.6 Bootstrap

No default password is committed. A server-side bootstrap command creates or resets the first administrator, prints a one-time temporary password once, and forces a password change. The current admin token may be used only during migration and is removed from the human login UI after HTTPS activation.

### 4.7 HTTPS gate

Username/password login is not enabled on the current public plaintext HTTP endpoint. Production login requires HTTPS as observed through the trusted Nginx proxy headers. Local development on loopback may opt into insecure login explicitly.

Until a domain and TLS certificate are configured:

- port `18080` remains an acceptance environment;
- no formal password is entered over public HTTP;
- existing service-token access remains the temporary administration path;
- formal business and rights data must not be entered.

## 5. Authorization Model

Each module exposes separate operation permissions:

- `{module}.list`
- `{module}.view`
- `{module}.create`
- `{module}.update`
- `{module}.delete`
- `{module}.export`

Existing `{module}.manage` permissions imply create, update, and delete during migration so current administrators do not lose access. Menu visibility requires list permission. Row action buttons are rendered and enabled from the same permission catalog used by the API.

Data-scope filters apply to list queries, reference pickers, detail reads, mutations, and relationship creation. A user cannot link a record that they cannot view.

## 6. Metadata-driven Form Contract

The module schema endpoint returns presentation and validation metadata instead of only a field name and primitive type.

```json
{
  "key": "linkedBlockIds",
  "label": "关联林班",
  "section": "空间关联",
  "type": "relation",
  "required": true,
  "widget": "remote-multi-select",
  "relation": {
    "resource": "forest-blocks",
    "valueKey": "id",
    "searchKeys": ["code", "name", "townName", "villageName"],
    "displayKeys": ["code", "name", "villageName", "areaMu"],
    "multiple": true
  },
  "validation": {"minItems": 1}
}
```

Supported metadata includes:

- field key, label, help text, section, display order, required state, and default;
- text, long text, phone, identity number, integer, decimal, money, area, date, datetime, boolean, select, multiselect, attachment, and relation widgets;
- length, range, precision, pattern, uniqueness, and conditional-required rules;
- list-column visibility, detail visibility, filterability, and export labels;
- option vocabularies with stable values and user-facing labels;
- relation target, cardinality, query filters, display template, and allowed target states.

Raw JSON is removed from normal create/edit forms. It may be shown read-only to users with a diagnostic permission.

## 7. Reference Selector Experience

The reusable reference selector opens as a searchable dialog or drawer and contains:

- keyword search;
- domain filters such as district, town, village, status, block type, and rights state;
- paginated results with stable dimensions;
- single or multiple selection according to schema;
- selected-record summary with remove and detail actions;
- disabled explanations for unavailable or out-of-scope records.

Forest-block rows show block code, name, village, area, resource type, geometry state, and status. Forest-rights rows show certificate/unit number, rights holder, area, term, archive state, and currently linked blocks.

Reference APIs:

- `GET /api/references/forest-blocks`
- `GET /api/references/forest-rights`
- `GET /api/references/business/{moduleKey}`
- `GET /api/references/equipment`
- `GET /api/references/materials`

All return `items,total,limit,offset` and apply authorization and data scope before results are returned.

## 8. Relationship Storage and Validation

Existing normalized block and rights link tables remain authoritative:

- `business_record_block_links`
- `business_record_right_links`

Add `business_record_links` for cross-business relationships:

| Column | Purpose |
| --- | --- |
| `source_record_id` | Owning business record |
| `relation_type` | Stable semantic key such as `member`, `supplier`, `executor` |
| `target_module_key` | Target business module |
| `target_record_id` | Target record |
| `sort_order` | UI ordering |
| `properties` | Relationship-specific metadata only |

The API accepts record IDs. Codes remain display/search attributes and are never the relationship key. Before commit, the backend checks existence, non-deleted state, permitted status, tenant/data scope, cardinality, and module compatibility. Any invalid target returns a field-specific `422` response; no target is silently discarded.

## 9. CRUD Page Pattern

Every administration module follows the same operational pattern:

1. The main page is a full-width ledger with filters, pagination, export, and a separate create action.
2. Row actions contain view, edit, and delete icons on the far right.
3. View opens a read-only detail surface.
4. Create and edit open an isolated form state; viewing a row never silently switches into editing.
5. Delete remains soft delete and requires a consistent confirmation dialog.
6. Forms are divided into compact domain sections; no nested cards are used.
7. Field errors appear beside the field and preserve valid user input.
8. Related records link to their own detail pages when permission allows.

## 10. Domain Field and Relationship Baseline

The schema below is the minimum formal baseline. Additional fields may be added without changing the form engine.

### 10.1 Core registries

| Module | Required domain fields | Primary relationships |
| --- | --- | --- |
| Farmers | farmer number, name, identity type/number, phone, town, village, address, operation area, active state | forest blocks, forest rights, cooperative |
| Cooperatives | cooperative number, unified credit code, name, legal representative, phone, address, member count, service capacity, operation state | farmers, managed blocks, stewardship agreements, orders |
| Enterprises | enterprise number, unified credit code, enterprise type, main business, contact, phone, processing capacity, purchase state, inventory state | cooperatives, source blocks, purchase batches |
| Plant-protection events | event number, issue type, severity, discovered time, source, affected area, advice, handler, closed time, closure state | forest blocks, maintenance tasks, consumed materials |
| Materials | material number, category, name, specification, unit, batch, stock, warning threshold, supplier, expiry, warehouse, state | supplier enterprise, issue/usage records |
| Policies | policy number, title, issuing body, policy level/type, publish date, effective date, deadline, target, summary, attachment, publish state | applications, projects, applicable subject modules |

### 10.2 Operations and maintenance

| Module | Required domain fields | Primary relationships |
| --- | --- | --- |
| Stewardship agreements | agreement number, parties, service mode, signed date, term, area, fee mode, performance state | cooperative/enterprise, farmers, blocks, rights archives |
| Franchise bases | base number, region, operator, area, service level, operation state | operator subject, blocks, agreements |
| Maintenance tasks | task number, type, priority, assignee, planned window, actual completion, closure state | blocks, farmers/cooperatives, equipment, materials |
| Work logs | log number, work stage, date, workers, labor count, quantity, result, reviewer | task, block, operator, materials |
| Drone tasks | task number, type, device code, route, planned/actual time, result state, result package | blocks, equipment, imagery/result record |
| Equipment | asset number, type, device code, model, owner, install location, purchase date, online state, maintenance due | owner subject, base, task |
| Pest warnings | warning number, risk type, severity, source, issued time, affected area, advice, review state | blocks, protection events, tasks |
| Material services | service number, type, supplier, requested/delivered quantity, requested/delivery date, delivery state, feedback state | materials, supplier, applicant, blocks |

### 10.3 Decision applications

| Module | Required domain fields | Primary relationships |
| --- | --- | --- |
| Yield forecasts | forecast number, object, period, bamboo species, area, forecast yield, model/version, confidence, publish state | blocks, imagery, source survey |
| Harvest plans | plan number, harvest type, planned dates, quantity, method, execution state | forecast, blocks, operator, equipment |
| Income estimates | estimate number, period, income type, expected income, cost, net income, assumptions, review state | blocks, harvest plan, enterprise/cooperative |
| Performance dashboards | metric number, metric type, coverage, definition, value, period, owner, publish state | organization/subject, blocks, source records |
| Carbon estimates | accounting number, type, boundary, period, carbon stock, increment, methodology, verifier, verification state | blocks, rights archives, imagery, carbon project |

### 10.4 Industry platform

| Module | Required domain fields | Primary relationships |
| --- | --- | --- |
| Trade matches | match/order number, trade type, product, grade, quantity, unit, price, delivery window, status | buyer/seller, source blocks, harvest batch |
| Logistics traces | logistics number, batch, carrier, vehicle/contact, current node, quantity, departure/arrival, state | trade order, enterprise, product batch |
| Product QR codes | code, code type, product, batch, target URL, issued time, publish state, scan count | product batch, block origin, enterprise, logistics |
| Supply-chain finance | application number, product, borrower, amount, term, due date, review state, risk level | borrower, trade order, rights/contract collateral |
| Price indexes | index number, product, grade, region, price, period, source count, publish state | market/source records, product category |
| Mobile service channels | channel number, target, channel type, entry, owner, release version, publish state | policy/service modules, responsible organization |

Map-layer publication remains a dedicated GIS module, with layer code/name, source type, service URL, coordinate system, min/max zoom, style, attribution, cache policy, sort order, publication state, and authorized roles.

## 11. API and Error Contract

Business CRUD keeps the current list shape and adds schema-aware validation. Errors use stable codes and field paths:

```json
{
  "error": "relation_target_invalid",
  "message": "One or more forest blocks cannot be linked.",
  "fields": {
    "linkedBlockIds": [
      {"id": "...", "reason": "out_of_scope"}
    ]
  }
}
```

Create/update and relationship writes run in one database transaction. An audit event stores actor, operation, module, record, changed field names, relationship deltas, timestamp, and request context without storing passwords or full sensitive identity values.

## 12. Migration and Compatibility

1. Add credential, session, generic relationship, and permission tables/columns through idempotent schema migration.
2. Keep current service-token authentication operational throughout migration.
3. Convert existing valid `linkedBlockCodes` and `linkedRightCodes` to ID-based links; report unresolved codes instead of deleting them.
4. Preserve existing properties JSON as legacy data, but map known keys into typed attributes.
5. Add compatibility readers so existing records remain visible while modules are migrated.
6. Migrate permissions with `manage` implication before enabling granular UI buttons.
7. Activate human password login only after HTTPS verification.

## 13. Delivery Phases

### Phase A: security and shared foundations

- credential/session schema;
- login, logout, password change/reset, lockout, and audit;
- granular action permissions;
- schema contract, field renderer, reference picker, and backend relationship validator.

### Phase B: core registries

- farmers, cooperatives, enterprises, plant protection, materials, policies;
- forest-block and forest-rights selectors;
- map-layer publication field completion.

### Phase C: operations and decisions

- agreements, bases, tasks, logs, drones, equipment, warnings, services;
- forecasts, harvest, income, performance, and carbon.

### Phase D: industry platform

- trade, logistics, QR codes, finance, price indexes, and mobile channels;
- cross-module navigation and final migration report.

All 25 business modules must meet the common acceptance criteria before the redesign is declared complete.

## 14. Testing Strategy

### Backend

- Argon2id hashing, login success/failure, lockout expiry, forced password change, session expiry, logout, reset, and revocation.
- Disabled/deleted account rejection and audit-event coverage.
- CSRF and HTTPS enforcement.
- Backward-compatible service-token authorization.
- CRUD and schema validation for every module.
- Reference search, pagination, data-scope filtering, invalid target rejection, and transaction rollback.
- Permission tests for list/view/create/update/delete/export.
- Migration tests for existing JSON/MySQL records and code-to-ID relationships.

### Frontend

- Username/password login, first-login password change, locked/disabled states, logout, and expired session handling.
- Field/widget rendering for every metadata type.
- Required, conditional, numeric, date, option, and relationship validation.
- Searchable forest block, rights archive, and business-record selectors.
- Full-width ledger and permission-controlled row actions across all modules.
- No normal create/edit form exposes raw JSON or comma-separated relationship codes.

### Production acceptance

- HTTPS and secure-cookie verification.
- Existing role/data-scope regression checks.
- Core module create/edit/detail/delete/export workflows.
- Relationship navigation from business record to block/right and back.
- Health/readiness and MySQL schema checks.

## 15. Completion Criteria

The release is complete when:

- human administrators authenticate with username/password over HTTPS;
- temporary human token entry is removed;
- all operation permissions are independently configurable;
- all 25 module create/edit forms use explicit domain fields;
- all relationship fields select existing authorized records;
- invalid or out-of-scope references are rejected visibly;
- existing production records remain accessible and linked;
- automated tests and production acceptance checks pass.
