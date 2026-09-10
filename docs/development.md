# Development

## Setup

See the [README](../README.md#local-development). Short version:

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Where code goes

| You are writing | Put it in |
|---|---|
| A new endpoint | `api/views/<domain>.py` + a route in `api/urls.py` |
| Request/response shape | `api/serializers/<domain>.py` |
| A business workflow | `api/services/<domain>/` |
| A call to Telebirr/TIMWE | `api/integrations/<provider>/` |
| A model | `api/models/<domain>.py`, then export it from `api/models/__init__.py` |
| A background job | `api/tasks/`, then export from `api/tasks/__init__.py` |
| An operational script | `api/management/commands/` — **not** an HTTP endpoint |
| A reusable permission | `common/permissions/` |
| Anything importing `api` | Not `common/` or `infrastructure/` |

## Adding a model

1. Define it in the appropriate `api/models/<domain>.py`.
2. Export it from `api/models/__init__.py` and add it to `__all__`.
3. `python manage.py makemigrations api`
4. Update the expected count in
   `tests/integration/test_model_registry.py::test_model_count_is_stable`.
5. Run `pytest tests/integration/test_model_registry.py`.

Do **not** add `PhoneOTP` or `PasswordResetToken` to the exports. Their tables
were dropped by migrations 0051 and 0054; registering them makes
`makemigrations` want to recreate them. A test guards this.

## Adding an endpoint

Keep the view thin:

```python
# api/views/wallet.py
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_withdrawal(request):
    serializer = WithdrawalRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    withdrawal = create_withdrawal(user=request.user, **serializer.validated_data)

    return Response(WithdrawalSerializer(withdrawal).data, status=201)
```

The workflow lives in `api/services/`, raises `common.exceptions` types, and the
DRF handler in `common/exceptions/handlers.py` maps them to responses.

### Error handling

Raise a domain exception rather than returning an ad-hoc dict:

```python
from common.exceptions import InsufficientFunds

if balance.earned_balance < amount:
    raise InsufficientFunds(available=balance.earned_balance, required=amount)
```

## Logging

Use `logging`, never `print`. The codebase still contains ~480 `print()` calls
from before structured logging existed; replace them opportunistically.

```python
import logging
logger = logging.getLogger(__name__)

logger.info('Withdrawal created', extra={'transaction_id': str(withdrawal.id)})
```

`request_id` and `user_id` are injected automatically by
`common.middleware.logging.RequestContextFilter`.

**Never log** an OTP, token, password, or provider credential. A redaction
filter exists as a backstop, not as permission.

## Tests

```bash
pytest                       # all
pytest -m unit               # no DB
pytest -m integration        # DB-backed
pytest -m financial          # wallet / payment behaviour
pytest tests/unit/test_settings_and_config.py -v
```

Mark tests so the fast suite stays fast:

```python
pytestmark = pytest.mark.unit
```

### The two suites that must not fail

- `tests/integration/test_url_contract.py` — a failure means an API consumer
  breaks. The mobile client is released and cannot be updated in lockstep.
- `tests/integration/test_model_registry.py` — a failure means a table rename,
  which requires a data migration.

## Lint

```bash
ruff check .
ruff check . --fix
ruff format .
```

Ruff replaces black + isort + flake8 + pyupgrade. Configuration is in
`pyproject.toml`; migrations are excluded.

## Conventions

- **Modules and functions:** `snake_case`. **Classes:** `PascalCase`.
- **Services** are verbs: `create_withdrawal`, `process_callback`.
- **Absolute imports** across package boundaries (`from api.models import Reel`),
  relative only between close siblings.
- **Money is `Decimal`**, never `float`, all the way to the serializer boundary.
- **Quote style:** single, enforced by `ruff format`.

## Things that will surprise you

- `config.settings` is a *package* that dispatches on `DJANGO_ENV`. The old
  `config/settings.py` module is gone; the import path still works.
- Production settings raise `ImproperlyConfigured` at import when misconfigured.
  That is intentional.
- `api/serializers/subscription.py` does not import — it references a
  `Subscription` model that `models/subscription.py` never defined. It is dead
  code, has never been imported by anything, and is left as-is pending deletion.
- `makemigrations --check` reports one pre-existing drift
  (`Alter field media on message`). It exists at the base commit and is not
  caused by the restructure.
