export interface Repo {
  id: number;
  name: string;
  local_path: string;
  chunk_count: number;
  last_indexed: string;
}

export interface SourceChunk {
  id: number;
  file_path: string;
  start_line: number;
  end_line: number;
  content: string;
  chunk_type: string;
  name: string;
  git_blame?: Record<string, string>;
  similarity_score?: number;
}

export interface AskResponseEvent {
  type: "token" | "sources" | "error" | "done";
  content?: string;
  sources?: SourceChunk[];
  error?: string;
}
