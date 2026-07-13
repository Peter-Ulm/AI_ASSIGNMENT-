import React, { useEffect, useState } from 'react';
import {
  FaPlus,
  FaSun,
  FaMoon,
  FaGraduationCap,
  FaBook,
  FaCog,
  FaTrash,
  FaComment,
  FaSignOutAlt,
} from 'react-icons/fa';
import { getHealth } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { AppView, ChatSession, HealthResponse } from '../types';

interface SidebarProps {
  sessions: ChatSession[];
  activeId: string | null;
  view: AppView;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNavigate: (view: AppView) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeId,
  view,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onNavigate,
}) => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);

  const statusClass = !health ? 'offline' : health.status === 'ok' ? 'ok' : 'degraded';
  const statusLabel = !health ? 'Backend offline' : health.status === 'ok' ? 'Online' : 'Model not ready';

  const sortedSessions = [...sessions].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

  return (
    <aside className="sidebar">
      <div className="brand">
        <FaGraduationCap size={20} />
        <span>Student Support</span>
      </div>

      <button className="new-chat-btn" onClick={onNewChat}>
        <FaPlus size={12} /> New chat
      </button>

      <div className="sidebar-section">
        <div className="sidebar-label">Chats</div>
        <div className="chat-history-list">
          {sortedSessions.length === 0 ? (
            <div className="kb-empty">No conversations yet.</div>
          ) : (
            sortedSessions.map((session) => (
              <div
                key={session.id}
                className={`chat-history-item ${view === 'chat' && session.id === activeId ? 'active' : ''}`}
                onClick={() => onSelectSession(session.id)}
              >
                <FaComment size={11} className="chat-history-icon" />
                <span className="chat-history-title" title={session.title}>
                  {session.title}
                </span>
                <button
                  className="chat-history-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  aria-label="Delete chat"
                >
                  <FaTrash size={10} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="sidebar-section">
        <button
          className={`nav-item ${view === 'knowledge-base' ? 'active' : ''}`}
          onClick={() => onNavigate('knowledge-base')}
        >
          <FaBook size={13} /> Knowledge base
        </button>
        <button
          className={`nav-item ${view === 'settings' ? 'active' : ''}`}
          onClick={() => onNavigate('settings')}
        >
          <FaCog size={13} /> Settings
        </button>
      </div>

      <div className="sidebar-footer">
        <div className="status-row">
          <span className={`status-dot ${statusClass}`} />
          <span>{statusLabel}{health && ` · ${health.model}`}</span>
        </div>
        {user && (
          <div className="user-row">
            <span className="user-name" title={user.email}>{user.name}</span>
            <button className="logout-btn" onClick={logout} aria-label="Log out">
              <FaSignOutAlt size={12} />
            </button>
          </div>
        )}
        <button className="theme-toggle-btn" onClick={toggleTheme}>
          {theme === 'dark' ? <FaSun size={13} /> : <FaMoon size={13} />}
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
