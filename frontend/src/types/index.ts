export interface HealthResponse {
  status: string;
  model: string;
  ollama_reachable: boolean;
  model_installed: boolean;
}

export type ChatRole = 'user' | 'assistant';

export interface RagSearchResult {
  text: string;
  source: string;
  heading: string;
  score: number;
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  // Present on assistant messages only.
  usedKb?: boolean;
  sources?: RagSearchResult[];
  model?: string;
  tokensUsed?: number;
  generationTime?: number;
  isError?: boolean;
}

export interface ChatApiResponse {
  session_id: string;
  title: string;
  answer: string;
  tokens_used: number;
  generation_time: number;
  timestamp: string;
  model: string;
  used_kb: boolean;
  sources: RagSearchResult[];
}

export interface StoredMessage {
  role: ChatRole;
  content: string;
  used_kb: boolean;
  sources: RagSearchResult[];
  model: string | null;
  tokens_used: number | null;
  generation_time: number | null;
  is_error: boolean;
}

export interface RagDocument {
  source: string;
  chunks: number;
}

export interface RagStatus {
  chunk_count: number;
  source_count: number;
  embedding_model: string;
}

export interface ApiError {
  detail: string;
}

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: string;
}

export type AppView = 'chat' | 'knowledge-base' | 'settings';

export interface User {
  id: string;
  name: string;
  email: string;
}

export type AuthView = 'login' | 'signup';
