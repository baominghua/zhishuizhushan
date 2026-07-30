# Smart Dictionaries, References, and Basemap Cache Implementation Plan

> **For Codex:** Execute this plan task by task with tests first. Keep database, JSON fallback, permissions, admin pages, and deployment checks aligned.

**Goal:** Fix production basemap cache reuse and service-token login, then replace governed free-text fields with reusable dictionary, administrative-division, and entity-reference controls.

**Architecture:** Add normalized dictionary type/item storage with MySQL and JSON fallback. Expose read options separately from management CRUD. Field schemas declare `dictionary`, `administrative-division`, `reference`, or `multi-reference` behavior so every admin module reuses the same controls and stores stable codes instead of duplicated labels.

**Tech Stack:** FastAPI, MySQL 8.4, JSON fallback, vanilla JavaScript admin shell, Node test runner, pytest, Docker Compose/Nginx.

---

## Task 1: Production Basemap and Service-Token Session

- [x] Add a failing test proving production uses the serving origin instead of forcing port `8010`.
- [x] Route Tianditu tile requests through the existing persistent server cache.
- [x] Add immutable browser cache and stale reuse headers to cached tiles.
- [x] Add failing tests proving a validated service token redirects and authorizes later admin API requests.
- [x] Keep service tokens in `sessionStorage` only; never copy them to cookies, URLs, profiles, or `localStorage`.
- [x] Run targeted Node and pytest checks.

## Task 2: Dictionary Data Model and API

**Files:**
- Create: `server/modules/dictionaries.py`
- Modify: `server/modules/mysql_schema.py`
- Modify: `server/modules/database.py`
- Modify: `server/app.py`
- Test: `tests/test_dictionaries_api.py`
- Test: `tests/test_mysql_schema.py`

- [ ] Write failing tests for dictionary type/item CRUD, hierarchy, search, soft delete, option lookup, and permissions.
- [ ] Add `dictionary_types` and `dictionary_items` MySQL tables, indexes, foreign keys, and core schema readiness checks.
- [ ] Add JSON fallback files under `data/remote-sensing/admin/`.
- [ ] Implement management CRUD and lightweight option APIs.
- [ ] Add an idempotent project seed for administrative divisions and common forestry/business dictionaries.
- [ ] Merge unique town/village values already present in forest-block data without overwriting curated records.

## Task 3: Permission and Menu Integration

**Files:**
- Modify: `server/modules/admin_roles.py`
- Modify: `admin-common.js`
- Test: `tests/test_admin_separation.py`
- Test: `tests/admin_shell_behavior.test.js`

- [ ] Write failing tests for dictionary menu visibility and action-level permissions.
- [ ] Add `system.dictionaries.view/create/update/delete/restore/import/manage`.
- [ ] Add a standalone “字典管理” menu page under data governance.
- [ ] Verify role profiles can grant viewing separately from create, update, delete, restore, and import.

## Task 4: Dictionary Management Admin Page

**Files:**
- Create: `admin-dictionaries.html`
- Create: `admin-dictionaries.js`
- Modify: `admin.css`
- Test: `tests/test_admin_separation.py`

- [ ] Build a full-width ledger with filters, pagination, status, and right-side row actions.
- [ ] Open read-only detail, create, and edit in separate drawers; keep delete as soft delete.
- [ ] Support hierarchical item browsing, parent selection, sorting, aliases, source, and metadata.
- [ ] Add CSV/XLSX import preview and idempotent commit for larger code tables.

## Task 5: Reusable Smart Field Controls

**Files:**
- Create: `admin-smart-fields.js`
- Modify: `admin-common.js`
- Modify: `admin.css`
- Test: `tests/admin_smart_fields_behavior.test.js`

- [ ] Write failing tests for dictionary autocomplete, cascading divisions, entity search, and multi-reference serialization.
- [ ] Implement a searchable single/multi option picker with keyboard and empty/loading/error states.
- [ ] Implement province/city/county/town/village cascades using stable codes and parent relationships.
- [ ] Implement remote reference pickers for forest blocks, forest-right archives, business entities, and equipment.
- [ ] Allow creating a missing dictionary item only when the user has dictionary-create permission.

## Task 6: Forest Block and Forest-Right Forms

**Files:**
- Modify: `admin-blocks.html`
- Modify: `admin-blocks.js`
- Modify: `admin-rights.html`
- Modify: `admin-rights.js`
- Test: `tests/test_admin_separation.py`

- [ ] Replace manual county/town/village code/name pairs with one administrative-division cascader.
- [ ] Derive names from selected codes and prevent inconsistent code/name combinations.
- [ ] Replace comma-separated block/right relations with searchable multi-reference pickers.
- [ ] Preserve existing records and API payload compatibility during migration.

## Task 7: Business Module Field Intelligence

**Files:**
- Modify: `server/modules/business.py`
- Modify: `admin-business-module.js`
- Test: `tests/test_business_api.py`
- Test: `tests/admin_business_module_behavior.test.js`

- [ ] Classify every field schema as open text, dictionary, division, entity reference, multi-reference, date, number, or boolean.
- [ ] Add dictionary codes and reference endpoint metadata to all governed fields.
- [ ] Render the corresponding smart control in the generic business editor.
- [ ] Replace manual forest-block and forest-right code lists with linked-record pickers.
- [ ] Add server validation for dictionary codes and referenced record existence.

## Task 8: Verification and Production Release

- [ ] Run syntax checks for every JavaScript file.
- [ ] Run focused Node and pytest suites, then the full suite with an approved external basetemp.
- [ ] Verify desktop and mobile layouts with Playwright screenshots and interaction checks.
- [ ] Confirm repeat Tianditu requests produce server cache hits and browser-cache headers.
- [ ] Confirm service-token login redirects and remains authorized for the tab session.
- [ ] Confirm dictionary CRUD, hierarchy, imports, permissions, and all smart field relationships.
- [ ] Build a fixed application image, deploy only the primary app, and complete HTTP/API smoke tests.
- [ ] Transfer the verified fixed image to standby without starting the dormant standby application.

