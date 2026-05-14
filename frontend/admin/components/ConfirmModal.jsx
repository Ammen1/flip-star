import { AlertTriangle, AlertCircle, CheckCircle2, Info } from 'lucide-react';
import { adminTheme } from '../theme';

export function ConfirmModal({ theme = {}, isOpen, onClose, onConfirm, title, message, confirmText = 'Confirm', cancelText = 'Cancel', type = 'danger', loading = false }) {
  if (!isOpen) return null;

  const palette = {
    danger:  { color: adminTheme.colors.error,    bg: '#FEF2F2', Icon: AlertTriangle },
    warning: { color: adminTheme.colors.warning, bg: '#F0F9E8', Icon: AlertCircle },
    success: { color: adminTheme.colors.success,  bg: '#ECFDF5', Icon: CheckCircle2 },
    info:    { color: adminTheme.colors.info,    bg: '#EFF6FF', Icon: Info },
  }[type] || { color: adminTheme.colors.primary, bg: '#EFF6FF', Icon: Info };

  const { color, bg, Icon } = palette;

  const handleConfirm = () => {
    if (loading) return;
    onConfirm();
    if (!loading) onClose?.();
  };

  return (
    <div
      className="admin-modal-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.55)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 99999,
        padding: adminTheme.spacing.xl,
      }}
      onClick={loading ? undefined : onClose}
    >
      <div
        className="admin-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        style={{
          background: adminTheme.colors.card,
          borderRadius: adminTheme.borderRadius.xl,
          padding: adminTheme.spacing['2xl'],
          width: '100%',
          maxWidth: 460,
          boxShadow: adminTheme.shadows.xl,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: adminTheme.spacing.lg,
          marginBottom: adminTheme.spacing.lg,
        }}>
          <div style={{
            width: 48,
            height: 48,
            borderRadius: adminTheme.borderRadius.lg,
            background: bg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color,
            flexShrink: 0,
          }}>
            <Icon size={24} strokeWidth={2.2} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 id="confirm-modal-title" style={{
              margin: `0 0 ${adminTheme.spacing.sm}`,
              fontSize: adminTheme.typography.fontSize.lg,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              color: adminTheme.colors.textPrimary,
              letterSpacing: '-0.01em',
            }}>
              {title}
            </h3>
            <p style={{
              margin: 0,
              fontSize: adminTheme.typography.fontSize.base,
              color: adminTheme.colors.textSecondary,
              lineHeight: 1.6,
            }}>
              {message}
            </p>
          </div>
        </div>

        <div style={{
          display: 'flex',
          gap: adminTheme.spacing.md,
          flexDirection: typeof window !== 'undefined' && window.innerWidth < 640 ? 'column' : 'row',
        }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              flex: 1,
              padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg}`,
              background: adminTheme.colors.background,
              border: `1px solid ${adminTheme.colors.border}`,
              borderRadius: adminTheme.borderRadius.md,
              color: adminTheme.colors.textPrimary,
              fontSize: adminTheme.typography.fontSize.base,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: `all ${adminTheme.transitions.base}`,
            }}
            onMouseEnter={(e) => {
              if (!loading) e.currentTarget.style.background = adminTheme.colors.hover;
            }}
            onMouseLeave={(e) => {
              if (!loading) e.currentTarget.style.background = adminTheme.colors.background;
            }}
          >
            {cancelText}
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            style={{
              flex: 1,
              padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg}`,
              background: color,
              border: 'none',
              borderRadius: adminTheme.borderRadius.md,
              color: adminTheme.colors.textLight,
              fontSize: adminTheme.typography.fontSize.base,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              cursor: loading ? 'not-allowed' : 'pointer',
              boxShadow: `0 4px 12px ${color}33`,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: adminTheme.spacing.sm,
              transition: `all ${adminTheme.transitions.base}`,
            }}
            onMouseEnter={(e) => {
              if (!loading) e.currentTarget.style.filter = 'brightness(1.1)';
            }}
            onMouseLeave={(e) => {
              if (!loading) e.currentTarget.style.filter = 'none';
            }}
          >
            {loading && <span className="admin-spinner sm" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.4)' }} />}
            {loading ? 'Working...' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}




