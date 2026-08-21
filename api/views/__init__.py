"""HTTP layer: DRF views and viewsets, grouped by business domain.

Modules here own request handling, authentication, authorization and response
shaping. Business workflows belong in ``api/services``; provider calls belong in
``api/integrations``.

Nothing is re-exported from this package -- import the specific module
(``from api.views.wallet import wallet_summary``) so the dependency is explicit.
"""
