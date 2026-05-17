"use client";

import { useState, useEffect, useRef } from "react";
import { Repo, SourceChunk } from "@/lib/types";
import { SourceCitations } from "@/components/SourceCitations";
import styles from "./page.module.css";
import { Send, Bot, Database, Server, Terminal, Layers } from "lucide-react";

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepoIds, setSelectedRepoIds] = useState<string[]>([]);
  const [allRepos, setAllRepos] = useState(false);
  const [expandDeps, setExpandDeps] = useState(false);
  
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
            setSelectedRepoIds([data[0].id]);
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
    if (!question.trim() || (selectedRepoIds.length === 0 && !allRepos)) return;

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
          repo_ids: selectedRepoIds,
          all_repos: allRepos,
          top_k: 10,
          expand_deps: expandDeps,
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

  const selectedRepos = repos.filter(r => selectedRepoIds.includes(r.id));
  const activeCount = allRepos ? repos.length : selectedRepoIds.length;

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div className={styles.logo}>
          <Layers className="text-accent-primary" />
          ContextCraft
        </div>
        
        <div className={styles.repoSelector}>
          <label className={styles.statusItem} style={{ marginRight: '8px', cursor: 'pointer' }}>
            <input 
              type="checkbox" 
              checked={expandDeps} 
              onChange={(e) => setExpandDeps(e.target.checked)} 
              style={{ marginRight: '4px' }}
            />
            Expand Graph Context
          </label>
          <Database size={16} className="text-text-tertiary" />
          <details className={styles.multiSelectDropdown}>
            <summary className={styles.select} style={{ cursor: 'pointer' }}>
              {activeCount === 0 ? "Select Repositories..." : 
               allRepos ? "All Repositories" :
               activeCount === 1 ? selectedRepos[0]?.name : `${activeCount} Repositories`}
            </summary>
            <div className={styles.dropdownMenu}>
              <label className={styles.dropdownItem}>
                <input 
                  type="checkbox" 
                  checked={allRepos} 
                  onChange={(e) => setAllRepos(e.target.checked)} 
                />
                <strong>All Repositories</strong>
              </label>
              <hr className={styles.dropdownDivider} />
              {repos.length === 0 ? (
                <div className={styles.dropdownItem}>No repositories indexed</div>
              ) : (
                repos.map(r => (
                  <label key={r.id} className={styles.dropdownItem}>
                    <input 
                      type="checkbox" 
                      checked={allRepos || selectedRepoIds.includes(r.id)} 
                      disabled={allRepos}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedRepoIds([...selectedRepoIds, r.id]);
                        else setSelectedRepoIds(selectedRepoIds.filter(id => id !== r.id));
                      }} 
                    />
                    {r.name} ({r.chunk_count} chunks)
                  </label>
                ))
              )}
            </div>
          </details>
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
          disabled={isAsking || activeCount === 0}
        />
        <button 
          type="submit" 
          className={styles.sendButton}
          disabled={!question.trim() || isAsking || activeCount === 0}
        >
          <Send size={16} />
        </button>
      </form>

      <footer className={styles.statusBar}>
        <div className={styles.statusItem}>
          <Server size={12} />
          {activeCount > 0 ? `Connected to ${activeCount} repo(s)` : "Not connected"}
        </div>
        <div className={styles.statusItem}>
          <Database size={12} />
          {allRepos 
            ? `${repos.reduce((acc, r) => acc + r.chunk_count, 0)} chunks total` 
            : `${selectedRepos.reduce((acc, r) => acc + r.chunk_count, 0)} chunks selected`}
        </div>
        <div className={styles.statusItem}>
          ContextCraft v0.1.0 UI
        </div>
      </footer>
    </main>
  );
}
