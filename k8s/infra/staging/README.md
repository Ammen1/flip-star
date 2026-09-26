# Staging infrastructure

Postgres, Redis and Vault for `flipstar-staging`, on one k3s node.

Two Argo CD `info` links in `argocd/application-infra-staging.yaml` point here
and called this the "Bootstrap and unseal runbook" before it existed. It is
written now because the question it answers — *where is the Vault token* — had
no answer anywhere in the repo, and the person who needed it was locked out.

---

## Read this before touching `vault.yaml`

Staging Vault uses **file storage, a single replica, no TLS on the listener,
and manual unseal**. Those are real limitations, chosen because this runs on
one node with no cloud KMS. The consequence that matters:

> **Vault seals itself on every pod restart, and a sealed Vault serves
> nothing.** No token authenticates. The backend cannot read its
> configuration. Somebody has to log in and unseal it by hand.

Any edit to the `vault-config` ConfigMap restarts the pod and therefore costs
an unseal. Treat a change to `vault.yaml` as a maintenance window, not a
routine sync.

The liveness probe deliberately remaps *sealed* and *uninitialised* to HTTP
204 (`sealedcode=204&uninitcode=204`). Without that, a sealed Vault answers
/health with 503, the probe kills the pod, it restarts sealed, and the loop
never leaves a window to `kubectl exec` in and fix it. The **readiness** probe
deliberately does *not* remap them: a sealed Vault genuinely cannot serve the
application and should leave the Service endpoints.

---

## Key custody

`vault operator init` prints the unseal key shares and the root token
**once**. They are not in this repo, not in Kubernetes, and not recoverable
from Vault.

> ### The stored init output does not match the running Vault
>
> `vault status` on the live pod reports **Total Shares 5, Threshold 3**.
> `/root/staging-secrets/vault-init.json` reports `unseal_shares: 1`,
> `unseal_threshold: 1`, and carries a single key. Both cannot describe the
> same seal, so that file is stale -- Vault was re-keyed after 2026-08-23, or
> that JSON belongs to an instance since replaced. `new-root-token.txt`
> (2026-08-28) is consistent with something having changed in that window.
>
> **Nobody has been shown to hold 3 of the current 5 shares.** That is
> survivable only while Vault stays unsealed. It seals on every pod restart,
> and any edit to `vault.yaml` restarts the pod -- so the next maintenance
> window is when this becomes an outage with no recovery path.
>
> Resolve it while Vault is open: find the 5 shares from the 2026-08-28 work,
> or re-key and store the new shares properly --
> `vault operator rekey -init -key-shares=5 -key-threshold=3`.

Where they are:

| | |
|---|---|
| Custodian | _WHO — name a person and a backup. STILL UNFILLED._ |
| Location | `/root/staging-secrets/` on `sky-staging-server`, mode 0600 |
| Init output | `vault-init.json` — `operator init -format=json`: `unseal_keys_b64[]` + `root_token` |
| Current root token | `new-root-token.txt` — regenerated 2026-08-28, newer than the init output |
| Key shares | **Live Vault: 5, threshold 3.** The stored `vault-init.json` says 1/1 and is stale — see the warning above |

A **pointer**, never the keys themselves. Note the JSON form: `grep`ping for
`Unseal Key` finds nothing, because that is the text format and this is
`-format=json`.

**This is a single point of failure, twice over.** There is one unseal key
(not a quorum), and it sits in the same 0600 directory as the root token,
`db_password`, `secret_key`, `github_pat` and `ghcr_pat` — on one node, with no
off-host copy. Anyone who reads that directory owns staging outright; losing
that disk loses staging Vault permanently.

Two separate fixes, both decisions rather than chores:

* **Off-host copy** of the unseal key and root token, in a password manager.
  This one is unambiguous and should happen regardless.
* **`vault operator rekey`** to split into several shares with a threshold, so
  no single person or file can unseal alone. Worth it only if the shares then
  actually live in different places — five shares in one file is what
  `shares=1` already is, with extra steps.

---

## Reaching Vault

The Service is `ClusterIP` on 8200 — no NodePort, no ingress. It is **not**
bound to the node's localhost, so SSH port-forwarding alone reaches nothing.

**Neither `vault` nor `jq` is installed on the node.** The vault binary lives
in the pod, so there is nothing to install -- and `VAULT_ADDR=…:8210` on the
node reaches nothing, because a laptop tunnel terminates on the laptop.

**From inside the cluster** (simplest; the CLI is already in the pod):

```bash
kubectl -n flipstar-staging exec -it deploy/vault -- sh
export VAULT_ADDR=http://127.0.0.1:8200
vault status
```

One-shot, without an interactive shell:

```bash
kubectl -n flipstar-staging exec -i deploy/vault --   env VAULT_ADDR=http://127.0.0.1:8200 vault status
```

Reading `vault-init.json` without `jq` -- structure and counts only, no values:

```bash
python3 -c "
import json; d=json.load(open('/root/staging-secrets/vault-init.json'))
print('keys:', sorted(d))
print('shares:', d.get('unseal_shares'), 'threshold:', d.get('unseal_threshold'))
"
```

**From a laptop** — two hops, because the first only gets you to the node:

```bash
# window 1, left running
ssh -i <key.pem> -L 8210:localhost:8210 root@<node> \
  "kubectl -n flipstar-staging port-forward svc/vault 8210:8200"

# window 2
export VAULT_ADDR=http://127.0.0.1:8210     # http, not https
vault status
```

`kubectl port-forward` is not a service. It dies with the shell that started
it, which is why a tunnel that worked yesterday reaches nothing today.

---

## Unsealing after a restart

```bash
vault status            # Sealed: true, Initialized: true
vault operator unseal   # x3 -- the live seal is shares=5, threshold=3
vault status            # Sealed: false
```

Pipe each share in rather than passing it as an argument, so it stays out of
shell history and off the process list:

```bash
printf '%s' '<share>' | kubectl -n flipstar-staging exec -i deploy/vault --   env VAULT_ADDR=http://127.0.0.1:8200 vault operator unseal -
```

Do **not** source the share from `vault-init.json` -- it is stale, and its key
is rejected as not belonging to the current seal.

Then restart the consumers, because the config payload is cached per process:

```bash
kubectl -n flipstar-staging rollout restart \
  deploy/flipstar-backend deploy/flipstar-celery-worker deploy/flipstar-celery-beat
```

---

## First-time bootstrap

Only on an empty Vault. `vault status` showing `Initialized: false` is the
one situation this applies to.

```bash
vault operator init          # SAVE the 5 shares and the root token, then
                             # record their location in Key custody above
vault operator unseal        # x3
vault login                  # root token; prompts, does not echo
```

Then follow `docs/secrets.md` → *Production setup* for the KV mount, the
per-environment policies, the AppRole, and `vault_push` to load the values.
Note the paths are per environment — `secret/flipstar/backend/staging`, not
`secret/flipstar/backend`; a policy on the bare path grants nothing here.

---

## Getting a token

Summarised; `docs/secrets.md` → *Getting a token* has the full version.

1. **AppRole login** — read-only, but available immediately from the
   `flipstar-backend-vault-approle` Secret already in the namespace. Enough to
   read and to prove connectivity; not enough for `vault_push`.
2. **Root token** — from the init output. See Key custody above.
3. **Lost the token, still have the shares** — `vault operator generate-root`.
4. **Lost both** — `vault operator init` again; everything stored is gone.

---

## Follow-up work, not done here

* **Auto-unseal** (Transit or a cloud KMS) and **Raft storage**. These remove
  the manual unseal that every item above works around. This is the real fix.
* **Vault Kubernetes auth**, so a pod authenticates with its own ServiceAccount
  token and the bootstrap AppRole Secret disappears entirely — see
  `docs/secrets.md` → *The bootstrap problem*.
* **TLS on the listener.** Staging traffic is in-cluster over http today.
