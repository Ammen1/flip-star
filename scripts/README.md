# Scripts

## Maintained

| Script | Purpose |
|---|---|
| `run_local.sh` | Run the backend standalone — SQLite, in-process cache, no Docker. `./scripts/run_local.sh` to serve, or pass any `manage.py` command. |
| `generate_postman.py` | Regenerate `docs/postman/` from the live URL resolver. Run after adding or changing routes. |

---

## Legacy

One-off and operational scripts, moved here from the backend root during the
restructure. Nothing in the application imports them.

Most predate the management-command layer. **Prefer a management command** for
anything that needs to run against production — commands get argument parsing,
`--dry-run` support, logging, and are runnable via
`docker compose exec backend python manage.py <name>`.

## Inventory

| Script | Purpose | Status |
|---|---|---|
| `check_neon_connection.py` | Probe a managed PostgreSQL connection | Diagnostic |
| `compare_databases.py` | Diff row counts between two databases | Diagnostic |
| `run_migrations.py` | Apply migrations outside `manage.py` | Superseded by `manage.py migrate` |
| `reset_db.py` | **Destructive.** Drops and recreates schema | Local only — never run against production |
| `create_initial_data.py` | Seed baseline records | Superseded by `seed_*` management commands |
| `create_test_user.py` | Create a development user | Local only |
| `populate_sample_data.py` | Generate demo content | Local only |
| `populate_subscription_tiers.py` | Seed subscription tiers | Superseded by `manage.py seed_subscription_tiers` |
| `setup_campaigns.py` | Seed campaigns | Local only |
| `setup_admin.py` | Create an admin user | Superseded by `manage.py create_superadmin` |
| `deploy_comment_fix.py` | One-off historical data fix | **Dead** — candidate for deletion |
| `setup.sh` | Legacy environment bootstrap | Superseded by the README instructions |
| `test_api.py` | Manual endpoint smoke check | Superseded by `tests/` |

## Preferred management commands

```bash
python manage.py create_superadmin
python manage.py seed_subscription_tiers
python manage.py seed_default_gifts
python manage.py create_user_profiles
python manage.py generate_video_thumbnails
python manage.py cleanup_broken_media --apply --confirm
```

Scripts marked *Superseded* or *Dead* are retained rather than deleted so their
removal can be reviewed separately. See the restructuring report.
