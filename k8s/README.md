# FlipStar Backend — CI/CD & GitOps

## Scope

This repository **is** the backend now — `frontend/` and `mobile-app/` have
already been extracted into their own repositories (`frontend/` deploys to
Vercel separately; `mobile-app/` was never containerized and never belonged
in a Kubernetes cluster). This pipeline covers the Django/Daphne API, Celery
worker, and Celery beat (one image family, three run modes) — everything at
the repository root.

## Architecture

```text
PR / push to main (api/, common/, config/, infrastructure/, etc. changed)
        │
        ▼
.github/workflows/backend-ci-cd.yml
  secret scan (gitleaks) → lint (diff-scoped) → typecheck → dependency audit
  (pip-audit) → dependency review (PRs) → unit tests → integration tests
  (real Postgres) → django checks → docker build + SBOM → Trivy scan
        │  (push to main only, all gates green)
        ▼
  push images to GHCR, tag = commit SHA (never `latest`) → sign with cosign
  (keyless, GitHub OIDC)
        │
        ▼
  kustomize edit set image → commit to k8s/overlays/staging/kustomization.yaml
        │
        ▼
  Argo CD (flipstar-backend-staging, automated sync) detects the commit,
  syncs, rolls out to the flipstar-staging namespace
```

Every sync, in both environments, is ordered by Argo CD sync waves:

```text
wave -2   ConfigMap, ServiceAccount
wave -1   Job/flipstar-backend-migrate  (must reach Complete)
wave  0   Deployment x3, Service, PDBs, NetworkPolicies, Ingress, HPA
```

A failed migration therefore blocks the rollout instead of half-applying it.
See defect 14 for why this is a wave and not a PreSync hook.

Production is **not** in that path. It's a separate, explicit promotion:

```text
Human runs workflow_dispatch (gated by the "production" GitHub Environment's
required reviewers, if configured -- see below) → backend-promote-production.yml
  (verifies the given commit SHA's images exist in GHCR AND carry a valid
   cosign signature from this repo's own CI -- never rebuilds, only
   promotes what already passed CI and ran in staging)
        │
        ▼
  kustomize edit set image → commit to k8s/overlays/production/kustomization.yaml
        │
        ▼
  Argo CD (flipstar-backend-production, MANUAL sync) shows OutOfSync
        │
        ▼
  Human runs: argocd app sync flipstar-backend-production
  (or clicks Sync in the UI)
        │
        ▼
  Rolls out to flipstar-production
```

Two independent, deliberate human actions between "staging is verified" and
"production is live." Neither CI nor Argo CD is ever given permission to
skip either one.

## Why these choices

- **CI never touches Kubernetes.** `.github/workflows/*.yml` only builds
  images, pushes to GHCR, and commits to this repo. It has zero cluster
  credentials, zero `kubectl`, and no Argo CD API access — Argo CD is what
  actually applies anything to a cluster, satisfying "CI should not have
  cluster-admin access" without needing a token scope negotiation.
- **Mono-repo GitOps**, not a separate GitOps repo. This project has one
  backend service and a small team — a second repo would be pure overhead.
  The `k8s/` tree lives in the same repo as the application code Argo CD is
  deploying, but Argo CD only ever watches `k8s/overlays/<env>`, so an
  application-code-only commit never triggers a sync.
- **Same branch (`main`), different overlay paths** for staging vs.
  production — not branch-per-environment. This repo's `main` and `master`
  have diverged significantly (see prior session notes / `git log
main..origin/master`) and `uat` is a third branch on top of that;
  building environment routing on top of that divergence would be fragile.
  Kustomize overlays exist precisely so one branch's history can serve
  multiple environments safely.
- **Immutable image tags only.** Every image is tagged with the full commit
  SHA it was built from (`ghcr.io/ammen1/flip-star-backend:<sha>`).
  `latest` is never pushed, never referenced by any manifest, and Argo CD's
  sync is driven by the SHA actually written into `kustomization.yaml`, not
  by polling a registry tag.
- **Vault, not a new secret system.** `infrastructure/secrets/provider.py`
  already resolves every application secret from HashiCorp Vault via
  AppRole (see `docs/secrets.md`), with `hvac` already in
  `requirements.txt`. Kubernetes doesn't need Sealed Secrets or External
  Secrets Operator on top of that — it just needs the one bootstrap
  credential (`VAULT_ROLE_ID` / `VAULT_SECRET_ID`) to reach the pod, which
  is exactly the "bootstrap problem" that doc already anticipates ("option 1
  [response-wrapped secret_id] once CD exists" — CD exists now). See
  `k8s/base/secret.example.yaml`.

## Defects found by deploying this for real

Everything in this section was found by building the images, running them
against a real PostgreSQL, Redis and Vault, and deploying the actual
manifests to a disposable `kind` cluster — not by reading them. Each is
recorded with how it was observed, because several look fine on inspection.

### 1. Every Kubernetes HTTP probe returned 400 (would have CrashLoopBackOff'd)

`k8s/base/deployment.yaml`'s startup/liveness/readiness probes were plain
`httpGet`s. A kubelet probe sends `Host: <pod-ip>:8000` over plain HTTP, and
this application's production settings reject both:

- `ALLOWED_HOSTS` never contains the pod IP (it cannot — pod IPs are assigned
  at schedule time), so Django raises `DisallowedHost` → **400**.
- `SECURE_SSL_REDIRECT=true` makes `SecurityMiddleware` 301-redirect anything
  it considers insecure, before routing.

Measured against the real image and real dependencies:

| Request                         | Result                                     |
| ------------------------------- | ------------------------------------------ |
| no headers (what kubelet sends) | `400` — probe fails                        |
| `Host: localhost` only          | `301` — passes, but never reaches the view |
| `X-Forwarded-Proto: https` only | `400`                                      |
| **both** (the fix)              | `200 {"status":"ok"}`                      |

Fixed by adding `httpHeaders` to all three probes. `Host: localhost` is always
valid because `config/settings/base.py` unconditionally appends
`REQUIRED_HOSTS = ['localhost', '127.0.0.1']` to `ALLOWED_HOSTS`;
`X-Forwarded-Proto: https` satisfies `SECURE_PROXY_SSL_HEADER` so the redirect
is skipped and the probe exercises the real view.

### 2. `ALLOWED_HOSTS` was not set at all — all real traffic would 400

Separate from the probes, and worse: the ConfigMap never set `ALLOWED_HOSTS`,
and `base.py` defaults it to `localhost,127.0.0.1`. Pods would have come up
**green** (probes send `Host: localhost`) while every request arriving through
the Ingress got a bare `400 Bad Request`. Verified directly: with it unset,
`Host: api.uat.flipstar.et` → 400; with it set → 200. It is now a required key in
`k8s/base/configmap.yaml` with a per-environment override in each overlay.

### 3. The production image shipped the entire git history, including secrets

`.dockerignore` did not exclude `.git`, and both Dockerfiles end with
`COPY . .`. The built image therefore contained `/app/.git` (175 MB) — and
`.env` was tracked in this repository's history. Confirmed by extracting
`.git` from a built image and recovering the file: real `SECRET_KEY`,
`DB_PASSWORD`, `ADMIN_PASSWORD`, `ONEVAS_APPLICATION_KEY` and
`TELEBIRR_ORG_OPERATOR_CREDENTIAL` values were readable from it. Anyone able
to pull the image could read them.

`.dockerignore` now excludes `.git`, every `.env*` form, `media/`,
`staticfiles/` and the local database dumps. **The exposed credentials still
need rotating** — see `docs/secrets.md`; this stops the leak recurring, it
does not undo it.

### 4. The Docker `HEALTHCHECK` could never fail

`curl --fail` does not treat a 3xx as failure, and `SECURE_SSL_REDIRECT` made
every request a 301 — so the healthcheck exited 0 regardless of application
state. Measured: `status=301, curl --fail exit 0`. It now sends
`X-Forwarded-Proto: https` and asserts the status is exactly `200`.

### 5. Celery worker probes could never pass — worker restarted every ~7 min

`celery -A config inspect ping` is not a cheap RPC in this codebase: `-A
config` imports `config/__init__.py` → `api.celery` → Django settings, so
**every probe invocation boots Django and performs a full Vault AppRole
login**. Timed inside a running worker pod: **~17.9s per invocation**.

The probes specified `timeoutSeconds: 10` — below the command's own runtime —
so they could never succeed. The worker was killed and restarted in a loop
(startup budget, then three failed liveness probes), which looks exactly like
an application crash loop and is not one. Timeouts are now sized from that
measurement (`timeoutSeconds: 30`, periods spaced so runs cannot overlap).
`Dockerfile.celery`'s own `HEALTHCHECK` had the identical defect and is fixed
the same way.

After the fix: **8 minutes of continuous soak, all three workloads Ready,
worker at zero restarts**, covering more than three full liveness cycles.

### 6. A readiness probe on the worker made things worse (tried, then removed)

Adding a readiness probe with the same command at a 15s period caused
invocations to overlap permanently and pile up Django processes until the
worker was starved out. It was also redundant: when a `startupProbe` is
defined, a container does not report Ready until it first succeeds, which
already provides the "not Ready until actually consuming" guarantee. Removed,
and the reasoning recorded in the manifest so it is not re-added.

### 7. A namespace-wide default-deny NetworkPolicy broke the application

The first version of `k8s/base/networkpolicy.yaml` used `podSelector: {}`. A
NetworkPolicy is evaluated from the perspective of the pod _receiving_ the
connection, so a namespace-wide default-deny-ingress also denied the backend's
connections _into_ an in-namespace PostgreSQL, Redis and Vault — and the
staging overlay points `DB_HOST` at
`postgres.flipstar-staging.svc.cluster.local`. Every pod went into
CrashLoopBackOff with `Failed to resolve 'vault'`; deleting the two policies
fixed it instantly.

This also established that **kind's kindnetd does enforce NetworkPolicy** as of
the v1.31 node image — older kind releases ignored it silently and would have
made the broken policy look fine. The selector is now scoped to
`app.kubernetes.io/part-of: flipstar`.

### 8. Celery beat had no probes; `inspect ping` is wrong for beat

Beat is not a worker and never answers `celery inspect ping` — a beat container
built from `Dockerfile.celery` reports "unhealthy" forever (observed directly).
Beat now has probes based on something it genuinely does: its
`PersistentScheduler` shelve file. Measured against a real beat process, the
file is created at startup and re-synced **every 180s exactly** (celery's
`Scheduler.sync_every = 3 * 60`). The `startupProbe` asserts the file exists
(proving beat opened its schedule DB and the path is writable — the exact
read-only-filesystem failure `--schedule=/tmp/...` exists to avoid); the
`livenessProbe` asserts it is fresher than 900s (5× the measured interval),
catching a beat that is still a live process but has stopped scheduling.
Verified in all three states: live → pass; file backdated 20 minutes → fail;
file removed → fail.

### 9. There was no database migration step at all

Nothing in the deployment ever ran `manage.py migrate`. Pods started and
`/api/v1/health/` returned 200 (it deliberately never touches the database),
while the first request that did touch it failed with
`psycopg2.errors.UndefinedTable: relation "auth_user" does not exist` — a green
rollout against an unmigrated database. Added `k8s/base/job-migrate.yaml`, ordered ahead of
the Deployments by Argo CD sync waves so migrations run to completion before
any Deployment is updated and a failed migration blocks the rollout rather
than half-applying it. (It began as a PreSync hook; see defect 14 for why that
did not survive a first deploy.) `batch/Job` was added to the AppProject
whitelist to permit it.

### 10. The CI pipeline could never build an image

`test-unit` installed `pytest`/`pytest-django`/`pytest-cov` by hand but not
`fakeredis`, which five test modules `import` at module scope. Reproduced by
running that job's exact install set: **5 collection errors,
`ModuleNotFoundError: No module named 'fakeredis'`**. Since `docker-build`
declares `needs: test-unit`, the pipeline could never build or publish
anything. Both test jobs now install `requirements-dev.txt` (which already pins
fakeredis and includes `requirements.txt` via `-r`).

### 11. Trivy scanned only one of the two published images

`push-image` publishes both the API and Celery images; `security-scan` only
scanned the API. The Celery image has its own runtime layer and runs the same
code with the same database and Vault credentials. Both are now scanned, both
blocking on CRITICAL.

### 12. Staging's PodDisruptionBudgets blocked node drains

The base PDBs use `minAvailable: 1` while the staging overlay runs a single
replica — together meaning "never allow the only pod to be evicted", which does
not protect availability, it just hangs `kubectl drain` forever. Staging now
patches them to `maxUnavailable: 1` (JSON 6902, because the two fields are
mutually exclusive and the old one has to be removed).

### 13. Promotion did not check the SHA had actually run in staging

`backend-promote-production.yml` verified the image existed in GHCR and was
signed by CI, but nothing tied it to staging. It now reads the SHA out of
`k8s/overlays/staging/kustomization.yaml` — the record of what staging was last
told to run — and refuses to promote anything else, with an explicit
`allow_unstaged_promotion` input for the legitimate exception (an emergency
rollback to an older known-good SHA). It also now logs in to GHCR first, since
`docker manifest inspect` fails closed on a private package and that reads
misleadingly as "the SHA was never built".

### 14. The migration step could not run at all on a first-ever deploy

Found on the first production sync into a genuinely empty namespace, and only
there — staging had masked it completely, because the resources involved
already existed there from an earlier deploy.

The migration Job was originally an Argo CD **PreSync hook**. Argo CD runs the
entire PreSync phase _before_ the Sync phase, so a PreSync hook cannot
reference anything the Sync phase creates. In a fresh namespace that failed
twice, for two different reasons in succession:

```
pods "flipstar-backend-migrate-" is forbidden: error looking up service
account flipstar-production/flipstar-backend: serviceaccount not found
```

then, after removing the ServiceAccount reference:

```
CreateContainerConfigError: configmap "flipstar-backend-config" not found
```

Each time the Job retried until `backoffLimit` was exhausted and blocked the
sync permanently — on the one deploy where nothing has ever worked before and
the error is hardest to interpret.

**Fixed by replacing the phase hook with sync-wave ordering**, which orders
resources _within_ the Sync phase so they can see each other:

| Wave          | Resources                                                           |
| ------------- | ------------------------------------------------------------------- |
| `-2`          | `ConfigMap`, `ServiceAccount`                                       |
| `-1`          | `Job/flipstar-backend-migrate` — must reach Complete                |
| `0` (default) | `Deployment` ×3, `Service`, PDBs, NetworkPolicies, `Ingress`, `HPA` |

Argo CD waits for each wave to become Healthy before starting the next, and a
Job is Healthy only when it Completes. This keeps the exact property the hook
was chosen for — **a failed migration blocks the rollout rather than
half-applying it** — while removing the phase-ordering trap. The Job also
carries `argocd.argoproj.io/sync-options: Replace=true`, because a Job's
`spec.template` is immutable and a plain apply would fail with "field is
immutable" on the second deploy once the image tag changes.

**The general rule for anything added to this tree later:** prefer sync waves
to PreSync hooks. A PreSync hook may only depend on resources that already
exist or that it creates itself.

### 15. `makemigrations --check` could never pass — migrations were machine-dependent

`Message.media` received a `FileSystemStorage` **instance**. Django serializes
an instance by its constructor arguments, so every migration touching the field
baked in that machine's absolute `settings.MEDIA_ROOT`. The repository still
carries three different developers' paths as proof:

```
FileSystemStorage(base_url='/media/', location='C:\Users\hp\Desktop\selfi_starrr\postworq\selfi_star\backend\media')
FileSystemStorage(base_url='/media/', location='C:\Users\hp\Downloads\Telegram Desktop\postwork\flipstar\backend\media')
FileSystemStorage(base_url='/media/', location='C:\Users\hp\Downloads\Telegram Desktop\postwork\selfi_star\backend\media')
```

That is why `alter_message_media` migrations kept reappearing (0040, 0045,
0046, 0070, 0088, 0097, 0098, 0099…), and why the blocking `django-checks`
gate could never go green: a CI runner's path matches none of them, so Django
always wanted to write another migration.

Fixed by passing a **callable** instead, which Django serializes by reference
(`api.models.messaging.message_media_storage`). Runtime behaviour is
unchanged — it still resolves to `settings.MEDIA_ROOT`/`MEDIA_URL`.
`0101_stabilise_message_media_storage.py` records the one-time change and is
schema-neutral (`storage` is a Django-level attribute, not a column property,
so the `AlterField` emits no DDL).

Verified by running `makemigrations --check --dry-run` from two completely
different working directories: **both now report "No changes detected"**,
where previously each would have produced its own migration.

### 16. A one-off Telebirr payment could never complete

`tests/integration/test_concurrency.py::test_one_off_webhook_does_not_credit_before_debit_confirmed`
failed against real PostgreSQL. The cause was one unreachable branch in the
webhook's JSON payload parser:

```python
tx = request.data.get('TransactionResult') or {}
...
'TransactionID': tx.get('TransactionID') if isinstance(tx, dict) else request.data.get('TransactionID'),
```

`tx` is `... or {}`, so it is **always** a dict and `isinstance(tx, dict)` is
always true — the top-level fallback could never run. A callback carrying a
top-level `TransactionID` parsed as `None`.

That is not cosmetic. `new_mandate_id` is `MandateID or TransactionID`, and it
is what separates Telebirr's _transaction-result_ callback ("the debit
completed — credit the coins") from the _mandate-acceptance_ callback ("now
initiate the debit"). With `TransactionID` lost, a genuine transaction-result
callback fell through to the acceptance branch, re-issued `initiate_debit` for
a payment that had already succeeded, and then marked the mandate `failed`.
Observed end-to-end: the mandate ended `failed` with
`Debit initiation failed: …`, and the user was never credited.

Fixed to `tx.get('TransactionID') or request.data.get('TransactionID')`. Only
the JSON branch is affected — real Telebirr traffic is XML and is handled by
`_parse_telebirr_soap_result` above it. All 11 concurrency tests, and all 298
integration tests, now pass.

### 17. `.env.example` was not a template — it held live credentials

Below roughly line 210 a real production `.env` had been pasted into the
tracked `.env.example`. Verified by hashing its values against the committed
`.env`: `ADMIN_PASSWORD`, `DB_PASSWORD`, `ONEVAS_APPLICATION_KEY`,
`SECRET_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_PUBLIC_KEY` matched
byte-for-byte, and the file additionally carried a full Telebirr RSA private
key and a VAPID EC private key in PEM form.

Because `.dockerignore` re-included it (`!.env.example`), it also shipped
inside every image — so fixing the `.git` leak alone would not have been
enough.

Sanitised: key names and comments kept, every value blanked, and the
`!.env.example` re-include removed. Both rebuilt images now contain **zero**
`.env`-style files and **zero** key material. Every affected credential is on
the ROTATION REQUIRED list.

### 18. CODEOWNERS protected nothing

Every rule was prefixed `/backend/`, left over from before the frontend/mobile
split. There is no `backend/` directory — this repository root _is_ the
backend — so none of the patterns matched, and the payments, security and
migration paths they claim to protect were unowned. Branch protection's
"require review from code owners" would have passed changes to
`api/views/wallet.py` straight through. Paths are now repo-root-relative and
each was verified to exist.

Related: the lint gate's `grep -v '^migrations/'` filter never matched either
(migrations live at `api/migrations/`), and ruff ignores `extend-exclude` for
paths passed explicitly on the command line. A PR touching a generated
migration therefore failed the blocking gate on generated code the project had
deliberately chosen not to lint. Both are fixed — the dead filter is gone and
the gate now passes `--force-exclude`.

## Required GitHub repository configuration

No repository secrets need to be created for the CI/CD workflows themselves
— `GITHUB_TOKEN` (automatic, scoped by the `permissions:` block in each
workflow) covers the GHCR push (`packages: write`), the GitOps commit
(`contents: write`), and cosign's keyless signing (`id-token: write`, no key
material to generate or store). Nothing else is needed unless GHCR's default
visibility is changed to private and the cluster needs its own pull
credential (see below).

| Setting                                  | Where                        | Why                                                                                                                                                                                                                                                                                                                                                                                                |
| ---------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Actions → General → Workflow permissions | Repo settings                | Ensure "Read and write permissions" is enabled, or the `contents: write` step in `update-gitops-staging` / `backend-promote-production.yml` will fail even though the workflow requests it.                                                                                                                                                                                                        |
| Branch protection on `main`              | Repo settings                | Require `backend-ci-cd.yml`'s and `k8s-validate.yml`'s gates to pass before merge, and require a CODEOWNERS review — the pipeline enforces gates on its own runs, but only branch protection stops someone bypassing it via direct push.                                                                                                                                                           |
| **Environments → `staging`**             | Repo settings → Environments | Not required to be protected — `push-image`/`update-gitops-staging` use it mainly so every staging deploy shows up in the repo's Environments tab (which SHA, when, which run). Add required reviewers here too if staging should ever need a gate.                                                                                                                                                |
| **Environments → `production`**          | Repo settings → Environments | **This is what actually makes production promotion a two-person action, not just a two-_step_ one.** Add required reviewers; `backend-promote-production.yml`'s `promote` job (`environment: production`) then pauses for approval before it runs at all — before the GitOps commit, before Argo CD ever sees a diff. Without this configured, `environment: production` is present but toothless. |
| `.github/CODEOWNERS`                     | This repo, already added     | Every owner in it is a `@REPLACE-ME-*` placeholder — replace with real GitHub usernames/teams before branch protection's "require review from code owners" has any effect. An unfilled CODEOWNERS file is silently inert, not an error.                                                                                                                                                            |
| `.github/dependabot.yml`                 | This repo, already added     | Nothing to configure — Dependabot is enabled by the file's presence. It keeps `requirements.txt`, the pinned Action SHAs, and both Dockerfiles' base image current on a weekly schedule.                                                                                                                                                                                                           |

## Required cluster / Argo CD configuration

1. **Argo CD installed**, with access to `https://github.com/Ammen1/flip-star.git` (public repo — no credential needed for reads).
2. **ingress-nginx** and **cert-manager** installed cluster-wide, with a `ClusterIssuer` named `letsencrypt-prod` (referenced by `k8s/overlays/*/ingress.yaml`). Neither is part of this Kustomize tree — they're cluster add-ons, not per-application resources.
   `k8s/base/networkpolicy.yaml` selects the controller by the
   `kubernetes.io/metadata.name` label on its namespace. Kubernetes sets that
   label automatically on every namespace, so this works out of the box _if_
   the controller really is in a namespace called `ingress-nginx` — confirm
   with `kubectl get pods -A | grep ingress` and update the policy if not. A
   wrong value here drops all API traffic silently rather than failing loudly.
   Also confirm the CNI actually enforces NetworkPolicy (Calico, Cilium, and
   recent kindnet do; some managed clusters ship without enforcement, in which
   case the policies apply cleanly and do nothing).
3. Apply the project once, out of band (not part of either Application's own sync, since an AppProject isn't itself an Application-managed resource):
   ```bash
   kubectl apply -f argocd/project.yaml
   ```
4. Register both Applications:
   ```bash
   kubectl apply -f argocd/application-staging.yaml
   kubectl apply -f argocd/application-production.yaml
   ```
   **Know this before you ever delete either Application.** Both carry the
   `resources-finalizer.argocd.argoproj.io` finalizer, and both manage their
   own `namespace.yaml` as part of their source. Confirmed directly in
   disposable-cluster testing: `kubectl delete application
flipstar-backend-staging` cascades through that finalizer to delete the
   _entire_ `flipstar-staging` namespace -- not just the resources Argo CD
   created, but everything in it, including anything else running there.
   This may be exactly what you want (tearing down an environment), but it's
   easy to trigger by accident while just trying to reset a stuck Application,
   so treat deleting either Application as equivalent to deleting its whole
   namespace.
5. **Create the Vault AppRole bootstrap Secret in each namespace** (see `k8s/base/secret.example.yaml` for the full rationale and the better long-term alternative):
   ```bash
   kubectl create namespace flipstar-staging      # or let Argo CD's namespace.yaml create it on first sync
   kubectl create secret generic flipstar-backend-vault-approle \
     --namespace flipstar-staging \
     --from-literal=VAULT_ROLE_ID='<role_id>' \
     --from-literal=VAULT_SECRET_ID='<secret_id>'
   # repeat for flipstar-production with that environment's AppRole credentials
   ```
   Without this Secret, both Deployments will fail to start — `VAULT_REQUIRED=true` in `configmap.yaml` makes a missing/unreachable Vault credential a hard startup failure by design (see `infrastructure/health/startup.py`), not a silent fallback to broken config.
6. **Resolve every `CHANGEME` value** — see the dedicated section below for the complete list and what each must be set to. The placeholders live in `k8s/overlays/*/patches/configmap-patch.yaml`, `k8s/overlays/production/ingress.yaml` and `k8s/base/networkpolicy.yaml`, and are placeholders — this project's only confirmed live domain today is `api.uat.flipstar.et` (used as-is for the staging overlay); production has no confirmed domain yet.

## Operational note: the Celery probe is expensive, and it scales with replicas

This is not a defect, but it is a property of this deployment that will bite in
production if nobody knows about it.

The Celery worker's startup and liveness probes run
`celery -A config inspect ping`. `-A config` imports `config/__init__.py` →
`api.celery` → Django settings, so **every single probe invocation**:

1. boots Django,
2. performs DNS lookups for Vault, PostgreSQL and Redis, and
3. performs a **full Vault AppRole login**.

Measured inside a running worker: **~17.9s per invocation**.

The load therefore multiplies by replica count:

| Environment | Worker replicas | Liveness period | Vault logins/min from probes alone |
| ----------- | --------------- | --------------- | ---------------------------------- |
| Staging     | 1               | 120s            | ~0.5                               |
| Production  | 3               | 120s            | ~1.5                               |

Two consequences worth planning for:

- **Vault AppRole `secret_id_num_uses` must not be set low.** If the AppRole is
  issued with a bounded use count, probe traffic will exhaust it and every pod
  will fail to start at the next restart. Issue the production AppRole with
  `secret_id_num_uses=0` (unlimited) or a generously high value, and monitor
  Vault's auth request rate after rollout.
- **Probe frequency is a real infrastructure knob**, not just a liveness
  setting. Do not shorten `periodSeconds` without accounting for the extra
  Vault and DNS load it creates across all replicas.

Observed directly during validation: with 3 worker replicas in a single-node
disposable cluster, the probes' own DNS lookups began failing intermittently
(`Failed to resolve 'vault...': Temporary failure in name resolution`) under
exactly this contention, while the worker processes themselves were healthy
and consuming from the broker the whole time (`transport:
redis://...:6379/0`, `celery@flipstar-celery-worker-...` registered). A plain
busybox pod in the same namespace resolved 10/10 concurrently. The disposable
cluster's CoreDNS was forwarding to an unreachable upstream, which amplified
it — but the underlying cost is real and is carried into any cluster.

If this proves noisy in a real deployment, the durable fix is to make the
health check cheap rather than to loosen the probe: a small script that checks
the worker's broker heartbeat directly, without importing Django settings and
without re-authenticating to Vault.

### Verdict: acceptable for production, with one condition

The probe was re-examined at handoff because it looked like it was failing.
The conclusion is that **the probe itself is sound and is acceptable for
production**, provided the cluster has working DNS. The evidence:

In the disposable cluster the worker showed 15 restarts and
`celery inspect ping` failed 9 times out of 10 by hand — while the worker was
genuinely healthy and consuming (a passing run returns `pong`, `1 node
online`). The cause is not the probe:

| Resolution mode                                                          | Result                        |
| ------------------------------------------------------------------------ | ----------------------------- |
| `AF_INET` (A records only), 8 attempts                                   | **8 ok, 0 fail, 0.0s total**  |
| `AF_UNSPEC` (A **and** AAAA — what `getaddrinfo`/kombu uses), 8 attempts | **5 ok, 3 fail, 41.3s total** |

The disposable cluster's CoreDNS forwards to an unreachable upstream
(192.168.65.254 — Docker Desktop's resolver), so every AAAA lookup stalls for
seconds and often fails outright. 30 upstream `i/o timeout` entries appeared in
CoreDNS's log in a 10-minute window. The long-lived worker process is immune —
it resolved Redis once at startup and holds the connection — but the probe
spawns a fresh process that must resolve from scratch every time, so it takes
the full brunt.

A production cluster with functioning DNS does not have this failure mode.
Raising the timeout would not have helped and was not done: the probe was not
timing out, it was getting `Temporary failure in name resolution`.

**The condition:** because each invocation boots Django, resolves DNS and
performs a **full Vault AppRole login**, any DNS or Vault degradation is
amplified into worker restarts — an infrastructure blip becomes a restart
storm across every replica. Two consequences, both already covered above:
issue the AppRole with `secret_id_num_uses=0`, and do not shorten
`periodSeconds` without accounting for the multiplied load.

### Recommended hardening (proposed, NOT applied)

Deliberately not applied — the failure mode traced to cluster DNS, not to the
manifests, and the audit's standing instruction is to avoid changes that are
not required by a verified blocker. Apply it if the amplification risk above is
judged unacceptable for the target cluster:

```yaml
# k8s/base/deployment-celery-worker.yaml, livenessProbe
failureThreshold: 5 # currently 3
```

At `periodSeconds: 120` that changes the restart trigger from 6 minutes of
sustained failure to 10. A genuinely wedged worker fails _every_ probe and is
still restarted; a transient DNS or Vault blip no longer kills healthy workers.
This is a threshold change, not a timeout increase — it does not extend how
long any single probe is allowed to run.

### Celery beat remains a singleton

Unchanged and verified in the rendered production manifest: `replicas: 1` with
`strategy: Recreate`. `replicas: 1` alone is not enough — a RollingUpdate
briefly runs old and new pods together, which is two beat processes, and every
periodic task would double-fire. `Recreate` guarantees the old pod is fully
gone first, trading a short scheduling gap for the singleton guarantee. There
is deliberately no PDB and no HPA for beat.

---

## Every CHANGEME value, and what it must be set to

> A fuller, per-row version of this — every value marked **KNOWN**,
> **UNKNOWN** or **REQUIRES INFRASTRUCTURE INPUT** — is in
> [`k8s/PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md). The leaked
> credentials that must be rotated are in
> [`k8s/ROTATION_REQUIRED.md`](ROTATION_REQUIRED.md).

Nothing here is invented. Where this project has no confirmed value (it has no
production domain today — `api.uat.flipstar.et` is the only live host), the
placeholder is left as `CHANGEME` deliberately rather than filled with a guess.
**The deployment will not work correctly until every row below is resolved.**

### Staging — `k8s/overlays/staging/patches/configmap-patch.yaml`

| Key             | Current value                                 | Action                                                                                                      |
| --------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `ALLOWED_HOSTS` | `api.uat.flipstar.et`                         | Confirm this is the host the Ingress serves. A mismatch means **every request returns 400** (see defect 2). |
| `DB_HOST`       | `postgres.flipstar-staging.svc.cluster.local` | Point at the real managed Postgres, or deploy one into the namespace.                                       |
| `REDIS_HOST`    | `redis.flipstar-staging.svc.cluster.local`    | Same.                                                                                                       |
| `VAULT_ADDR`    | `https://vault.internal:8200`                 | Real staging Vault address.                                                                                 |

### Production — `k8s/overlays/production/patches/configmap-patch.yaml`

| Key                    | Placeholder                                   | Action                                               |
| ---------------------- | --------------------------------------------- | ---------------------------------------------------- |
| `ALLOWED_HOSTS`        | `CHANGEME-production-backend-domain`          | **Required.** The production backend hostname.       |
| `DB_HOST`              | `CHANGEME-production-postgres-host`           | Production PostgreSQL host.                          |
| `REDIS_HOST`           | `CHANGEME-production-redis-host`              | Production Redis host.                               |
| `CORS_ALLOWED_ORIGINS` | `https://CHANGEME-production-frontend-domain` | The frontend origin (deployed separately to Vercel). |
| `CSRF_TRUSTED_ORIGINS` | `https://CHANGEME-production-frontend-domain` | Same origin as above.                                |
| `BACKEND_URL`          | `https://CHANGEME-production-backend-domain`  | Public backend URL.                                  |
| `VAULT_ADDR`           | `https://CHANGEME-production-vault-addr:8200` | Production Vault address.                            |

### Production — `k8s/overlays/production/ingress.yaml`

| Field                                         | Placeholder                          | Action                                              |
| --------------------------------------------- | ------------------------------------ | --------------------------------------------------- |
| `spec.tls[0].hosts[0]` / `spec.rules[0].host` | `CHANGEME-production-backend-domain` | Real domain. Must match `ALLOWED_HOSTS`.            |
| `spec.tls[0].secretName`                      | `flipstar-production-tls`            | Match the cluster's cert-manager naming convention. |
| `cert-manager.io/cluster-issuer`              | `letsencrypt-prod`                   | Must name a `ClusterIssuer` that actually exists.   |

### Base — `k8s/base/configmap.yaml`

Values here are overridden per environment, but two are worth checking
directly: `VAPID_SUBJECT` (`mailto:admin@flipstar.et`) and the Telebirr
non-secret settings (`TELEBIRR_PAYEE_ACCOUNT_NAME`, `TELEBIRR_CALLER_TYPE`).
Every Telebirr _credential_ comes from Vault, not from here.

### Base — `k8s/base/networkpolicy.yaml`

| Field                                               | Placeholder     | Action                                                                                                 |
| --------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------ |
| `namespaceSelector` → `kubernetes.io/metadata.name` | `ingress-nginx` | The namespace the ingress controller actually runs in. Wrong value = all API traffic silently dropped. |
| `ipBlock.cidr`                                      | `10.0.0.0/8`    | The cluster's node CIDR, for kubelet probe traffic. Narrow it to the real node subnet.                 |

### Secrets that must exist in Vault before first deploy

The bootstrap Secret (`flipstar-backend-vault-approle`) is the only credential
Kubernetes holds. Everything else is read from Vault at
`VAULT_SECRET_PATH` (`flipstar/backend/staging` and
`flipstar/backend/production`) by `infrastructure/secrets/provider.py`.
Minimum keys, from `config/settings/production.py`'s own validation:

- `SECRET_KEY` — must not be a development default, or the process refuses to start.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD` — all validated non-empty.
- Integration credentials (warn, not fatal, if absent): `TELEBIRR_*`
  (SOAP URL, third-party id/password, SP operator id/credential, fabric app
  id, app secret, merchant app id, merchant code, private/public key). OneVAS
  has been removed; no `ONEVAS_*` key is read any more.

### Credential rotation still outstanding

`.env` was tracked in this repository's history and its contents are
recoverable from any clone (and were, until this change, baked into the
published image — see defect 3). **`SECRET_KEY`, `DB_PASSWORD`,
`ADMIN_PASSWORD`, the VAPID keypair, and the Telebirr/Onevas credentials must
be rotated.** Untracking the file and fixing `.dockerignore` stops the leak
from continuing; neither undoes the exposure.

## Staging readiness

The staging overlay contains **no `CHANGEME` placeholders** — verified against
the rendered output. Four values are nonetheless assumptions that must be
confirmed against the real cluster before first deploy, and none of them can be
guessed from this repository.

### Values that must be supplied or confirmed

| Value                                                                             | Current                                       | State                             | Action                                                                                                                         |
| --------------------------------------------------------------------------------- | --------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` / `BACKEND_URL` | `api.uat.flipstar.et`                         | `[KNOWN]`                         | Confirm this is the host the staging ingress serves. **Must equal the ingress host** or every request returns `400`.           |
| `DB_HOST`                                                                         | `postgres.flipstar-staging.svc.cluster.local` | `[REQUIRES INFRASTRUCTURE INPUT]` | An in-cluster service name. Correct only if PostgreSQL really runs in that namespace; otherwise point at the managed instance. |
| `REDIS_HOST`                                                                      | `redis.flipstar-staging.svc.cluster.local`    | `[REQUIRES INFRASTRUCTURE INPUT]` | Same.                                                                                                                          |
| `VAULT_ADDR`                                                                      | `https://vault.internal:8200`                 | `[REQUIRES INFRASTRUCTURE INPUT]` | Placeholder hostname, never verified to resolve. **This is the one value most likely to be wrong.**                            |
| Ingress controller namespace                                                      | `ingress-nginx`                               | `[REQUIRES INFRASTRUCTURE INPUT]` | `k8s/base/networkpolicy.yaml`. A wrong value silently drops all API traffic.                                                   |
| Node CIDR                                                                         | `10.0.0.0/8`                                  | `[REQUIRES INFRASTRUCTURE INPUT]` | `k8s/base/networkpolicy.yaml`. Allows kubelet probe traffic; narrow it.                                                        |
| `flipstar-staging-tls` / `letsencrypt-prod`                                       | as named                                      | `[REQUIRES INFRASTRUCTURE INPUT]` | Must match the cluster's cert-manager conventions.                                                                             |

Everything else is settled: `VAULT_SECRET_PATH=flipstar/backend/staging`,
`VAULT_REQUIRED=true`, `VAULT_KV_MOUNT=secret`, `DEBUG=False`,
`SECURE_SSL_REDIRECT=true`, and both images pinned to a commit-SHA tag that CI
rewrites (never `latest`).

### Staging must not reuse the compromised credentials

Staging reads from `flipstar/backend/staging` in Vault. Populate it with
**freshly rotated** values, not the ones listed in
[`ROTATION_REQUIRED.md`](ROTATION_REQUIRED.md). Reusing a compromised
`SECRET_KEY` or `DB_PASSWORD` in staging keeps the exposure live and gives an
attacker a foothold adjacent to production.

### First staging deploy

```bash
# 1. Confirm the values in the table above, then edit:
#      k8s/overlays/staging/patches/configmap-patch.yaml   (VAULT_ADDR, DB_HOST, REDIS_HOST)
#      k8s/base/networkpolicy.yaml                          (ingress namespace, node CIDR)

# 2. Namespace and the one bootstrap credential (never in Git)
kubectl create namespace flipstar-staging
kubectl create secret generic flipstar-backend-vault-approle \
  --namespace flipstar-staging \
  --from-literal=VAULT_ROLE_ID='<role_id>' \
  --from-literal=VAULT_SECRET_ID='<secret_id>'

# 3. Populate Vault at flipstar/backend/staging with ROTATED values
#    Minimum: SECRET_KEY, DB_NAME, DB_USER, DB_PASSWORD

# 4. Register the project and the staging Application
kubectl apply -f argocd/project.yaml
kubectl apply -f argocd/application-staging.yaml

# 5. Staging auto-syncs. Watch it land:
argocd app get flipstar-backend-staging
kubectl -n flipstar-staging get job flipstar-backend-migrate   # must reach Complete
kubectl -n flipstar-staging get deploy                          # 1/1, 1/1, 1/1

# 6. Verify through the ingress
curl -sS https://api.uat.flipstar.et/api/v1/health/        # {"status":"ok"}
curl -sS https://api.uat.flipstar.et/api/v1/health/deep/   # database block populated
```

From then on, every push to `main` that passes CI updates the staging overlay
automatically and Argo CD syncs it — no manual step.

---

## Production Handoff

Everything required to take this from "validated in a disposable cluster" to
"running in production", separated by who has to do it.

Two companion documents are authoritative and referenced throughout:

- [`k8s/ROTATION_REQUIRED.md`](ROTATION_REQUIRED.md) — the compromised-credential checklist.
- [`k8s/PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md) — every configuration value and its state.

---

### A. Security actions

**INFRASTRUCTURE/SECURITY OWNER ACTION REQUIRED** — none of this can be done
from the repository, and no replacement values may be committed.

1. **Rotate every credential in `ROTATION_REQUIRED.md`.** They are recoverable
   from git history by anyone with a clone (`git log --all -- .env`), and were
   shipped inside published images until `.dockerignore` was fixed. Rotation is
   what makes them worthless; nothing in this repo can substitute for it.
   Covers: three `SECRET_KEY`s, three `DB_PASSWORD`s, the VAPID keypair, the
   Telebirr RSA private key, ten Telebirr credentials, `ADMIN_PASSWORD`,
   `CRM_ACCESS_PASSWORD`, `SECRET_ACCESS_KEY`, and four Onevas application keys.
2. **Check whether a superuser was ever created with the leaked
   `ADMIN_PASSWORD`.** If so, rotate that account's password too.
3. **Decide on history rewrite.** `git filter-repo` or repository re-creation
   removes the values from history. Rotation is the part that matters; this is
   a separate, disruptive decision.

**CODE FIX REQUIRED** — repository changes, owned by the application team, not
done here:

4. **Move the four hardcoded Onevas application keys into Vault.** They live in
   `api/migrations/0057_create_subscription_tiers.py` and
   `scripts/populate_subscription_tiers.py`. See "Onevas keys in an applied
   migration" below for why they were not touched and how to do it safely.
   Once done, delete the two path entries from `.gitleaks.toml`.

---

### B. Infrastructure values required

Every value is enumerated with its state in
[`PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md). Summary of what is
**not** known and must be supplied:

| Value                                              | Where                                                                                                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Production backend domain                          | production `configmap-patch.yaml` (`ALLOWED_HOSTS`, `BACKEND_URL`) **and** `ingress.yaml` (`tls.hosts`, `rules.host`) — these must match exactly |
| Production frontend origin                         | production `configmap-patch.yaml` (`CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`)                                                               |
| Production `DB_HOST` / `REDIS_HOST` / `VAULT_ADDR` | production `configmap-patch.yaml`                                                                                                                |
| Staging `DB_HOST` / `REDIS_HOST` / `VAULT_ADDR`    | staging `configmap-patch.yaml` (currently in-cluster service names / a placeholder Vault host)                                                   |
| Ingress controller namespace                       | `k8s/base/networkpolicy.yaml` `namespaceSelector`                                                                                                |
| Node CIDR                                          | `k8s/base/networkpolicy.yaml` `ipBlock.cidr`                                                                                                     |
| `ClusterIssuer` name and TLS secret names          | both `ingress.yaml`                                                                                                                              |
| CODEOWNERS owners                                  | `.github/CODEOWNERS` (every entry is `@REPLACE-ME-*`)                                                                                            |
| `production` environment reviewers                 | GitHub → Settings → Environments                                                                                                                 |

**`ALLOWED_HOSTS` must equal the ingress host.** A mismatch does not fail
loudly — pods stay green (probes use `Host: localhost`) while every real
request returns a bare `400`. This was defect 2; do not reintroduce it.

---

### C. Vault setup

Paths are fixed by `k8s/overlays/*/patches/configmap-patch.yaml` and verified
against `infrastructure/secrets/provider.py`:

```
flipstar/backend/staging
flipstar/backend/production
```

KV v2 at mount `secret` (`VAULT_KV_MOUNT`).

**Required keys** — `config/settings/production.py::_validate()` refuses to
start without these:

```
SECRET_KEY        # rejected if it matches a known development default
DB_NAME
DB_USER
DB_PASSWORD
```

**Integration credentials** — absent values produce a startup warning, not a
failure, so an integration can be deliberately disabled: `TELEBIRR_*` (SOAP
URL, third-party id/password, SP operator id/credential, fabric app id, app
secret, merchant app id, merchant code, private/public key), `TIMWE_*`, plus
the `TELEBIRR_B2C_*` / `TELEBIRR_USSD_*` / `CRM_*` families, `VAPID_*`,
`EMAIL_*`, and the object-storage keys.

**AppRole.** The one bootstrap credential Kubernetes holds. Create it per
namespace, out of band — it is never in Git and never managed by Argo CD
(`Secret` is deliberately absent from the AppProject whitelist, verified):

```bash
kubectl create secret generic flipstar-backend-vault-approle \
  --namespace flipstar-production \
  --from-literal=VAULT_ROLE_ID='<role_id>' \
  --from-literal=VAULT_SECRET_ID='<secret_id>'
```

**Issue the AppRole with `secret_id_num_uses=0`.** The Celery probe
re-authenticates to Vault on every invocation (see the probe-cost note above).
A bounded use count will be exhausted and every pod will fail to start on its
next restart.

---

### D. GitHub environment protection

| Setting                                            | Where                                | Why                                                                                                                                                                                  |
| -------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Required reviewers on the `production` environment | Settings → Environments → production | **This is what makes promotion a two-person action.** Without it, `environment: production` in `backend-promote-production.yml` is a label with no effect.                           |
| Branch protection on `main`                        | Settings → Branches                  | Require `backend-ci-cd.yml` and `k8s-validate.yml` to pass, and require code-owner review. The pipeline gates its own runs; only branch protection stops a direct push bypassing it. |
| Workflow permissions: "Read and write"             | Settings → Actions → General         | The `contents: write` steps in `update-gitops-staging` and the promotion workflow fail without it, even though the workflow requests it.                                             |
| Fill in `.github/CODEOWNERS`                       | Repository                           | Every owner is `@REPLACE-ME-*`. An unfilled CODEOWNERS is silently inert — code-owner review protects nothing until real owners are set.                                             |

No repository secrets are required: `GITHUB_TOKEN` covers the GHCR push
(`packages: write`), the GitOps commit (`contents: write`) and cosign keyless
signing (`id-token: write`).

---

### E. TLS / Ingress requirements — **NOT VALIDATED**

Neither an ingress controller nor cert-manager exists in the disposable
cluster (verified absent: 0 ingress controller pods, and the `clusterissuer`
resource type is not registered). What **is** validated: both `Ingress`
resources render, pass `kubeconform -strict`, and are accepted by a real API
server. What is **not**: that any request ever traverses them.

Prerequisites:

1. **ingress-nginx** installed, with `ingressClassName: nginx` matching.
2. **cert-manager** installed, with a `ClusterIssuer` whose name matches the
   `cert-manager.io/cluster-issuer` annotation (currently `letsencrypt-prod`).
3. **DNS** A/AAAA record for the production domain pointing at the ingress
   load balancer's external address.
4. `k8s/base/networkpolicy.yaml`'s `namespaceSelector` must name the namespace
   the controller actually runs in — a wrong value **silently drops all API
   traffic** rather than failing loudly.

**Production validation procedure** — run in order, stop at the first failure:

```bash
# 1. DNS resolves to the load balancer
dig +short <production-domain>
kubectl -n ingress-nginx get svc -o wide          # compare EXTERNAL-IP

# 2. Ingress has been assigned that address
kubectl -n flipstar-production get ingress flipstar-backend
#    ADDRESS must be populated, not empty

# 3. Ingress controller accepted the resource
kubectl -n ingress-nginx logs deploy/ingress-nginx-controller | grep flipstar

# 4. TLS certificate actually issued
kubectl -n flipstar-production get certificate
kubectl -n flipstar-production describe certificate flipstar-production-tls
#    Ready must be True; check the Order/Challenge if not

# 5. TLS terminates and the chain is valid
openssl s_client -connect <production-domain>:443 -servername <production-domain> </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

# 6. End to end: DNS -> LB -> controller -> Service -> Pod -> app
curl -sS -o /dev/null -w 'status=%{http_code}\n' https://<production-domain>/api/v1/health/
#    expect 200

curl -sS https://<production-domain>/api/v1/health/
#    expect {"status":"ok"}

# 7. HTTP redirects to HTTPS (ssl-redirect annotation)
curl -sS -o /dev/null -w 'status=%{http_code}\n' http://<production-domain>/api/v1/health/
#    expect 308

# 8. Service endpoints are populated (rules out a selector mismatch)
kubectl -n flipstar-production get endpoints flipstar-backend
```

If step 6 returns **400**, `ALLOWED_HOSTS` does not match the domain — see
section B.

---

### F. Production deployment procedure

Prerequisite: everything in A–E complete.

```bash
# 1. Cluster prerequisites, once
kubectl apply -f argocd/project.yaml
kubectl create namespace flipstar-production
kubectl create secret generic flipstar-backend-vault-approle \
  --namespace flipstar-production \
  --from-literal=VAULT_ROLE_ID='<role_id>' \
  --from-literal=VAULT_SECRET_ID='<secret_id>'
kubectl apply -f argocd/application-production.yaml

# 2. Confirm the SHA you intend to promote is what staging is running
grep -A2 'flip-star-backend$' k8s/overlays/staging/kustomization.yaml

# 3. Promote (GitHub → Actions → "Promote Backend to Production" →
#    Run workflow → paste the full 40-character commit SHA)
#    The workflow verifies, in order:
#      - the SHA is a real 40-char commit SHA
#      - both images exist in GHCR
#      - both carry a valid cosign signature from this repo's CI
#      - the SHA matches what the staging overlay is running
#    then rewrites k8s/overlays/production/kustomization.yaml and commits.
#    It NEVER rebuilds an image.

# 4. Argo CD now shows OutOfSync. Nothing has deployed.
argocd app get flipstar-backend-production

# 5. A human syncs. This is the second deliberate gate.
argocd app sync flipstar-backend-production
```

Sync order is enforced by sync waves: wave `-2` ConfigMap + ServiceAccount,
wave `-1` the migration Job (must reach Complete), wave `0` the workloads. **A
failed migration blocks the rollout rather than half-applying it.**

---

### G. Rollback procedure

Rollback is a git operation. **The image is never rebuilt** — the previous
immutable SHA is still in GHCR.

```bash
# Find the promotion commit
git log --oneline -- k8s/overlays/production/kustomization.yaml

# Revert it
git revert <promotion-commit-sha>
git push origin main

# Production is manual-sync, so a human must still sync
argocd app sync flipstar-backend-production
```

Staging auto-syncs on the revert with no further action.

**Database migrations do not roll back.** Reverting the GitOps commit restores
the image, not the schema. If the bad release included a migration, reverse it
deliberately — check `kubectl -n flipstar-production logs job/flipstar-backend-migrate`
for what was applied.

---

### H. Post-deployment verification

```bash
# Sync completed and healthy
argocd app get flipstar-backend-production

# Migration completed
kubectl -n flipstar-production get job flipstar-backend-migrate
kubectl -n flipstar-production logs job/flipstar-backend-migrate | tail -20

# All workloads Ready at expected replica counts (3 / 3 / 1)
kubectl -n flipstar-production get deploy

# No bad pod states
kubectl -n flipstar-production get pods
#   expect no CrashLoopBackOff, no ImagePullBackOff

# The exact promoted SHA is what is running
kubectl -n flipstar-production get deploy flipstar-backend \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# Celery beat is EXACTLY one replica (two would double-fire every periodic task)
kubectl -n flipstar-production get deploy flipstar-celery-beat \
  -o jsonpath='{.spec.replicas}{"\n"}'

# Health through the real ingress path
curl -sS https://<production-domain>/api/v1/health/          # {"status":"ok"}
curl -sS https://<production-domain>/api/v1/health/deep/      # database block populated

# Vault authenticated (not falling back to defaults)
kubectl -n flipstar-production logs deploy/flipstar-backend | grep -i vault
#   expect "Authenticated to Vault via AppRole"
```

---

### I. Emergency rollback

When production is broken and you need it working now, in preference order.

**Fastest — Argo CD history, no commit needed:**

```bash
argocd app history flipstar-backend-production
argocd app rollback flipstar-backend-production <history-id>
```

Then land the git revert afterwards so Git and the cluster agree — otherwise
the next sync re-applies the bad version.

**If Argo CD is unavailable**, roll the Deployment back directly. This is
drift and Argo CD will revert it on the next sync, so treat it as a stopgap
and follow with the git revert:

```bash
kubectl -n flipstar-production rollout undo deploy/flipstar-backend
kubectl -n flipstar-production rollout status deploy/flipstar-backend
```

**If the migration is the problem**, the image rollback will not help — the
schema has already changed. Reverse the migration deliberately:

```bash
kubectl -n flipstar-production logs job/flipstar-backend-migrate   # what was applied
kubectl -n flipstar-production run migrate-rollback --rm -it \
  --image=<the-previous-good-image-sha> --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"m","image":"<sha>","command":["python","manage.py","migrate","api","<previous-migration>"],"envFrom":[{"configMapRef":{"name":"flipstar-backend-config"}},{"secretRef":{"name":"flipstar-backend-vault-approle"}}]}]}}'
```

Not every migration is reversible. Check the migration before relying on this.

**Do not** delete the Argo CD Application to "reset" it. Both Applications
carry the `resources-finalizer` and manage their own `namespace.yaml`, so
deleting one cascades to deleting the entire namespace — confirmed by accident
during testing.

---

### Onevas keys in an applied migration

`api/migrations/0057_create_subscription_tiers.py` embeds four real Onevas
application keys, one byte-identical to the leaked `ONEVAS_APPLICATION_KEY`.
**They were deliberately not removed.**

**The risk of editing it:** migrations are applied history. Any environment
that has already run `0057` has it recorded in `django_migrations`; rewriting
the file changes what the code says was applied without changing what actually
was. Fresh databases would then build differently from existing ones — the
classic source of "works on staging, fails in production" schema drift. Editing
it also does not remove the values from git history, so it buys no security.

**Correct remediation, in order:**

1. **Rotate the four keys with Onevas first.** This is what actually closes the
   exposure. Everything below is cleanup.
2. **Write the new keys to Vault** at `flipstar/backend/<environment>`.
3. **Add a new forward migration** (e.g. `0102_onevas_keys_from_vault`) that
   updates the existing rows to read from configuration rather than carrying
   literals. Do not edit `0057`.
4. **Change `scripts/populate_subscription_tiers.py`** to read the keys from
   `infrastructure.secrets.secret()` instead of hardcoding them. This file is a
   seeding script, not applied history, so it can be edited freely — but it
   changes what new environments seed, so it needs the application team's
   review.
5. **Delete the two path entries from `.gitleaks.toml`** and confirm the
   blocking secret-scan gate still passes.

Until step 1 is done, treat all four keys as compromised regardless of what the
repository looks like.

---

## Rollback

Because this is GitOps, rollback is a git operation, not a cluster
operation:

```bash
# Staging (auto-syncs the moment the revert lands on main):
git revert <bad-gitops-commit-sha>
git push origin main

# Production (still requires the manual sync step even after reverting):
git revert <bad-gitops-commit-sha>
git push origin main
argocd app sync flipstar-backend-production
```

Alternatively, roll back through Argo CD directly without a new commit —
useful when you need to be live again _now_ and can commit the git-level
revert afterward:

```bash
argocd app history flipstar-backend-production
argocd app rollback flipstar-backend-production <history-id>
```

Note this only reverts what Kubernetes knows about (the image tag and any
manifest changes). **Database migrations do not roll back.** If the bad
release included one, check what was applied and reverse it deliberately —
see `docs/deployment.md`'s "Rollback" section, which already covers
this for the current docker-compose deployment and applies unchanged here
(same database, same Django app, same `manage.py migrate` mechanics).

## Validation performed

The whole chain was exercised, not just rendered. What follows separates what
was actually run from what could not be.

### Static

- `kustomize build k8s/overlays/staging` and `.../production` both render
  cleanly — 13 and 14 resources respectively (Namespace, ServiceAccount,
  ConfigMap, migrate Job, 3 Deployments, Service, 2 PDBs, 2 NetworkPolicies,
  Ingress, plus HPA for production only).
- Every workflow YAML parses, and each job's `needs:`/`outputs` references
  resolve to a job actually declared.
- No `:latest` tag appears anywhere in either rendered overlay.

### Docker

- Both images build from the current Dockerfiles.
- The API image was run against real PostgreSQL 15, Redis 7 and a real Vault
  (AppRole auth) under `config.settings.production`. Startup log confirms
  `Authenticated to Vault via AppRole`, `Loaded 5 secrets from Vault`,
  `Redis: reachable`, keypair initialised, `Listening on TCP address
0.0.0.0:8000`.
- Verified the built image contains no `.git`, no `.env`, and an empty
  `/app/media` (see defect 3).

### Application endpoints

- `/api/v1/health/` → `200 {"status":"ok"}` (with the probe headers).
- `/api/v1/health/deep/` → `200`, reporting the live PostgreSQL connection:
  `{"engine":"django.db.backends.postgresql","name":"flipstar","host":"postgres"}`.
- Host-header rejection still works correctly: `Host: evil.example.com` → 400.

### Kubernetes (disposable `kind` v1.31 cluster)

- All three workloads reach `1/1 Running`: `flipstar-backend`,
  `flipstar-celery-worker`, `flipstar-celery-beat`.
- **8-minute soak with zero restarts** on the worker after the probe-timeout
  fix, covering more than three full liveness cycles.
- The `flipstar-backend-migrate` PreSync Job completes, applying the full
  migration set (`Applying sessions.0001_initial... OK`, etc.).
- Service → Pod routing verified through the ClusterIP.
- PostgreSQL, Redis and Vault connectivity all confirmed from inside the
  cluster, through the real manifests.
- Startup, liveness and readiness probes verified working — and verified
  _failing correctly_ before the fix (see defects 1, 5, 8).
- No `CrashLoopBackOff` and no `ImagePullBackOff` in the final state.

### Argo CD

Validated against a real Argo CD v2.13.2 install in the disposable cluster,
using the actual `argocd/*.yaml` manifests (only `repoURL` was repointed at an
in-cluster Git daemon, since the cluster cannot reach GitHub):

- AppProject destination enforcement: pointing an Application at `kube-system`
  is rejected — `application destination ... namespace 'kube-system' do not
match any of the allowed destinations`.
- AppProject resource-kind enforcement: a `Secret` added to the overlay fails
  sync with `resource :Secret is not permitted in project flipstar-backend`.
- Staging automated sync: a commit is detected and applied without
  intervention.
- Production manual sync: after the same GitOps change, production stays
  `OutOfSync` / `Missing` with nothing applied.
- Image promotion: the exact SHA committed is the exact tag running, confirmed
  via `kubectl get pod -o jsonpath='{...image}'`.
- Rollback: `git revert` of the promotion commit restores the previous image
  tag, reusing the already-built image with no rebuild.

### Not validated, and why

- **TLS / cert-manager.** `[NOT VALIDATED]` No `ClusterIssuer` CRD is even
  registered in the disposable cluster, and there is no real domain or CA. The
  `Ingress` resources render, pass `kubeconform -strict`, and are accepted by a
  real API server; no certificate was ever issued. The exact production
  validation procedure is in **Production Handoff → E**.
- **Ingress request routing.** `[NOT VALIDATED]` No ingress controller is
  installed (0 controller pods), so Service→Pod routing was validated by
  ClusterIP instead. The NetworkPolicy rule allowing the ingress namespace is
  therefore also unproven, and its namespace label is a documented
  `[REQUIRES INFRASTRUCTURE INPUT]` value.
- **Production deployment.** `[NOT VALIDATED]` Only ever deployed to a
  disposable kind cluster against disposable PostgreSQL/Redis/Vault.
- **NetworkPolicy egress restriction.** Not attempted — see the reasoning in
  `k8s/base/networkpolicy.yaml`.
- **HPA scaling behaviour.** The `HorizontalPodAutoscaler` is production-only
  and no metrics-server was installed; the resource is created by the sync but
  no scale event was observed.
- **cosign signing and verification, GHCR push, dependency-review, pip-audit.**
  These run only inside GitHub Actions against the real repository and
  registry. Configuration was reviewed line by line but not executed. The
  promotion workflow's staging-SHA parser _was_ tested directly against the
  real `kustomization.yaml`, including a negative case proving it does not
  match the Celery image's tag.
- **Typecheck.** 10 pre-existing mypy errors in `infrastructure/keys/` and
  `common/security/e2e_encryption.py`; non-blocking in CI by design. This work
  added none.

### Since validated

These were listed as unvalidated in an earlier pass and have since been run:

- **gitleaks** — executed against a CI-equivalent checkout: _no leaks found_.
- **Trivy** — executed against the canonical image: **0 CRITICAL** (it found
  and blocked 2 before the Django 4.2.26 bump).
- **kubeconform `-strict`** — 27/27 resources valid.
- **Canonical Docker build** — the API image builds from the repository
  `Dockerfile` and `requirements.txt`, exit 0, with `django-4.2.26` resolved
  cleanly and no dependency conflicts.
- **Production worker readiness at 3 replicas** — production reached 3/3 API,
  3/3 worker and 1/1 beat Ready. The earlier restarts traced to the disposable
  cluster's broken CoreDNS (AAAA lookups against a dead upstream), not to the
  probe; see the probe verdict above.

### Test suite state

All gates green, verified against Django 4.2.26 (the version `requirements.txt`
now pins):

| Gate                                                                    | Result                                                      |
| ----------------------------------------------------------------------- | ----------------------------------------------------------- |
| Unit + e2e (`pytest -m "not integration"`)                              | **319 passed, 0 failed**                                    |
| Integration (`pytest -m integration`, real PostgreSQL 15)               | **298 passed, 0 failed**                                    |
| `manage.py check`                                                       | 0 issues                                                    |
| `makemigrations --check --dry-run`                                      | No changes detected, from two different working directories |
| `ruff check` + `ruff format --check` (changed files, `--force-exclude`) | exit 0                                                      |
| gitleaks                                                                | no leaks found                                              |
| Trivy (canonical image, CRITICAL, `--ignore-unfixed`)                   | 0                                                           |
| kubeconform `-strict`                                                   | 27/27 valid                                                 |

Four separate blockers had to be cleared to get here — the two named failing
tests, machine-dependent migrations, a payments webhook parsing bug, 28
gitleaks findings, and two CRITICAL Django CVEs. Each is written up in
"Defects found by deploying this for real" above.

The one remaining non-green item is `typecheck`, which reports 10 pre-existing
errors and is `continue-on-error: true` in CI by design. This work added none.
