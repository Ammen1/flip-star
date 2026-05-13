"""Support / Help request API endpoints (user + admin)."""
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models_support import SupportRequest


CATEGORY_VALUES = {c[0] for c in SupportRequest.CATEGORY_CHOICES}
STATUS_VALUES = {s[0] for s in SupportRequest.STATUS_CHOICES}


def _serialize(req, include_user=False):
    data = {
        'id': req.id,
        'category': req.category,
        'category_display': req.get_category_display(),
        'subject': req.subject,
        'message': req.message,
        'status': req.status,
        'status_display': req.get_status_display(),
        'admin_response': req.admin_response,
        'created_at': req.created_at.isoformat(),
        'updated_at': req.updated_at.isoformat(),
    }
    if include_user:
        data['user'] = {
            'id': req.user_id,
            'username': req.user.username,
            'email': req.user.email,
        }
        if req.handled_by_id:
            data['handled_by'] = req.handled_by.username
    return data


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def my_support_requests(request):
    """List my support requests or create a new one."""
    if request.method == 'GET':
        qs = SupportRequest.objects.filter(user=request.user).order_by('-created_at')
        return Response({
            'count': qs.count(),
            'results': [_serialize(r) for r in qs[:100]],
        })

    # POST: create a new request
    category = (request.data.get('category') or 'other').strip()
    subject = (request.data.get('subject') or '').strip()
    message = (request.data.get('message') or '').strip()

    if category not in CATEGORY_VALUES:
        return Response({'error': 'Invalid category'}, status=status.HTTP_400_BAD_REQUEST)
    if not subject:
        return Response({'error': 'Subject is required'}, status=status.HTTP_400_BAD_REQUEST)
    if len(subject) > 200:
        return Response({'error': 'Subject too long (max 200 characters)'}, status=status.HTTP_400_BAD_REQUEST)
    if not message:
        return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)
    if len(message) > 5000:
        return Response({'error': 'Message too long (max 5000 characters)'}, status=status.HTTP_400_BAD_REQUEST)

    req = SupportRequest.objects.create(
        user=request.user,
        category=category,
        subject=subject,
        message=message,
        status='received',
    )
    return Response({'request': _serialize(req)}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_support_requests(request):
    """List all support requests for admins. Supports ?status=&category=&page=&page_size="""
    qs = SupportRequest.objects.select_related('user', 'handled_by').order_by('-created_at')

    status_filter = request.query_params.get('status')
    if status_filter and status_filter in STATUS_VALUES:
        qs = qs.filter(status=status_filter)

    category_filter = request.query_params.get('category')
    if category_filter and category_filter in CATEGORY_VALUES:
        qs = qs.filter(category=category_filter)

    try:
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = min(max(int(request.query_params.get('page_size', 25)), 1), 100)
    except ValueError:
        page, page_size = 1, 25

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size

    summary = {key: SupportRequest.objects.filter(status=key).count() for key in STATUS_VALUES}

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'has_next': end < total,
        'summary': summary,
        'results': [_serialize(r, include_user=True) for r in qs[start:end]],
    })


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def admin_update_support_request(request, request_id):
    """Update status / response of a support request."""
    try:
        req = SupportRequest.objects.get(id=request_id)
    except SupportRequest.DoesNotExist:
        return Response({'error': 'Support request not found'}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get('status')
    response_text = request.data.get('admin_response')

    if new_status is not None:
        if new_status not in STATUS_VALUES:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        req.status = new_status

    if response_text is not None:
        req.admin_response = str(response_text)[:5000]

    req.handled_by = request.user
    req.updated_at = timezone.now()
    req.save()

    return Response({'request': _serialize(req, include_user=True)})
