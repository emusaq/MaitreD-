# Red Flags

## Highest-confidence staff portal risk

### 1. DB schema drift can still break the staff portal
- The staff portal reads and writes newer reservation fields such as `status`, `guest_name`, `occasion`, `guest_phone`, `note`, and reservation-settings messaging fields.
- Older databases that predate those columns will fail at runtime when `/staff/`, `/staff/reservations`, or the confirm/deny/cancel flows execute their queries.
- This is the most likely DB-level explanation for a portal that "still has issues" after code changes.
- Added coverage in `tests/test_db_schema_consistency.py` to catch this class of problem earlier.

## Repo hygiene and deployment risks

### 2. Secrets and local environment artifacts are tracked
- `.env` is tracked even though `.gitignore` says it should be ignored.
- This is a strong signal that secrets may already have been committed and rotated credentials should be assumed necessary whenever `.env` changes.

### 3. A local virtualenv appears to be committed
- `.venv/` contents and many compiled cache files are tracked.
- This bloats the repository, creates noisy diffs, and makes installs less reproducible across machines.

### 4. Local SQLite test/debug DBs are sitting in the repo root
- Files like `test_staff.db`, `test_staff_auth.db`, `tmp_portal_debug.db`, and `tmp_toolcall.db` are present in the working tree.
- These can hide real migration problems by making local behavior depend on stale data instead of the intended setup path.

## Product and architecture risks

### 5. Multi-restaurant support is not implemented, but the schema suggests it is
- `reservation_settings` has a `restaurant_id`, but staff and MCP flows still use `.first()` instead of filtering by restaurant.
- This can silently apply the wrong settings if more than one row exists.

### 6. Legacy employee passwords can still cause staff login issues
- The login path handles plaintext legacy passwords by migrating them on successful login.
- Accounts with missing or bad password data still fail, and dormant legacy users will remain broken until reset.

### 7. Archived schema file still exists beside Alembic + ORM definitions
- `database/schema.py` is described as archived, while Alembic + ORM are now the active schema sources.
- Keeping multiple schema descriptions around increases the chance that developers update the wrong source.

## Operational gaps

### 8. Error monitoring is still missing
- Staff portal and reservation failures currently depend on local logs for visibility.
- Without centralized monitoring, intermittent production portal errors will be hard to diagnose.

### 9. Multi-process reservation safety is still incomplete
- The reservation insert logic is safer than before, but the documented multi-worker race is still open.
- Scaling workers before adding DB-level locking could reintroduce booking inconsistencies.

## Suggested next checks for the staff portal
- Run the new DB consistency test against the schema used by staff routes.
- Verify the deployed database has all required `reservations` and `reservation_settings` columns.
- Confirm there is exactly one intended `reservation_settings` row for the active restaurant.
- Reset or inspect any legacy staff accounts that still have invalid password data.
