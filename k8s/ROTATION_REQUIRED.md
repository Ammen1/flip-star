# ROTATION REQUIRED — leaked credentials

Every credential below is **compromised** and must be rotated. None of them
were rotated by this work: rotation needs access to Telebirr, Onevas, Ethio
Telecom CRM, the database provider and Vault, which this environment does not
have. Removing the files stops the leak from continuing; it does not undo the
exposure.

**Why these must be treated as compromised even though the files are now
untracked:** the values are in this repository's git history and are
recoverable by anyone with a clone, using nothing more exotic than
`git log --all -- .env`. Untracking a file at HEAD does not remove it from
history. They were additionally shipped inside every published Docker image
until `.dockerignore` was fixed (see `k8s/README.md`, defect 3).

No values are reproduced here.

---

## How the exposure happened

Three separate paths, all now closed:

1. **Committed `.env` files.** `.env`, `backend/.env`, `backend/.env.production`
   and `backend/render.env` were tracked. Verified with
   `git log --all --diff-filter=A -- .env`.
2. **`.env.example`.** Below roughly line 210 this file was not a template at
   all — a real production `.env` had been pasted in. Verified by hashing its
   values against the committed `.env`: six matched byte-for-byte, and it also
   carried a Telebirr RSA private key and a VAPID EC private key in full PEM
   form. It has been sanitised: key names kept, values blanked.
3. **The Docker image.** `.dockerignore` did not exclude `.git`, and both
   Dockerfiles end with `COPY . .`, so `/app/.git` (175 MB of history) shipped
   in every image. Confirmed by extracting it from a built image and reading
   the credentials back out.

---

## Rotate these

### Django

| Credential | Where it leaked | Notes |
|---|---|---|
| `SECRET_KEY` | `.env` (32 ch), `backend/render.env` (40 ch), `backend/.env.production` (67 ch), `.env.example` | **Three distinct values** — rotate whichever the environment actually uses, and treat all three as burned. Rotating invalidates existing sessions, password-reset tokens and any signed value. |

### Database

| Credential | Where it leaked | Notes |
|---|---|---|
| `DB_PASSWORD` | `.env` (12 ch), `backend/render.env` (21 ch), `backend/.env.production` (16 ch), `.env.example` | **Three distinct passwords**, so plausibly three different databases (one is the Neon Postgres password flagged in the earlier audit). Rotate every one. |

### Admin

| Credential | Where it leaked | Notes |
|---|---|---|
| `ADMIN_PASSWORD` | `.env`, `.env.example` | Consumed by `manage.py create_superadmin`. Rotate, and check whether a superuser was ever created with it. |

### Web Push (VAPID)

| Credential | Where it leaked | Notes |
|---|---|---|
| `VAPID_PRIVATE_KEY` | `backend/.env`, `.env.example` (full PEM EC private key) | Rotating the VAPID keypair invalidates **all existing push subscriptions** — clients must re-subscribe. Plan the rollout. |
| `VAPID_PUBLIC_KEY` | same | Rotate as a pair. |

### Onevas

| Credential | Where it leaked | Notes |
|---|---|---|
| `ONEVAS_APPLICATION_KEY` | `.env`, `.env.example`, **and hardcoded in application source** | See the source-code note below — **four** distinct keys are involved, not one. |

### Telebirr (Ethio Telecom)

Rotate with Ethio Telecom. All leaked via `.env` / `backend/.env` /
`.env.example`:

| Credential |
|---|
| `TELEBIRR_PRIVATE_KEY` (full RSA private key, in `.env.example`) |
| `TELEBIRR_PUBLIC_KEY` (rotate with the private key) |
| `TELEBIRR_THIRD_PARTY_PASSWORD` |
| `TELEBIRR_SP_OPERATOR_CREDENTIAL` |
| `TELEBIRR_ORG_OPERATOR_CREDENTIAL` |
| `TELEBIRR_APP_SECRET` |
| `TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL` |
| `TELEBIRR_B2C_THIRD_PARTY_PASSWORD` |
| `TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL` |
| `TELEBIRR_USSD_THIRD_PARTY_PASSWORD` |

### Ethio Telecom CRM

| Credential | Where it leaked |
|---|---|
| `CRM_ACCESS_PASSWORD` | `.env.example` |

### Object storage

| Credential | Where it leaked | Notes |
|---|---|---|
| `SECRET_ACCESS_KEY` | `.env.example` (40 ch, AWS-shaped) | Empty in `.env`, populated in `.env.example`. Rotate the corresponding `ACCESS_KEY_ID` too. |

---

## Still hardcoded in application source — not fixed here

`api/migrations/0057_create_subscription_tiers.py` and
`scripts/populate_subscription_tiers.py` each embed **four distinct 32-character
Onevas application keys**. One is byte-identical to the `ONEVAS_APPLICATION_KEY`
that leaked via `.env` (verified by SHA-256 comparison); the other three are
additional keys that leak only through these two files.

They were deliberately **not** removed:

- The migration is applied history. Editing it risks state drift for any
  environment that has already run it.
- `populate_subscription_tiers.py` seeds real subscription tiers with those
  keys; blanking them changes seeded application data.

Both are business-data decisions for the owning team, not deployment changes.
They are allowlisted in `.gitleaks.toml` **by path, with this file referenced**,
so the blocking secret-scan gate stays useful instead of failing on every run —
not because they are acceptable. **Recommended follow-up:** move the four keys
into Vault, read them at runtime, and delete the `.gitleaks.toml` entry.

---

## After rotating

1. Write the new values to Vault at `flipstar/backend/staging` and
   `flipstar/backend/production`. They must not return to Git.
2. Restart the API, Celery worker and Celery beat — secrets are fetched once at
   process start and cached for the process lifetime.
3. Consider whether history should be rewritten (`git filter-repo`) or the
   repository re-created. Rotation makes the leaked values worthless, which is
   the part that actually matters; rewriting history is a separate, disruptive
   decision.
4. Re-run `gitleaks detect --no-git --source .` and confirm it stays clean.
