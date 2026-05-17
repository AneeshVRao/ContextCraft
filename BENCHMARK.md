# ContextCraft Benchmark Results

Evaluated against ContextCraft's own codebase (v0.3.0).  
Eval set: 25 hand-curated questions with verified ground-truth source files.  
Hardware: [your machine specs]  
Date: [date]

## Methodology
The evaluation harness runs 3 complete iterations for each configuration to stabilize latency metrics. Before measurement, the system undergoes a warm-up phase (1 throwaway embedding, 1 pgvector hybrid search, and 1 LLM generation call) to eliminate cold-start penalties from the connection pool, network initialization, and VRAM loading.

**Ground Truth Verification:** 
The expected sources were strictly derived by manual inspection of the codebase prior to system evaluation to ensure no artificial inflation of source hit rates.

## Retrieval Quality

| Configuration | Source Hit Rate | Notes |
|---|---|---|
| RRF only | [X]% | pgvector + BM25, top-8 |
| RRF + Reranker | [X]% | Cohere rerank-english-v3.0, 60→8 |
| RRF + Reranker + Deps | [X]% | +1-hop import expansion, capped at 10 |

*Source Hit Rate: percentage of queries where the target file appeared in the retrieved context (position-agnostic).*

## Latency (steady-state, averaged over 3 runs)

| Configuration | P50 | P95 |
|---|---|---|
| RRF only | [X]ms | [X]ms |
| RRF + Reranker | [X]ms | [X]ms |
| RRF + Reranker + Deps | [X]ms | [X]ms |

*Latency measured from query receipt to first SSE token. Excludes LLM generation time (model-dependent).*

## Trade-offs & Limitations
- **Reranker Latency:** [Insert honest observation on the latency penalty of the cross-encoder vs. the precision gain]
- **Dependency Bloat:** [Insert honest observation on whether 1-hop expansion occasionally pulls in loosely related imports that dilute the context]

## Eval Set
25 questions covering: retrieval logic, parser behaviour, CLI commands, API endpoints, and cross-file dependencies. Questions and expected sources are available in `eval/test_cases.json`.

## Reproducing

```bash
cp .env.example .env  # add OPENAI_API_KEY, COHERE_API_KEY
docker compose -f docker/docker-compose.yml up -d
contextcraft index .
python eval/run_eval.py --runs 3
python eval/run_eval.py --rerank --runs 3
python eval/run_eval.py --rerank --deps --runs 3
```
