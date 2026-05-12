import { useState, useEffect } from 'react';
import { CreditCard, TrendingUp, TrendingDown, AlertCircle, CheckCircle, XCircle, Download, RefreshCw, Calendar, Filter, Search } from 'lucide-react';
import api from '../../api';

export function ChargingDashboard({ theme }) {
  const [statistics, setStatistics] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadStatistics();
    loadTransactions();
  }, [days, statusFilter, page]);

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
      const statusParam = statusFilter ? `&status=${statusFilter}` : '';
      const response = await api.request(
        `/charging/on-demand/transactions/?days=${days}&page=${page}&page_size=20${statusParam}`
      );
      setTransactions(response);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    }
  };

  const handleExport = () => {
    // Export transactions to CSV
    if (!transactions.transactions) return;
    
    const headers = ['Date', 'User', 'Phone', 'Tier', 'Amount (ETB)', 'Status', 'Error'];
    const rows = transactions.transactions.map(t => [
      new Date(t.created_at).toLocaleDateString(),
      t.user,
      t.phone_number,
      t.subscription_tier || 'N/A',
      t.amount_etb,
      t.status,
      t.error_message || ''
    ]);
    
    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `charging_transactions_${days}days.csv`;
    a.click();
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'success': return '#10B981';
      case 'failed': return '#EF4444';
      case 'insufficient_balance': return '#F59E0B';
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
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: theme.txt }}>
            On-Demand Charging
          </h1>
          <p style={{ margin: '4px 0 0', color: theme.sub, fontSize: 14 }}>
            Track airtime charging transactions for on-demand subscriptions
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            style={{
              padding: '8px 12px',
              borderRadius: 8,
              border: `1px solid ${theme.border}`,
              background: theme.card,
              color: theme.txt,
              fontSize: 14
            }}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button
            onClick={() => { loadStatistics(); loadTransactions(); }}
            style={{
              padding: '8px 16px',
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
              padding: '8px 16px',
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

      {statistics && (
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
              value={statistics.total_transactions}
              color={theme.pri}
              theme={theme}
            />
            <StatCard
              icon={CheckCircle}
              label="Successful"
              value={statistics.successful_transactions}
              color="#10B981"
              theme={theme}
            />
            <StatCard
              icon={XCircle}
              label="Failed"
              value={statistics.failed_transactions}
              color="#EF4444"
              theme={theme}
            />
            <StatCard
              icon={AlertCircle}
              label="Insufficient Balance"
              value={statistics.insufficient_balance}
              color="#F59E0B"
              theme={theme}
            />
            <StatCard
              icon={TrendingUp}
              label="Expected Collection"
              value={`ETB ${statistics.expected_collection.toFixed(2)}`}
              color="#3B82F6"
              theme={theme}
            />
            <StatCard
              icon={TrendingDown}
              label="Actual Collection"
              value={`ETB ${statistics.actual_collection.toFixed(2)}`}
              color="#8B5CF6"
              theme={theme}
            />
            <StatCard
              icon={CheckCircle}
              label="Success Rate"
              value={`${statistics.success_rate}%`}
              color="#10B981"
              theme={theme}
            />
          </div>

          {/* Transactions Table */}
          <div style={{
            background: theme.card,
            borderRadius: 12,
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
                Transactions
              </h2>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 6,
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.txt,
                    fontSize: 13
                  }}
                >
                  <option value="">All Status</option>
                  <option value="success">Success</option>
                  <option value="failed">Failed</option>
                  <option value="insufficient_balance">Insufficient Balance</option>
                  <option value="pending">Pending</option>
                </select>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{
                    background: theme.bg,
                    borderBottom: `1px solid ${theme.border}`
                  }}>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>Date</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>User</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>Phone</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>Tier</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'right',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>Amount (ETB)</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>Status</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.transactions?.map((t, idx) => {
                    const StatusIcon = getStatusIcon(t.status);
                    return (
                      <tr key={idx} style={{
                        borderBottom: idx < transactions.transactions.length - 1 ? `1px solid ${theme.border}` : 'none'
                      }}>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt }}>
                          {new Date(t.created_at).toLocaleString()}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt }}>
                          {t.user}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt, fontFamily: 'monospace' }}>
                          {t.phone_number}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt }}>
                          {t.subscription_tier || 'N/A'}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.txt, textAlign: 'right', fontWeight: 600 }}>
                          {t.amount_etb.toFixed(2)}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: getStatusColor(t.status), display: 'flex', alignItems: 'center', gap: 6 }}>
                          <StatusIcon size={14} />
                          {t.status}
                        </td>
                        <td style={{ padding: 12, fontSize: 13, color: theme.sub, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {t.error_message || '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div style={{
              padding: 16,
              borderTop: `1px solid ${theme.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div style={{ fontSize: 13, color: theme.sub }}>
                Showing {transactions.transactions?.length || 0} of {transactions.total || 0} transactions
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 6,
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.txt,
                    fontSize: 13,
                    cursor: page === 1 ? 'not-allowed' : 'pointer',
                    opacity: page === 1 ? 0.5 : 1
                  }}
                >
                  Previous
                </button>
                <span style={{ padding: '6px 12px', fontSize: 13, color: theme.txt }}>
                  Page {page}
                </span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={!transactions.transactions || transactions.transactions.length < 20}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 6,
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.txt,
                    fontSize: 13,
                    cursor: !transactions.transactions || transactions.transactions.length < 20 ? 'not-allowed' : 'pointer',
                    opacity: !transactions.transactions || transactions.transactions.length < 20 ? 0.5 : 1
                  }}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </>
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
