import axios, { AxiosError } from 'axios';
import {
  ChatApiResponse,
  HealthResponse,
  RagDocument,
  RagSearchResult,
  RagStatus,
  ChatSession,
  StoredMessage,
  User,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const REQUEST_TIMEOUT = 180000;

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

function errorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError;
  const detail = (axiosError.response?.data as any)?.detail;
  if (typeof detail === 'string') return detail;
  if (detail) return JSON.stringify(detail);
  return fallback;
}

// ── Auth ─────────────────────────────────────────────────────────────────

export const signup = async (name: string, email: string, password: string): Promise<User> => {
  try {
    const response = await apiClient.post<User>('/auth/signup', { name, email, password });
    return response.data;
  } catch (error) {
    throw new Error(errorMessage(error, 'Failed to create an account.'));
  }
};

export const login = async (email: string, password: string): Promise<User> => {
  try {
    const response = await apiClient.post<User>('/auth/login', { email, password });
    return response.data;
  } catch (error) {
    throw new Error(errorMessage(error, 'Failed to log in.'));
  }
};

export const logout = async (): Promise<void> => {
  await apiClient.post('/auth/logout');
};

export const getMe = async (): Promise<User | null> => {
  try {
    const response = await apiClient.get<User>('/auth/me', { timeout: 5000 });
    return response.data;
  } catch (error) {
    return null;
  }
};

// ── Chat ─────────────────────────────────────────────────────────────────

export const getHealth = async (): Promise<HealthResponse | null> => {
  try {
    const response = await apiClient.get<HealthResponse>('/health', { timeout: 5000 });
    return response.data;
  } catch (error) {
    return null;
  }
};

export const sendChat = async (
  sessionId: string | null,
  message: string,
  temperature: number,
): Promise<ChatApiResponse> => {
  try {
    const response = await apiClient.post<ChatApiResponse>('/chat', {
      session_id: sessionId,
      message,
      temperature,
    });
    return response.data;
  } catch (error) {
    throw new Error(errorMessage(error, 'Failed to get a response from the assistant.'));
  }
};

export const listSessions = async (): Promise<ChatSession[]> => {
  const response = await apiClient.get<ChatSession[]>('/chat/sessions');
  return response.data;
};

export const getSession = async (
  sessionId: string,
): Promise<{ id: string; title: string; messages: StoredMessage[] }> => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}`);
  return response.data;
};

export const deleteSession = async (sessionId: string): Promise<boolean> => {
  try {
    await apiClient.delete(`/chat/sessions/${sessionId}`);
    return true;
  } catch (error) {
    return false;
  }
};

export const sendFeedback = async (
  question: string,
  answer: string,
  rating: string,
): Promise<boolean> => {
  try {
    const response = await apiClient.post(
      '/feedback',
      { question, answer, rating },
      { timeout: 10000 },
    );
    return response.status === 200;
  } catch (error) {
    return false;
  }
};

// ── RAG management ───────────────────────────────────────────────────────

export const listDocuments = async (): Promise<RagDocument[]> => {
  const response = await apiClient.get<RagDocument[]>('/rag/documents');
  return response.data;
};

export const uploadTextDocument = async (source: string, text: string): Promise<RagDocument> => {
  try {
    const response = await apiClient.post<RagDocument>('/rag/documents/text', { source, text });
    return response.data;
  } catch (error) {
    throw new Error(errorMessage(error, 'Failed to ingest text.'));
  }
};

export const uploadFileDocument = async (file: File): Promise<RagDocument> => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<RagDocument>('/rag/documents/file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  } catch (error) {
    throw new Error(errorMessage(error, 'Failed to ingest file.'));
  }
};

export const deleteDocument = async (source: string): Promise<boolean> => {
  try {
    await apiClient.delete(`/rag/documents/${encodeURIComponent(source)}`);
    return true;
  } catch (error) {
    return false;
  }
};

export const searchKnowledgeBase = async (
  query: string,
  k = 5,
): Promise<RagSearchResult[]> => {
  const response = await apiClient.post<RagSearchResult[]>('/rag/search', { query, k });
  return response.data;
};

export const getRagStatus = async (): Promise<RagStatus | null> => {
  try {
    const response = await apiClient.get<RagStatus>('/rag/status', { timeout: 5000 });
    return response.data;
  } catch (error) {
    return null;
  }
};
