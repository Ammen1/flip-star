import { useState, useEffect } from 'react';
import { CreditCard, TrendingUp, TrendingDown, AlertCircle, CheckCircle, XCircle, Download, RefreshCw, Calendar, Filter, Search, User, Phone, BarChart3, PieChart, DollarSign, Activity, Users, Star } from 'lucide-react';
import api from '../../api';

export function ChargingDashboard({ theme }) {
  const [activeTab, setActiveTab] = useState('transactions'); // transactions, analytics_daily, analytics_monthly, analytics_yearly
  const [statistics, setStatistics] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState('phone'); // phone, user_id
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [analyticsPeriod, setAnalyticsPeriod] = useState('daily'); // daily, monthly, yearly

  useEffect(() => {
    loadStatistics();
    loadTransactions();
  }, [days, statusFilter, page]);

  useEffect(() => {
    if (activeTab.startsWith('analytics')) {
      loadAnalytics();
    }
  }, [activeTab, analyticsPeriod]);

  const loadStatistics = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/charging/on-demand/statistics/?days=${days}`);
      setStatistics(response);
    } catch (err) {
      setError('Failed to load statistics');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadTransactions = async () => {
    try {
      const response = await api.request(`/charging/on-demand/transactions/?days=${days}&page=${page}&page_size=50`);
      setTransactions(response);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    }
  };

  const loadAnalytics = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/charging/on-demand/analytics/?period=${analyticsPeriod}`);
      setAnalyticsData(response);
    } catch (err) {
      console.error('Failed to load analytics:', err);
      setError('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    setSearching(true);
    try {
      let url = `/charging/on-demand/search/?`;
      if (searchType === 'phone') {
        url += `phone=${searchQuery}`;
      } else {
        url += `user_id=${searchQuery}`;
      }
      const response = await api.request(url);
      setSearchResults(response);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setSearching(false);
    }
  };

  const handleExport = () => {
    const dataToExport = searchResults?.transactions || statistics?.transactions || [];
    if (!dataToExport || dataToExport.length === 0) return;

    const headers = ['Date', 'User', 'Phone', 'Tier', 'Amount (ETB)', 'Status', 'Transaction ID'];
    const rows = dataToExport.map(t => [
      t.created_at || '',
      t.user || '',
      t.phone_number || '',
      t.subscription_tier || '',
      t.amount_etb || 0,
      t.status || '',
      t.transaction_id || ''
    ]);

    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ondemand_transactions_${searchQuery ? 'search' : 'export'}.csv`;
    a.click();
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'success': return '#10B981';
      case 'failed': return '#EF4444';
      case 'insufficient_balance': return '#8fc441';
      case 'pending': return '#3B82F6';
      default: return '#6B7280';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'success': return CheckCircle;
      case 'failed': return XCircle;
      case 'insufficient_balance': return AlertCircle;
      default: return CreditCard;
    }
  };

  if (loading && !statistics) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
        <RefreshCw className="animate-spin" style={{ margin: '0 auto 16px', display: 'block' }} />
        Loading charging data...
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: '#fff' }}>
            On-Demand Charging
          </h1>
          <p style={{ margin: '4px 0 0', color: theme.sub, fontSize: 14 }}>
            Track airtime charging transactions and analytics
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={() => { loadStatistics(); loadTransactions(); if (activeTab.startsWith('analytics')) loadAnalytics(); }}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: `1px solid ${theme.border}`,
              background: theme.card,
              color: theme.txt,
              fontSize: 14,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            onClick={handleExport}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: 'none',
              background: theme.pri,
              color: '#fff',
              fontSize: 14,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}
          >
            <Download size={16} />
            Export
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 8, borderBottom: `1px solid ${theme.border}`, paddingBottom: 16 }}>
        {[
          { id: 'transactions', label: 'Transactions', icon: CreditCard },
          { id: 'search', label: 'Search', icon: Search },
          { id: 'analytics_daily', label: 'Daily Analytics', icon: BarChart3 },
          { id: 'analytics_monthly', label: 'Monthly Analytics', icon: PieChart },
          { id: 'analytics_yearly', label: 'Yearly Analytics', icon: Activity },
        ].map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '10px 16px',
                background: activeTab === tab.id ? theme.pri : 'transparent',
                border: 'none',
                borderRadius: 8,
                color: activeTab === tab.id ? '#fff' : theme.sub,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                transition: 'all 0.2s',
              }}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div style={{
          padding: 16,
          background: '#FEF2F2',
          border: '1px solid #FCA5A5',
          borderRadius: 8,
          marginBottom: 24,
          color: '#DC2626',
          fontSize: 14,
          display: 'flex',
          alignItems: 'center',
          gap: 8
        }}>
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* Transactions Tab */}
      {activeTab === 'transactions' && statistics && (
        <>
          {/* Statistics Cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 16,
            marginBottom: 24
          }}>
            <StatCard
              icon={CreditCard}
              label="Total Transactions"
              value={statistics.total_transactions || 0}
              color={theme.pri}
              theme={theme}
            />
            <StatCard
              icon={CheckCircle}
              label="Successful"
              value={statistics.successful_transactions || 0}
              color="#10B981"
              theme={theme}
            />
            <StatCard
              icon={XCircle}
              label="Failed"
              value={statistics.failed_transactions || 0}
              color="#EF4444"
              theme={theme}
            />
            <StatCard
              icon={AlertCircle}
              label="Insufficient Balance"
              value={statistics.insufficient_balance || 0}
              color="#F59E0B"
              theme={theme}
            />
            <StatCard
              icon={DollarSign}
              label="Expected Collection"
              value={`ETB ${statistics.expected_collection?.toFixed(2) || '0.00'}`}
              color="#3B82F6"
              theme={theme}
            />
            <StatCard
              icon={TrendingUp}
              label="Actual Collection"
              value={`ETB ${statistics.actual_collection?.toFixed(2) || '0.00'}`}
              color="#10B981"
              theme={theme}
            />
            <StatCard
              icon={Activity}
              label="Success Rate"
              value={`${statistics.success_rate?.toFixed(1) || 0}%`}
              color="#8B5CF6"
              theme={theme}
            />
          </div>

          {/* Transactions Table */}
          <div style={{
            background: theme.card,
            borderRadius: 12,
            padding: 24,
            border: `1px solid ${theme.border}`,
            overflow: 'hidden'
          }}>
            <div style={{
              padding: 16,
              borderBottom: `1px solid ${theme.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: theme.txt }}>
                Recent Charging Transactions
              </h2>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                <thead>
                  <tr style={{
                    background: theme.bg,
                    borderBottom: `1px solid ${theme.border}`
                  }}>
                    {['Date', 'User', 'Phone', 'Tier', 'Amount (ETB)', 'Status', 'Transaction ID'].map(h => (
                      <th key={h} style={{
                        padding: 12,
                        textAlign: h === 'Amount (ETB)' ? 'right' : 'left',
                        fontSize: 12,
                        fontWeight: 600,
                        color: theme.sub,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(!statistics.transactions || statistics.transactions.length === 0) ? (
                    <tr>
                      <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: theme.sub, fontSize: 13 }}>
                        No transactions yet.
                      </td>
                    </tr>
                  ) : statistics.transactions.map((t, idx) => (
                    <tr key={t.id || idx} style={{
                      borderBottom: idx < statistics.transactions.length - 1 ? `1px solid ${theme.border}` : 'none'
                    }}>
                      <td style={{ padding: 12, fontSize: 12, color: theme.sub, whiteSpace: 'nowrap' }}>
                        {new Date(t.created_at).toLocaleString()}
                      </td>
                      <td style={{ padding: 12, fontSize: 13, color: theme.txt, whiteSpace: 'nowrap' }}>
                        <div style={{ fontWeight: 600 }}>@{t.user}</div>
                      </td>
                      <td style={{ padding: 12, fontSize: 13, color: theme.txt, whiteSpace: 'nowrap' }}>{t.phone_number || '—'}</td>
                      <td style={{ padding: 12, fontSize: 13, color: theme.txt, whiteSpace: 'nowrap' }}>{t.subscription_tier || '—'}</td>
                      <td style={{ padding: 12, fontSize: 13, color: theme.txt, textAlign: 'right', fontWeight: 700, whiteSpace: 'nowrap' }}>
                        {t.amount_etb?.toFixed(2) || '0.00'}
                      </td>
                      <td style={{ padding: 12, fontSize: 13, whiteSpace: 'nowrap' }}>
                        <span style={{
                          padding: '3px 8px', borderRadius: 999,
                          background: t.status === 'success' ? '#10B98122' : t.status === 'failed' ? '#EF444422' : '#F59E0B22',
                          color: t.status === 'success' ? '#10B981' : t.status === 'failed' ? '#EF4444' : '#F59E0B',
                          fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.4,
                        }}>{t.status || '—'}</span>
                      </td>
                      <td style={{ padding: 12, fontSize: 12, color: theme.sub, whiteSpace: 'nowrap' }}>
                        {t.transaction_id || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Search Tab */}
      {activeTab === 'search' && (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`
        }}>
          <h2 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 600, color: theme.txt }}>
            Search Transactions
          </h2>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setSearchType('phone')}
                style={{
                  padding: '8px 16px',
                  borderRadius: 6,
                  border: searchType === 'phone' ? 'none' : `1px solid ${theme.border}`,
                  background: searchType === 'phone' ? theme.pri : theme.bg,
                  color: searchType === 'phone' ? '#fff' : theme.txt,
                  fontSize: 13,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6
                }}
              >
                <Phone size={14} />
                Phone
              </button>
              <button
                onClick={() => setSearchType('user_id')}
                style={{
                  padding: '8px 16px',
                  borderRadius: 6,
                  border: searchType === 'user_id' ? 'none' : `1px solid ${theme.border}`,
                  background: searchType === 'user_id' ? theme.pri : theme.bg,
                  color: searchType === 'user_id' ? '#fff' : theme.txt,
                  fontSize: 13,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6
                }}
              >
                <User size={14} />
                User ID
              </button>
            </div>
            <input
              type={searchType === 'user_id' ? 'number' : 'text'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={searchType === 'phone' ? 'Enter phone number' : 'Enter user ID'}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              style={{
                flex: 1,
                padding: '8px 12px',
                borderRadius: 6,
                border: `1px solid ${theme.border}`,
                background: theme.bg,
                color: theme.txt,
                fontSize: 14
              }}
            />
            <button
              onClick={handleSearch}
              disabled={searching}
              style={{
                padding: '8px 16px',
                borderRadius: 6,
                border: 'none',
                background: theme.pri,
                color: '#fff',
                fontSize: 14,
                cursor: searching ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}
            >
              {searching ? <RefreshCw size={14} className="animate-spin" /> : <Search size={14} />}
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>

          {searchResults && searchResults.transactions && (
            <div style={{ marginTop: 20 }}>
              <div style={{ marginBottom: 12, fontSize: 13, color: theme.sub }}>
                Found {searchResults.transactions.length} transactions
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                  <thead>
                    <tr style={{
                      background: theme.bg,
                      borderBottom: `1px solid ${theme.border}`
                    }}>
                      {['Date', 'User', 'Phone', 'Tier', 'Amount (ETB)', 'Status', 'Transaction ID'].map(h => (
                        <th key={h} style={{
                          padding: 12,
                          textAlign: h === 'Amount (ETB)' ? 'right' : 'left',
                          fontSize: 12,
                          fontWeight: 600,
                          color: theme.sub,
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                          whiteSpace: 'nowrap',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {searchResults.transactions.map((t, idx) => (
                      <tr key={t.id || idx} style={{
                        borderBottom: idx < searchResults.transactions.length - 1 ? `1px solid ${theme.border}` : 'none'
                      }}>
                        <td style={{ padding: 12, fontSize: 12, color: theme.sub, whiteSpace: 'nowrap' }}>
                          {new Date(t.created_at).toLocaleString()}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt, whiteSpace: 'nowrap' }}>
                          <div style={{ fontWeight: 600 }}>@{t.user}</div>
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt, whiteSpace: 'nowrap' }}>{t.phone_number || '—'}</td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt, whiteSpace: 'nowrap' }}>{t.subscription_tier || '—'}</td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt, textAlign: 'right', fontWeight: 700, whiteSpace: 'nowrap' }}>
                          {t.amount_etb?.toFixed(2) || '0.00'}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, whiteSpace: 'nowrap' }}>
                          <span style={{
                            padding: '3px 8px', borderRadius: 999,
                            background: t.status === 'success' ? '#10B98122' : t.status === 'failed' ? '#EF444422' : '#F59E0B22',
                            color: t.status === 'success' ? '#10B981' : t.status === 'failed' ? '#EF4444' : '#F59E0B',
                            fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.4,
                          }}>{t.status || '—'}</span>
                        </td>
                        <td style={{ padding: 12, fontSize: 12, color: theme.sub, whiteSpace: 'nowrap' }}>
                          {t.transaction_id || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Analytics Tabs */}
      {activeTab.startsWith('analytics') && analyticsData && (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: theme.txt }}>
              {activeTab.replace('analytics_', '').charAt(0).toUpperCase() + activeTab.replace('analytics_', '').slice(1)} Analytics
            </h2>
            {loading && <RefreshCw size={16} className="animate-spin" color={theme.sub} />}
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 16
          }}>
            <StatCard
              icon={CreditCard}
              label="Total Transactions"
              value={analyticsData.total_transactions || 0}
              color={theme.pri}
              theme={theme}
            />
            <StatCard
              icon={CheckCircle}
              label="Successful"
              value={analyticsData.successful || 0}
              color="#10B981"
              theme={theme}
            />
            <StatCard
              icon={XCircle}
              label="Failed"
              value={analyticsData.failed || 0}
              color="#EF4444"
              theme={theme}
            />
            <StatCard
              icon={AlertCircle}
              label="Insufficient Balance"
              value={analyticsData.insufficient_balance || 0}
              color="#F59E0B"
              theme={theme}
            />
            <StatCard
              icon={DollarSign}
              label="Total Revenue"
              value={`ETB ${analyticsData.total_revenue?.toFixed(2) || '0.00'}`}
              color="#8B5CF6"
              theme={theme}
            />
            <StatCard
              icon={Activity}
              label="Success Rate"
              value={`${analyticsData.success_rate?.toFixed(1) || 0}%`}
              color="#10B981"
              theme={theme}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color, theme }) {
  return (
    <div style={{
      background: theme.card,
      borderRadius: 12,
      padding: 20,
      border: `1px solid ${theme.border}`,
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }}>
      <div style={{
        width: 40,
        height: 40,
        borderRadius: 10,
        background: `${color}15`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: color
      }}>
        <Icon size={20} />
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: theme.txt }}>
        {value}
      </div>
      <div style={{ fontSize: 13, color: theme.sub, fontWeight: 500 }}>
        {label}
      </div>
    </div>
  );
}
