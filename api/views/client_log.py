"""Endpoint for receiving frontend logs and printing them to the backend log.

Useful for debugging client-side issues (e.g. camera access) on production
deployments where the browser's developer console is not accessible to the
engineer.
"""

import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def client_log(request):
    """Receive a client-side log message and write it to the backend log."""
    try:
        data = request.data or {}
        source = str(data.get('source', 'client'))[:64]
        level = str(data.get('level', 'info')).lower()
        message = str(data.get('message', ''))[:2000]
        context = data.get('context', {})
        user_agent = str(data.get('userAgent', ''))[:300]
        username = getattr(getattr(request, 'user', None), 'username', 'anonymous')

        line = f'[CLIENT-LOG][{source}][user={username}] {message} | UA={user_agent}'
        if context:
            line += f' | Context: {str(context)[:500]}'

        if level == 'error':
            logger.error(line)
        elif level in ('warn', 'warning'):
            logger.warning(line)
        else:
            logger.info(line)

        return Response({'ok': True})
    except Exception as e:
        logger.exception('client_log failed: %s', e)
        return Response({'ok': False, 'error': str(e)}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def clear_pending_mandate(request):
    """
    Tell the frontend to clear telebirr_pending_mandate from localStorage --
    useful when a mandate was never actually created on Telebirr but the
    frontend keeps trying to reconcile it.
    """
    try:
        username = getattr(getattr(request, 'user', None), 'username', 'anonymous')
        logger.info('[CLEAR_PENDING_MANDATE] Request received from user=%s', username)
        return Response({'ok': True, 'action': 'clear_local_storage', 'key': 'telebirr_pending_mandate'})
    except Exception as e:
        logger.exception('clear_pending_mandate failed: %s', e)
        return Response({'ok': False, 'error': str(e)}, status=200)
