# Production configuration checklist

Every value the deployment needs before it can go to production, with its
current state. Nothing here is invented: where this repository has no
confirmed value, the row says so rather than guessing.

**Legend — configuration state**

| Mark | Meaning |
|---|---|
| `[KNOWN]` | A real value exists in the repo and is used as-is. |
| `[UNKNOWN]` | No value exists anywhere in this project. Someone must decide it. |
| `[REQUIRES INFRASTRUCTURE INPUT]` | Determined by the cluster/provider; can only be read off the real environment. |

**Legend — verification state**

| Mark | Meaning |
|---|---|
| `[VALIDATED]` | Exercised against a real running system and observed to work. |
| `[NOT VALIDATED]` | Not exercised. Renders and passes schema validation only, or was not run at all. |

---

## 0. Verification state at handoff

| Area | State | Evidence / reason |
|---|---|---|
| Unit + e2e tests (319) | `[VALIDATED]` | Run against Django 4.2.26; 0 failures. |
| Integration tests (298, real PostgreSQL 15) | `[VALIDATED]` | Run against Django 4.2.26; 0 failures. |
| Django checks | `[VALIDATED]` | `manage.py check` — 0 issues. |
| Migration drift | `[VALIDATED]` | `makemigrations --check` clean from two different working directories. |
| Lint (changed files) | `[VALIDATED]` | `ruff check` + `ruff format --check` with `--force-exclude`, exit 0. |
| Typecheck | `[NOT VALIDATED]` | 10 pre-existing errors in `infrastructure/keys/` and `common/security/`; non-blocking in CI by design. 0 added. |
| Gitleaks | `[VALIDATED]` | "no leaks found" on a CI-equivalent checkout. |
| Canonical Docker build | `[VALIDATED]` | API image built from the repo `Dockerfile` + `requirements.txt`, exit 0. |
| Trivy | `[VALIDATED]` | 0 CRITICAL on the canonical API image (was 2 before the Django bump). |
| Image secret audit | `[VALIDATED]` | `.git` absent, 0 `.env*` files, 0 key files, runs as uid 1001. |
| Cosign signing / verification | `[NOT VALIDATED]` | Runs only inside GitHub Actions; requires the real repo and GHCR. Configuration reviewed, not executed. |
| Kustomize build | `[VALIDATED]` | staging 13 / production 14 resources. |
| kubeconform `-strict` | `[VALIDATED]` | 27/27 valid, 0 invalid, 0 errors. |
| Sync-wave ordering | `[VALIDATED]` | `-2` ConfigMap/SA → `-1` Job → `0` workloads, observed in a live cluster. |
| Migration Job | `[VALIDATED]` | Ran to Complete in both namespaces; blocks the rollout on failure. |
| API / Celery worker / Celery beat | `[VALIDATED]` | Staging 3/3 Ready; production 3 API + 3 worker + 1 beat reached Ready. |
| Probes | `[VALIDATED]` | Verified working, and verified failing correctly before the fixes. |
| Service routing | `[VALIDATED]` | ClusterIP → Pod, `/api/v1/health/` 200, `/api/v1/health/deep/` 200 with live DB. |
| PDB / HPA | `[VALIDATED]` | Render correctly and are accepted by the API server. HPA scale events `[NOT VALIDATED]` — no metrics-server. |
| NetworkPolicy | `[VALIDATED]` | Enforcement confirmed on kindnet. The two `CHANGEME` values inside it are `[REQUIRES INFRASTRUCTURE INPUT]`. |
| Argo CD staging auto-sync | `[VALIDATED]` | Commit detected and applied with no intervention. |
| Argo CD production manual sync | `[VALIDATED]` | Stayed `OutOfSync`; namespace did not exist until a human synced. |
| AppProject restrictions | `[VALIDATED]` | Destination and resource-kind enforcement both observed rejecting violations. |
| Image promotion | `[VALIDATED]` | Exact committed SHA observed running. |
| Rollback | `[VALIDATED]` | `git revert` restored the previous image with no rebuild. |
| **Ingress routing** | `[NOT VALIDATED]` | No ingress controller installed. Resources render, pass kubeconform, and are accepted by the API server — nothing backs them. |
| **TLS / cert-manager** | `[NOT VALIDATED]` | No `ClusterIssuer` CRD registered. No certificate was ever issued. |
| **Production deployment** | `[NOT VALIDATED]` | Only ever deployed to a disposable kind cluster against test dependencies. |

---

## 1. Domains and origins

| Value | File | State | Notes |
|---|---|---|---|
| Staging domain | `k8s/overlays/staging/patches/configmap-patch.yaml` → `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `BACKEND_URL` | `[KNOWN]` — `uat.flipstar.et` | The only live domain this project has. Also in `docker-compose.yml`/`nginx.conf`. |
| Staging ingress host | `k8s/overlays/staging/ingress.yaml` | `[KNOWN]` — `uat.flipstar.et` | Matches the ConfigMap. |
| Production backend domain | `k8s/overlays/production/patches/configmap-patch.yaml` → `ALLOWED_HOSTS`, `BACKEND_URL`; `k8s/overlays/production/ingress.yaml` → `spec.tls[0].hosts[0]`, `spec.rules[0].host` | `[UNKNOWN]` — `CHANGEME-production-backend-domain` | This project has no production domain. **`ALLOWED_HOSTS` must match the ingress host exactly or every request returns `400`.** |
| Production frontend origin | `k8s/overlays/production/patches/configmap-patch.yaml` → `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | `[UNKNOWN]` — `CHANGEME-production-frontend-domain` | The frontend deploys to Vercel separately; its production URL is not recorded here. |

## 2. Datastores

| Value | File | State | Notes |
|---|---|---|---|
| Staging `DB_HOST` | staging `configmap-patch.yaml` | `[REQUIRES INFRASTRUCTURE INPUT]` — currently `postgres.flipstar-staging.svc.cluster.local` | An in-cluster service name. Correct only if PostgreSQL actually runs in that namespace; point at the managed instance otherwise. |
| Staging `REDIS_HOST` | staging `configmap-patch.yaml` | `[REQUIRES INFRASTRUCTURE INPUT]` — currently `redis.flipstar-staging.svc.cluster.local` | Same. |
| Production `DB_HOST` | production `configmap-patch.yaml` | `[UNKNOWN]` — `CHANGEME-production-postgres-host` | |
| Production `REDIS_HOST` | production `configmap-patch.yaml` | `[UNKNOWN]` — `CHANGEME-production-redis-host` | |
| `DB_SSLMODE` | not set in either overlay | `[REQUIRES INFRASTRUCTURE INPUT]` | Defaults to `prefer` in `config/settings/production.py`. A managed provider normally wants `require`. |

## 3. Vault

| Value | File | State | Notes |
|---|---|---|---|
| Staging `VAULT_ADDR` | staging `configmap-patch.yaml` | `[REQUIRES INFRASTRUCTURE INPUT]` — currently `https://vault.internal:8200` | Placeholder hostname; not verified to resolve anywhere. |
| Production `VAULT_ADDR` | production `configmap-patch.yaml` | `[UNKNOWN]` — `CHANGEME-production-vault-addr` | |
| `VAULT_SECRET_PATH` | both overlays | `[KNOWN]` — `flipstar/backend/staging`, `flipstar/backend/production` | Verified against `infrastructure/secrets/provider.py`. |
| `VAULT_KV_MOUNT` | `k8s/base/configmap.yaml` | `[KNOWN]` — `secret` (KV v2 default) | Change only if the mount is named differently. |
| AppRole `VAULT_ROLE_ID` / `VAULT_SECRET_ID` | **not in Git** — created out of band per namespace | `[REQUIRES INFRASTRUCTURE INPUT]` | See `k8s/base/secret.example.yaml`. Issue with `secret_id_num_uses=0` — probes re-authenticate on every cycle (see the probe-cost note in `k8s/README.md`). |

## 4. Cluster add-ons

| Value | File | State | Notes |
|---|---|---|---|
| Ingress controller namespace | `k8s/base/networkpolicy.yaml` → `namespaceSelector` `kubernetes.io/metadata.name` | `[REQUIRES INFRASTRUCTURE INPUT]` — currently `ingress-nginx` | Kubernetes sets this label automatically. Confirm with `kubectl get pods -A \| grep ingress`. **A wrong value drops all API traffic silently.** |
| Node CIDR | `k8s/base/networkpolicy.yaml` → `ipBlock.cidr` | `[REQUIRES INFRASTRUCTURE INPUT]` — currently `10.0.0.0/8` | Allows kubelet probe traffic. Read with `kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'`. Narrow it. |
| CNI enforces NetworkPolicy | — | `[REQUIRES INFRASTRUCTURE INPUT]` | Calico/Cilium/recent kindnet do. Some managed clusters silently ignore NetworkPolicy. |
| `ClusterIssuer` name | both `ingress.yaml` | `[REQUIRES INFRASTRUCTURE INPUT]` — currently `letsencrypt-prod` | Must name a ClusterIssuer that exists. |
| TLS secret names | `flipstar-staging-tls`, `flipstar-production-tls` | `[REQUIRES INFRASTRUCTURE INPUT]` | Must match the cluster's cert-manager naming convention. |
| Argo CD `repoURL` | all three `argocd/*.yaml` | `[KNOWN]` — `https://github.com/Ammen1/flip-star.git` | |
| GHCR image names | workflows + `k8s/base/kustomization.yaml` | `[KNOWN]` — `ghcr.io/ammen1/flip-star-backend{,-celery}` | |

## 5. GitHub repository

| Value | File | State | Notes |
|---|---|---|---|
| CODEOWNERS owners | `.github/CODEOWNERS` | `[UNKNOWN]` — every owner is `@REPLACE-ME-*` | Paths are now correct (they previously all pointed at a non-existent `backend/` directory and matched nothing). An unfilled CODEOWNERS is silently inert. |
| `production` environment reviewers | GitHub → Settings → Environments | `[REQUIRES INFRASTRUCTURE INPUT]` | Without required reviewers, `environment: production` in the promotion workflow is a no-op label. |
| Branch protection on `main` | GitHub → Settings → Branches | `[REQUIRES INFRASTRUCTURE INPUT]` | Require `backend-ci-cd.yml` + `k8s-validate.yml` and code-owner review. |
| Repository secrets | — | `[KNOWN]` — none required | `GITHUB_TOKEN` covers GHCR push, the GitOps commit and cosign keyless signing. |

## 6. Application secrets that must exist in Vault

Written to `flipstar/backend/<environment>`, read at process start by
`infrastructure/secrets/provider.py`. **Never in Git.**

Hard requirements — `config/settings/production.py::_validate()` refuses to
start without them:

| Key | Why |
|---|---|
| `SECRET_KEY` | Rejected if it equals a known development default. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Validated non-empty on the resolved connection. |

Integration credentials — absence is a startup **warning**, not fatal, so an
integration can be deliberately disabled:

`TELEBIRR_SOAP_URL`, `TELEBIRR_THIRD_PARTY_ID`, `TELEBIRR_THIRD_PARTY_PASSWORD`,
`TELEBIRR_SP_OPERATOR_ID`, `TELEBIRR_SP_OPERATOR_CREDENTIAL`,
`TELEBIRR_FABRIC_APP_ID`, `TELEBIRR_APP_SECRET`, `TELEBIRR_MERCHANT_APP_ID`,
`TELEBIRR_MERCHANT_CODE`, `TELEBIRR_PRIVATE_KEY`, `TELEBIRR_PUBLIC_KEY`,
`ONEVAS_APPLICATION_KEY`, `ONEVAS_PRODUCT_NUMBER`.

Also read with defaults (set them if the feature is used): the `TELEBIRR_B2C_*`
and `TELEBIRR_USSD_*` families, `CRM_*`, `VAPID_PUBLIC_KEY` /
`VAPID_PRIVATE_KEY`, `EMAIL_*`, `ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` /
`STORAGE_BUCKET_NAME`, `FIREBASE_SERVER_KEY`.

---

## Blocking summary

Production **cannot** be deployed until every `[UNKNOWN]` row has a decided
value and every `[REQUIRES INFRASTRUCTURE INPUT]` row has been read off the
real cluster. Staging is deployable today apart from `VAULT_ADDR`, the
datastore hostnames, and the two NetworkPolicy values.
