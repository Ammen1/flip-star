// Reusable Admin loading / empty / error state components.
// Pages can drop these in to provide consistent UX with smooth animations.
import { AlertCircle, Inbox, RefreshCw } from 'lucide-react';

export function AdminLoading({ label = 'Loading...', size = 'md', fullHeight = false }) {
  return (
    <div
      className="admin-state"
      style={fullHeight ? { minHeight: '60vh' } : undefined}
      role="status"
      aria-live="polite"
    >
      <span className={`admin-spinner ${size === 'sm' ? 'sm' : size === 'lg' ? 'lg' : ''}`} />
      <p className="admin-state-message" style={{ marginTop: 4 }}>{label}</p>
    </div>
  );
}

export function AdminEmpty({
  title = 'Nothing here yet',
  message = 'There is no data to display.',
  icon: Icon = Inbox,
  action,
}) {
  return (
    <div className="admin-state">
      <div className="admin-state-icon empty">
        <Icon size={26} />
      </div>
      <h3 className="admin-state-title">{title}</h3>
      <p className="admin-state-message">{message}</p>
      {action ? <div style={{ marginTop: 8 }}>{action}</div> : null}
    </div>
  );
}

export function AdminError({
  title = 'Something went wrong',
  message = 'Please try again or contact support if the issue persists.',
  onRetry,
  retryLabel = 'Retry',
}) {
  return (
    <div className="admin-state">
      <div className="admin-state-icon error">
        <AlertCircle size={26} />
      </div>
      <h3 className="admin-state-title">{title}</h3>
      <p className="admin-state-message">{message}</p>
      {onRetry ? (
        <button
          onClick={onRetry}
          style={{
            marginTop: 8,
            padding: '8px 16px',
            background: '#2563EB',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <RefreshCw size={14} />
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

export function AdminSkeleton({ lines = 3, height = 14 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="admin-skeleton"
          style={{
            height,
            width: `${100 - i * 8}%`,
          }}
        />
      ))}
    </div>
  );
}
