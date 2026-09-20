"""
A new message has to reach the person it was sent to.

The report: messages arrive and nothing tells the recipient. The count
endpoint was not at fault -- ``/messages/unread-count/`` has existed since
messaging was built, honours each conversation's read marker, and was simply
never called by the web client, whose badge was a ``useState(0)`` with no
setter. So the server half is what these tests pin: the numbers the badge
will now be drawn from, and the read marker that has to clear them.

The properties that matter for a notification, as opposed to a counter:

* a message from somebody else counts, and my own does not -- otherwise
  sending a reply would light up my own badge;
* asking twice does not count twice, which is what "do not repeatedly notify
  for the same message" means for a count derived on every request;
* the count survives a reload, because it is derived from rows rather than
  kept in the client;
* opening the conversation clears it, and a *later* message starts it again.

Written against the real encrypted transport, so a change to the endpoint's
plumbing cannot pass here and fail in the browser.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models.messaging import Conversation, Message, MessageRead
from common.security.e2e_encryption import decrypt_payload

pytestmark = pytest.mark.django_db


# ─── the two people, and the thread between them ─────────────────────────────


@pytest.fixture
def recipient():
    return User.objects.create_user(username='amina', password='x')


@pytest.fixture
def sender():
    return User.objects.create_user(username='dawit', password='x')


@pytest.fixture
def conversation(recipient, sender):
    conv = Conversation.objects.create()
    conv.participants.add(recipient, sender)
    return conv


def say(conversation, sender, text='selam'):
    """A message, the way the messaging view creates one."""
    msg = Message.objects.create(
        conversation=conversation,
        sender=sender,
        text=text,
        media_type=Message.MEDIA_TEXT,
        delivery_status=Message.DELIVERY_SENT,
    )
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=['last_message_at'])
    return msg


# ─── talking to the endpoints the way the browser does ───────────────────────


@pytest.fixture
def badge(encrypted_client_keys):
    """Read the unread count as a signed-in client would.

    The view sits behind ``@encrypted_endpoint``; ``encrypted_client_keys``
    (tests/conftest.py) stands the server keypair up in an in-memory Redis so
    there is a key to seal the reply with. A *fresh* APIClient each call, so
    every one of these is a cold request -- which is what makes the
    "survives a reload" test mean anything.
    """
    server_public_key, public, private = encrypted_client_keys

    def _badge(user):
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(reverse('dm-unread-count'), HTTP_X_CLIENT_PUBLIC_KEY=public)
        assert response.status_code == 200, response.status_code
        response.render()
        raw = json.loads(response.content)
        # Insisted on rather than tolerated: if the reply ever came back in
        # the clear these tests would keep passing while the browser broke.
        assert {'encrypted', 'nonce', 'checksum'} <= raw.keys(), 'reply was not sealed'
        raw = json.loads(
            decrypt_payload(
                raw['encrypted'], raw['nonce'], server_public_key, raw['checksum'], private
            )
        )
        return raw['unread_count']

    return _badge


@pytest.fixture
def open_thread(encrypted_client_keys):
    """Open a conversation -- the POST the thread view fires on load."""
    server_public_key, public, private = encrypted_client_keys

    def _open(user, conversation):
        from common.security.e2e_encryption import encrypt_payload

        sealed = encrypt_payload({}, server_public_key, private)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            reverse('dm-conv-read', args=[conversation.id]),
            sealed.to_dict(),
            format='json',
            HTTP_X_CLIENT_PUBLIC_KEY=public,
        )
        assert response.status_code == 200, response.status_code
        return response

    return _open


# ─── 1. a new message updates the unread state ───────────────────────────────


def test_nothing_unread_before_anybody_says_anything(recipient, conversation, badge):
    assert badge(recipient) == 0


def test_a_new_message_makes_the_count_go_up(recipient, sender, conversation, badge):
    """The reported fault, at the layer the badge reads from."""
    say(conversation, sender)

    assert badge(recipient) == 1


def test_each_new_message_counts(recipient, sender, conversation, badge):
    say(conversation, sender, 'one')
    say(conversation, sender, 'two')
    say(conversation, sender, 'three')

    assert badge(recipient) == 3


def test_my_own_message_does_not_notify_me(recipient, sender, conversation, badge):
    """Sending would otherwise raise a badge on the sender's own nav."""
    say(conversation, sender=recipient)

    assert badge(recipient) == 0
    # ...and it does reach the other person.
    assert badge(sender) == 1


def test_messages_in_somebody_elses_conversation_are_not_mine(recipient, sender, badge):
    stranger = User.objects.create_user(username='hanna', password='x')
    theirs = Conversation.objects.create()
    theirs.participants.add(sender, stranger)
    say(theirs, sender)

    assert badge(recipient) == 0
    assert badge(stranger) == 1


def test_unread_messages_across_conversations_add_up(recipient, sender, conversation, badge):
    """The badge is one number over one icon, so it spans every thread."""
    other_sender = User.objects.create_user(username='kalkidan', password='x')
    second = Conversation.objects.create()
    second.participants.add(recipient, other_sender)

    say(conversation, sender)
    say(second, other_sender)
    say(second, other_sender)

    assert badge(recipient) == 3


# ─── 2. the same message is not notified twice ───────────────────────────────


def test_asking_again_does_not_count_the_message_again(recipient, sender, conversation, badge):
    """The badge polls. If a poll consumed or accumulated anything, a minute
    later the same message would be counted twice."""
    say(conversation, sender)

    assert badge(recipient) == 1
    assert badge(recipient) == 1
    assert badge(recipient) == 1


def test_the_count_is_unchanged_by_reading_it(recipient, sender, conversation, badge):
    """Reading the count is not reading the messages: only opening the
    conversation may clear it."""
    say(conversation, sender)
    badge(recipient)

    assert MessageRead.objects.filter(user=recipient, conversation=conversation).exists() is False


# ─── 3. the count survives a reload ──────────────────────────────────────────


def test_the_count_survives_a_reload(recipient, sender, conversation, badge):
    """Each call here is a new client with no state carried over -- the same
    situation as a refreshed tab. The count comes back because it is derived
    from the messages and the read marker, not remembered anywhere."""
    say(conversation, sender)
    say(conversation, sender)

    first_load = badge(recipient)
    after_reload = badge(recipient)

    assert first_load == 2
    assert after_reload == 2


# ─── 4. opening the message marks it read ────────────────────────────────────


def test_opening_the_conversation_clears_the_badge(
    recipient, sender, conversation, badge, open_thread
):
    """The whole sequence the issue describes: message → unread → open → read."""
    say(conversation, sender)
    assert badge(recipient) == 1

    open_thread(recipient, conversation)

    assert badge(recipient) == 0


def test_opening_records_a_read_marker(recipient, sender, conversation, open_thread):
    say(conversation, sender)

    open_thread(recipient, conversation)

    marker = MessageRead.objects.get(user=recipient, conversation=conversation)
    assert marker.last_read_at is not None


def test_opening_again_does_not_undo_anything(recipient, sender, conversation, badge, open_thread):
    """The thread view re-fires the read POST on every poll while open."""
    say(conversation, sender)
    open_thread(recipient, conversation)
    open_thread(recipient, conversation)

    assert badge(recipient) == 0
    assert MessageRead.objects.filter(user=recipient, conversation=conversation).count() == 1


def test_reading_my_thread_does_not_clear_the_other_persons(
    recipient, sender, conversation, badge, open_thread
):
    say(conversation, sender)
    say(conversation, sender=recipient)

    open_thread(recipient, conversation)

    assert badge(recipient) == 0
    assert badge(sender) == 1, 'the other side still has something to read'


def test_reading_one_conversation_leaves_the_others_unread(
    recipient, sender, conversation, badge, open_thread
):
    other_sender = User.objects.create_user(username='selam', password='x')
    second = Conversation.objects.create()
    second.participants.add(recipient, other_sender)
    say(conversation, sender)
    say(second, other_sender)

    open_thread(recipient, conversation)

    assert badge(recipient) == 1


def test_a_message_sent_after_reading_is_unread_again(
    recipient, sender, conversation, badge, open_thread
):
    """The marker is a timestamp, so this is the case it exists for -- and the
    one a naive 'mark everything read' flag would get wrong."""
    say(conversation, sender, 'first')
    open_thread(recipient, conversation)
    assert badge(recipient) == 0

    say(conversation, sender, 'second')

    assert badge(recipient) == 1


def test_somebody_who_is_not_in_the_conversation_cannot_mark_it_read(
    recipient, sender, conversation, badge, open_thread
):
    intruder = User.objects.create_user(username='outsider', password='x')
    say(conversation, sender)

    # open_thread asserts a 200, so a refusal surfaces here as that assertion
    # failing -- which is the outcome being pinned.
    with pytest.raises(AssertionError):
        open_thread(intruder, conversation)

    assert MessageRead.objects.filter(conversation=conversation, user=intruder).exists() is False
    assert badge(recipient) == 1, 'their badge is untouched'


# ─── 5. the endpoint is not open to anyone ───────────────────────────────────


def test_a_signed_out_visitor_has_no_count(encrypted_client_keys):
    _, public, _ = encrypted_client_keys
    response = APIClient().get(reverse('dm-unread-count'), HTTP_X_CLIENT_PUBLIC_KEY=public)

    assert response.status_code in (401, 403), response.status_code
    assert b'unread_count' not in response.content
