"""
Legal Documents Models - Terms & Conditions, Privacy Policy, etc.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class LegalDocument(models.Model):
    """
    Model for managing legal documents like Terms & Conditions, Privacy Policy, etc.
    Supports versioning and tracking user acceptance.
    """
    DOCUMENT_TYPES = [
        ('terms', 'Terms & Conditions'),
        ('privacy', 'Privacy Policy'),
        ('community', 'Community Guidelines'),
        ('contest', 'Contest Rules'),
        ('cookie', 'Cookie Policy'),
        ('refund', 'Refund Policy'),
        ('dmca', 'DMCA Policy'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    content = models.TextField(help_text='Full document content (supports HTML/Markdown)')
    summary = models.TextField(blank=True, help_text='Brief summary of the document')
    
    version = models.CharField(max_length=20, default='1.0')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Effective dates
    effective_date = models.DateTimeField(null=True, blank=True, help_text='When this version becomes effective')
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_legal_docs')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_legal_docs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Settings
    requires_acceptance = models.BooleanField(default=True, help_text='Users must accept this document')
    show_on_signup = models.BooleanField(default=True, help_text='Show during user registration')
    is_mandatory = models.BooleanField(default=True, help_text='Users cannot use platform without accepting')
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Legal Document'
        verbose_name_plural = 'Legal Documents'
    
    def __str__(self):
        return f"{self.title} (v{self.version})"
    
    def publish(self, user=None):
        """Publish this document version"""
        self.status = 'published'
        self.effective_date = timezone.now()
        if user:
            self.updated_by = user
        self.save()
    
    def archive(self, user=None):
        """Archive this document"""
        self.status = 'archived'
        if user:
            self.updated_by = user
        self.save()
    
    @classmethod
    def get_active_document(cls, document_type):
        """Get the currently active (published) document of a type"""
        return cls.objects.filter(
            document_type=document_type,
            status='published'
        ).order_by('-effective_date').first()
    
    @classmethod
    def get_all_active_documents(cls):
        """Get all currently active documents"""
        active_docs = {}
        for doc_type, _ in cls.DOCUMENT_TYPES:
            doc = cls.get_active_document(doc_type)
            if doc:
                active_docs[doc_type] = doc
        return active_docs


class LegalDocumentVersion(models.Model):
    """
    Track version history of legal documents
    """
    document = models.ForeignKey(LegalDocument, on_delete=models.CASCADE, related_name='versions')
    version = models.CharField(max_length=20)
    content = models.TextField()
    changes_summary = models.TextField(blank=True, help_text='Summary of changes from previous version')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['document', 'version']
    
    def __str__(self):
        return f"{self.document.title} - v{self.version}"


class UserLegalAcceptance(models.Model):
    """
    Track which users have accepted which legal documents
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='legal_acceptances')
    document = models.ForeignKey(LegalDocument, on_delete=models.CASCADE, related_name='acceptances')
    version_accepted = models.CharField(max_length=20)
    
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-accepted_at']
        unique_together = ['user', 'document']
    
    def __str__(self):
        return f"{self.user.username} accepted {self.document.title} v{self.version_accepted}"
    
    @classmethod
    def has_accepted_latest(cls, user, document_type):
        """Check if user has accepted the latest version of a document type"""
        latest_doc = LegalDocument.get_active_document(document_type)
        if not latest_doc:
            return True  # No document to accept
        
        acceptance = cls.objects.filter(
            user=user,
            document=latest_doc,
            version_accepted=latest_doc.version
        ).first()
        
        return acceptance is not None
    
    @classmethod
    def get_pending_acceptances(cls, user):
        """Get list of documents user needs to accept"""
        pending = []
        for doc_type, doc_name in LegalDocument.DOCUMENT_TYPES:
            doc = LegalDocument.get_active_document(doc_type)
            if doc and doc.requires_acceptance and doc.is_mandatory:
                if not cls.has_accepted_latest(user, doc_type):
                    pending.append(doc)
        return pending
