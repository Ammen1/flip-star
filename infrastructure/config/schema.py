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
    'timwe',
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
    # -- timwe ----------------------------------------------------------------
    # OneVAS has been removed; its ONEVAS_* keys went with it.
    _k('TIMWE_INTEGRATION_ENABLED', kind='bool', group='timwe'),
    _k(
        'TIMWE_CHARGE_URL',
        group='timwe',
        doc='chargeAmount endpoint, '
        'http://IP:Port/AmountChargingService/services/AmountCharging. Supplied by '
        'TIMWE. NOT the SMPP host -- do not reuse TIMWE_SMPP_HOST/PORT.',
    ),
    _k('TIMWE_SP_ID', group='timwe'),
    _k(
        'TIMWE_SP_PASSWORD',
        group='timwe',
        doc='chargeAmount account password, hashed into MD5(spId+Password+timeStamp) '
        'per request. Secret. Confirm with TIMWE -- it need not equal the SMPP password.',
    ),
    _k('TIMWE_SERVICE_ID', group='timwe'),
    _k(
        'TIMWE_CHARGE_SERVICE_ID',
        group='timwe',
        doc='Service quoted on chargeAmount, when TIMWE charge under a different '
        'service than their subscription notifications carry. Falls back to '
        'TIMWE_SERVICE_ID.',
    ),
    _k(
        'TIMWE_CHARGE_CODE',
        group='timwe',
        doc="The MA's charging code, sent as <code>. Optional per the guide; "
        "TIMWE's own working example sends one.",
    ),
    _k(
        'TIMWE_CHARGE_TEL_PREFIX',
        kind='bool',
        group='timwe',
        doc="Write endUserIdentifier as 'tel:2519...' (guide) or bare digits "
        "(TIMWE's working example). Default true.",
    ),
    _k(
        'TIMWE_CHARGE_PASSWORD_MODE',
        group='timwe',
        doc="'md5' (default, the guide): spPassword = MD5(spId+Password+timeStamp), "
        "the password never leaves us. 'plain' sends the password itself, as TIMWE's "
        'own example does; refused over plain HTTP.',
    ),
    _k(
        'TIMWE_CHARGE_CA_BUNDLE',
        group='timwe',
        doc="Path to TIMWE's chargeAmount certificate. Set it and only that "
        'certificate is trusted -- the answer to their untrusted HTTPS endpoint.',
    ),
    _k(
        'TIMWE_CHARGE_VERIFY_TLS',
        kind='bool',
        group='timwe',
        doc='Default true. False stops the MA certificate being checked: encrypted '
        'but unauthenticated, so a party on the path could read or alter a charge. '
        'Staging stopgap only; every charge logs TIMWE_CHARGE_TLS_UNVERIFIED.',
    ),
    _k('TIMWE_CURRENCY', group='timwe'),
    _k(
        'TIMWE_CHARGE_TIMEOUT',
        kind='int',
        group='timwe',
        doc='chargeAmount read timeout in seconds. The guide says the MA answers '
        'within 60s; giving up sooner turns a slow success into an ambiguous charge.',
    ),
    _k(
        'TIMWE_AIRTIME_PURCHASE_ENABLED',
        kind='bool',
        group='timwe',
        doc='Coin purchase via airtime through chargeAmount. Off by default: '
        'enabling it reverses the "SIM cards are for OTP only" policy.',
    ),
    _k(
        'TIMWE_CHARGING_ENABLED',
        kind='bool',
        group='timwe',
        doc='Master switch for chargeAmount. While false nothing is ever sent, '
        'whatever else is configured. Each flow also needs its own switch.',
    ),
    _k(
        'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED',
        kind='bool',
        group='timwe',
        doc='Charge an expired short-code subscriber once for the next period. Off by '
        'default; leave off unless TIMWE confirms it does not renew these itself.',
    ),
    _k(
        'TIMWE_RENEWAL_RETRY_MINUTES',
        kind='int',
        group='timwe',
        doc='Minutes before a renewal charge TIMWE refused (nothing taken) is tried '
        'again. Default 60. Ambiguous charges are never retried.',
    ),
    _k(
        'TIMWE_RENEWAL_WINDOW_DAYS',
        kind='int',
        group='timwe',
        doc='Days after a short-code subscription runs out that renewal keeps being '
        'attempted. Default 7; after that the subscriber must opt in again.',
    ),
    _k('TIMWE_ALLOWED_IPS', kind='csv', group='timwe'),
    # -- timwe smpp -----------------------------------------------------------
    # Deliberately separate from TIMWE_SP_ID / TIMWE_SP_PASSWORD above. Those
    # are the HTTP charging API credentials and are read only by
    # api/integrations/timwe/charge.py. The SMPP link is a different protocol
    # with its own login, and two integration documents quote two different
    # SP identifiers (300263 and 015164), so nothing here is inferred from
    # them -- every SMPP value is set explicitly by an operator.
    _k(
        'SMS_PROVIDER',
        group='sms',
        doc="Which SMS gateway delivers application SMS. 'timwe_smpp' in "
        "production; 'console' logs instead of sending, for local development. "
        'OneVAS has been removed and is not an option.',
    ),
    _k('TIMWE_SMPP_HOST', group='sms', doc='SMPP gateway host, e.g. 10.175.206.42.'),
    _k('TIMWE_SMPP_PORT', kind='int', group='sms', doc='SMPP gateway TCP port, e.g. 6986.'),
    _k(
        'TIMWE_SMPP_SYSTEM_ID',
        group='sms',
        doc='SMPP bind login (system_id). This is the SMPP account name, NOT '
        'the charging API TIMWE_SP_ID -- set it from the SMPP credentials '
        'TIMWE supplied, even if the two happen to match.',
    ),
    _k(
        'TIMWE_SMPP_PASSWORD',
        group='sms',
        doc='SMPP bind password. Secret: resolve through Vault, never log it.',
    ),
    _k(
        'TIMWE_SMPP_SYSTEM_TYPE',
        group='sms',
        doc='SMPP system_type sent on bind. Blank unless TIMWE specify one.',
    ),
    _k(
        'TIMWE_SMPP_SOURCE_ADDR',
        group='sms',
        doc='Source address shown on the handset (the short code or SP ID). '
        'Distinct from system_id: one authenticates the link, this one labels '
        'the message.',
    ),
    _k(
        'TIMWE_SMPP_SOURCE_TON',
        kind='int',
        group='sms',
        doc='Type of Number for the source address. 5 = alphanumeric, '
        '3 = national/short code, 1 = international.',
    ),
    _k(
        'TIMWE_SMPP_SOURCE_NPI',
        kind='int',
        group='sms',
        doc='Numbering Plan Indicator for the source address. 0 = unknown, 1 = ISDN.',
    ),
    _k(
        'TIMWE_SMPP_DEST_TON',
        kind='int',
        group='sms',
        doc='Type of Number for the destination MSISDN. 1 = international.',
    ),
    _k(
        'TIMWE_SMPP_DEST_NPI',
        kind='int',
        group='sms',
        doc='Numbering Plan Indicator for the destination MSISDN. 1 = ISDN.',
    ),
    _k(
        'TIMWE_SMPP_SERVICE_TYPE',
        group='sms',
        doc='SMPP service_type on submit_sm. Blank unless TIMWE require one.',
    ),
    _k(
        'TIMWE_SMPP_REGISTERED_DELIVERY',
        kind='int',
        group='sms',
        doc='registered_delivery on submit_sm. 1 requests a delivery receipt; ' '0 disables DLR.',
    ),
    _k(
        'TIMWE_SMPP_ENQUIRE_LINK_SECONDS',
        kind='int',
        group='sms',
        doc='Keepalive interval on an idle bind.',
    ),
    _k(
        'SMS_SHORT_CODE',
        group='sms',
        doc='The short code subscribers text to subscribe and send STOP to. Default 9286.',
    ),
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
    # -- admin bootstrap ------------------------------------------------------
    _k(
        'ADMIN_PASSWORD',
        group='core',
        doc='Password for the superuser created by `manage.py create_superadmin` '
        'and the setup-admin endpoint. Deliberately optional: an environment '
        'that has already been bootstrapped does not need it, and a default '
        'here once produced a superuser whose password was published in this '
        'repository.',
    ),
    # -- object storage -------------------------------------------------------
    _k('S3_ENDPOINT_URL', group='storage'),
    _k('STORAGE_BUCKET_NAME', group='storage'),
    _k('ACCESS_KEY_ID', group='storage'),
    _k('SECRET_ACCESS_KEY', group='storage'),
    _k('REGION_NAME', group='storage'),
    _k('S3_USE_SSL', kind='bool', group='storage'),
    _k('S3_DEFAULT_ACL', group='storage'),
    _k(
        'S3_QUERYSTRING_AUTH',
        kind='bool',
        group='storage',
        doc='Sign media URLs. Defaults on exactly when S3_DEFAULT_ACL is not '
        'public-read (a private bucket needs signatures).',
    ),
    _k(
        'S3_QUERYSTRING_EXPIRE',
        kind='int',
        group='storage',
        doc='Seconds a signed media URL works (default 3600, 60 to 604800). '
        'Clients refresh expired URLs through POST /api/v1/posts/media/.',
    ),
    _k(
        'MINIO_ROOT_USER',
        group='storage',
        doc='Local MinIO console/API user (docker-compose only; the Kubernetes '
        'deployment uses S3-compatible credentials above).',
    ),
    _k('MINIO_ROOT_PASSWORD', group='storage'),
    # -- media pipeline (api/services/media_pipeline.py, api/tasks/media.py) --
    _k(
        'MEDIA_MAX_UPLOAD_BYTES',
        kind='int',
        group='storage',
        doc='Largest photo or video a post may upload. Default 52428800 (50 MB), '
        'matching DATA_UPLOAD_MAX_MEMORY_SIZE and the web client.',
    ),
    _k(
        'MEDIA_MAX_VIDEO_SECONDS',
        kind='int',
        group='storage',
        doc='Longest video the worker accepts. Default 92: the recorder stops '
        'at 90 and a recording runs a little over.',
    ),
    _k(
        'MEDIA_MAX_IMAGE_PIXELS',
        kind='int',
        group='storage',
        doc='Largest photo, in pixels (width x height), accepted at upload. '
        'Default 40000000. Guards the workers against decompression bombs.',
    ),
    _k(
        'MEDIA_SOURCE_RETENTION_DAYS',
        kind='int',
        group='storage',
        doc='Days an original upload is kept after its post is processed. '
        '0 (default) keeps originals indefinitely. Originals are needed to '
        're-process a post; nothing is deleted before processing succeeds.',
    ),
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
