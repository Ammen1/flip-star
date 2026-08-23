"""
Declarative schema for every runtime configuration value.

One place that answers: what does this application need to run, what type is
it, and is it mandatory? Nothing outside this file decides whether a key is
required -- so "what must Vault contain" is answerable by reading one list
rather than grepping 108 call sites.

Required vs optional
--------------------
``required=True`` means the application cannot serve a single request without
it. A missing one aborts startup.

``required=False`` means a *feature* is unavailable without it -- Telebirr
payments, push notifications, outbound email. The application starts and every
other feature works. These are still Vault-only: there is no environment
fallback for them, and the loader reports at startup which optional groups are
unconfigured so the gap is visible rather than discovered by a user.

Marking third-party credentials required would make staging unstartable until
every provider has issued keys, which trades one failure mode for a worse one.
Flip any of them to ``required=True`` when that integration must be live.

Not in here
-----------
Bootstrap keys (VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID, VAULT_SECRET_PATH,
VAULT_KV_MOUNT, DJANGO_SETTINGS_MODULE, DJANGO_ENV) come from the environment
by necessity -- reading Vault's address out of Vault is circular. See
loader.py.

Static application constants -- enum values, business rules, error codes --
stay in code. Only environment-specific and secret values belong here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal['str', 'int', 'bool', 'csv']

Group = Literal[
    'core',
    'database',
    'redis',
    'http',
    'telebirr',
    'telebirr_b2c',
    'telebirr_ussd',
    'telebirr_h5',
    'onevas',
    'crm',
    'email',
    'push',
    'sms',
    'storage',
]


@dataclass(frozen=True)
class Key:
    name: str
    kind: Kind = 'str'
    required: bool = False
    group: Group = 'core'
    doc: str = ''
    #: Only for non-secret values with a genuinely universal answer, e.g. a
    #: protocol port. Never used to paper over a missing credential -- a Key
    #: with a fallback and required=True is rejected at import.
    fallback: Any = None


def _k(name, kind='str', required=False, group='core', doc='', fallback=None):
    return Key(name=name, kind=kind, required=required, group=group, doc=doc, fallback=fallback)


SCHEMA: tuple[Key, ...] = (
    # -- core -----------------------------------------------------------------
    _k(
        'SECRET_KEY',
        required=True,
        group='core',
        doc='Django signing key. Rotating it invalidates every session and token.',
    ),
    _k(
        'ALLOWED_HOSTS',
        kind='csv',
        required=True,
        group='http',
        doc='Hosts this instance answers for. Must match the ingress host exactly '
        'or every request returns 400.',
    ),
    _k(
        'BACKEND_URL',
        required=True,
        group='http',
        doc='Absolute base used when building media and callback URLs.',
    ),
    _k(
        'CORS_ALLOWED_ORIGINS',
        kind='csv',
        required=True,
        group='http',
        doc='Browser origins permitted to call this API.',
    ),
    _k(
        'CSRF_TRUSTED_ORIGINS',
        kind='csv',
        required=True,
        group='http',
        doc='Origins trusted for unsafe methods.',
    ),
    _k(
        'LOG_LEVEL', required=True, group='core', doc='Root log level: DEBUG, INFO, WARNING, ERROR.'
    ),
    _k(
        'TRUSTED_PROXY_IPS',
        kind='csv',
        required=True,
        group='http',
        doc='Proxies whose X-Forwarded-For is believed. Wrong values let a caller '
        'spoof their IP past per-IP throttling.',
    ),
    _k(
        'AUTH_TOKEN_TTL_DAYS',
        kind='int',
        required=True,
        group='core',
        doc='Lifetime of a DRF auth token.',
    ),
    # -- database -------------------------------------------------------------
    _k('DB_ENGINE', required=True, group='database'),
    _k('DB_NAME', required=True, group='database'),
    _k('DB_USER', required=True, group='database'),
    _k('DB_PASSWORD', required=True, group='database'),
    _k('DB_HOST', required=True, group='database'),
    _k('DB_PORT', kind='int', required=True, group='database'),
    _k(
        'DB_SSLMODE',
        required=True,
        group='database',
        doc='disable / prefer / require / verify-full.',
    ),
    _k(
        'DB_CONN_MAX_AGE',
        kind='int',
        required=True,
        group='database',
        doc='Seconds a connection is reused. 0 closes after every request.',
    ),
    # -- redis ----------------------------------------------------------------
    _k(
        'REDIS_HOST',
        required=True,
        group='redis',
        doc='Backs the cache, Channels layer, Celery broker and keypair store.',
    ),
    _k('REDIS_PORT', kind='int', required=True, group='redis'),
    # -- telebirr: direct debit ----------------------------------------------
    _k('TELEBIRR_SOAP_URL', group='telebirr'),
    _k('TELEBIRR_THIRD_PARTY_ID', group='telebirr'),
    _k('TELEBIRR_THIRD_PARTY_PASSWORD', group='telebirr'),
    _k('TELEBIRR_SHORTCODE', group='telebirr'),
    _k(
        'TELEBIRR_RESULT_URL',
        group='telebirr',
        doc='Callback Telebirr posts to. Must be whitelisted on their side.',
    ),
    _k('TELEBIRR_PAYEE_ACCOUNT_NAME', group='telebirr'),
    _k('TELEBIRR_CALLER_TYPE', group='telebirr'),
    _k('TELEBIRR_SP_OPERATOR_ID', group='telebirr'),
    _k('TELEBIRR_SP_OPERATOR_CREDENTIAL', group='telebirr'),
    _k('TELEBIRR_ORG_OPERATOR_ID', group='telebirr'),
    _k('TELEBIRR_ORG_OPERATOR_CREDENTIAL', group='telebirr'),
    _k(
        'TELEBIRR_VERIFY_SSL',
        kind='bool',
        group='telebirr',
        doc='Testbed certificates are not always chain-trusted. Must be true '
        'against production Telebirr.',
    ),
    # -- telebirr: B2C payouts ------------------------------------------------
    _k('TELEBIRR_B2C_SOAP_URL', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_SERVICE_CODE', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_REASON_TYPE', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_RESULT_URL', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_THIRD_PARTY_ID', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_THIRD_PARTY_PASSWORD', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_ORG_OPERATOR_ID', group='telebirr_b2c'),
    _k('TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL', group='telebirr_b2c'),
    # -- telebirr: USSD -------------------------------------------------------
    _k('TELEBIRR_USSD_SOAP_URL', group='telebirr_ussd'),
    _k('TELEBIRR_USSD_MERCHANT_SHORTCODE', group='telebirr_ussd'),
    _k('TELEBIRR_USSD_RESULT_URL', group='telebirr_ussd'),
    _k('TELEBIRR_USSD_THIRD_PARTY_ID', group='telebirr_ussd'),
    _k('TELEBIRR_USSD_THIRD_PARTY_PASSWORD', group='telebirr_ussd'),
    _k('TELEBIRR_USSD_ORG_OPERATOR_ID', group='telebirr_ussd'),
    _k('TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL', group='telebirr_ussd'),
    _k('TELEBIRR_SUBSCRIPTION_USSD_RESULT_URL', group='telebirr_ussd'),
    # -- telebirr: H5 / SuperApp checkout ------------------------------------
    _k('TELEBIRR_H5_BASE_URL', group='telebirr_h5'),
    _k('TELEBIRR_FABRIC_APP_ID', group='telebirr_h5'),
    _k('TELEBIRR_APP_SECRET', group='telebirr_h5'),
    _k('TELEBIRR_MERCHANT_APP_ID', group='telebirr_h5'),
    _k('TELEBIRR_MERCHANT_CODE', group='telebirr_h5'),
    _k('TELEBIRR_PRIVATE_KEY', group='telebirr_h5', doc='RSA private key, PEM.'),
    _k('TELEBIRR_PUBLIC_KEY', group='telebirr_h5', doc="Telebirr's public key, PEM."),
    _k('TELEBIRR_NOTIFY_URL', group='telebirr_h5'),
    _k('TELEBIRR_REDIRECT_URL', group='telebirr_h5'),
    # -- onevas ---------------------------------------------------------------
    _k('ONEVAS_APPLICATION_KEY', group='onevas'),
    _k('ONEVAS_PRODUCT_NUMBER', group='onevas'),
    _k('ONEVAS_SMS_URL', group='onevas'),
    _k('ONEVAS_CHARGING_URL', group='onevas'),
    _k('ONEVAS_SPID', group='onevas'),
    _k('ONEVAS_SHORT_CODE', group='onevas'),
    # -- crm ------------------------------------------------------------------
    _k('CRM_ENDPOINT', group='crm'),
    _k('CRM_SERVICE_NUMBER_A', group='crm'),
    _k('CRM_ACCESS_USER', group='crm'),
    _k('CRM_ACCESS_PASSWORD', group='crm'),
    _k('CRM_CHANNEL_ID', group='crm'),
    _k('CRM_TECHNICAL_CHANNEL_ID', group='crm'),
    _k('CRM_TENANT_ID', group='crm'),
    _k('CRM_CURRENCY_ID', group='crm'),
    _k('CRM_CHARGE_CODE', group='crm'),
    _k('CRM_OFFERING_ID', group='crm'),
    # -- email ----------------------------------------------------------------
    _k('EMAIL_HOST', group='email'),
    _k('EMAIL_PORT', kind='int', group='email'),
    _k('EMAIL_USE_TLS', kind='bool', group='email'),
    _k('EMAIL_HOST_USER', group='email'),
    _k('EMAIL_HOST_PASSWORD', group='email'),
    _k('DEFAULT_FROM_EMAIL', group='email'),
    # -- push -----------------------------------------------------------------
    _k('VAPID_PUBLIC_KEY', group='push'),
    _k('VAPID_PRIVATE_KEY', group='push'),
    _k('VAPID_SUBJECT', group='push'),
    _k('FIREBASE_SERVER_KEY', group='push'),
    # -- sms ------------------------------------------------------------------
    _k('AT_USERNAME', group='sms'),
    _k('AT_API_KEY', group='sms'),
    # -- object storage -------------------------------------------------------
    _k('S3_ENDPOINT_URL', group='storage'),
    _k('STORAGE_BUCKET_NAME', group='storage'),
    _k('ACCESS_KEY_ID', group='storage'),
    _k('SECRET_ACCESS_KEY', group='storage'),
    _k('REGION_NAME', group='storage'),
    _k('S3_USE_SSL', kind='bool', group='storage'),
    _k('S3_DEFAULT_ACL', group='storage'),
)

BY_NAME: dict[str, Key] = {k.name: k for k in SCHEMA}

REQUIRED: tuple[str, ...] = tuple(k.name for k in SCHEMA if k.required)

GROUPS: dict[str, tuple[Key, ...]] = {}
for _key in SCHEMA:
    GROUPS.setdefault(_key.group, ())
    GROUPS[_key.group] += (_key,)


# -- integrity checks, run at import so a bad schema fails loudly -------------

_dupes = [k.name for k in SCHEMA if [x.name for x in SCHEMA].count(k.name) > 1]
if _dupes:
    raise RuntimeError(f'duplicate keys in SCHEMA: {sorted(set(_dupes))}')

_bad = [k.name for k in SCHEMA if k.required and k.fallback is not None]
if _bad:
    raise RuntimeError(
        f'these keys are required AND carry a fallback, which defeats fail-fast: {sorted(_bad)}'
    )


CASTS: dict[Kind, Callable[[str], Any]] = {
    'str': lambda v: v,
    'int': int,
    'bool': lambda v: str(v).strip().lower() in {'1', 'true', 'yes', 'on', 't', 'y'},
    'csv': lambda v: tuple(p.strip() for p in v.split(',') if p.strip()),
}
