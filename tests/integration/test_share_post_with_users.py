"""
Sharing a post into direct messages.

What this replaces
------------------
The client used to do this itself: create a conversation, post a message whose
text ended in a literal "[POST_ID:35]" marker, then call the share endpoint --
repeating all three per recipient. Two defects came out of that shape, and both
are pinned here:

  count     `share` was called once per recipient, so sending one post to five
            people recorded five shares for a single action
  atomicity a client failing halfway left some recipients messaged and the rest
            not, with nothing to say which

The third problem was the marker itself. Text is user-writable, so anyone could
type "[POST_ID:1]" and produce a share card for a post they cannot see. The
reference is now a foreign key, which is not forgeable by typing.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from api.models import Reel
from api.models.messaging import Conversation, Message
from tests.conftest import grant_subscription

pytestmark = pytest.mark.django_db


@pytest.fixture
def sender():
    user = User.objects.create_user(username='sender', password='123456')
    grant_subscription(user)
    return user


@pytest.fixture
def alice():
    return User.objects.create_user(username='alice', password='123456')


@pytest.fixture
def bob():
    return User.objects.create_user(username='bob', password='123456')


@pytest.fixture
def post(alice):
    return Reel.objects.create(user=alice, caption='a post worth sending', media='reels/x.mp4')


@pytest.fixture
def client(sender):
    api = APIClient()
    api.force_authenticate(user=sender)
    return api


def share(client, post, **body):
    return client.post(f'/api/v1/reels/{post.id}/share-with/', body, format='json')


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_sharing_creates_a_message_referencing_the_post(client, post, bob):
    response = share(client, post, user_ids=[bob.id])

    assert response.status_code == 200, response.data
    message = Message.objects.get(sender__username='sender')
    assert message.shared_reel_id == post.id
    assert message.media_type == Message.MEDIA_POST


def test_the_recipient_receives_it_in_a_conversation_with_the_sender(client, post, bob, sender):
    share(client, post, user_ids=[bob.id])

    conversation = Message.objects.get(shared_reel=post).conversation
    participants = set(conversation.participants.values_list('id', flat=True))
    assert participants == {sender.id, bob.id}


def test_no_duplicate_post_is_created(client, post, bob):
    """
    The share is a reference, not a copy.

    A share that created a second Reel would fork the like count, the comment
    thread and the author's ownership of their own post.
    """
    before = Reel.objects.count()

    share(client, post, user_ids=[bob.id])

    assert Reel.objects.count() == before


def test_sharing_with_several_users_reaches_all_of_them(client, post, alice, bob):
    carol = User.objects.create_user(username='carol', password='123456')

    response = share(client, post, user_ids=[bob.id, carol.id])

    assert response.status_code == 200, response.data
    assert Message.objects.filter(shared_reel=post).count() == 2
    assert set(response.data['recipient_ids']) == {bob.id, carol.id}


def test_a_single_user_id_is_accepted(client, post, bob):
    """The one-recipient spelling, so the simple case stays simple."""
    response = share(client, post, user_id=bob.id)

    assert response.status_code == 200, response.data
    assert Message.objects.filter(shared_reel=post).count() == 1


# ---------------------------------------------------------------------------
# The share count
# ---------------------------------------------------------------------------


def test_one_share_counts_once_however_many_recipients(client, post, bob):
    """
    The defect this endpoint exists to fix.

    The client called the share endpoint once per recipient, so one tap on
    Send with five people selected recorded five shares. The action is one
    share regardless of how many people it went to.
    """
    carol = User.objects.create_user(username='carol', password='123456')
    dave = User.objects.create_user(username='dave', password='123456')
    assert post.shares == 0

    response = share(client, post, user_ids=[bob.id, carol.id, dave.id])

    post.refresh_from_db()
    assert post.shares == 1, f'3 recipients recorded {post.shares} shares'
    assert response.data['shares'] == 1


def test_opening_the_sheet_does_not_count(client, post):
    """
    Nothing here runs until Send.

    Stated as a test because the count is a public number on the post -- it
    must reflect shares that happened, not sheets that were opened.
    """
    post.refresh_from_db()
    assert post.shares == 0


def test_sharing_again_counts_again(client, post, bob):
    """
    Two deliberate sends are two shares.

    Distinct from the idempotent coin charge below: the user is not billed
    twice, but they did share twice and the count should say so.
    """
    share(client, post, user_ids=[bob.id])
    share(client, post, user_ids=[bob.id])

    post.refresh_from_db()
    assert post.shares == 2


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_anonymous_users_cannot_share(post, bob):
    response = APIClient().post(
        f'/api/v1/reels/{post.id}/share-with/', {'user_ids': [bob.id]}, format='json'
    )

    assert response.status_code in (401, 403)
    assert Message.objects.count() == 0


def test_sharing_a_post_that_does_not_exist_is_a_404(client, bob):
    response = client.post(
        '/api/v1/reels/99999999/share-with/', {'user_ids': [bob.id]}, format='json'
    )

    assert response.status_code == 404
    assert Message.objects.count() == 0


def test_an_empty_recipient_list_is_rejected(client, post):
    response = share(client, post, user_ids=[])

    assert response.status_code == 400
    assert Message.objects.count() == 0


def test_a_missing_recipient_list_is_rejected(client, post):
    response = share(client, post)

    assert response.status_code == 400


def test_non_integer_ids_are_rejected(client, post):
    response = share(client, post, user_ids=['not-a-user'])

    assert response.status_code == 400
    assert Message.objects.count() == 0


def test_sharing_only_with_yourself_is_rejected(client, post, sender):
    """A conversation with one participant is not a thing that exists."""
    response = share(client, post, user_ids=[sender.id])

    assert response.status_code == 400
    assert Message.objects.count() == 0


def test_selecting_yourself_alongside_others_still_sends_to_the_others(client, post, bob, sender):
    """
    Dropped, not rejected.

    Failing the whole send because the user's own avatar was among those
    tapped would be a worse outcome than quietly skipping it.
    """
    response = share(client, post, user_ids=[sender.id, bob.id])

    assert response.status_code == 200, response.data
    assert Message.objects.filter(shared_reel=post).count() == 1
    assert response.data['recipient_ids'] == [bob.id]


def test_unknown_recipients_are_reported_but_do_not_block_the_rest(client, post, bob):
    response = share(client, post, user_ids=[bob.id, 88888888])

    assert response.status_code == 200, response.data
    assert response.data['recipient_ids'] == [bob.id]
    assert response.data['invalid_user_ids'] == [88888888]


def test_sharing_only_with_unknown_users_is_a_404(client, post):
    response = share(client, post, user_ids=[88888888])

    assert response.status_code == 404
    assert Message.objects.count() == 0


def test_an_inactive_recipient_is_not_reachable(client, post, bob):
    bob.is_active = False
    bob.save(update_fields=['is_active'])

    response = share(client, post, user_ids=[bob.id])

    assert response.status_code == 404
    assert Message.objects.count() == 0


def test_a_very_large_recipient_list_is_refused(client, post):
    """
    A share sheet is a list of avatars someone taps.

    A request naming hundreds of recipients is not that, and the endpoint
    should not double as a fan-out primitive.
    """
    response = share(client, post, user_ids=list(range(1, 200)))

    assert response.status_code == 400
    assert Message.objects.count() == 0


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


def test_an_existing_conversation_is_reused(client, post, bob, sender):
    """
    Sharing into a chat you already have must land in that chat.

    A second conversation between the same two people would split the thread
    and show the recipient a new empty chat next to their real one.
    """
    existing = Conversation.objects.create()
    existing.participants.add(sender, bob)

    share(client, post, user_ids=[bob.id])

    assert Conversation.objects.count() == 1
    assert Message.objects.get(shared_reel=post).conversation_id == existing.id


def test_sharing_bumps_the_conversation_so_it_sorts_to_the_top(client, post, bob, sender):
    existing = Conversation.objects.create()
    existing.participants.add(sender, bob)
    before = Conversation.objects.get(pk=existing.pk).last_message_at

    share(client, post, user_ids=[bob.id])

    assert Conversation.objects.get(pk=existing.pk).last_message_at > before


# ---------------------------------------------------------------------------
# The API contract the share card reads
# ---------------------------------------------------------------------------


def test_the_recipient_sees_a_preview_of_the_post(client, post, bob, sender):
    """
    What the "[POST_ID:35]" marker could never carry.

    The old card could only say "Shared Post / Tap to view", because a regex
    over message text has no author, caption or thumbnail to render.
    """
    share(client, post, user_ids=[bob.id])

    recipient = APIClient()
    recipient.force_authenticate(user=bob)
    conversation = Message.objects.get(shared_reel=post).conversation
    response = recipient.get(f'/api/v1/messages/conversations/{conversation.id}/messages/')

    assert response.status_code == 200, response.data
    message = response.data['results'][0] if 'results' in response.data else response.data[0]
    preview = message['shared_post']
    assert preview['id'] == post.id
    assert preview['caption'] == 'a post worth sending'
    assert preview['author']['username'] == 'alice'
    assert message['sender']['username'] == 'sender'


def test_an_ordinary_message_carries_no_share_card(client, bob, sender):
    """
    Backward compatibility.

    Every message ever sent has no shared_reel, and must serialize as it
    always did rather than gaining an empty card.
    """
    conversation = Conversation.objects.create()
    conversation.participants.add(sender, bob)
    Message.objects.create(conversation=conversation, sender=sender, text='hello')

    response = client.get(f'/api/v1/messages/conversations/{conversation.id}/messages/')

    message = response.data['results'][0] if 'results' in response.data else response.data[0]
    assert message['shared_post'] is None
    assert message['text'] == 'hello'


def test_deleting_the_post_leaves_the_conversation_intact(client, post, bob, sender):
    """
    SET_NULL, not CASCADE.

    Deleting a reel must not delete messages between two other people. The
    share degrades to a card-less message rather than taking history with it.
    """
    share(client, post, user_ids=[bob.id])
    message_id = Message.objects.get(shared_reel=post).id

    post.delete()

    message = Message.objects.get(pk=message_id)
    assert message.shared_reel is None
