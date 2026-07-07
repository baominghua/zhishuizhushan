# Task 6 Report: Forest Block To Imagery Links

## Completed

- Added `tests/test_forest_scene_links.py` first and verified the new scene-link routes failed before implementation.
- Implemented `server/modules/forest_scene_links.py` with:
  - `GET /api/forest-blocks/{block_id}/scenes`
  - `POST /api/forest-blocks/{block_id}/scenes`
  - `DELETE /api/forest-blocks/{block_id}/scenes/{scene_id}`
- Stored link data in JSON fallback storage at `get_data_dir()/forest-blocks/forest_block_scene_links.json`.
- Enforced:
  - write access for POST/DELETE
  - forest block existence
  - forest block area visibility using the same block-lookup behavior as the forest block APIs
- Implemented duplicate upsert on `(forestBlockId, sceneId, relationType)`.
- Pinned delete behavior in tests:
  - with `relationType`, delete only the matching relation row
  - without `relationType`, delete all matching scene links for that block and scene id
- Mounted the new router in `server/app.py`.
- Added an admin-side scene link panel with:
  - scene id
  - relation type
  - captured date
  - confidence
  - link action
  - linked scene list
  - remove action
- Added live big-screen card support in `zhushan-bigdata.js` so live API-backed forest blocks show an additional linked-scene tab without changing demo block tabs.

## Verification

- `.\.venv\Scripts\python.exe -m pytest tests/test_forest_scene_links.py -v`
  - Result: 5 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_forest_scene_links.py tests/test_forest_blocks.py tests/test_imports.py -v`
  - Result: 40 passed
- `node --check admin.js`
  - Result: passed
- `node --check zhushan-bigdata.js`
  - Result: passed

## Notes

- `server/app.py` and `zhushan-bigdata.js` already had unrelated local edits before Task 6 work. Only the Task 6 hunks should be committed.
- New UI copy for the Task 6 additions uses clean UTF-8 Chinese.

## Review Fixes

- Added catalog-backed scene validation in `server/modules/forest_scene_links.py` using the existing JSON fallback file at `REMOTE_SENSING_DATA_DIR/catalog.json`.
- `POST /api/forest-blocks/{block_id}/scenes` now returns `404` when the catalog file is missing and `404` when the provided `sceneId` is not present in the catalog.
- Kept local JSON link persistence unchanged.
- Inspected the scene-link panel in `admin.html`; the current file is structurally clean, so no HTML change was needed for this review round.
- Updated `tests/test_forest_scene_links.py` so successful link cases seed catalog scenes and added a regression test that rejects an unknown `sceneId`.

### Verification Output

- `.\.venv\Scripts\python.exe -m pytest tests/test_forest_scene_links.py -k nonexistent_scene_id -v`
  - Result: `1 failed` before implementation (`test_scene_links_reject_nonexistent_scene_id` received `200` instead of `404`)
- `.\.venv\Scripts\python.exe -m pytest tests/test_forest_scene_links.py -v`
  - Result: `6 passed`
- `.\.venv\Scripts\python.exe -m pytest tests/test_forest_scene_links.py tests/test_forest_blocks.py tests/test_imports.py -v`
  - Result: `41 passed`
- `node --check admin.js`
  - Result: passed
- `node --check zhushan-bigdata.js`
  - Result: passed
