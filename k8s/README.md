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
  SHA it was built from (`ghcr.io/skykin-technologies/flip-star-backend:<sha>`).
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

## A bug found while building this, not fixed here

`Dockerfile`'s `HEALTHCHECK` and `docker-compose.yml`'s `backend`
healthcheck both used to curl `http://localhost:8000/api/health/` while
`config/urls.py` only mounts routes under `/api/v1/` — that path 404s.
`docs/deployment.md`'s own curl example already used the correct
`/api/v1/health/`, and the Kubernetes probes in `k8s/base/deployment.yaml`
were written against the correct path from the start. **Fixed**: both
`Dockerfile` and `docker-compose.yml` now use `/api/v1/health/` too,
confirmed directly (the old path 404s, the corrected one returns
`{"status": "ok"}`) rather than assumed.

## Required GitHub repository configuration

No repository secrets need to be created for the CI/CD workflows themselves
— `GITHUB_TOKEN` (automatic, scoped by the `permissions:` block in each
workflow) covers the GHCR push (`packages: write`), the GitOps commit
(`contents: write`), and cosign's keyless signing (`id-token: write`, no key
material to generate or store). Nothing else is needed unless GHCR's default
visibility is changed to private and the cluster needs its own pull
credential (see below).

| Setting | Where | Why |
|---|---|---|
| Actions → General → Workflow permissions | Repo settings | Ensure "Read and write permissions" is enabled, or the `contents: write` step in `update-gitops-staging` / `backend-promote-production.yml` will fail even though the workflow requests it. |
| Branch protection on `main` | Repo settings | Require `backend-ci-cd.yml`'s and `k8s-validate.yml`'s gates to pass before merge, and require a CODEOWNERS review — the pipeline enforces gates on its own runs, but only branch protection stops someone bypassing it via direct push. |
| **Environments → `staging`** | Repo settings → Environments | Not required to be protected — `push-image`/`update-gitops-staging` use it mainly so every staging deploy shows up in the repo's Environments tab (which SHA, when, which run). Add required reviewers here too if staging should ever need a gate. |
| **Environments → `production`** | Repo settings → Environments | **This is what actually makes production promotion a two-person action, not just a two-*step* one.** Add required reviewers; `backend-promote-production.yml`'s `promote` job (`environment: production`) then pauses for approval before it runs at all — before the GitOps commit, before Argo CD ever sees a diff. Without this configured, `environment: production` is present but toothless. |
| `.github/CODEOWNERS` | This repo, already added | Every owner in it is a `@REPLACE-ME-*` placeholder — replace with real GitHub usernames/teams before branch protection's "require review from code owners" has any effect. An unfilled CODEOWNERS file is silently inert, not an error. |
| `.github/dependabot.yml` | This repo, already added | Nothing to configure — Dependabot is enabled by the file's presence. It keeps `requirements.txt`, the pinned Action SHAs, and both Dockerfiles' base image current on a weekly schedule. |

## Required cluster / Argo CD configuration

1. **Argo CD installed**, with access to `https://github.com/Skykin-Technologies/flip-star.git` (public repo — no credential needed for reads).
2. **ingress-nginx** and **cert-manager** installed cluster-wide, with a `ClusterIssuer` named `letsencrypt-prod` (referenced by `k8s/overlays/*/ingress.yaml`). Neither is part of this Kustomize tree — they're cluster add-ons, not per-application resources.
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
   *entire* `flipstar-staging` namespace -- not just the resources Argo CD
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
6. **Point `DB_HOST` / `REDIS_HOST` / `VAULT_ADDR` at real infrastructure.** Every `CHANGEME*` value in `k8s/overlays/*/configmap-patch.yaml` and `k8s/overlays/production/ingress.yaml` is a placeholder — this project's only confirmed live domain today is `uat.flipstar.et` (used as-is for the staging overlay); production has no confirmed domain yet.

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
useful when you need to be live again *now* and can commit the git-level
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

- `k8s/base` and both overlays build cleanly: `kustomize build k8s/overlays/staging` and `kustomize build k8s/overlays/production` both render without error, producing the expected Namespace, ServiceAccount, ConfigMap, three Deployments, Service, two PodDisruptionBudgets, Ingress (and HorizontalPodAutoscaler for production only).
- Every workflow YAML file parses as valid YAML and each job's `needs:`/`outputs` references resolve to a job actually listed in its own `needs:` array.
- `mypy` and the full-repo `ruff check` were run for real against this codebase (not assumed clean) to size the pre-existing debt before deciding how strict to make those two CI gates — see the comments in `backend-ci-cd.yml`'s `lint-and-format` and `typecheck` jobs for the exact numbers and reasoning.

### Deployed for real against a disposable cluster

A follow-up audit went further than static validation: a disposable `kind` cluster plus a disposable Argo CD install, with the actual `Dockerfile` and `Dockerfile.celery` images built and deployed. This surfaced three real bugs that static review hadn't caught, all now fixed in `k8s/base/`:

1. **`deployment-celery-beat.yaml`** — `readOnlyRootFilesystem: true` blocked celery's default `PersistentScheduler` from writing its `celerybeat-schedule` file to its working directory. Fixed with `--schedule=/tmp/celerybeat-schedule`, pointed at the already-writable `/tmp` `emptyDir`. Confirmed directly: `shelve.open('/app/...')` raised `Read-only file system` inside the pod; `/tmp` did not.
2. **`deployment-celery-worker.yaml`** — the liveness/startup probes used `celery@$(HOSTNAME)`. Kubernetes' `$(VAR_NAME)` substitution applies to a container's own `command`/`args` at launch, **not** to `exec` probes, which the kubelet invokes directly via the container runtime's exec API. The literal, unsubstituted string was passed to celery every time (100% reproducible, confirmed by testing celery's own `inspect ping` manually against both forms). Fixed by wrapping in `sh -c` for genuine shell expansion — the same pattern `Dockerfile.celery`'s own `HEALTHCHECK` already used successfully, since Docker's shell-form `CMD` does go through `/bin/sh -c`.
3. Same probes were also intermittently failing even after the above fix, with `celery inspect ping`'s own internal reply-wait (default 1.0s, unrelated to the probe's `timeoutSeconds`) too tight for a real broker round-trip under any scheduling jitter. Fixed with an explicit `--timeout=8`, applied to both the Kubernetes probes and, for consistency, `Dockerfile.celery`'s native `HEALTHCHECK`.

After all three fixes: `flipstar-backend`, `flipstar-celery-worker`, and `flipstar-celery-beat` all reached `1/1 Running` with **zero restarts**, confirmed over multiple redeploys.

Also validated against the disposable Argo CD instance, each with direct empirical proof, not just configuration review:
- **AppProject destination enforcement** — pointing the staging Application at `kube-system` was rejected: `"application destination server ... and namespace 'kube-system' do not match any of the allowed destinations"`. Nothing touched `kube-system`.
- **AppProject resource-kind enforcement** — adding a `Secret` to the staging overlay (a kind not in `namespaceResourceWhitelist`) failed sync with `"resource :Secret is not permitted in project flipstar-backend"`. The Secret was never created.
- **Staging automated sync** — a new commit was picked up via Argo CD's normal ~3-minute polling (not a forced refresh) and deployed automatically.
- **Production manual sync** — after the same GitOps update, production stayed `OutOfSync` with nothing applied; `flipstar-production` didn't even exist as a namespace until manually synced.
- **Full GitOps round trip with SHA verification** — committed an image-tag change ("Version B"), confirmed Argo CD detected and deployed it, and confirmed via `kubectl get pod -o jsonpath='{...image}'` that the exact tag committed was the exact tag running.
- **Rollback without a rebuild** — `git revert` of the Version B commit, pushed; Argo CD redeployed Version A's image tag, using the already-built image with no new `docker build`.
- **A sharp edge, not a bug**: deleting an Argo CD Application that owns its own `namespace.yaml` resource, combined with the `resources-finalizer`, cascades to delete the *entire* namespace — confirmed by accident during this testing when it wiped a namespace's worth of resources this project's own manifests didn't create. Documented above under "Register both Applications" as something to know before ever running that delete.

**Not validated in this pass**: TLS/cert-manager (no real domain or CA available in a disposable cluster — this is a genuine limitation of testing without one, not something skipped), and full Ingress request routing (no `ingress-nginx` controller installed in the disposable cluster; the `Ingress` resource itself was confirmed to apply without schema errors, and Service→Pod routing was validated directly via port-forward instead).

### Hardening pass — pinned actions, signing, secret scanning, k8s-validate.yml

A later pass professionalized the pipeline itself: every third-party GitHub
Action pinned to a commit SHA (a tag can be repointed after the fact; a SHA
can't), `timeout-minutes` on every job, gitleaks secret scanning, pip-audit
dependency auditing, SBOM generation, cosign keyless image signing (verified
again before production promotion, not just produced and forgotten), GitHub
Environments wired to `staging`/`production` for native approval gating, a
dedicated `k8s-validate.yml` workflow (`k8s/`/`argocd/` had no CI coverage
at all before this), Dependabot, CODEOWNERS, and a PR template.

**Also found and fixed while wiring the secret scanner in**: `.env`,
`.env.production` (the file with the real Neon Postgres password
flagged during the earlier production-readiness audit), and
`render.env` were all still tracked in this repository's current
`HEAD` — not just old history. `.gitignore` already had rules that
would have caught them (`.env`, `.env.*`, `render.env`), but gitignore
doesn't retroactively untrack a file added before the rule existed. All
three (plus the repository-root `.env`, which had no covering rule at
either level) are now untracked via `git rm --cached` — the local files are
untouched, only git no longer follows them — and the root `.gitignore` gained
its own `.env`/`.env.*` rule so this can't quietly recur at the root either.
**None of these credentials are rotated by this change.** Per
`docs/secrets.md`: "every secret that has ever been in this
repository is compromised and must be rotated regardless" — untracking stops
the bleeding, it doesn't undo the exposure. Rotating the Neon DB password,
the VAPID key pair, the admin password, and the Telebirr/Onevas credentials
in `.env` is still outstanding.

**Not validated in this pass**: gitleaks, cosign, kubeconform, and pip-audit
were all wired into the workflows based on documentation and prior
experience with each tool, not exercised end-to-end locally — the
authoring environment's disk filled to 0 bytes free mid-session (unrelated
to this work; largely pre-existing on the host) and Docker became
unresponsive as a direct result, which is what the earlier disposable-
cluster testing had depended on. Every new/changed YAML file was still
parsed and structurally checked (job graphs, `needs:` references), and the
`dependency-audit` job was deliberately started non-blocking specifically
*because* pip-audit's actual finding count couldn't be verified first,
mirroring the same calibration already applied to `typecheck`. Before
relying on this hardening pass in production, trigger a real run of both
workflows (a PR is enough to exercise `k8s-validate.yml`; a push to `main`
exercises the rest) and read the actual output rather than assuming it's
clean.
