## What changed and why

<!-- One or two sentences. Link an issue if there is one. -->

## Checklist

- [ ] `backend-ci-cd.yml` is green (lint, typecheck, tests, django-checks, build, scans)
- [ ] New/changed endpoints or models have test coverage
- [ ] Migrations included, if the change needs one, and reviewed for reversibility
- [ ] No secrets, credentials, or `.env*` files in this diff
- [ ] If this touches `k8s/` or `argocd/`: overlays still build (`kustomize build k8s/overlays/staging|production`)
- [ ] If this touches wallet/payments/direct-debit code: race-condition and idempotency implications considered

## Deployment notes

<!-- Anything the person promoting this to production needs to know:
     required env vars, manual migration steps, rollback caveats. -->
