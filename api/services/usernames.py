"""
Whether a username is free, and what to say when it is not.

Two things went wrong when somebody picked a name that was taken.

**The message was the database's.** Both registration paths ended in
``except Exception as e: return Response({'error': str(e)})``. When the
duplicate slipped past the pre-check -- which it does, see below -- the
customer was shown the Postgres constraint violation, table and column names
included. They were told nothing they could act on and something they should
never have seen.

**The check could not stop it anyway.** ``exists()`` then ``create_user()``
is a check followed by a write, and two requests can pass the check before
either writes. The database constraint is what actually prevents duplicates;
the pre-check only makes the common case a tidy 409 instead of an exception.
So both are kept, and the race is handled where it surfaces.

Case
----
Case-insensitively taken, matching the rule the rest of the codebase already
applies: organization admin creation refuses a name that differs only in case
(api/views/organizations.py), and gift delivery resolves a recipient with
``username__iexact`` (api/views/gamification.py). If registration allowed
'Ammen' alongside 'ammen', that gift lookup would match two rows and raise --
so allowing them is not a neutral choice.

The database's own uniqueness stays case-sensitive: making it otherwise means
a migration and a collation decision on a live table, which is a separate
piece of work. Until then the application rule is the stricter one, and the
constraint remains the backstop.
"""

import logging

logger = logging.getLogger(__name__)

#: What the client branches on. Prose may be reworded; this may not.
USERNAME_TAKEN_CODE = 'USERNAME_TAKEN'

#: What the customer reads. One sentence, and it says what to do next.
USERNAME_TAKEN_MESSAGE = 'That username is already in use. Please choose another username.'


def is_taken(username, *, exclude_user_id=None):
    """Is this username already somebody's?

    Case-insensitive, per the rule above. ``exclude_user_id`` lets an account
    keep its own name when editing.
    """
    from django.contrib.auth.models import User

    name = (username or '').strip()
    if not name:
        return False

    query = User.objects.filter(username__iexact=name)
    if exclude_user_id is not None:
        query = query.exclude(pk=exclude_user_id)
    return query.exists()


def taken_payload():
    """The body every endpoint returns for a duplicate username."""
    return {'error': USERNAME_TAKEN_MESSAGE, 'code': USERNAME_TAKEN_CODE, 'field': 'username'}


def is_duplicate_username_error(exc):
    """Did this database error come from the username constraint?

    Matched on the column name rather than the driver's message shape, which
    differs between SQLite and Postgres. A false negative here means the
    caller falls back to a generic failure -- unhelpful, but never the raw
    exception.
    """
    text = str(exc).lower()
    return 'username' in text and ('unique' in text or 'duplicate' in text)
