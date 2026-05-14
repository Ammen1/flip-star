import {
  BarChart3, Users, FileVideo, CreditCard, LogOut, LayoutDashboard,
  Settings, Key, FileText, Activity, Bell, Shield, Lock, Trophy,
  Target, Zap, Award, Flag, Scale, Smartphone, Gift as GiftIcon, Coins, Zap as ChargingIcon,
  LifeBuoy,
} from 'lucide-react';
export function AdminSidebar({ theme, currentPage, onPageChange, adminUser, onLogout }) {
  // Grouped menu structure for cleaner navigation
  const sections = [
    {
      label: 'Overview',
      items: [
        { id: 'dashboard',   icon: LayoutDashboard, label: 'Dashboard' },
        { id: 'analytics',   icon: BarChart3,       label: 'Analytics' },
        { id: 'performance', icon: Activity,        label: 'Performance' },
      ],
    },
    {
      label: 'Operations',
      items: [
        { id: 'mobile-app', icon: Smartphone, label: 'Mobile App' },
        { id: 'judging',    icon: Target,     label: 'Judging Portal' },
        { id: 'anti-cheat', icon: Zap,        label: 'Anti-Cheat' },
        { id: 'reports',    icon: Flag,       label: 'Reports' },
        { id: 'support',    icon: LifeBuoy,   label: 'Support Requests' },
      ],
    },
    {
      label: 'Content',
      items: [
        { id: 'users',            icon: Users,     label: 'Users' },
        { id: 'content',          icon: FileVideo, label: 'Content' },
        { id: 'master-campaigns', icon: Trophy,    label: 'Master Campaigns' },
        { id: 'campaigns',        icon: Award,     label: 'Sub-Campaigns' },
      ],
    },
    {
      label: 'Monetization',
      items: [
        { id: 'gifts',         icon: GiftIcon,   label: 'Gifts' },
        { id: 'coins',         icon: Coins,      label: 'Coin Management' },
        { id: 'subscriptions', icon: CreditCard, label: 'Subscriptions' },
        { id: 'charging',      icon: ChargingIcon, label: 'On-Demand Charging' },
      ],
    },
    {
      label: 'System',
      items: [
        { id: 'notifications', icon: Bell,     label: 'Notifications' },
        { id: 'admins',        icon: Shield,   label: 'Admins' },
        { id: 'api-keys',      icon: Key,      label: 'API Keys' },
        { id: 'security',      icon: Lock,     label: 'Security' },
        { id: 'legal',         icon: Scale,    label: 'Legal Docs' },
        { id: 'logs',          icon: FileText, label: 'Logs' },
        { id: 'settings',      icon: Settings, label: 'Settings' },
      ],
    },
  ];

  const PRIMARY = theme.pri || '#2563EB';
  const PRIMARY_DARK = theme.dark || '#1D4ED8';
  const TEXT = '#FFFFFF'; // Force white text for visibility
  const SUB = '#A8A8A8';  // Force gray text for visibility
  const BORDER = theme.border || '#333333';

  return (
    <aside style={{
      width: 240,
      background: '#1A1A1A',
      display: 'flex',
      flexDirection: 'column',
      borderRight: `1px solid ${BORDER}`,
      height: '100vh',
      position: 'fixed',
      left: 0,
      top: 0,
      zIndex: 1000,
      boxShadow: '0 0 24px rgba(0, 0, 0, 0.5)',
    }}>
      {/* Brand */}
      <div style={{
        padding: '20px 20px 16px',
        borderBottom: `1px solid ${BORDER}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            background: `linear-gradient(135deg, ${PRIMARY}, ${PRIMARY_DARK})`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 800,
            fontSize: 14,
            boxShadow: '0 4px 12px rgba(37, 99, 235, 0.25)',
          }}>
            FS
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{
              fontSize: 16,
              fontWeight: 800,
              color: TEXT,
              letterSpacing: '-0.02em',
              lineHeight: 1.1,
            }}>
              FlipStar
            </div>
            <div style={{
              fontSize: 10,
              color: SUB,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginTop: 2,
            }}>
              Admin Panel
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{
        flex: 1,
        padding: '12px 8px',
        overflowY: 'auto',
      }}>
        {sections.map((section, sIdx) => (
          <div key={section.label} style={{ marginBottom: sIdx === sections.length - 1 ? 0 : 14 }}>
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              color: SUB,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              padding: '6px 12px',
            }}>
              {section.label}
            </div>
            {section.items.map(item => {
              const Icon = item.icon;
              const isActive = currentPage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onPageChange(item.id)}
                  className={`admin-sidebar-item ${isActive ? 'active' : ''}`}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.background = '#262626';
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.background = 'transparent';
                  }}
                  style={{
                    width: 'calc(100% - 4px)',
                    padding: '9px 12px',
                    margin: '2px 2px',
                    background: isActive ? `${PRIMARY}14` : 'transparent',
                    border: 'none',
                    borderRadius: 8,
                    color: isActive ? PRIMARY : TEXT,
                    fontSize: 13,
                    fontWeight: isActive ? 600 : 500,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    textAlign: 'left',
                  }}
                >
                  <Icon size={18} strokeWidth={isActive ? 2.4 : 2} />
                  <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.label}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div style={{
        padding: '10px 12px',
        borderTop: `1px solid ${BORDER}`,
        background: '#1A1A1A',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}>
          <div style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: `linear-gradient(135deg, ${PRIMARY}, ${PRIMARY_DARK})`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 13,
            fontWeight: 700,
            color: '#fff',
            flexShrink: 0,
          }}>
            {adminUser?.username?.[0]?.toUpperCase() || 'A'}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 12,
              fontWeight: 600,
              color: TEXT,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {adminUser?.username || 'Admin'}
            </div>
            <div style={{
              fontSize: 10,
              color: SUB,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              Administrator
            </div>
          </div>
        </div>

        <button
          onClick={onLogout}
          style={{
            width: '100%',
            padding: '6px 10px',
            background: 'transparent',
            border: `1px solid ${BORDER}`,
            borderRadius: 6,
            color: SUB,
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#FEF2F2';
            e.currentTarget.style.borderColor = '#FCA5A5';
            e.currentTarget.style.color = '#DC2626';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.borderColor = BORDER;
            e.currentTarget.style.color = SUB;
          }}
        >
          <LogOut size={12} />
          Logout
        </button>
      </div>
    </aside>
  );
}




