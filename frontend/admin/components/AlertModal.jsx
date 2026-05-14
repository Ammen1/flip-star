import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react';

export function AlertModal({ isOpen, title, message, type = 'info', onClose, onConfirm, showCancel = true, confirmText, cancelText = 'Cancel' }) {
  if (!isOpen) return null;

  const config = {
    success: { color: '#10B981', bg: '#ECFDF5', Icon: CheckCircle2 },
    error:   { color: '#EF4444', bg: '#FEF2F2', Icon: XCircle },
    warning: { color: '#8fc441', bg: '#F0F9E8', Icon: AlertTriangle },
    info:    { color: '#2563EB', bg: '#EFF6FF', Icon: Info },
  }[type] || { color: '#2563EB', bg: '#EFF6FF', Icon: Info };

  const { color, bg, Icon } = config;

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
        zIndex: 10000,
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        className="admin-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="alert-modal-title"
        style={{
          background: '#fff',
          borderRadius: 16,
          padding: 0,
          maxWidth: 420,
          width: '100%',
          boxShadow: '0 24px 60px rgba(15, 23, 42, 0.25)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close (X) */}
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94A3B8',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#F1F5F9'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        >
          <X size={16} />
        </button>

        <div style={{ padding: '28px 24px 20px' }}>
          <div style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            background: bg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px',
            color,
          }}>
            <Icon size={28} strokeWidth={2.2} />
          </div>

          <h3 id="alert-modal-title" style={{
            margin: '0 0 8px',
            fontSize: 18,
            fontWeight: 700,
            color: '#0F172A',
            textAlign: 'center',
            letterSpacing: '-0.01em',
          }}>
            {title}
          </h3>

          <p style={{
            margin: 0,
            fontSize: 14,
            color: '#64748B',
            textAlign: 'center',
            lineHeight: 1.55,
          }}>
            {message}
          </p>
        </div>

        <div style={{
          display: 'flex',
          gap: 10,
          padding: '0 24px 24px',
        }}>
          {showCancel && (
            <button
              onClick={onClose}
              style={{
                flex: 1,
                padding: '11px 16px',
                background: '#fff',
                border: '1px solid #E2E8F0',
                borderRadius: 10,
                color: '#0F172A',
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {cancelText}
            </button>
          )}
          <button
            onClick={() => {
              if (onConfirm) onConfirm();
              onClose();
            }}
            style={{
              flex: 1,
              padding: '11px 16px',
              background: color,
              border: 'none',
              borderRadius: 10,
              color: '#fff',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: `0 4px 12px ${color}33`,
            }}
          >
            {confirmText || (onConfirm ? 'Confirm' : 'OK')}
          </button>
        </div>
      </div>
    </div>
  );
}




