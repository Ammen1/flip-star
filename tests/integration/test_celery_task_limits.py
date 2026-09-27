"""Audit H-06: every prefork task is bounded, and the media override is sane.

A task with no time limit holds its worker slot for as long as it likes. The
worker runs ``--concurrency=4`` on one staging replica, so four of them stop all
background work: subscription renewals, SMS, prize payouts, media.

These tests pin the limits rather than the implementation, so removing the
global setting or dropping a per-task override fails here instead of in
production six months later.
"""

import pytest
from django.conf import settings

pytestmark = pytest.mark.integration

#: Tasks Celery cannot time-limit, with the reason. Kept explicit so an addition
#: here is a deliberate decision rather than an omission.
_POOL_EXEMPT = {
    # k8s/base/deployment-sms-worker.yaml runs --pool=solo so the SMPP bind
    # survives; Celery enforces time limits in the prefork pool only. Bounded
    # instead by the SMPP client's SUBMIT_TIMEOUT_SECONDS.
    'api.tasks.sms.deliver_sms',
}


def _registered_tasks():
    from api.celery import app

    app.loader.import_default_modules()
    return {
        name: task
        for name, task in app.tasks.items()
        if name.startswith('api.tasks.') or name.startswith('api.')
        if not name.startswith('celery.')
    }


def test_a_global_time_limit_is_configured():
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT, 'H-06: no global soft time limit'
    assert settings.CELERY_TASK_TIME_LIMIT, 'H-06: no global hard time limit'


def test_the_soft_limit_is_below_the_hard_limit():
    """Otherwise the hard kill lands first and the soft handler never runs."""
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT < settings.CELERY_TASK_TIME_LIMIT


def test_the_global_limit_is_a_real_bound():
    """A limit measured in hours is not a limit. pywebpush shipped a 10000s one."""
    assert 0 < settings.CELERY_TASK_SOFT_TIME_LIMIT <= 600
    assert 0 < settings.CELERY_TASK_TIME_LIMIT <= 900


def test_every_task_resolves_to_a_finite_limit():
    """Either its own override, or the global default it inherits."""
    unbounded = []
    for name, task in _registered_tasks().items():
        if name in _POOL_EXEMPT:
            continue
        soft = task.soft_time_limit or settings.CELERY_TASK_SOFT_TIME_LIMIT
        hard = task.time_limit or settings.CELERY_TASK_TIME_LIMIT
        if not soft or not hard:
            unbounded.append(name)
    assert not unbounded, f'tasks with no effective time limit: {sorted(unbounded)}'


def test_media_processing_overrides_the_global_limit_upward():
    """The one task whose real work legitimately exceeds 300s."""
    from api.tasks.media import process_reel_media

    assert process_reel_media.soft_time_limit > settings.CELERY_TASK_SOFT_TIME_LIMIT
    assert process_reel_media.time_limit > process_reel_media.soft_time_limit


def test_media_processing_is_still_finite():
    from api.tasks.media import process_reel_media

    assert (
        process_reel_media.time_limit <= 1800
    ), 'a wedged FFmpeg must still be reclaimed within a sane window'


def test_per_task_overrides_keep_soft_below_hard():
    offenders = []
    for name, task in _registered_tasks().items():
        soft, hard = task.soft_time_limit, task.time_limit
        if soft and hard and soft >= hard:
            offenders.append((name, soft, hard))
    assert not offenders, f'soft limit at or above hard limit: {offenders}'


def test_the_pool_exemption_list_still_matches_reality():
    """If deliver_sms stops existing, the exemption should not linger."""
    tasks = _registered_tasks()
    for name in _POOL_EXEMPT:
        assert name in tasks, (
            f'{name} is exempted from the time-limit requirement but is no longer '
            'a registered task; remove it from _POOL_EXEMPT.'
        )
