"use client";

import { useEffect, useState } from "react";
import { codeToHtml } from "shiki";
import { SourceChunk } from "@/lib/types";
import styles from "./SourceCitations.module.css";
import { FileCode, GitCommit, Target } from "lucide-react";

interface SourceCitationsProps {
  sources: SourceChunk[];
}

export function SourceCitations({ sources }: SourceCitationsProps) {
  const [highlightedSources, setHighlightedSources] = useState<Record<number, string>>({});

  useEffect(() => {
    async function highlight() {
      const newHighlighted: Record<number, string> = {};
      
      for (const source of sources) {
        // Guess language from file extension
        let lang = "plaintext";
        if (source.file_path.endsWith(".py")) lang = "python";
        if (source.file_path.endsWith(".js") || source.file_path.endsWith(".jsx")) lang = "javascript";
        if (source.file_path.endsWith(".ts") || source.file_path.endsWith(".tsx")) lang = "typescript";
        if (source.file_path.endsWith(".go")) lang = "go";
        
        try {
          const html = await codeToHtml(source.content, {
            lang,
            theme: "github-dark-dimmed",
          });
          newHighlighted[source.id] = html;
        } catch (e) {
          // Fallback if shiki fails
          newHighlighted[source.id] = `<pre><code>${source.content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>`;
        }
      }
      setHighlightedSources(newHighlighted);
    }
    
    if (sources.length > 0) {
      highlight();
    }
  }, [sources]);

  if (sources.length === 0) return null;

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Sources</h3>
      {sources.map((source, index) => (
        <div key={`${source.id}-${index}`} className={`${styles.sourceCard} glass-panel`}>
          <div className={styles.header}>
            <div className={styles.filePath}>
              <FileCode size={14} style={{ display: "inline", marginRight: "6px", verticalAlign: "text-bottom" }} />
              {source.file_path}:{source.start_line}-{source.end_line}
            </div>
            <div className={styles.metadata}>
              {source.similarity_score !== undefined && (
                <span title="Relevance Score">
                  <Target size={12} style={{ display: "inline", marginRight: "4px" }} />
                  {source.similarity_score.toFixed(3)}
                </span>
              )}
              {source.git_blame && Object.keys(source.git_blame).length > 0 && (
                <span title="Git Blame">
                  <GitCommit size={12} style={{ display: "inline", marginRight: "4px" }} />
                  {Object.values(source.git_blame)[0]?.substring(0, 7)}
                </span>
              )}
            </div>
          </div>
          <div 
            className={styles.codeContainer}
            dangerouslySetInnerHTML={{ 
              __html: highlightedSources[source.id] || "Loading syntax highlight..." 
            }} 
          />
        </div>
      ))}
    </div>
  );
}
