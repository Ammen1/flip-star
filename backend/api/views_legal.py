"""
Legal Documents API Views - Terms & Conditions, Privacy Policy management
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Count

from .models_legal import LegalDocument, LegalDocumentVersion, UserLegalAcceptance


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_legal_documents_list(request):
    """
    List all legal documents with stats
    """
    try:
        doc_type_filter = request.GET.get('type')
        status_filter = request.GET.get('status')
        
        documents = LegalDocument.objects.all()
        
        if doc_type_filter:
            documents = documents.filter(document_type=doc_type_filter)
        if status_filter:
            documents = documents.filter(status=status_filter)
        
        documents = documents.annotate(
            acceptance_count=Count('acceptances')
        ).order_by('-updated_at')
        
        return Response({
            'documents': [{
                'id': doc.id,
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'title': doc.title,
                'slug': doc.slug,
                'summary': doc.summary,
                'version': doc.version,
                'status': doc.status,
                'status_display': doc.get_status_display(),
                'effective_date': doc.effective_date.isoformat() if doc.effective_date else None,
                'requires_acceptance': doc.requires_acceptance,
                'show_on_signup': doc.show_on_signup,
                'is_mandatory': doc.is_mandatory,
                'acceptance_count': doc.acceptance_count,
                'created_by': doc.created_by.username if doc.created_by else None,
                'updated_by': doc.updated_by.username if doc.updated_by else None,
                'created_at': doc.created_at.isoformat(),
                'updated_at': doc.updated_at.isoformat(),
            } for doc in documents],
            'document_types': [
            {'value': dt[0], 'label': dt[1]} 
            for dt in LegalDocument.DOCUMENT_TYPES
        ],
        'status_options': [
            {'value': st[0], 'label': st[1]} 
            for st in LegalDocument.STATUS_CHOICES
        ],
    })
    except Exception as e:
        return Response({
            'error': str(e),
            'message': 'Database tables may not exist. Please run migrations.',
            'documents': [],
            'document_types': [
                {'value': dt[0], 'label': dt[1]} 
                for dt in LegalDocument.DOCUMENT_TYPES
            ],
            'status_options': [
                {'value': st[0], 'label': st[1]} 
                for st in LegalDocument.STATUS_CHOICES
            ],
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_legal_document_detail(request, document_id):
    """
    Get full details of a legal document including content
    """
    try:
        doc = LegalDocument.objects.annotate(
            acceptance_count=Count('acceptances')
        ).get(id=document_id)
    except LegalDocument.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get version history
    versions = LegalDocumentVersion.objects.filter(document=doc).order_by('-created_at')[:10]
    
    return Response({
        'document': {
            'id': doc.id,
            'document_type': doc.document_type,
            'document_type_display': doc.get_document_type_display(),
            'title': doc.title,
            'slug': doc.slug,
            'content': doc.content,
            'summary': doc.summary,
            'version': doc.version,
            'status': doc.status,
            'status_display': doc.get_status_display(),
            'effective_date': doc.effective_date.isoformat() if doc.effective_date else None,
            'requires_acceptance': doc.requires_acceptance,
            'show_on_signup': doc.show_on_signup,
            'is_mandatory': doc.is_mandatory,
            'acceptance_count': doc.acceptance_count,
            'created_by': doc.created_by.username if doc.created_by else None,
            'updated_by': doc.updated_by.username if doc.updated_by else None,
            'created_at': doc.created_at.isoformat(),
            'updated_at': doc.updated_at.isoformat(),
        },
        'versions': [{
            'id': v.id,
            'version': v.version,
            'changes_summary': v.changes_summary,
            'created_by': v.created_by.username if v.created_by else None,
            'created_at': v.created_at.isoformat(),
        } for v in versions]
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_legal_document_create(request):
    """
    Create a new legal document
    """
    data = request.data
    
    # Validate required fields
    required_fields = ['document_type', 'title', 'content']
    for field in required_fields:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate slug if not provided
    slug = data.get('slug') or slugify(data['title'])
    
    # Check for duplicate slug
    if LegalDocument.objects.filter(slug=slug).exists():
        slug = f"{slug}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
    
    try:
        doc = LegalDocument.objects.create(
            document_type=data['document_type'],
            title=data['title'],
            slug=slug,
            content=data['content'],
            summary=data.get('summary', ''),
            version=data.get('version', '1.0'),
            status=data.get('status', 'draft'),
            requires_acceptance=data.get('requires_acceptance', True),
            show_on_signup=data.get('show_on_signup', True),
            is_mandatory=data.get('is_mandatory', True),
            created_by=request.user,
            updated_by=request.user,
        )
        
        # Create initial version record
        LegalDocumentVersion.objects.create(
            document=doc,
            version=doc.version,
            content=doc.content,
            changes_summary='Initial version',
            created_by=request.user,
        )
        
        return Response({
            'message': 'Document created successfully',
            'document': {
                'id': doc.id,
                'title': doc.title,
                'slug': doc.slug,
                'status': doc.status,
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdminUser])
def admin_legal_document_update(request, document_id):
    """
    Update a legal document
    """
    try:
        doc = LegalDocument.objects.get(id=document_id)
    except LegalDocument.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data = request.data
    old_version = doc.version
    old_content = doc.content
    
    # Update fields
    if 'title' in data:
        doc.title = data['title']
    if 'content' in data:
        doc.content = data['content']
    if 'summary' in data:
        doc.summary = data['summary']
    if 'version' in data:
        doc.version = data['version']
    if 'status' in data:
        doc.status = data['status']
    if 'requires_acceptance' in data:
        doc.requires_acceptance = data['requires_acceptance']
    if 'show_on_signup' in data:
        doc.show_on_signup = data['show_on_signup']
    if 'is_mandatory' in data:
        doc.is_mandatory = data['is_mandatory']
    if 'effective_date' in data:
        doc.effective_date = data['effective_date']
    
    doc.updated_by = request.user
    doc.save()
    
    # Create version record if content or version changed
    if doc.version != old_version or doc.content != old_content:
        LegalDocumentVersion.objects.create(
            document=doc,
            version=doc.version,
            content=doc.content,
            changes_summary=data.get('changes_summary', f'Updated from v{old_version}'),
            created_by=request.user,
        )
    
    return Response({
        'message': 'Document updated successfully',
        'document': {
            'id': doc.id,
            'title': doc.title,
            'version': doc.version,
            'status': doc.status,
        }
    })


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_legal_document_delete(request, document_id):
    """
    Delete a legal document
    """
    try:
        doc = LegalDocument.objects.get(id=document_id)
    except LegalDocument.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Don't allow deleting published mandatory documents
    if doc.status == 'published' and doc.is_mandatory:
        return Response({
            'error': 'Cannot delete a published mandatory document. Archive it instead.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    title = doc.title
    doc.delete()
    
    return Response({
        'message': f'Document "{title}" deleted successfully'
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_legal_document_publish(request, document_id):
    """
    Publish a legal document
    """
    try:
        doc = LegalDocument.objects.get(id=document_id)
    except LegalDocument.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Archive any other published documents of the same type
    LegalDocument.objects.filter(
        document_type=doc.document_type,
        status='published'
    ).exclude(id=doc.id).update(status='archived')
    
    doc.publish(user=request.user)
    
    return Response({
        'message': f'Document "{doc.title}" published successfully',
        'effective_date': doc.effective_date.isoformat()
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_legal_document_archive(request, document_id):
    """
    Archive a legal document
    """
    try:
        doc = LegalDocument.objects.get(id=document_id)
    except LegalDocument.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    doc.archive(user=request.user)
    
    return Response({
        'message': f'Document "{doc.title}" archived successfully'
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_legal_document_acceptances(request, document_id):
    """
    Get list of users who accepted a document
    """
    try:
        doc = LegalDocument.objects.get(id=document_id)
    except LegalDocument.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    
    acceptances = UserLegalAcceptance.objects.filter(
        document=doc
    ).select_related('user').order_by('-accepted_at')
    
    total = acceptances.count()
    start = (page - 1) * page_size
    end = start + page_size
    
    return Response({
        'document_title': doc.title,
        'total_acceptances': total,
        'page': page,
        'page_size': page_size,
        'acceptances': [{
            'user_id': a.user.id,
            'username': a.user.username,
            'email': a.user.email,
            'version_accepted': a.version_accepted,
            'accepted_at': a.accepted_at.isoformat(),
            'ip_address': a.ip_address,
        } for a in acceptances[start:end]]
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_legal_stats(request):
    """
    Get overall legal document statistics
    """
    from django.contrib.auth.models import User
    
    try:
        total_users = User.objects.filter(is_active=True).count()
        
        stats = []
        for doc_type, doc_name in LegalDocument.DOCUMENT_TYPES:
            try:
                active_doc = LegalDocument.get_active_document(doc_type)
                if active_doc:
                    acceptance_count = UserLegalAcceptance.objects.filter(
                        document=active_doc,
                        version_accepted=active_doc.version
                    ).count()
                    
                    stats.append({
                        'document_type': doc_type,
                        'document_name': doc_name,
                        'document_id': active_doc.id,
                        'title': active_doc.title,
                        'version': active_doc.version,
                        'acceptance_count': acceptance_count,
                        'acceptance_rate': round((acceptance_count / total_users * 100), 1) if total_users > 0 else 0,
                        'effective_date': active_doc.effective_date.isoformat() if active_doc.effective_date else None,
                    })
                else:
                    stats.append({
                        'document_type': doc_type,
                        'document_name': doc_name,
                        'document_id': None,
                        'title': None,
                        'version': None,
                        'acceptance_count': 0,
                        'acceptance_rate': 0,
                        'effective_date': None,
                    })
            except Exception:
                stats.append({
                    'document_type': doc_type,
                    'document_name': doc_name,
                    'document_id': None,
                    'title': None,
                    'version': None,
                    'acceptance_count': 0,
                    'acceptance_rate': 0,
                    'effective_date': None,
                })
        
        return Response({
            'total_users': total_users,
            'document_stats': stats
        })
    except Exception as e:
        # Return empty stats if tables don't exist
        return Response({
            'total_users': 0,
            'document_stats': [
                {
                    'document_type': doc_type,
                    'document_name': doc_name,
                    'document_id': None,
                    'title': None,
                    'version': None,
                    'acceptance_count': 0,
                    'acceptance_rate': 0,
                    'effective_date': None,
                }
                for doc_type, doc_name in LegalDocument.DOCUMENT_TYPES
            ],
            'error': str(e),
            'message': 'Database tables may not exist. Please run migrations.'
        })


# ============================================================================
# PUBLIC ENDPOINTS (for users)
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def get_legal_document(request, document_type):
    """
    Get the active legal document of a specific type (public)
    """
    doc = LegalDocument.get_active_document(document_type)
    
    if not doc:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    return Response({
        'document': {
            'id': doc.id,
            'document_type': doc.document_type,
            'title': doc.title,
            'content': doc.content,
            'summary': doc.summary,
            'version': doc.version,
            'effective_date': doc.effective_date.isoformat() if doc.effective_date else None,
            'requires_acceptance': doc.requires_acceptance,
        }
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_legal_documents(request):
    """
    Get all active legal documents (public)
    """
    active_docs = LegalDocument.get_all_active_documents()
    
    return Response({
        'documents': [{
            'document_type': doc.document_type,
            'title': doc.title,
            'summary': doc.summary,
            'version': doc.version,
            'effective_date': doc.effective_date.isoformat() if doc.effective_date else None,
        } for doc in active_docs.values()]
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_legal_document(request, document_type):
    """
    User accepts a legal document
    """
    doc = LegalDocument.get_active_document(document_type)
    
    if not doc:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get IP address
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Create or update acceptance
    acceptance, created = UserLegalAcceptance.objects.update_or_create(
        user=request.user,
        document=doc,
        defaults={
            'version_accepted': doc.version,
            'ip_address': ip_address,
            'user_agent': user_agent[:500] if user_agent else '',
        }
    )
    
    return Response({
        'message': f'You have accepted {doc.title}',
        'document_type': doc.document_type,
        'version': doc.version,
        'accepted_at': acceptance.accepted_at.isoformat()
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pending_acceptances(request):
    """
    Get list of legal documents user needs to accept
    """
    pending = UserLegalAcceptance.get_pending_acceptances(request.user)
    
    return Response({
        'pending_documents': [{
            'id': doc.id,
            'document_type': doc.document_type,
            'title': doc.title,
            'summary': doc.summary,
            'version': doc.version,
            'is_mandatory': doc.is_mandatory,
        } for doc in pending],
        'has_pending': len(pending) > 0
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_acceptances(request):
    """
    Get user's acceptance history
    """
    acceptances = UserLegalAcceptance.objects.filter(
        user=request.user
    ).select_related('document').order_by('-accepted_at')
    
    return Response({
        'acceptances': [{
            'document_type': a.document.document_type,
            'document_title': a.document.title,
            'version_accepted': a.version_accepted,
            'current_version': a.document.version,
            'needs_update': a.version_accepted != a.document.version,
            'accepted_at': a.accepted_at.isoformat(),
        } for a in acceptances]
    })
