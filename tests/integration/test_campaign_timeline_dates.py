"""
Campaign timeline dates: what is stored, and what the API says about it.

The report was an entry deadline displayed later than the voting end. Working
back through the layers, three of them were innocent:

* the model has one field per date, each its own column;
* the API maps each field to itself -- no swap, no aliasing;
* serialization is faithful and carries the offset. A deadline an admin sets
  as 23:59 on 25 September is stored 20:59Z and emitted
  ``2026-09-25T23:59:00+03:00``.

And one thing is decisive: **a timezone conversion cannot reverse two dates.**
The offset is uniform, so if one instant precedes another it precedes it in
every timezone. Rendering can collapse two dates onto the same day; it can
never swap them. A timeline that appears out of order is stored out of order.

Nothing stopped that being stored. The model had no validation and the create
and update endpoints passed the values straight through, so an entry deadline
after the voting end saved cleanly and every layer below displayed it
faithfully. That is the fix: the rule is now in the model, enforced at both
endpoints.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from api.models.campaign import Campaign

pytestmark = pytest.mark.django_db

ADDIS = ZoneInfo('Africa/Addis_Ababa')


def campaign(**dates):
    """A campaign with a sensible timeline unless a date is overridden."""
    base = {
        'start_date': datetime(2026, 9, 1, 0, 0, tzinfo=ADDIS),
        'entry_deadline': datetime(2026, 9, 25, 23, 59, tzinfo=ADDIS),
        'voting_start': datetime(2026, 9, 26, 0, 0, tzinfo=ADDIS),
        'voting_end': datetime(2026, 9, 30, 23, 59, tzinfo=ADDIS),
    }
    base.update(dates)
    return Campaign(title='Test campaign', description='x', **base)


# ── what is stored ──────────────────────────────────────────────────────────


def test_a_deadline_is_stored_as_the_instant_it_was_configured_for():
    """23:59 Addis is 20:59 UTC. The stored instant is the configured one."""
    c = campaign()
    c.save()
    c.refresh_from_db()

    assert c.entry_deadline.astimezone(UTC) == datetime(2026, 9, 25, 20, 59, tzinfo=UTC)
    assert c.entry_deadline.astimezone(ADDIS).hour == 23


def test_the_dates_keep_their_own_identities():
    """Each field is its own column -- no aliasing between deadline and end."""
    c = campaign()
    c.save()
    c.refresh_from_db()

    assert c.entry_deadline != c.voting_end
    assert c.entry_deadline.astimezone(ADDIS).day == 25
    assert c.voting_end.astimezone(ADDIS).day == 30


def test_a_valid_timeline_is_not_altered():
    """Nothing normalises or reorders a campaign that is already correct."""
    c = campaign()
    before = (c.start_date, c.entry_deadline, c.voting_start, c.voting_end)
    c.save()
    c.refresh_from_db()

    assert (c.start_date, c.entry_deadline, c.voting_start, c.voting_end) == before


# ── the rule that was missing ───────────────────────────────────────────────


def test_an_entry_deadline_after_the_voting_end_is_refused():
    """The reported case."""
    c = campaign(
        entry_deadline=datetime(2026, 10, 5, 23, 59, tzinfo=ADDIS),
        voting_start=datetime(2026, 10, 6, 0, 0, tzinfo=ADDIS),
        voting_end=datetime(2026, 9, 30, 23, 59, tzinfo=ADDIS),
    )

    problems = c.timeline_problems()
    assert problems, 'an inverted timeline reported no problem'
    assert any('after' in p for p in problems)


def test_the_problem_names_both_dates_so_it_can_be_acted_on():
    c = campaign(entry_deadline=datetime(2026, 10, 5, 0, 0, tzinfo=ADDIS))

    problem = c.timeline_problems()[0]
    assert 'Entry deadline' in problem
    assert 'Voting start' in problem


def test_clean_raises_so_the_admin_refuses_it_too():
    c = campaign(entry_deadline=datetime(2026, 10, 5, 0, 0, tzinfo=ADDIS))

    with pytest.raises(ValidationError):
        c.clean()


def test_a_correct_timeline_has_no_problems():
    assert campaign().timeline_problems() == []


def test_dates_one_second_apart_are_in_order():
    """The rule is 'not after', so touching dates are fine."""
    moment = datetime(2026, 9, 26, 0, 0, tzinfo=ADDIS)
    c = campaign(entry_deadline=moment, voting_start=moment)

    assert c.timeline_problems() == []


def test_an_unscheduled_date_is_incomplete_not_inconsistent():
    """A campaign that has not set its voting dates must not be reported as
    broken -- blank is not zero."""
    assert campaign(voting_start=None, voting_end=None).timeline_problems() == []
    assert campaign(start_date=None).timeline_problems() == []


def test_a_gap_does_not_hide_an_inversion():
    """With voting_start missing, the deadline must still be compared against
    the voting end rather than skipped along with it."""
    c = campaign(
        voting_start=None,
        entry_deadline=datetime(2026, 10, 5, 0, 0, tzinfo=ADDIS),
        voting_end=datetime(2026, 9, 30, 0, 0, tzinfo=ADDIS),
    )

    assert c.timeline_problems(), 'an inversion across a gap went unreported'


# ── what the API reports ────────────────────────────────────────────────────


def test_the_api_emits_the_offset_so_a_client_cannot_guess_wrong():
    """A bare '2026-09-25T23:59:00' would leave the client to assume a
    timezone. The offset is what makes the instant unambiguous."""
    from rest_framework.renderers import JSONRenderer

    c = campaign()
    rendered = JSONRenderer().render({'entry_deadline': c.entry_deadline}).decode()

    assert '+03:00' in rendered or 'Z' in rendered


def test_the_api_value_round_trips_to_the_same_instant():
    from rest_framework.renderers import JSONRenderer

    c = campaign()
    c.save()
    c.refresh_from_db()

    rendered = JSONRenderer().render({'d': c.entry_deadline}).decode()
    value = rendered.split('"d":"')[1].rstrip('"}')

    assert datetime.fromisoformat(value) == c.entry_deadline


def test_an_active_campaign_is_judged_on_the_stored_instants():
    """is_active compares against the deadline directly; a correct timeline
    must not be made inactive by the comparison."""
    now = timezone.now()
    c = campaign(
        start_date=now - timedelta(days=1),
        entry_deadline=now + timedelta(days=1),
        voting_start=now + timedelta(days=2),
        voting_end=now + timedelta(days=3),
    )
    c.status = 'active'
    c.save()

    assert c.is_active() is True
