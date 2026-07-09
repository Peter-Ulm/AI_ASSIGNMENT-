import React, { useEffect, useRef, useState } from 'react';
import { FaTrash, FaSearch, FaFileUpload, FaPlus } from 'react-icons/fa';
import {
  deleteDocument,
  getRagStatus,
  listDocuments,
  searchKnowledgeBase,
  uploadFileDocument,
  uploadTextDocument,
} from '../services/api';
import { RagDocument, RagSearchResult, RagStatus } from '../types';

const KnowledgeBasePage: React.FC = () => {
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [source, setSource] = useState('');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string } | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<RagSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    try {
      setDocuments(await listDocuments());
      setStatus(await getRagStatus());
    } catch {
      // Backend not reachable yet; leave the list empty rather than erroring loudly here.
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const flash = (type: 'error' | 'success', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const handleAddText = async () => {
    if (!source.trim() || !text.trim()) {
      flash('error', 'Add a source name and some text first.');
      return;
    }
    setBusy(true);
    try {
      const doc = await uploadTextDocument(source.trim(), text.trim());
      flash('success', `Added "${doc.source}" (${doc.chunks} chunks).`);
      setSource('');
      setText('');
      await refresh();
    } catch (err) {
      flash('error', err instanceof Error ? err.message : 'Failed to add text.');
    } finally {
      setBusy(false);
    }
  };

  const handleFilePicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    try {
      const doc = await uploadFileDocument(file);
      flash('success', `Added "${doc.source}" (${doc.chunks} chunks).`);
      await refresh();
    } catch (err) {
      flash('error', err instanceof Error ? err.message : 'Failed to upload file.');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (docSource: string) => {
    const ok = await deleteDocument(docSource);
    if (ok) {
      flash('success', `Removed "${docSource}".`);
      await refresh();
    } else {
      flash('error', `Could not remove "${docSource}".`);
    }
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setResults(await searchKnowledgeBase(query.trim()));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Knowledge Base</h1>
        {status && (
          <p className="page-subtitle">
            {status.chunk_count} chunks · {status.source_count} documents · embedding model:{' '}
            {status.embedding_model}
          </p>
        )}
      </div>

      {message && <div className={`kb-message ${message.type}`}>{message.text}</div>}

      <div className="page-grid">
        <section className="page-card">
          <h2>Add documents</h2>
          <input
            className="kb-text-input"
            placeholder="Source name (e.g. Fee Policy)"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            disabled={busy}
          />
          <textarea
            className="kb-textarea kb-textarea-lg"
            placeholder="Paste text to add to the knowledge base..."
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
          />
          <div className="kb-upload-row">
            <button className="kb-add-btn" onClick={handleAddText} disabled={busy}>
              <FaPlus size={11} /> Add text
            </button>
            <button className="kb-file-btn" onClick={() => fileInputRef.current?.click()} disabled={busy}>
              <FaFileUpload size={11} /> Upload file
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.pdf"
              hidden
              onChange={handleFilePicked}
            />
          </div>
        </section>

        <section className="page-card">
          <h2>Documents ({documents.length})</h2>
          <div className="kb-doc-list kb-doc-list-lg">
            {documents.length === 0 ? (
              <div className="kb-empty">No documents yet.</div>
            ) : (
              documents.map((doc) => (
                <div className="kb-doc-item" key={doc.source}>
                  <span className="kb-doc-name" title={doc.source}>{doc.source}</span>
                  <span className="kb-doc-count">{doc.chunks}</span>
                  <button className="kb-doc-delete" onClick={() => handleDelete(doc.source)} aria-label="Delete">
                    <FaTrash size={11} />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="page-card page-card-wide">
          <h2>Search directly</h2>
          <p className="page-hint">Search the knowledge base without asking the chat assistant.</p>
          <div className="kb-upload-row">
            <input
              className="kb-search-input"
              placeholder="Search the knowledge base..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button className="kb-add-btn" onClick={handleSearch} disabled={searching}>
              <FaSearch size={11} /> {searching ? 'Searching...' : 'Search'}
            </button>
          </div>
          {results && (
            <div className="kb-search-results kb-search-results-lg">
              {results.length === 0 ? (
                <div className="kb-empty">No matches found.</div>
              ) : (
                results.map((r, i) => (
                  <div className="kb-search-result" key={i}>
                    <div className="kb-search-result-meta">
                      <span>{r.heading ? `${r.source} - ${r.heading}` : r.source}</span>
                      <span>{r.score.toFixed(2)}</span>
                    </div>
                    <div className="kb-search-result-text">{r.text}</div>
                  </div>
                ))
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default KnowledgeBasePage;
