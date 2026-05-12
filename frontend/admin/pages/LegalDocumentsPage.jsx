import { useState, useEffect } from 'react';
import { 
  FileText, Plus, Edit, Trash2, Eye, Check, Archive, 
  Users, Clock, AlertCircle, ChevronDown, X, Save,
  Globe, Shield, BookOpen, Scale, Cookie, RefreshCw, Gavel
} from 'lucide-react';
import api from '../../api';

const DOCUMENT_TYPE_ICONS = {
  terms: Scale,
  privacy: Shield,
  community: Users,
  contest: Gavel,
  cookie: Cookie,
  refund: RefreshCw,
  dmca: FileText,
};

const STATUS_COLORS = {
  draft: '#F59E0B',
  published: '#10B981',
  archived: '#6B7280',
};

export function LegalDocumentsPage({ theme }) {
  const [documents, setDocuments] = useState([]);
  const [documentTypes, setDocumentTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [showEditor, setShowEditor] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [showAcceptances, setShowAcceptances] = useState(false);
  const [filter, setFilter] = useState({ type: '', status: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    loadDocuments();
    loadStats();
  }, [filter]);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filter.type) params.set('type', filter.type);
      if (filter.status) params.set('status', filter.status);
      
      const response = await api.request(`/admin/legal/?${params}`);
      setDocuments(response.documents || []);
      setDocumentTypes(response.document_types || []);
    } catch (err) {
      setError('Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await api.request('/admin/legal/stats/');
      setStats(response);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const handlePublish = async (docId) => {
    try {
      await api.request(`/admin/legal/${docId}/publish/`, { method: 'POST' });
      setSuccess('Document published successfully');
      loadDocuments();
      loadStats();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to publish');
    }
  };

  const handleArchive = async (docId) => {
    try {
      await api.request(`/admin/legal/${docId}/archive/`, { method: 'POST' });
      setSuccess('Document archived');
      loadDocuments();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to archive');
    }
  };

  const handleDelete = async (docId) => {
    if (!confirm('Are you sure you want to delete this document?')) return;
    try {
      await api.request(`/admin/legal/${docId}/delete/`, { method: 'DELETE' });
      setSuccess('Document deleted');
      loadDocuments();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete');
    }
  };

  const getIcon = (type) => {
    const Icon = DOCUMENT_TYPE_ICONS[type] || FileText;
    return Icon;
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: theme.txt }}>
            Legal Documents
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 14, color: theme.sub }}>
            Manage Terms & Conditions, Privacy Policy, and other legal documents
          </p>
        </div>
        <button
          onClick={() => { setSelectedDoc(null); setShowEditor(true); }}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', background: theme.pri,
            color: '#fff', border: 'none', borderRadius: 8,
            fontSize: 14, fontWeight: 600, cursor: 'pointer',
          }}
        >
          <Plus size={18} /> New Document
        </button>
      </div>

      {/* Alerts */}
      {error && (
        <div style={{
          padding: 12, background: theme.red + '15', border: `1px solid ${theme.red}`,
          borderRadius: 8, color: theme.red, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8
        }}>
          <AlertCircle size={18} /> {error}
          <button onClick={() => setError('')} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={16} color={theme.red} />
          </button>
        </div>
      )}
      {success && (
        <div style={{
          padding: 12, background: theme.green + '15', border: `1px solid ${theme.green}`,
          borderRadius: 8, color: theme.green, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8
        }}>
          <Check size={18} /> {success}
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
          {stats.document_stats.map((stat) => {
            const Icon = getIcon(stat.document_type);
            return (
              <div key={stat.document_type} style={{
                background: theme.card, borderRadius: 12, padding: 16,
                border: `1px solid ${theme.border}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: stat.document_id ? theme.green + '15' : theme.sub + '15',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon size={18} color={stat.document_id ? theme.green : theme.sub} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: theme.txt }}>{stat.document_name}</div>
                    <div style={{ fontSize: 11, color: theme.sub }}>
                      {stat.version ? `v${stat.version}` : 'Not created'}
                    </div>
                  </div>
                </div>
                {stat.document_id && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span style={{ color: theme.sub }}>Acceptances</span>
                    <span style={{ fontWeight: 600, color: theme.txt }}>
                      {stat.acceptance_count} ({stat.acceptance_rate}%)
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <select
          value={filter.type}
          onChange={(e) => setFilter({ ...filter, type: e.target.value })}
          style={{
            padding: '8px 12px', borderRadius: 8, border: `1px solid ${theme.border}`,
            background: theme.card, fontSize: 13, color: theme.txt, cursor: 'pointer',
          }}
        >
          <option value="">All Types</option>
          {documentTypes.map((dt) => (
            <option key={dt.value} value={dt.value}>{dt.label}</option>
          ))}
        </select>
        <select
          value={filter.status}
          onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          style={{
            padding: '8px 12px', borderRadius: 8, border: `1px solid ${theme.border}`,
            background: theme.card, fontSize: 13, color: theme.txt, cursor: 'pointer',
          }}
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      {/* Documents List */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: theme.sub }}>Loading...</div>
      ) : documents.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 60, background: theme.card,
          borderRadius: 12, border: `1px solid ${theme.border}`,
        }}>
          <FileText size={48} color={theme.sub} style={{ marginBottom: 16 }} />
          <div style={{ fontSize: 16, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
            No Documents Found
          </div>
          <div style={{ fontSize: 14, color: theme.sub, marginBottom: 20 }}>
            Create your first legal document to get started
          </div>
          <button
            onClick={() => { setSelectedDoc(null); setShowEditor(true); }}
            style={{
              padding: '10px 20px', background: theme.pri, color: '#fff',
              border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}
          >
            Create Document
          </button>
        </div>
      ) : (
        <div style={{ background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
          {documents.map((doc, idx) => {
            const Icon = getIcon(doc.document_type);
            return (
              <div
                key={doc.id}
                style={{
                  padding: 16,
                  borderBottom: idx < documents.length - 1 ? `1px solid ${theme.border}` : 'none',
                  display: 'flex', alignItems: 'center', gap: 16,
                }}
              >
                <div style={{
                  width: 44, height: 44, borderRadius: 10,
                  background: STATUS_COLORS[doc.status] + '15',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon size={20} color={STATUS_COLORS[doc.status]} />
                </div>
                
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: theme.txt }}>{doc.title}</span>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                      background: STATUS_COLORS[doc.status] + '20',
                      color: STATUS_COLORS[doc.status],
                      textTransform: 'uppercase',
                    }}>
                      {doc.status}
                    </span>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                      background: theme.blue + '15', color: theme.blue,
                    }}>
                      v{doc.version}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: theme.sub }}>
                    {doc.document_type_display} • Updated {new Date(doc.updated_at).toLocaleDateString()}
                    {doc.acceptance_count > 0 && ` • ${doc.acceptance_count} acceptances`}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => { setSelectedDoc(doc); setShowPreview(true); }}
                    title="Preview"
                    style={{
                      width: 36, height: 36, borderRadius: 8, border: `1px solid ${theme.border}`,
                      background: theme.bg, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <Eye size={16} color={theme.sub} />
                  </button>
                  <button
                    onClick={() => { setSelectedDoc(doc); setShowEditor(true); }}
                    title="Edit"
                    style={{
                      width: 36, height: 36, borderRadius: 8, border: `1px solid ${theme.border}`,
                      background: theme.bg, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <Edit size={16} color={theme.blue} />
                  </button>
                  {doc.status === 'draft' && (
                    <button
                      onClick={() => handlePublish(doc.id)}
                      title="Publish"
                      style={{
                        width: 36, height: 36, borderRadius: 8, border: `1px solid ${theme.green}`,
                        background: theme.green + '10', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      <Check size={16} color={theme.green} />
                    </button>
                  )}
                  {doc.status === 'published' && (
                    <>
                      <button
                        onClick={() => { setSelectedDoc(doc); setShowAcceptances(true); }}
                        title="View Acceptances"
                        style={{
                          width: 36, height: 36, borderRadius: 8, border: `1px solid ${theme.purple}`,
                          background: theme.purple + '10', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}
                      >
                        <Users size={16} color={theme.purple} />
                      </button>
                      <button
                        onClick={() => handleArchive(doc.id)}
                        title="Archive"
                        style={{
                          width: 36, height: 36, borderRadius: 8, border: `1px solid ${theme.orange}`,
                          background: theme.orange + '10', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}
                      >
                        <Archive size={16} color={theme.orange} />
                      </button>
                    </>
                  )}
                  {doc.status !== 'published' && (
                    <button
                      onClick={() => handleDelete(doc.id)}
                      title="Delete"
                      style={{
                        width: 36, height: 36, borderRadius: 8, border: `1px solid ${theme.red}`,
                        background: theme.red + '10', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      <Trash2 size={16} color={theme.red} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Editor Modal */}
      {showEditor && (
        <DocumentEditor
          theme={theme}
          document={selectedDoc}
          documentTypes={documentTypes}
          onClose={() => { setShowEditor(false); setSelectedDoc(null); }}
          onSave={() => { setShowEditor(false); setSelectedDoc(null); loadDocuments(); loadStats(); }}
        />
      )}

      {/* Preview Modal */}
      {showPreview && selectedDoc && (
        <DocumentPreview
          theme={theme}
          document={selectedDoc}
          onClose={() => { setShowPreview(false); setSelectedDoc(null); }}
        />
      )}

      {/* Acceptances Modal */}
      {showAcceptances && selectedDoc && (
        <AcceptancesModal
          theme={theme}
          document={selectedDoc}
          onClose={() => { setShowAcceptances(false); setSelectedDoc(null); }}
        />
      )}
    </div>
  );
}

function DocumentEditor({ theme, document, documentTypes, onClose, onSave }) {
  const [formData, setFormData] = useState({
    document_type: document?.document_type || 'terms',
    title: document?.title || '',
    content: document?.content || '',
    summary: document?.summary || '',
    version: document?.version || '1.0',
    requires_acceptance: document?.requires_acceptance ?? true,
    show_on_signup: document?.show_on_signup ?? true,
    is_mandatory: document?.is_mandatory ?? true,
    changes_summary: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [loadingContent, setLoadingContent] = useState(false);

  useEffect(() => {
    if (document?.id) {
      loadFullDocument();
    }
  }, [document?.id]);

  const loadFullDocument = async () => {
    try {
      setLoadingContent(true);
      const response = await api.request(`/admin/legal/${document.id}/`);
      setFormData({
        document_type: response.document.document_type,
        title: response.document.title,
        content: response.document.content,
        summary: response.document.summary,
        version: response.document.version,
        requires_acceptance: response.document.requires_acceptance,
        show_on_signup: response.document.show_on_signup,
        is_mandatory: response.document.is_mandatory,
        changes_summary: '',
      });
    } catch (err) {
      setError('Failed to load document');
    } finally {
      setLoadingContent(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    try {
      if (document?.id) {
        await api.request(`/admin/legal/${document.id}/update/`, {
          method: 'PUT',
          body: JSON.stringify(formData),
        });
      } else {
        await api.request('/admin/legal/create/', {
          method: 'POST',
          body: JSON.stringify(formData),
        });
      }
      onSave();
    } catch (err) {
      setError(err.message || 'Failed to save document');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 20,
    }} onClick={onClose}>
      <div style={{
        background: '#fff', borderRadius: 16, width: '100%', maxWidth: 900,
        maxHeight: '90vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{
          padding: '20px 24px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.txt }}>
              {document ? 'Edit Document' : 'Create New Document'}
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: theme.sub }}>
              {document ? `Editing: ${document.title}` : 'Create a new legal document'}
            </p>
          </div>
          <button onClick={onClose} style={{
            width: 36, height: 36, borderRadius: 8, border: 'none',
            background: theme.bg, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <X size={18} color={theme.sub} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {error && (
            <div style={{
              padding: 12, background: theme.red + '15', border: `1px solid ${theme.red}`,
              borderRadius: 8, color: theme.red, marginBottom: 16, fontSize: 14,
            }}>
              {error}
            </div>
          )}

          {loadingContent ? (
            <div style={{ textAlign: 'center', padding: 40, color: theme.sub }}>Loading document...</div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>
                    Document Type *
                  </label>
                  <select
                    value={formData.document_type}
                    onChange={(e) => setFormData({ ...formData, document_type: e.target.value })}
                    disabled={!!document}
                    style={{
                      width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${theme.border}`,
                      fontSize: 14, color: theme.txt, background: document ? theme.bg : '#fff',
                    }}
                  >
                    {documentTypes.map((dt) => (
                      <option key={dt.value} value={dt.value}>{dt.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>
                    Version *
                  </label>
                  <input
                    type="text"
                    value={formData.version}
                    onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                    placeholder="1.0"
                    style={{
                      width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${theme.border}`,
                      fontSize: 14, color: theme.txt, boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>
                  Title *
                </label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g., Terms and Conditions"
                  required
                  style={{
                    width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${theme.border}`,
                    fontSize: 14, color: theme.txt, boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>
                  Summary
                </label>
                <textarea
                  value={formData.summary}
                  onChange={(e) => setFormData({ ...formData, summary: e.target.value })}
                  placeholder="Brief summary of the document..."
                  rows={2}
                  style={{
                    width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${theme.border}`,
                    fontSize: 14, color: theme.txt, resize: 'vertical', boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>
                  Content * (HTML/Markdown supported)
                </label>
                <textarea
                  value={formData.content}
                  onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                  placeholder="Enter the full document content here..."
                  required
                  rows={15}
                  style={{
                    width: '100%', padding: 12, borderRadius: 8, border: `1px solid ${theme.border}`,
                    fontSize: 13, color: theme.txt, resize: 'vertical', fontFamily: 'monospace',
                    boxSizing: 'border-box', lineHeight: 1.6,
                  }}
                />
              </div>

              {document && (
                <div style={{ marginBottom: 20 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>
                    Changes Summary (for version history)
                  </label>
                  <input
                    type="text"
                    value={formData.changes_summary}
                    onChange={(e) => setFormData({ ...formData, changes_summary: e.target.value })}
                    placeholder="What changed in this version?"
                    style={{
                      width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${theme.border}`,
                      fontSize: 14, color: theme.txt, boxSizing: 'border-box',
                    }}
                  />
                </div>
              )}

              <div style={{
                padding: 16, background: theme.bg, borderRadius: 10, marginBottom: 20,
                display: 'flex', flexWrap: 'wrap', gap: 20,
              }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.requires_acceptance}
                    onChange={(e) => setFormData({ ...formData, requires_acceptance: e.target.checked })}
                  />
                  <span style={{ fontSize: 13, color: theme.txt }}>Requires user acceptance</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.show_on_signup}
                    onChange={(e) => setFormData({ ...formData, show_on_signup: e.target.checked })}
                  />
                  <span style={{ fontSize: 13, color: theme.txt }}>Show during signup</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.is_mandatory}
                    onChange={(e) => setFormData({ ...formData, is_mandatory: e.target.checked })}
                  />
                  <span style={{ fontSize: 13, color: theme.txt }}>Mandatory (blocks usage)</span>
                </label>
              </div>
            </>
          )}
        </form>

        {/* Footer */}
        <div style={{
          padding: '16px 24px', borderTop: `1px solid ${theme.border}`,
          background: '#fff',
          display: 'flex', justifyContent: 'flex-end', gap: 12,
        }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '10px 20px', background: theme.bg, border: `1px solid ${theme.border}`,
              borderRadius: 8, fontSize: 14, fontWeight: 600, color: theme.txt, cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            style={{
              padding: '10px 24px', background: saving ? theme.sub : theme.pri,
              border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600,
              color: '#fff', cursor: saving ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
            }}
          >
            <Save size={16} />
            {saving ? 'Saving...' : 'Save Document'}
          </button>
        </div>
      </div>
    </div>
  );
}

function DocumentPreview({ theme, document, onClose }) {
  const [fullDoc, setFullDoc] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDocument();
  }, [document.id]);

  const loadDocument = async () => {
    try {
      const response = await api.request(`/admin/legal/${document.id}/`);
      setFullDoc(response.document);
    } catch (err) {
      console.error('Failed to load document:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 20,
    }} onClick={onClose}>
      <div style={{
        background: '#fff', borderRadius: 16, width: '100%', maxWidth: 800,
        maxHeight: '90vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{
          padding: '20px 24px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.txt }}>
              {document.title}
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: theme.sub }}>
              Version {document.version} • {document.document_type_display}
            </p>
          </div>
          <button onClick={onClose} style={{
            width: 36, height: 36, borderRadius: 8, border: 'none',
            background: theme.bg, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <X size={18} color={theme.sub} />
          </button>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: theme.sub }}>Loading...</div>
          ) : fullDoc ? (
            <div
              style={{ fontSize: 14, lineHeight: 1.8, color: theme.txt }}
              dangerouslySetInnerHTML={{ __html: fullDoc.content.replace(/\n/g, '<br/>') }}
            />
          ) : (
            <div style={{ textAlign: 'center', padding: 40, color: theme.sub }}>Failed to load document</div>
          )}
        </div>
      </div>
    </div>
  );
}

function AcceptancesModal({ theme, document, onClose }) {
  const [acceptances, setAcceptances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    loadAcceptances();
  }, [document.id]);

  const loadAcceptances = async () => {
    try {
      const response = await api.request(`/admin/legal/${document.id}/acceptances/`);
      setAcceptances(response.acceptances || []);
      setTotal(response.total_acceptances);
    } catch (err) {
      console.error('Failed to load acceptances:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 20,
    }} onClick={onClose}>
      <div style={{
        background: '#fff', borderRadius: 16, width: '100%', maxWidth: 600,
        maxHeight: '80vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{
          padding: '20px 24px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.txt }}>
              User Acceptances
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: theme.sub }}>
              {total} users accepted {document.title}
            </p>
          </div>
          <button onClick={onClose} style={{
            width: 36, height: 36, borderRadius: 8, border: 'none',
            background: theme.bg, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <X size={18} color={theme.sub} />
          </button>
        </div>

        <div style={{ flex: 1, overflow: 'auto' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: theme.sub }}>Loading...</div>
          ) : acceptances.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: theme.sub }}>No acceptances yet</div>
          ) : (
            acceptances.map((a, idx) => (
              <div key={idx} style={{
                padding: '12px 24px',
                borderBottom: idx < acceptances.length - 1 ? `1px solid ${theme.border}` : 'none',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>{a.username}</div>
                  <div style={{ fontSize: 12, color: theme.sub }}>{a.email}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 12, color: theme.sub }}>
                    v{a.version_accepted}
                  </div>
                  <div style={{ fontSize: 11, color: theme.sub }}>
                    {new Date(a.accepted_at).toLocaleString()}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default LegalDocumentsPage;




