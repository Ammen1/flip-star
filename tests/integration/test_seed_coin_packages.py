"""
Regression test for the seed_coin_packages management command -- ported
from the master branch, missing entirely in the current project before this
change.

Deliberately does NOT port master's own price/coin lineup: current's
CoinPackage model has no allows_airtime field (master's version references
it), and api/views/wallet.py:get_wallet_config already has its own fallback
package lineup (10/25/50/100/250 ETB) with different numbers from master's
(10/50/100/500/1000 ETB). Seeding master's mismatched tiers would leave the
DB rows out of sync with that fallback and with whatever the frontend
expects. The ported command seeds the lineup that fallback already declares.

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
    assert [p.price_etb for p in packages] == [10, 25, 50, 100, 250]

    most_popular = packages.get(name='Most Popular')
    assert most_popular.is_featured is True
    assert most_popular.get_total_coins() == 575


def test_seed_coin_packages_is_idempotent(db):
    call_command('seed_coin_packages', stdout=io.StringIO())
    call_command('seed_coin_packages', stdout=io.StringIO())

    assert CoinPackage.objects.filter(is_active=True).count() == 5


def test_seed_coin_packages_deactivates_stale_packages(db):
    stale = CoinPackage.objects.create(name='Old Discontinued Pack', price_etb=15, coin_amount=150, is_active=True)

    call_command('seed_coin_packages', stdout=io.StringIO())

    stale.refresh_from_db()
    assert stale.is_active is False
    assert CoinPackage.objects.filter(is_active=True).count() == 5
