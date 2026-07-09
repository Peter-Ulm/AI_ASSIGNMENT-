import { useEffect, useState } from 'react';
import './App.css';

import { ThemeProvider } from './context/ThemeContext';
import Sidebar from './components/Sidebar';
import ChatPane from './components/ChatPane';
import KnowledgeBasePage from './components/KnowledgeBasePage';
import SettingsPage from './components/SettingsPage';
import SourcesPanel from './components/SourcesPanel';
import { sendChat } from './services/api';
import { AppView, ChatMessage, ChatSession } from './types';

const SESSIONS_KEY = 'chat_sessions_v1';
const TEMPERATURE_KEY = 'chat_temperature_v1';
// Lower than a typical default (0.7) so the assistant stays focused and
// consistent rather than rambling - this is a factual support bot, not a
// creative-writing one. Adjustable on the Settings page.
const DEFAULT_TEMPERATURE = 0.3;

function makeTitle(content: string): string {
  const flat = content.trim().replace(/\s+/g, ' ');
  return flat.length > 40 ? `${flat.slice(0, 40)}…` : flat;
}

function AppContent() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [view, setView] = useState<AppView>('chat');
  const [loading, setLoading] = useState(false);
  const [detailsMessage, setDetailsMessage] = useState<ChatMessage | null>(null);
  const [temperature, setTemperature] = useState(DEFAULT_TEMPERATURE);

  useEffect(() => {
    const saved = localStorage.getItem(SESSIONS_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setSessions(parsed.sessions ?? []);
        setActiveId(parsed.activeId ?? null);
      } catch (e) {
        console.error('Failed to load chat sessions:', e);
      }
    }

    const savedTemperature = localStorage.getItem(TEMPERATURE_KEY);
    if (savedTemperature) {
      const parsed = parseFloat(savedTemperature);
      if (!Number.isNaN(parsed)) setTemperature(parsed);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify({ sessions, activeId }));
  }, [sessions, activeId]);

  useEffect(() => {
    localStorage.setItem(TEMPERATURE_KEY, String(temperature));
  }, [temperature]);

  const activeMessages = sessions.find((s) => s.id === activeId)?.messages ?? [];

  const handleSend = async (content: string) => {
    const userMessage: ChatMessage = { role: 'user', content };

    let sessionId = activeId;
    let historyForRequest: ChatMessage[];

    if (sessionId === null) {
      sessionId = crypto.randomUUID();
      historyForRequest = [userMessage];
      const newSession: ChatSession = {
        id: sessionId,
        title: makeTitle(content),
        messages: historyForRequest,
        updatedAt: Date.now(),
      };
      setSessions((prev) => [...prev, newSession]);
      setActiveId(sessionId);
    } else {
      historyForRequest = [...activeMessages, userMessage];
      const id = sessionId;
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, messages: historyForRequest, updatedAt: Date.now() } : s)),
      );
    }

    setLoading(true);
    const id = sessionId;
    try {
      const result = await sendChat(historyForRequest, temperature);
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: result.answer,
        usedKb: result.used_kb,
        sources: result.sources,
        model: result.model,
        tokensUsed: result.tokens_used,
        generationTime: result.generation_time,
      };
      setSessions((prev) =>
        prev.map((s) =>
          s.id === id ? { ...s, messages: [...s.messages, assistantMessage], updatedAt: Date.now() } : s,
        ),
      );
    } catch (error) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: error instanceof Error ? error.message : 'Something went wrong.',
        isError: true,
      };
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, messages: [...s.messages, errorMessage] } : s)),
      );
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = () => {
    setActiveId(null);
    setView('chat');
  };

  const handleSelectSession = (id: string) => {
    setActiveId(id);
    setView('chat');
  };

  const handleDeleteSession = (id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (id === activeId) setActiveId(null);
  };

  return (
    <div className="app-shell">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        view={view}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNavigate={setView}
      />

      {view === 'chat' && (
        <ChatPane
          messages={activeMessages}
          loading={loading}
          onSend={handleSend}
          onShowDetails={setDetailsMessage}
        />
      )}
      {view === 'knowledge-base' && <KnowledgeBasePage />}
      {view === 'settings' && (
        <SettingsPage temperature={temperature} onTemperatureChange={setTemperature} />
      )}

      <SourcesPanel message={detailsMessage} onClose={() => setDetailsMessage(null)} />
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}

export default App;
