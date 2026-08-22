from django.db import models
from django.contrib.auth.models import User


class PhoneOTP(models.Model):
    """Stores a 6-digit OTP sent via SMS to an Ethiopian phone number during registration."""
    phone = models.CharField(max_length=20, db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['phone', 'code'])]

    def __str__(self):
        return f"OTP for {self.phone} (verified={self.verified})"


class PasswordResetToken(models.Model):
    """Stores a 6-digit code emailed to the user for password reset."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='password_reset_token')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"ResetToken for {self.user.username}"
