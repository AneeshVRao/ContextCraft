"use client";

import { useState, useEffect, useRef } from "react";
import { Repo, SourceChunk } from "@/lib/types";
import { SourceCitations } from "@/components/SourceCitations";
import styles from "./page.module.css";
import { Send, Bot, Database, Server, Terminal, Layers } from "lucide-react";

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  
  // Chat state
  const [currentQuery, setCurrentQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [error, setError] = useState("");
  
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Fetch repos on load
  useEffect(() => {
    async function fetchRepos() {
      try {
        const res = await fetch("/api/repos");
        if (res.ok) {
          const data = await res.json();
          setRepos(data);
          if (data.length > 0) {
            setSelectedRepoId(data[0].id);
          }
        }
      } catch (e) {
        console.error("Failed to fetch repos", e);
      }
    }
    fetchRepos();
  }, []);

  // Auto scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [answer, sources]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !selectedRepoId) return;

    setCurrentQuery(question);
    setQuestion("");
    setAnswer("");
    setSources([]);
    setError("");
    setIsAsking(true);

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          repo_id: selectedRepoId,
          top_k: 10,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error("Failed to get answer");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      
      let done = false;
      let currentAnswer = "";

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        
        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");
          
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                
                if (data.type === "token" && data.content) {
                  currentAnswer += data.content;
                  setAnswer(currentAnswer);
                } else if (data.type === "sources" && data.sources) {
                  setSources(data.sources);
                } else if (data.type === "error" && data.error) {
                  setError(data.error);
                }
              } catch (e) {
                console.error("Error parsing SSE JSON", e);
              }
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setIsAsking(false);
    }
  };

  const selectedRepo = repos.find(r => r.id === selectedRepoId);

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div className={styles.logo}>
          <Layers className="text-accent-primary" />
          ContextCraft
        </div>
        
        <div className={styles.repoSelector}>
          <Database size={16} className="text-text-tertiary" />
          <select 
            className={styles.select}
            value={selectedRepoId || ""}
            onChange={(e) => setSelectedRepoId(Number(e.target.value))}
            disabled={repos.length === 0}
          >
            {repos.length === 0 ? (
              <option value="">No repositories indexed</option>
            ) : (
              repos.map(r => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.chunk_count} chunks)
                </option>
              ))
            )}
          </select>
        </div>
      </header>

      <div className={styles.chatContainer}>
        {!currentQuery ? (
          <div className={styles.emptyState}>
            <Bot size={48} color="var(--text-tertiary)" />
            <h2>What would you like to know about your code?</h2>
            <p>Ask a question, and I'll search your indexed repositories to find the answer.</p>
          </div>
        ) : (
          <>
            {/* User Query */}
            <div className={styles.message}>
              <div className={styles.content}>
                <div className={styles.userMessage}>
                  {currentQuery}
                </div>
              </div>
            </div>

            {/* Assistant Response */}
            <div className={`${styles.message} ${styles.assistantMessage}`}>
              <div className={styles.avatar}>
                <Bot size={20} />
              </div>
              <div className={styles.content}>
                {error ? (
                  <div className="text-error" style={{ color: "var(--error)" }}>
                    Error: {error}
                  </div>
                ) : (
                  <>
                    <div className={styles.answerText}>{answer}</div>
                    
                    {isAsking && !answer && (
                      <div className={styles.loadingIndicator}>
                        <Terminal size={14} /> Searching repository and thinking...
                      </div>
                    )}
                    
                    {sources.length > 0 && <SourceCitations sources={sources} />}
                  </>
                )}
              </div>
            </div>
          </>
        )}
        <div ref={chatEndRef} />
      </div>

      <form className={styles.inputForm} onSubmit={handleAsk}>
        <input
          type="text"
          className={styles.input}
          placeholder="Ask a question about the codebase..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={isAsking || repos.length === 0}
        />
        <button 
          type="submit" 
          className={styles.sendButton}
          disabled={!question.trim() || isAsking || repos.length === 0}
        >
          <Send size={16} />
        </button>
      </form>

      <footer className={styles.statusBar}>
        <div className={styles.statusItem}>
          <Server size={12} />
          {selectedRepo ? `Connected to ${selectedRepo.name}` : "Not connected"}
        </div>
        <div className={styles.statusItem}>
          <Database size={12} />
          {selectedRepo ? `${selectedRepo.chunk_count} chunks indexed` : "0 chunks"}
        </div>
        <div className={styles.statusItem}>
          ContextCraft v0.1.0 UI
        </div>
      </footer>
    </main>
  );
}
