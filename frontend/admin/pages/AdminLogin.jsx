import { useState } from 'react';
import { Lock, Mail, AlertCircle } from 'lucide-react';
import { adminTheme } from '../theme';

export function AdminLogin({ onLogin, theme }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result = await onLogin(email, password);
    
    if (!result.success) {
      setError(result.error);
    }
    
    setLoading(false);
  };

  return (
    <div className="admin-root" style={{
      width: '100vw',
      height: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: adminTheme.colors.background,
      padding: adminTheme.spacing.xl,
      fontFamily: adminTheme.typography.fontFamily,
    }}>
      <div className="admin-modal-content" style={{
        width: '100%',
        maxWidth: 440,
        padding: adminTheme.spacing['3xl'],
        background: adminTheme.colors.card,
        borderRadius: adminTheme.borderRadius.xl,
        boxShadow: adminTheme.shadows.xl,
      }}>
        {/* Logo */}
        <div style={{
          textAlign: 'center',
          marginBottom: adminTheme.spacing['2xl'],
        }}>
          <div style={{
            width: 72,
            height: 72,
            margin: `0 auto ${adminTheme.spacing.lg}`,
            borderRadius: adminTheme.borderRadius.lg,
            background: `linear-gradient(135deg, ${adminTheme.colors.primary}, ${adminTheme.colors.secondary})`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: adminTheme.typography.fontSize['3xl'],
            fontWeight: adminTheme.typography.fontWeight.bold,
            color: adminTheme.colors.textLight,
            letterSpacing: '-0.02em',
            boxShadow: adminTheme.shadows.lg,
          }}>
            FS
          </div>
          <h1 style={{
            margin: 0,
            fontSize: adminTheme.typography.fontSize['3xl'],
            fontWeight: adminTheme.typography.fontWeight.semibold,
            color: adminTheme.colors.textPrimary,
            marginBottom: adminTheme.spacing.sm,
          }}>
            Admin Panel
          </h1>
          <p style={{
            margin: 0,
            fontSize: adminTheme.typography.fontSize.base,
            color: adminTheme.colors.textSecondary,
          }}>
            Sign in to access the dashboard
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div style={{
            padding: `${adminTheme.spacing.md} ${adminTheme.spacing.lg}`,
            background: `${adminTheme.colors.error}15`,
            border: `1px solid ${adminTheme.colors.error}`,
            borderRadius: adminTheme.borderRadius.md,
            marginBottom: adminTheme.spacing['2xl'],
            display: 'flex',
            alignItems: 'center',
            gap: adminTheme.spacing.md,
            color: adminTheme.colors.error,
            fontSize: adminTheme.typography.fontSize.base,
          }}>
            <AlertCircle size={20} />
            {error}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: adminTheme.spacing.xl }}>
            <label style={{
              display: 'block',
              fontSize: adminTheme.typography.fontSize.base,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              color: adminTheme.colors.textPrimary,
              marginBottom: adminTheme.spacing.sm,
            }}>
              Email
            </label>
            <div style={{ position: 'relative' }}>
              <Mail size={20} style={{
                position: 'absolute',
                left: adminTheme.spacing.lg,
                top: '50%',
                transform: 'translateY(-50%)',
                color: adminTheme.colors.textSecondary,
              }} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@flipstar.com"
                required
                style={{
                  width: '100%',
                  padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg} ${adminTheme.spacing.sm} 48px`,
                  border: `1px solid ${adminTheme.colors.border}`,
                  borderRadius: adminTheme.borderRadius.md,
                  fontSize: adminTheme.typography.fontSize.base,
                  outline: 'none',
                  transition: `all ${adminTheme.transitions.base}`,
                }}
                onFocus={(e) => e.target.style.borderColor = adminTheme.colors.primary}
                onBlur={(e) => e.target.style.borderColor = adminTheme.colors.border}
              />
            </div>
          </div>

          <div style={{ marginBottom: adminTheme.spacing['2xl'] }}>
            <label style={{
              display: 'block',
              fontSize: adminTheme.typography.fontSize.base,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              color: adminTheme.colors.textPrimary,
              marginBottom: adminTheme.spacing.sm,
            }}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <Lock size={20} style={{
                position: 'absolute',
                left: adminTheme.spacing.lg,
                top: '50%',
                transform: 'translateY(-50%)',
                color: adminTheme.colors.textSecondary,
              }} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                required
                style={{
                  width: '100%',
                  padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg} ${adminTheme.spacing.sm} 48px`,
                  border: `1px solid ${adminTheme.colors.border}`,
                  borderRadius: adminTheme.borderRadius.md,
                  fontSize: adminTheme.typography.fontSize.base,
                  outline: 'none',
                  transition: `all ${adminTheme.transitions.base}`,
                }}
                onFocus={(e) => e.target.style.borderColor = adminTheme.colors.primary}
                onBlur={(e) => e.target.style.borderColor = adminTheme.colors.border}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg}`,
              background: adminTheme.colors.primary,
              border: 'none',
              borderRadius: adminTheme.borderRadius.md,
              color: adminTheme.colors.textLight,
              fontSize: adminTheme.typography.fontSize.lg,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
              transition: `all ${adminTheme.transitions.base}`,
            }}
            onMouseEnter={(e) => {
              if (!loading) e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            {loading ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: adminTheme.spacing.sm }}>
                <span className="admin-spinner sm" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.4)' }} />
                Signing in...
              </span>
            ) : 'Sign In'}
          </button>
        </form>

        {/* Footer */}
        <div style={{
          marginTop: adminTheme.spacing['2xl'],
          paddingTop: adminTheme.spacing['2xl'],
          borderTop: `1px solid ${adminTheme.colors.border}`,
          background: adminTheme.colors.card,
          textAlign: 'center',
        }}>
          <p style={{
            margin: 0,
            fontSize: adminTheme.typography.fontSize.xs,
            color: adminTheme.colors.textSecondary,
            fontWeight: adminTheme.typography.fontWeight.medium,
          }}>
            🔒 Secure admin access only
          </p>
        </div>
      </div>
    </div>
  );
}




