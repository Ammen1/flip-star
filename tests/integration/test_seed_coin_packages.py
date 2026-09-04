"""
Regression test for the seed_coin_packages management command -- ported
from the master branch, missing entirely in the current project before this
change.

The lineup is no longer duplicated. It lived in two places -- this command
and get_wallet_config's empty-table fallback -- which is why the original
version of this file warned at length about keeping them in sync. Both now
import api/services/coin_packages.py, so the prices a user is shown before
seeding and the rows created by seeding cannot disagree.

Telebirr is configured for exactly 10, 50, 100, 250 and 500 ETB. The 25 ETB
tier this file used to assert was retired when 500 was added; an amount
Telebirr does not recognise is rejected at their gateway after the user has
already confirmed the USSD prompt.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from api.models.contest import CoinPackage

pytestmark = pytest.mark.integration


def test_seed_coin_packages_creates_the_five_tiers(db):
    out = io.StringIO()
    call_command('seed_coin_packages', stdout=out)

    packages = CoinPackage.objects.filter(is_active=True).order_by('sort_order')
    assert packages.count() == 5
    # Compared as ints: price_etb comes back as Decimal('10.00'), and pinning
    # the string form would pin decimal_places, which is a schema detail.
    assert [int(p.price_etb) for p in packages] == [10, 50, 100, 250, 500]

    most_popular = packages.get(name='Most Popular')
    assert most_popular.is_featured is True
    assert most_popular.get_total_coins() == 575


def test_seed_coin_packages_is_idempotent(db):
    call_command('seed_coin_packages', stdout=io.StringIO())
    call_command('seed_coin_packages', stdout=io.StringIO())

    assert CoinPackage.objects.filter(is_active=True).count() == 5


def test_seed_coin_packages_deactivates_stale_packages(db):
    stale = CoinPackage.objects.create(
        name='Old Discontinued Pack', price_etb=15, coin_amount=150, is_active=True
    )

    call_command('seed_coin_packages', stdout=io.StringIO())

    stale.refresh_from_db()
    assert stale.is_active is False
    assert CoinPackage.objects.filter(is_active=True).count() == 5
