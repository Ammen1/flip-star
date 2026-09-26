"""The six open gaps from the end-to-end audit, closed.

    10  Comment          one of two write paths charged; the other was free
    13  Creator points   a balance with no ledger behind it
    22  Moderation       a pending queue nothing ever looked at
    26  Webhooks         three unsigned callbacks open to the internet
    27  Data prizes      no OfferingId, so every daily prize failed
    28  Notifications    preferences read by no code; no system notices

They share a file because they share an origin -- one audit pass -- not
because they are one subject. Each section below stands alone.

Two of them are only partly closable in code, and the tests say which part:

* **26** cannot be closed by code at all in the sense that matters. Telebirr
  signs nothing on these three envelopes, so there is no signature to check.
  What is tested here is the allow-list: that it refuses a stranger when
  configured, that it allows everything when not (which is today's
  behaviour, deliberately preserved), and that a forged
  ``X-Forwarded-For`` does not get round it.

* **27** needs an OfferingId from Ethio Telecom that cannot be invented. What
  is tested is that its absence is *reported* -- at deploy time by a system
  check, and again by the prize sweep when winners are actually waiting --
  rather than surfacing as a delivery failure hours after a win.
"""

import json
from datetime import timedelta

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Comment, CommentReply, Notification, NotificationPreference, Reel
from api.models.campaign import Campaign
from api.models.campaign_extended import PostScore
from api.models.contest import CoinTransaction, UserCoinBalance
from api.models.wallet import PointTransaction, WithdrawalRequest
from api.services import moderation_queue, webhook_allowlist
from api.services.notifications import notify_system, push_allowed
from common.security.e2e_encryption import encrypt_payload, generate_keypair
from infrastructure.keys import redis_store
from tests.conftest import grant_subscription

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


# ── shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def author(db):
    return User.objects.create_user(username='author', password='x')


@pytest.fixture
def actor(db):
    """Somebody acting on another person's post, subscribed and funded."""
    user = User.objects.create_user(username='actor', password='x')
    grant_subscription(user)
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.add_purchased(500, payment_method='telebirr')
    return user


@pytest.fixture
def reel(author):
    return Reel.objects.create(user=author, caption='a post')


@pytest.fixture
def server_key(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


def sealed_post(view, user, path, body, server_public):
    """POST a genuinely sealed body to an encrypted endpoint."""
    client_public, client_private = generate_keypair()
    envelope = encrypt_payload(
        body, receiver_public_key_b64=server_public, sender_private_key_b64=client_private
    ).to_dict()
    request = factory.post(
        path,
        data=json.dumps(envelope),
        content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public,
    )
    force_authenticate(request, user=user)
    response = view(request)
    response.render()
    return response


def coins(user):
    return UserCoinBalance.objects.get(user=user).balance


# ═══ 10. Comment charging ═══════════════════════════════════════════════════
#
# The reel's own action charged 2 coins; CommentViewSet wrote the same
# Comment row for nothing. Two write paths to one row, priced differently.


def test_a_comment_through_the_viewset_is_charged(server_key, actor, reel):
    """The gap itself: this route took no money."""
    from api.views.extended import CommentViewSet

    before = coins(actor)
    response = sealed_post(
        CommentViewSet.as_view({'post': 'create'}),
        actor,
        '/api/comments/',
        {'reel': reel.id, 'text': 'nice'},
        server_key,
    )

    assert response.status_code == 201
    assert coins(actor) == before - 2
    assert Comment.objects.filter(reel=reel, user=actor).count() == 1


def test_both_comment_routes_cost_the_same(server_key, author, reel):
    """The requirement: a comment costs 2 coins wherever it is made."""
    from api.views.core import ReelViewSet
    from api.views.extended import CommentViewSet

    via_viewset = User.objects.create_user(username='via_viewset', password='x')
    via_action = User.objects.create_user(username='via_action', password='x')
    for user in (via_viewset, via_action):
        grant_subscription(user)
        balance, _ = UserCoinBalance.objects.get_or_create(user=user)
        balance.add_purchased(500, payment_method='telebirr')

    before_viewset = coins(via_viewset)
    sealed_post(
        CommentViewSet.as_view({'post': 'create'}),
        via_viewset,
        '/api/comments/',
        {'reel': reel.id, 'text': 'one'},
        server_key,
    )
    viewset_cost = before_viewset - coins(via_viewset)

    before_action = coins(via_action)
    request = factory.post(f'/api/reels/{reel.id}/comments/', {'text': 'two'})
    force_authenticate(request, user=via_action)
    response = ReelViewSet.as_view({'post': 'comments'})(request, pk=reel.id)
    response.render()
    action_cost = before_action - coins(via_action)

    assert response.status_code == 201
    assert viewset_cost == action_cost == 2


def test_the_comment_charge_is_recorded_in_the_ledger(server_key, actor, reel):
    from api.views.extended import CommentViewSet

    sealed_post(
        CommentViewSet.as_view({'post': 'create'}),
        actor,
        '/api/comments/',
        {'reel': reel.id, 'text': 'nice'},
        server_key,
    )

    charge = CoinTransaction.objects.filter(user=actor, transaction_type='campaign_comment').first()
    assert charge is not None
    assert charge.coins == -2


def test_commenting_on_your_own_post_is_free(server_key, author, reel):
    """charge_engagement never bills a user for their own post."""
    from api.views.extended import CommentViewSet

    grant_subscription(author)
    balance, _ = UserCoinBalance.objects.get_or_create(user=author)
    balance.add_purchased(500, payment_method='telebirr')
    before = coins(author)

    response = sealed_post(
        CommentViewSet.as_view({'post': 'create'}),
        author,
        '/api/comments/',
        {'reel': reel.id, 'text': 'my own'},
        server_key,
    )

    assert response.status_code == 201
    assert coins(author) == before


def test_a_comment_that_cannot_be_paid_for_is_not_written(server_key, reel):
    """The charge and the row commit together, or neither does.

    This is the failure the reel action was fixed for and this route had
    never faced: a 400 that still leaves a comment behind is a free comment.
    """
    from api.views.extended import CommentViewSet

    broke = User.objects.create_user(username='broke', password='x')
    grant_subscription(broke)
    balance, _ = UserCoinBalance.objects.get_or_create(user=broke)
    # Welcome bonus lands on registration; spend it down to nothing.
    balance.bonus_balance = 0
    balance.earned_balance = 0
    balance.purchased_balance = 0
    balance._sync_balance()
    balance.save()

    response = sealed_post(
        CommentViewSet.as_view({'post': 'create'}),
        broke,
        '/api/comments/',
        {'reel': reel.id, 'text': 'free?'},
        server_key,
    )

    assert response.status_code == 400
    assert Comment.objects.filter(user=broke).count() == 0


def test_replies_are_still_not_charged(server_key, actor, reel, author):
    """Deliberate, and pinned so it is not changed by accident.

    A CommentReply is a different row from a Comment and no route has ever
    charged for one. The requirement prices a *comment*; inventing a price
    for replies here would be changing a business rule rather than closing a
    gap. Recorded as a decision, not an oversight.
    """
    from api.views.extended import CommentReplyViewSet

    parent = Comment.objects.create(user=author, reel=reel, text='parent')
    before = coins(actor)

    response = sealed_post(
        CommentReplyViewSet.as_view({'post': 'create'}),
        actor,
        '/api/comment-replies/',
        {'comment': parent.id, 'text': 'a reply'},
        server_key,
    )

    assert response.status_code == 201
    assert coins(actor) == before
    assert CommentReply.objects.count() == 1


# ═══ 13. The creator-points ledger ══════════════════════════════════════════
#
# UserProfile.points was a bare integer. Every movement overwrote it, so a
# disputed balance could not be reconstructed.


def test_adding_points_writes_a_ledger_row(actor):
    actor.profile.add_points(50, reason='gift_received')

    row = PointTransaction.objects.get(user=actor)
    assert row.points == 50
    assert row.balance_after == 50
    assert row.transaction_type == 'gift_received'


def test_deducting_points_writes_a_negative_row(actor):
    actor.profile.add_points(100, reason='gift_received')
    actor.profile.deduct_points(30, reason='swap')

    # By id, not created_at: auto_now_add on a coarse clock gives both rows
    # the same microsecond, and 'the later one' then depends on which the
    # database happens to return first. The same hazard is documented in
    # SubscriptionPlan._grant_bonus_coins.
    row = PointTransaction.objects.filter(user=actor).order_by('id').last()
    assert row.points == -30
    assert row.balance_after == 70
    assert row.transaction_type == 'swap'


def test_the_ledger_sums_to_the_balance(actor):
    """The property that makes it a ledger rather than a log."""
    actor.profile.add_points(100, reason='gift_received')
    actor.profile.add_points(40, reason='campaign_reward')
    actor.profile.deduct_points(25, reason='withdrawal')
    actor.profile.refresh_from_db()

    total = sum(PointTransaction.objects.filter(user=actor).values_list('points', flat=True))
    assert total == actor.profile.points == 115


def test_balance_after_tracks_each_movement(actor):
    actor.profile.add_points(10, reason='gift_received')
    actor.profile.add_points(10, reason='gift_received')
    actor.profile.add_points(10, reason='gift_received')

    running = list(
        PointTransaction.objects.filter(user=actor)
        .order_by('id')
        .values_list('balance_after', flat=True)
    )
    assert running == [10, 20, 30]


def test_a_refused_deduction_writes_nothing(actor):
    """No partial write, and no phantom row for a movement that never was."""
    actor.profile.add_points(10, reason='gift_received')

    with pytest.raises(ValueError):
        actor.profile.deduct_points(999, reason='withdrawal')

    assert PointTransaction.objects.filter(user=actor).count() == 1
    actor.profile.refresh_from_db()
    assert actor.profile.points == 10


def test_an_unattributed_movement_is_recorded_as_an_adjustment(actor):
    """A caller that names no reason is not silently dropped from the ledger."""
    actor.profile.add_points(5)

    row = PointTransaction.objects.get(user=actor)
    assert row.transaction_type == 'admin_adjustment'


def test_expiry_writes_its_own_row(actor):
    """The one movement that does not go through _apply_delta.

    It zeroes the balance with a direct UPDATE, so it writes its own row --
    and it is the movement a user is most likely to dispute.
    """
    from api.services import points_expiry

    actor.profile.add_points(400, reason='gift_received')
    PointTransaction.objects.filter(user=actor).delete()

    stale = timezone.now() - timedelta(days=points_expiry.INACTIVITY_DAYS + 5)
    CoinTransaction.objects.filter(user=actor).update(created_at=stale)
    User.objects.filter(pk=actor.pk).update(last_login=stale, date_joined=stale)
    actor.refresh_from_db()

    taken = points_expiry.expire_points_for(actor)
    assert taken == 400

    row = PointTransaction.objects.get(user=actor, transaction_type='expiry')
    assert row.points == -400
    assert row.balance_after == 0


def test_coins_never_appear_in_the_points_ledger(actor):
    """Two currencies, two ledgers. A coin movement writes no point row."""
    before = PointTransaction.objects.count()
    actor.profile.add_coins(100)
    assert PointTransaction.objects.count() == before


def test_a_gift_credits_points_as_gift_received(actor, author):
    """The rate is unchanged; what is new is that it leaves a trace."""
    author.profile.add_points(7, reason='gift_received', description='from actor')

    row = PointTransaction.objects.get(user=author)
    assert row.transaction_type == 'gift_received'
    assert row.description == 'from actor'


def test_a_withdrawal_refund_is_distinguishable_from_a_gift(actor):
    """Both are credits. Only the ledger says which."""
    withdrawal = WithdrawalRequest.objects.create(
        user=actor,
        point_amount=60,
        gross_birr=60,
        fee_birr=0,
        net_birr=60,
        conversion_rate=1,
        payout_account='0911000000',
    )
    withdrawal.refund_to_user(reason='rejected')

    row = PointTransaction.objects.get(user=actor)
    assert row.transaction_type == 'withdrawal_refund'
    assert row.points == 60


# ═══ 22. The moderation queue ═══════════════════════════════════════════════
#
# Entries queue as 'pending' and eligibility counts them, so an unreviewed
# entry can carry someone to a prize. Nothing ever looked at the queue.


@pytest.fixture
def campaign(db):
    now = timezone.now()
    return Campaign.objects.create(
        title='daily',
        campaign_type='daily',
        status='active',
        start_date=now - timedelta(days=1),
        entry_deadline=now + timedelta(days=1),
    )


def entry(user, campaign, *, age_hours=0, moderation_status='pending'):
    reel = Reel.objects.create(user=user, caption='entry', is_campaign_post=True)
    score = PostScore.objects.create(
        reel=reel, campaign=campaign, user=user, moderation_status=moderation_status
    )
    when = timezone.now() - timedelta(hours=age_hours)
    PostScore.objects.filter(pk=score.pk).update(created_at=when)
    score.refresh_from_db()
    return score


def test_an_empty_queue_reports_nothing_pending(campaign):
    report = moderation_queue.queue_report()
    assert report['pending'] == 0
    assert report['oldest_hours'] == 0.0


def test_pending_entries_are_counted(actor, campaign):
    entry(actor, campaign)
    entry(actor, campaign)
    entry(actor, campaign, moderation_status='approved')

    assert moderation_queue.queue_report()['pending'] == 2


def test_a_fresh_queue_is_not_stale(actor, campaign):
    entry(actor, campaign, age_hours=1)

    report = moderation_queue.queue_report()
    assert report['pending'] == 1
    assert report['stale'] == 0


def test_an_entry_past_the_threshold_is_stale(actor, campaign):
    entry(actor, campaign, age_hours=moderation_queue.STALE_AFTER_HOURS + 1)

    report = moderation_queue.queue_report()
    assert report['stale'] == 1
    assert report['critical'] == 0


def test_an_entry_past_the_critical_threshold_is_both(actor, campaign):
    """Critical entries are stale too -- the thresholds nest, not partition."""
    entry(actor, campaign, age_hours=moderation_queue.CRITICAL_AFTER_HOURS + 1)

    report = moderation_queue.queue_report()
    assert report['stale'] == 1
    assert report['critical'] == 1


def test_the_report_names_the_oldest_entry(actor, campaign):
    """The number that matters: a small old queue is worse than a big new one."""
    oldest = entry(actor, campaign, age_hours=30)
    entry(actor, campaign, age_hours=1)

    report = moderation_queue.queue_report()
    assert report['oldest_entry_id'] == oldest.pk
    assert report['oldest_hours'] >= 29


def test_a_backlog_is_reported_per_campaign(actor, campaign):
    """One neglected campaign inside a healthy queue is what a total hides.

    And it is the campaign, not the queue, that awards a prize.
    """
    other = Campaign.objects.create(
        title='weekly',
        campaign_type='weekly',
        status='active',
        start_date=timezone.now() - timedelta(days=7),
        entry_deadline=timezone.now() + timedelta(days=1),
    )
    entry(actor, campaign, age_hours=1)
    entry(actor, other, age_hours=48)

    reports = moderation_queue.per_campaign_report()
    assert reports[campaign.pk]['stale'] == 0
    assert reports[other.pk]['critical'] == 1


def test_approved_and_rejected_entries_leave_the_queue(actor, campaign):
    entry(actor, campaign, age_hours=50, moderation_status='approved')
    entry(actor, campaign, age_hours=50, moderation_status='rejected')

    assert moderation_queue.queue_report()['pending'] == 0


def test_the_backlog_task_returns_the_summary(actor, campaign):
    from api.tasks.moderation import report_moderation_backlog

    entry(actor, campaign, age_hours=moderation_queue.CRITICAL_AFTER_HOURS + 2)

    result = report_moderation_backlog()
    assert result['pending'] == 1
    assert result['critical'] == 1


def test_the_backlog_task_is_quiet_on_an_empty_queue(campaign):
    from api.tasks.moderation import report_moderation_backlog

    assert report_moderation_backlog()['pending'] == 0


def test_the_backlog_task_is_scheduled():
    """A report nothing runs is not a report."""
    from api.celery import app

    assert 'report-moderation-backlog' in app.conf.beat_schedule


# ═══ 26. Unsigned webhook allow-listing ═════════════════════════════════════


def webhook_request(ip='203.0.113.9', **extra):
    request = factory.post(
        '/api/webhooks/telebirrB2C/', data='<xml/>', content_type='text/xml', **extra
    )
    request.META['REMOTE_ADDR'] = ip
    return request


def test_without_an_allowlist_everything_is_allowed(settings):
    """Today's behaviour, deliberately preserved.

    Shipping a populated default would mean guessing Telebirr's egress
    addresses, and a wrong guess silently drops real payout confirmations --
    a worse failure than the one being fixed.
    """
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = []

    assert webhook_allowlist.is_configured() is False
    assert webhook_allowlist.request_allowed(webhook_request()) is True


def test_a_configured_address_is_allowed(settings):
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.9']

    assert webhook_allowlist.request_allowed(webhook_request(ip='203.0.113.9')) is True


def test_an_address_outside_the_allowlist_is_refused(settings):
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.9']

    assert webhook_allowlist.request_allowed(webhook_request(ip='198.51.100.7')) is False


def test_a_cidr_range_is_honoured(settings):
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.0/24']

    assert webhook_allowlist.ip_allowed('203.0.113.200') is True
    assert webhook_allowlist.ip_allowed('203.0.114.1') is False


def test_a_comma_separated_string_is_accepted(settings):
    """Environment-driven settings arrive as strings."""
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = '203.0.113.9, 198.51.100.7'

    assert webhook_allowlist.ip_allowed('198.51.100.7') is True
    assert webhook_allowlist.ip_allowed('192.0.2.1') is False


def test_a_malformed_entry_does_not_open_the_list(settings):
    """A typo in an allow-list is a hole in it. It is dropped, not honoured."""
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['not-an-ip', '203.0.113.9']

    assert webhook_allowlist.ip_allowed('203.0.113.9') is True
    assert webhook_allowlist.ip_allowed('198.51.100.7') is False


def test_a_forged_forwarded_header_does_not_bypass_the_list(settings):
    """Without this, an allow-list is bypassed by setting a header.

    X-Forwarded-For is honoured only from a configured trusted proxy --
    see common/security/client_ip.py.
    """
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.9']
    settings.TRUSTED_PROXY_IPS = ['127.0.0.1']

    request = webhook_request(ip='198.51.100.7', HTTP_X_FORWARDED_FOR='203.0.113.9')
    assert webhook_allowlist.request_allowed(request) is False


def test_an_unparseable_peer_is_refused_when_a_list_is_in_force(settings):
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.9']

    assert webhook_allowlist.ip_allowed('') is False


def test_refuse_returns_a_403_only_for_a_stranger(settings):
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.9']

    assert webhook_allowlist.refuse(webhook_request(ip='203.0.113.9'), webhook='x') is None
    denied = webhook_allowlist.refuse(webhook_request(ip='198.51.100.7'), webhook='x')
    assert denied is not None
    assert denied.status_code == 403


@pytest.mark.parametrize(
    'module_path, func_name',
    [
        ('api.views.direct_debit', 'telebirr_b2c_webhook'),
        ('api.views.direct_debit', 'telebirr_direct_debit_webhook'),
        ('api.views.wallet', 'telebirr_ussd_webhook'),
    ],
)
def test_every_unsigned_webhook_consults_the_allowlist(module_path, func_name):
    """All three, not just the one that pays money out.

    Read from the source rather than exercised, because each handler needs a
    different SOAP envelope to get past its own parsing -- and what is being
    asserted is that the guard is present at all.
    """
    source = function_source(module_path, func_name)
    assert 'webhook_refuse' in source, f'{func_name} does not consult the allow-list'


def test_a_refused_webhook_never_reaches_the_handler(settings):
    """End to end: the refusal happens before any body parsing."""
    from api.views.direct_debit import telebirr_b2c_webhook

    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = ['203.0.113.9']

    request = factory.post('/api/webhooks/telebirrB2C/', data='<garbage/>', content_type='text/xml')
    request.META['REMOTE_ADDR'] = '198.51.100.7'
    response = telebirr_b2c_webhook(request)
    assert response.status_code == 403


# ═══ 27. Data prize provisioning config ═════════════════════════════════════


def test_an_unset_offering_id_is_reported_at_deploy_time(settings):
    """The gap: every daily data prize failed, and nothing said why until
    a delivery attempt hours after the win."""
    from api.checks import check_data_prize_provisioning

    settings.DATA_PRIZE_OFFERING_ID = ''
    settings.CRM_OFFERING_ID = ''

    ids = [w.id for w in check_data_prize_provisioning(None)]
    assert 'flipstar.W001' in ids


def test_a_configured_offering_id_is_not_reported(settings):
    from api.checks import check_data_prize_provisioning

    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    settings.DATA_PRIZE_PROVISIONING_NUMBER = '0911227833'

    assert check_data_prize_provisioning(None) == []


def test_the_crm_offering_id_is_accepted_as_a_fallback(settings):
    from api.checks import check_data_prize_provisioning

    settings.DATA_PRIZE_OFFERING_ID = ''
    settings.CRM_OFFERING_ID = 'OFFER-FALLBACK'
    settings.DATA_PRIZE_PROVISIONING_NUMBER = '0911227833'

    assert check_data_prize_provisioning(None) == []


def test_a_missing_provisioning_number_is_reported(settings):
    from api.checks import check_data_prize_provisioning

    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    settings.DATA_PRIZE_PROVISIONING_NUMBER = ''

    ids = [w.id for w in check_data_prize_provisioning(None)]
    assert 'flipstar.W002' in ids


def test_an_open_webhook_is_reported_outside_debug(settings):
    from api.checks import check_webhook_allowlist

    settings.DEBUG = False
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = []

    ids = [w.id for w in check_webhook_allowlist(None)]
    assert 'flipstar.W003' in ids


def test_a_developer_machine_is_not_nagged(settings):
    from api.checks import check_webhook_allowlist

    settings.DEBUG = True
    settings.TELEBIRR_WEBHOOK_ALLOWED_IPS = []

    assert check_webhook_allowlist(None) == []


def test_waiting_data_prizes_are_reported_when_no_package_is_configured(settings, actor, caplog):
    """The other moment it matters: winners are actually waiting.

    A warning tied to a real count of waiting winners is the one an operator
    acts on -- and the config can be removed long after deployment.
    """
    from api.models.gift import WinnerGiftTransaction
    from api.tasks.prizes import _report_missing_data_package

    settings.DATA_PRIZE_OFFERING_ID = ''
    settings.CRM_OFFERING_ID = ''
    WinnerGiftTransaction.objects.create(
        winner=actor,
        winner_type='daily',
        amount=1024,
        payment_method='crm',
        status='pending',
        idempotency_key='test-waiting-1',
    )

    with caplog.at_level('ERROR'):
        _report_missing_data_package()

    assert 'PRIZE_DATA_PACKAGE_UNCONFIGURED' in caplog.text


def test_nothing_is_reported_when_no_prizes_are_waiting(settings, caplog):
    from api.tasks.prizes import _report_missing_data_package

    settings.DATA_PRIZE_OFFERING_ID = ''
    settings.CRM_OFFERING_ID = ''

    with caplog.at_level('ERROR'):
        _report_missing_data_package()

    assert 'PRIZE_DATA_PACKAGE_UNCONFIGURED' not in caplog.text


# ═══ 28. Notification preferences and system notices ════════════════════════


@pytest.fixture
def pushes(monkeypatch):
    """Capture what the post_save signal tries to push."""
    sent = []

    class FakeTask:
        @staticmethod
        def delay(recipient_id, payload):
            sent.append(('fcm', recipient_id, payload))

    import api.integrations.push.webpush as webpush
    import api.tasks as tasks

    monkeypatch.setattr(tasks, 'send_push_notification', FakeTask, raising=False)
    monkeypatch.setattr(
        webpush,
        'send_web_push_to_user',
        lambda user, payload: sent.append(('web', user.id, payload)),
        raising=False,
    )
    return sent


def prefs_for(user, **flags):
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    for field, value in flags.items():
        setattr(prefs, field, value)
    prefs.save()
    return prefs


def test_push_is_sent_when_nothing_is_switched_off(pushes, author, actor):
    prefs_for(author)
    Notification.objects.create(
        recipient=author, sender=actor, notification_type='like', message='liked'
    )
    assert pushes


def test_the_master_switch_suppresses_every_push(pushes, author, actor):
    """The gap: turning push off in settings changed nothing at all."""
    prefs_for(author, push_notifications=False)
    Notification.objects.create(
        recipient=author, sender=actor, notification_type='like', message='liked'
    )
    assert pushes == []


def test_a_per_type_switch_suppresses_only_that_type(pushes, author, actor):
    prefs_for(author, likes=False)

    Notification.objects.create(
        recipient=author, sender=actor, notification_type='like', message='liked'
    )
    assert pushes == []

    Notification.objects.create(
        recipient=author, sender=actor, notification_type='comment', message='commented'
    )
    assert len(pushes) == 2  # fcm + web, for the comment only


def test_the_in_app_row_survives_a_suppressed_push(pushes, author, actor):
    """Only the push is suppressed.

    The in-app list is the user's record of what happened to their account;
    silently dropping rows from it would lose information rather than reduce
    noise.
    """
    prefs_for(author, push_notifications=False)
    Notification.objects.create(
        recipient=author, sender=actor, notification_type='like', message='liked'
    )

    assert Notification.objects.filter(recipient=author).count() == 1
    assert pushes == []


def test_moderation_notices_cannot_be_muted(pushes, author, actor):
    """A user cannot opt out of being told their content was actioned."""
    prefs_for(author, likes=False, comments=False, follows=False, mentions=False, gifts=False)

    Notification.objects.create(
        recipient=author, sender=actor, notification_type='moderation', message='removed'
    )
    assert pushes


def test_the_master_switch_even_silences_moderation(pushes, author, actor):
    """Off means off. The per-type exemption is not a master override."""
    prefs_for(author, push_notifications=False)
    Notification.objects.create(
        recipient=author, sender=actor, notification_type='moderation', message='removed'
    )
    assert pushes == []


def test_a_missing_preference_row_allows_push(author):
    """A missing row is a gap in our data, not a statement by the user."""
    NotificationPreference.objects.filter(user=author).delete()
    assert push_allowed(author, 'like') is True


def test_an_unknown_type_is_allowed(author):
    """A new type should be visible and then mapped, not silently swallowed."""
    prefs_for(author)
    assert push_allowed(author, 'something_new') is True


def test_a_system_notification_has_no_sender(author):
    """The schema change: sender was non-nullable, so a system notice had no
    valid sender and could not be written at all."""
    notification = notify_system(author, 'prize_won', 'You won!')

    assert notification is not None
    assert notification.sender is None
    assert notification.is_system is True


def test_the_system_switch_governs_system_notices(pushes, author):
    prefs_for(author, system=False)
    notify_system(author, 'prize_won', 'You won!')

    assert Notification.objects.filter(recipient=author).count() == 1
    assert pushes == []


def test_notify_system_refuses_a_non_system_type(author, caplog):
    """A 'like' has a sender by definition; it must not come through here."""
    with caplog.at_level('ERROR'):
        assert notify_system(author, 'like', 'nope') is None


def test_notify_system_never_raises(author):
    """Callers are mid-way through activating a subscription or paying a prize."""
    assert notify_system(None, 'prize_won', 'nobody') is None


# ── the events that had no notification at all ──────────────────────────────


def test_activating_a_subscription_notifies_the_user(author):
    from api.models.subscription import SubscriptionPlan

    tier = seeded_tier()
    plan = SubscriptionPlan.objects.create(user=author, tier=tier)
    plan.activate()

    notification = Notification.objects.get(
        recipient=author, notification_type='subscription_activated'
    )
    assert notification.sender is None
    assert 'active' in notification.message


def test_renewing_a_subscription_says_renewed_not_activated(author):
    """A second period is a renewal. The distinction is read before
    end_date is overwritten, because there is no record of it afterwards."""
    from api.models.subscription import SubscriptionPlan

    tier = seeded_tier()
    plan = SubscriptionPlan.objects.create(user=author, tier=tier)
    plan.activate()

    # Period ends, then a renewal charge activates it again.
    plan.end_date = timezone.now() - timedelta(days=1)
    plan.status = 'expired'
    plan.save()
    plan.activate()

    assert (
        Notification.objects.filter(
            recipient=author, notification_type='subscription_renewed'
        ).count()
        == 1
    )


def test_a_duplicate_activation_webhook_notifies_once(author):
    """Same guard as the bonus grant, and for the same reason: a provider
    may deliver the activation callback more than once."""
    from api.models.subscription import SubscriptionPlan

    tier = seeded_tier()
    plan = SubscriptionPlan.objects.create(user=author, tier=tier)
    plan.activate()
    plan.activate()  # duplicate webhook, still inside the period

    assert Notification.objects.filter(recipient=author).count() == 1


def test_winning_a_prize_notifies_the_winner(author, campaign):
    """Winners previously learned of a cash prize only when the money
    arrived -- up to twenty days later, or never if delivery failed."""
    from api.services.prize_delivery import award

    prize, created = award(campaign, author, 'daily')

    assert created is True
    notification = Notification.objects.get(recipient=author, notification_type='prize_won')
    assert notification.sender is None


def test_re_running_winner_selection_does_not_congratulate_twice(author, campaign):
    from api.services.prize_delivery import award

    award(campaign, author, 'daily')
    award(campaign, author, 'daily')

    assert Notification.objects.filter(recipient=author, notification_type='prize_won').count() == 1


def test_delivering_a_prize_notifies_the_winner(author, campaign):
    from api.services.prize_delivery import award

    prize, _ = award(campaign, author, 'daily')
    prize.mark_success('CRM-123')

    assert (
        Notification.objects.filter(recipient=author, notification_type='prize_delivered').count()
        == 1
    )


def test_a_repeated_delivery_callback_notifies_once(author, campaign):
    """mark_success is reached from a retry and from a provider callback
    that may arrive twice."""
    from api.services.prize_delivery import award

    prize, _ = award(campaign, author, 'daily')
    prize.mark_success('CRM-123')
    prize.mark_success('CRM-123')

    assert (
        Notification.objects.filter(recipient=author, notification_type='prize_delivered').count()
        == 1
    )


def test_a_paid_withdrawal_notifies_the_user(actor, monkeypatch):
    """Paid was announced by SMS only; there was nothing in the app."""
    import api.services.withdrawal_sms as withdrawal_sms

    monkeypatch.setattr(withdrawal_sms, '_send', lambda *a, **k: True)

    withdrawal = WithdrawalRequest.objects.create(
        user=actor,
        point_amount=100,
        gross_birr=100,
        fee_birr=0,
        net_birr=95,
        conversion_rate=1,
        payout_account='0911000000',
    )
    withdrawal_sms.notify_paid(withdrawal)

    notification = Notification.objects.get(recipient=actor, notification_type='withdrawal_paid')
    assert '95' in notification.message


def seeded_tier():
    """An active tier from the seeded set.

    Tiers carry provider identifiers (spid, service_id, application_key)
    that a hand-built row would have to invent, so tests take one that
    already exists rather than constructing one.
    """
    from api.models import SubscriptionTier

    tier = SubscriptionTier.objects.filter(is_active=True).first()
    assert tier is not None, 'no seeded subscription tier to test against'
    return tier


def function_source(module_path, func_name):
    """The source of a module-level function, read from the file.

    ``inspect.getsource`` on a DRF view returns the ``@api_view`` wrapper --
    three lines of ``def view(request, *args, **kwargs)`` that contain none
    of the decorated function's body. Slicing the file is the only way to
    see what the handler actually does.
    """
    import importlib

    module = importlib.import_module(module_path)
    lines = open(module.__file__, encoding='utf-8').read().split('\n')

    start = next(i for i, line in enumerate(lines) if line.startswith(f'def {func_name}('))
    end = start + 1
    while end < len(lines) and not (lines[end] and not lines[end][0].isspace()):
        end += 1
    return '\n'.join(lines[start:end])


# ── the switches have to be reachable through the API ───────────────────────
#
# A gate that reads a field nobody can set is not a preference, it is a
# constant. These two endpoints are what the web client actually calls --
# they carry their own hardcoded field list, separate from
# NotificationPreferenceSerializer.


def test_the_settings_endpoint_returns_every_switch(actor, server_key):
    from api.views.core import get_notification_settings

    client_public, client_private = generate_keypair()
    request = factory.get('/api/notifications/me/', HTTP_X_CLIENT_PUBLIC_KEY=client_public)
    force_authenticate(request, user=actor)
    response = get_notification_settings(request)
    response.render()

    from common.security.e2e_encryption import decrypt_payload

    body = json.loads(response.content)
    if {'encrypted', 'nonce', 'checksum'} <= body.keys():
        body = json.loads(
            decrypt_payload(
                body['encrypted'], body['nonce'], server_key, body['checksum'], client_private
            )
        )

    from api.services.notifications import PREFERENCE_FIELD

    needed = {field for field in PREFERENCE_FIELD.values() if field} | {'push_notifications'}
    missing = needed - set(body)
    assert not missing, f'the push gate reads {missing}, which the API does not return'


def test_every_gated_switch_can_be_changed(actor):
    """Read from the endpoint's own field list rather than exercised.

    Each switch would otherwise need its own sealed round trip, and what
    matters is that none of them is missing from the list.
    """
    source = function_source('api.views.core', 'update_notification_settings')

    from api.services.notifications import PREFERENCE_FIELD

    for field in {f for f in PREFERENCE_FIELD.values() if f} | {'push_notifications'}:
        assert f"'{field}'" in source, f'{field} cannot be changed through the API'


def test_every_notification_type_maps_to_a_switch_or_none():
    """A type absent from the map is allowed through by default.

    That is the right default -- a new type should be visible and then
    mapped, not silently swallowed -- but it should be a decision, so this
    fails when a type is added to the model and not considered here.
    """
    from api.models import Notification
    from api.services.notifications import PREFERENCE_FIELD

    declared = {value for value, _label in Notification.NOTIFICATION_TYPES}
    unmapped = declared - set(PREFERENCE_FIELD)
    assert not unmapped, f'{unmapped} have no entry in PREFERENCE_FIELD'


def test_every_system_type_is_governed_by_the_system_switch():
    from api.models import Notification
    from api.services.notifications import PREFERENCE_FIELD

    for notification_type in Notification.SYSTEM_TYPES:
        assert PREFERENCE_FIELD[notification_type] == 'system'
