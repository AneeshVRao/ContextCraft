"""Evaluation harness for ContextCraft retrieval and generation.

Runs test queries against the currently indexed codebase and measures:
- Source hit rate (did the right file get retrieved?)
- Faithfulness (does the LLM answer match the ground truth context?)
- Latency (p50, p95 per query)
"""

import asyncio
import json
import logging
import statistics
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from contextcraft.config import settings
from contextcraft.db.connection import get_pool, close_pool, run_migrations
from contextcraft.db import chunks_repo
from contextcraft.embeddings.openai import OpenAIEmbedder
from contextcraft.search.hybrid import hybrid_search

# We use the configured LLM for "LLM-as-a-judge" evaluation of faithfulness
from contextcraft.llm.openai import OpenAILLM

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
console = Console()

TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"


async def llm_judge_faithfulness(question: str, ground_truth: str, generated_answer: str) -> bool:
    """Use an LLM to evaluate if the generated answer covers the ground truth."""
    llm = OpenAILLM()
    system_prompt = (
        "You are an evaluator for a RAG system. "
        "Your task is to determine if the GENERATED ANSWER successfully provides "
        "the information contained in the GROUND TRUTH for the given QUESTION. "
        "Respond ONLY with 'PASS' if it contains the information, or 'FAIL' if it misses it or hallucinates."
    )
    user_prompt = f"QUESTION: {question}\n\nGROUND TRUTH: {ground_truth}\n\nGENERATED ANSWER: {generated_answer}"
    
    response = await llm.generate(system_prompt, user_prompt)
    return "PASS" in response.upper()


async def run_evaluation(use_reranker: bool = False):
    """Run the evaluation suite."""
    test_cases = json.loads(TEST_CASES_PATH.read_text())
    
    await run_migrations()
    repos = await chunks_repo.list_repositories()
    if not repos:
        console.print("[red]No repos indexed. Please index the codebase first.[/red]")
        await close_pool()
        return

    repo_id = repos[0].id
    embedder = OpenAIEmbedder()
    llm = OpenAILLM()

    results = []
    latencies = []
    
    console.print(f"\n[bold]Running Evaluation ({'with' if use_reranker else 'without'} reranker)[/bold]\n")

    for idx, tc in enumerate(test_cases, 1):
        question = tc["question"]
        expected_sources = tc["expected_sources"]
        ground_truth = tc["ground_truth"]
        
        console.print(f"[{idx}/{len(test_cases)}] {question}")
        
        # 1. Retrieval
        start_time = time.time()
        
        query_embedding = await embedder.embed_single(question)
        
        fetch_k = 20 if use_reranker else settings.search_top_k
        chunks = await hybrid_search(
            query_embedding=query_embedding,
            query_text=question,
            repo_id=repo_id,
            top_k=fetch_k,
        )
        
        if use_reranker:
            from contextcraft.reranker.cohere import CohereReranker
            reranker = CohereReranker()
            chunks = await reranker.rerank(question, chunks, settings.search_top_k)
            
        retrieval_time = time.time() - start_time
        latencies.append(retrieval_time)
        
        # Check source hit rate
        retrieved_files = {c.chunk.file_path for c in chunks}
        source_hits = [src for src in expected_sources if src in retrieved_files]
        hit_rate = len(source_hits) / len(expected_sources) if expected_sources else 0
        
        # 2. Generation (using ContextCraft standard prompt)
        context_text = "\n".join([f"File: {c.chunk.file_path}\n{c.chunk.content}" for c in chunks])
        system = "Answer the question based ONLY on the provided context."
        user = f"Context:\n{context_text}\n\nQuestion: {question}"
        
        answer = await llm.generate(system, user)
        
        # 3. Judge Faithfulness
        is_faithful = await llm_judge_faithfulness(question, ground_truth, answer)
        
        results.append({
            "question": question,
            "hit_rate": hit_rate,
            "is_faithful": is_faithful,
            "latency": retrieval_time
        })
        
        color = "green" if is_faithful and hit_rate > 0 else "red"
        console.print(f"  [{color}]Hit Rate: {hit_rate:.1f} | Faithful: {is_faithful} | {retrieval_time:.2f}s[/{color}]")

    # Aggregate
    avg_hit_rate = statistics.mean([r["hit_rate"] for r in results])
    pct_faithful = sum([1 for r in results if r["is_faithful"]]) / len(results) * 100
    p50 = statistics.median(latencies)
    
    # Print summary
    table = Table(title=f"Evaluation Summary ({'Reranker ON' if use_reranker else 'Reranker OFF'})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Avg Source Hit Rate", f"{avg_hit_rate * 100:.1f}%")
    table.add_row("Faithful Answers", f"{pct_faithful:.1f}%")
    table.add_row("Retrieval p50 Latency", f"{p50:.3f}s")
    
    console.print()
    console.print(table)
    
    await close_pool()

if __name__ == "__main__":
    import sys
    use_rerank = "--rerank" in sys.argv
    asyncio.run(run_evaluation(use_reranker=use_rerank))
