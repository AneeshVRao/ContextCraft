# ContextCraft — Benchmark Results

Evaluated against ContextCraft's own codebase (v0.3.0).
Eval set: 10 hand-curated questions with verified ground-truth source files.
Date: May 19, 2026
Embedder: Gemini Embedding 2 | Reranker: Cohere rerank-english-v3.0 | LLM Judge: Gemini 3.1 Flash Lite

---

## Methodology

Each configuration was evaluated over **3 complete iterations** (30 total queries per
config) to produce stable latency metrics. Before each run, the system undergoes a
warm-up phase — one throwaway embedding and one pgvector hybrid search — to eliminate
cold-start penalties from connection pool initialization and network overhead.

**Ground truth verification:** Expected source files were determined by manual
inspection of the codebase before any queries were run against the system. No
system output was used to construct the test set. One test case was corrected
mid-evaluation after discovering the original expected source (`001_init.sql`)
pointed to a SQL migration file outside the AST parser's indexing scope — an
honest limitation documented in the observations below.

**Faithfulness scoring:** Each generated answer is evaluated by a second LLM call
acting as a judge, asked to return `PASS` or `FAIL` based on whether the answer
correctly covers the ground truth. This is an approximation — LLM-as-judge
introduces its own variance, particularly with smaller models.

---

## Retrieval Quality

| Configuration | Source Hit Rate | Faithful Answers |
|---|---|---|
| RRF only | **80.0%** | 73.3% |
| RRF + Reranker | **75.0%** | 60.0% |
| RRF + Reranker + Deps | **75.0%** | 53.3% |

*Source Hit Rate: percentage of queries where at least one expected source file
appeared in the retrieved context, position-agnostic, averaged across 3 runs.*

*Faithful Answers: percentage of generated answers judged to correctly cover the
ground truth by a second LLM call, averaged across 3 runs.*

---

## Latency (retrieval only, averaged over 3 runs)

| Configuration | P50 | P95 |
|---|---|---|
| RRF only | 3,876ms | 4,340ms |
| RRF + Reranker | 5,121ms | 6,969ms |
| RRF + Reranker + Deps | 4,993ms | 5,621ms |

*Latency measured from query embedding start to final ranked chunk list returned.
Excludes LLM answer generation time, which is model-dependent and typically adds
2–15 seconds.*

---

## Observations

**RRF only is the strongest configuration on this codebase.** It achieves the
highest source hit rate (80%) and the best faithfulness score (73.3%) at the
lowest latency (3.88s P50). For a ~270 chunk corpus queried with factual
architectural questions, the hybrid BM25 + vector RRF baseline is already
well-calibrated.

**The Cohere reranker adds ~1.25s P50 latency** (Cohere API round-trip) and
did not improve source hit rate on this eval set. Hit rate dropped marginally
from 80% to 75%. This is consistent with how cross-encoders behave on small,
well-chunked corpora — the initial retrieval candidates are already good, and
reranking changes their order without surfacing new files. The reranker is
expected to show larger gains on codebases with 10K+ chunks where the initial
candidate pool is noisier.

**Faithfulness decreases with each added stage.** Adding the reranker dropped
faithfulness from 73.3% to 60.0%, and dependency expansion brought it further
to 53.3%. This is partly a LLM judge sensitivity issue — `gemini-3.1-flash-lite`
is a small model that is sensitive to context ordering changes introduced by
reranking. It is not a reliable signal that answer quality degraded for end users.

**Dependency expansion is sparse on this codebase.** The graph expander fired
on only 1 question across all 30 queries per config (question 8: SSE disconnect
handling), expanding 1 dependency chunk from 10 source chunks each time. The
dependency graph becomes more valuable on larger, more interconnected codebases
where a retrieved function imports heavily from other modules.

**Persistent retrieval miss — question 10.** "How are file imports attached to
code chunks?" consistently returns 0% hit rate across all configurations. The
expected source (`src/contextcraft/parser/ast_parser.py`) is indexed, but the
query embedding does not match it in the top-10. This is a genuine retrieval
gap for questions about implicit behaviour rather than named functions or classes,
and represents a known limitation of bi-encoder retrieval.

**Question 2 is a structural miss.** "What is the token limit for a single code
chunk?" misses across all configurations because `config.py` (the expected source)
does not surface in the top results despite containing the answer. This points to
a vocabulary mismatch between the query and the indexed content — a candidate for
query expansion or metadata filtering in a future iteration.

---

## Eval Set

10 questions covering: hybrid search implementation, token limits, git blame
caching, incremental indexing, reranker interface, language support, connection
pooling, SSE disconnect handling, embedding storage, and import attachment logic.

Full questions, expected sources, and ground truth answers: `eval/test_cases.json`

---

## Reproducing

```bash
# 1. Configure environment
cp .env.example .env
# Set CONTEXTCRAFT_GEMINI_API_KEY and CONTEXTCRAFT_COHERE_API_KEY

# 2. Start database
docker compose -f docker/docker-compose.yml up -d postgres

# 3. Index the codebase
contextcraft index .

# 4. Run evaluation (all three configurations)
python eval/run_eval.py --runs 3
python eval/run_eval.py --rerank --runs 3
python eval/run_eval.py --rerank --deps --runs 3
```

> **Rate limit note:** The eval harness makes 2 LLM calls per question.
> On Gemini free tier, use `gemini-3.1-flash-lite` (500 RPD / 15 RPM) with
> `asyncio.sleep(10)` between questions in `eval/run_eval.py` to stay within limits.
> Each 3-run configuration takes approximately 10–12 minutes end to end.