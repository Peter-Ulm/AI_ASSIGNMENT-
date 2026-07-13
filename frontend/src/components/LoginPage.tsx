import React, { useState } from 'react';
import { FaGraduationCap } from 'react-icons/fa';
import { useAuth } from '../context/AuthContext';

interface LoginPageProps {
  onSwitchToSignup: () => void;
}

const LoginPage: React.FC<LoginPageProps> = ({ onSwitchToSignup }) => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to log in.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={handleSubmit}>
        <div className="auth-brand">
          <FaGraduationCap size={22} />
          <span>Student Support</span>
        </div>
        <h1>Welcome back</h1>
        <p className="auth-subtitle">Log in to continue to your conversations.</p>

        {error && <div className="auth-error">{error}</div>}

        <label className="auth-label" htmlFor="login-email">Email</label>
        <input
          id="login-email"
          className="auth-input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />

        <label className="auth-label" htmlFor="login-password">Password</label>
        <input
          id="login-password"
          className="auth-input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <button className="auth-submit" type="submit" disabled={loading}>
          {loading ? 'Logging in...' : 'Log in'}
        </button>

        <p className="auth-switch">
          Don't have an account?{' '}
          <button type="button" onClick={onSwitchToSignup}>Sign up</button>
        </p>
      </form>
    </div>
  );
};

export default LoginPage;
