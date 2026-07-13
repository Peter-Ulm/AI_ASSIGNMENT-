import { useEffect, useState } from 'react';
import './App.css';

import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Sidebar from './components/Sidebar';
import ChatPane from './components/ChatPane';
import KnowledgeBasePage from './components/KnowledgeBasePage';
import SettingsPage from './components/SettingsPage';
import SourcesPanel from './components/SourcesPanel';
import LoginPage from './components/LoginPage';
import SignupPage from './components/SignupPage';
import { deleteSession, getSession, listSessions, sendChat } from './services/api';
import { AppView, AuthView, ChatMessage, ChatSession, StoredMessage } from './types';

const TEMPERATURE_KEY = 'chat_temperature_v1';
// Lower than a typical default (0.7) so the assistant stays focused and
// consistent rather than rambling - this is a factual support bot, not a
// creative-writing one. Adjustable on the Settings page.
const DEFAULT_TEMPERATURE = 0.3;

function mapStoredMessage(m: StoredMessage): ChatMessage {
  return {
    role: m.role,
    content: m.content,
    usedKb: m.used_kb,
    sources: m.sources,
    model: m.model ?? undefined,
    tokensUsed: m.tokens_used ?? undefined,
    generationTime: m.generation_time ?? undefined,
    isError: m.is_error,
  };
}

function AuthGate() {
  const [authView, setAuthView] = useState<AuthView>('login');
  return authView === 'login' ? (
    <LoginPage onSwitchToSignup={() => setAuthView('signup')} />
  ) : (
    <SignupPage onSwitchToLogin={() => setAuthView('login')} />
  );
}

function ChatApp() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeMessages, setActiveMessages] = useState<ChatMessage[]>([]);
  const [view, setView] = useState<AppView>('chat');
  const [loading, setLoading] = useState(false);
  const [detailsMessage, setDetailsMessage] = useState<ChatMessage | null>(null);
  const [temperature, setTemperature] = useState(DEFAULT_TEMPERATURE);

  const refreshSessions = async () => {
    try {
      setSessions(await listSessions());
    } catch {
      // Not fatal - the sidebar just shows an empty list until this succeeds.
    }
  };

  useEffect(() => {
    const savedTemperature = localStorage.getItem(TEMPERATURE_KEY);
    if (savedTemperature) {
      const parsed = parseFloat(savedTemperature);
      if (!Number.isNaN(parsed)) setTemperature(parsed);
    }
    refreshSessions();
  }, []);

  useEffect(() => {
    localStorage.setItem(TEMPERATURE_KEY, String(temperature));
  }, [temperature]);

  const handleSend = async (content: string) => {
    setActiveMessages((prev) => [...prev, { role: 'user', content }]);
    setLoading(true);
    try {
      const result = await sendChat(activeId, content, temperature);
      setActiveMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: result.answer,
          usedKb: result.used_kb,
          sources: result.sources,
          model: result.model,
          tokensUsed: result.tokens_used,
          generationTime: result.generation_time,
        },
      ]);
      setActiveId(result.session_id);
      refreshSessions();
    } catch (error) {
      setActiveMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: error instanceof Error ? error.message : 'Something went wrong.',
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = () => {
    setActiveId(null);
    setActiveMessages([]);
    setView('chat');
  };

  const handleSelectSession = async (id: string) => {
    setActiveId(id);
    setView('chat');
    try {
      const session = await getSession(id);
      setActiveMessages(session.messages.map(mapStoredMessage));
    } catch {
      setActiveMessages([]);
    }
  };

  const handleDeleteSession = async (id: string) => {
    const ok = await deleteSession(id);
    if (ok) {
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (id === activeId) {
        setActiveId(null);
        setActiveMessages([]);
      }
    }
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

function AppContent() {
  const { user, loading } = useAuth();

  if (loading) return null;
  return user ? <ChatApp /> : <AuthGate />;
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
