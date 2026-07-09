import React, { useEffect, useState } from 'react';
import { FaChevronDown, FaChevronRight } from 'react-icons/fa';

interface SettingsPageProps {
  temperature: number;
  onTemperatureChange: (value: number) => void;
}

const TEMPERATURE_DESCRIPTIONS: Record<string, string> = {
  low: 'Focused and consistent - best for factual, policy-accurate answers.',
  mid: 'A balance of consistency and natural phrasing.',
  high: 'More varied phrasing, at some risk of drifting off-topic.',
};

function describeTemperature(value: number): string {
  if (value <= 0.3) return TEMPERATURE_DESCRIPTIONS.low;
  if (value <= 0.6) return TEMPERATURE_DESCRIPTIONS.mid;
  return TEMPERATURE_DESCRIPTIONS.high;
}

const SettingsPage: React.FC<SettingsPageProps> = ({ temperature, onTemperatureChange }) => {
  const [reducedMotion, setReducedMotion] = useState(false);
  const [ragOpen, setRagOpen] = useState(false);

  useEffect(() => {
    setReducedMotion(window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <section className="page-card page-card-wide">
        <h2>Chat behavior</h2>
        <div className="settings-row">
          <div className="settings-row-label">
            <span>Response creativity</span>
            <span className="settings-row-value">{temperature.toFixed(1)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={temperature}
            onChange={(e) => onTemperatureChange(parseFloat(e.target.value))}
            className="settings-slider"
          />
          <div className="settings-row-scale">
            <span>Focused</span>
            <span>Creative</span>
          </div>
          <p className="page-hint">{describeTemperature(temperature)}</p>
        </div>
      </section>

      <section className="page-card page-card-wide">
        <h2>About</h2>
        <p>
          The University Student Support Assistant is a self-hosted chat app that answers
          questions about course registration, exams, the library, ICT support, hostels,
          fees, the academic calendar, and student conduct.
        </p>
        <p>
          It runs entirely on your own machine: a local language model served by{' '}
          <strong>Ollama</strong> answers questions, and can search a <strong>RAG</strong>{' '}
          (retrieval-augmented generation) knowledge base as a tool whenever a question needs
          grounding in real university information - rather than every answer being forced
          through a search, the model decides for itself when to look something up.
        </p>
      </section>

      <section className="page-card page-card-wide">
        <h2>Architecture</h2>
        <p className="page-hint">
          How a message travels through the app: your browser talks to the backend, which asks
          the local model for an answer. If the question needs university-specific facts, the
          model calls a tool that searches the RAG knowledge base before replying. Click the RAG
          node below to see how that search actually works.
        </p>

        <svg
          viewBox="0 0 620 300"
          className="architecture-diagram"
          role="img"
          aria-label="Diagram of the request flow: Browser to Backend to Ollama, with a branch to the RAG knowledge base"
        >
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" className="diagram-arrowhead" />
            </marker>
          </defs>

          <path d="M160,140 L250,140" className="diagram-line" markerEnd="url(#arrow)" />
          <path d="M390,140 L460,140" className="diagram-line" markerEnd="url(#arrow)" />
          <path d="M530,170 L530,210" className="diagram-line diagram-line-dashed" markerEnd="url(#arrow)" />

          <circle r="5" className="diagram-dot">
            {!reducedMotion && (
              <animateMotion
                path="M90,140 L320,140 L530,140 L530,240 L530,140 L320,140 L90,140"
                dur="6s"
                repeatCount="indefinite"
              />
            )}
          </circle>

          <g className="diagram-node">
            <rect x="20" y="110" width="140" height="60" rx="12" />
            <text x="90" y="145" textAnchor="middle">Browser</text>
          </g>

          <g className="diagram-node">
            <rect x="250" y="110" width="140" height="60" rx="12" />
            <text x="320" y="131" textAnchor="middle">
              <tspan x="320" dy="0">FastAPI</tspan>
              <tspan x="320" dy="18">Backend</tspan>
            </text>
          </g>

          <g className="diagram-node diagram-node-accent">
            <rect x="460" y="110" width="140" height="60" rx="12" />
            <text x="530" y="131" textAnchor="middle">
              <tspan x="530" dy="0">Ollama</tspan>
              <tspan x="530" dy="18">(LLM)</tspan>
            </text>
          </g>

          <g
            className={`diagram-node diagram-node-accent diagram-node-interactive ${ragOpen ? 'is-open' : ''}`}
            onClick={() => setRagOpen((v) => !v)}
            role="button"
            tabIndex={0}
            aria-expanded={ragOpen}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') setRagOpen((v) => !v);
            }}
          >
            <title>Click to see how RAG retrieval works</title>
            <rect x="460" y="210" width="140" height="60" rx="12" />
            <text x="530" y="228" textAnchor="middle">
              <tspan x="530" dy="0">RAG</tspan>
              <tspan x="530" dy="18">Knowledge Base</tspan>
            </text>
          </g>
        </svg>

        <div className="diagram-legend">
          <span><span className="diagram-legend-dot" /> Request / answer flow</span>
          <span>Dashed = only when the model calls the search tool</span>
        </div>

        <button className="rag-detail-toggle" onClick={() => setRagOpen((v) => !v)}>
          {ragOpen ? <FaChevronDown size={11} /> : <FaChevronRight size={11} />}
          How RAG retrieval works
        </button>

        <div className={`rag-detail ${ragOpen ? 'open' : ''}`}>
          <div className="rag-detail-inner">
            <div className="rag-detail-row">
              <span className="rag-detail-label">Ingestion</span>
              <div className="rag-flow">
                <div className="rag-flow-step">
                  Upload
                  <small>.txt · .md · .pdf</small>
                </div>
                <div className="rag-flow-connector" style={{ animationDelay: '0s' }}>
                  <span className="rag-flow-dot" style={{ animationDelay: '0s' }} />
                </div>
                <div className="rag-flow-step">Chunk text</div>
                <div className="rag-flow-connector">
                  <span className="rag-flow-dot" style={{ animationDelay: '0.4s' }} />
                </div>
                <div className="rag-flow-step">
                  Embed
                  <small>nomic-embed-text</small>
                </div>
                <div className="rag-flow-connector">
                  <span className="rag-flow-dot" style={{ animationDelay: '0.8s' }} />
                </div>
                <div className="rag-flow-step accent">FAISS index</div>
              </div>
            </div>

            <div className="rag-detail-row">
              <span className="rag-detail-label">Retrieval</span>
              <div className="rag-flow">
                <div className="rag-flow-step">Search query</div>
                <div className="rag-flow-connector">
                  <span className="rag-flow-dot" style={{ animationDelay: '0s' }} />
                </div>
                <div className="rag-flow-step">Embed query</div>
                <div className="rag-flow-connector">
                  <span className="rag-flow-dot" style={{ animationDelay: '0.4s' }} />
                </div>
                <div className="rag-flow-step accent">FAISS search</div>
                <div className="rag-flow-connector">
                  <span className="rag-flow-dot" style={{ animationDelay: '0.8s' }} />
                </div>
                <div className="rag-flow-step">Best match → Ollama</div>
              </div>
            </div>

            <p className="rag-detail-note">
              FAISS stores every chunk as a vector and ranks them by cosine similarity to the
              query. Only the single best match above a relevance threshold is handed back to
              the model - keeping answers grounded in one specific, relevant passage instead of
              a pile of loosely related ones.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};

export default SettingsPage;
