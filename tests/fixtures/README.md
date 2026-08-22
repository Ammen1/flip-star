# Fixtures

Shared test data: JSON fixtures loaded with `django_db_setup`, factory helpers,
and recorded provider payloads (Telebirr SOAP envelopes, Onevas webhook bodies)
for integration tests that must not hit the network.

Fixtures used by more than one suite belong here. Fixtures used by a single test
module belong in that module.
