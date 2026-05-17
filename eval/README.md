# ContextCraft Evaluation Harness

This directory contains a lightweight RAGAS-style evaluation harness to measure the retrieval quality of ContextCraft on its own codebase.

## Metrics Measured

1. **Source Hit Rate**: Does the exact file containing the answer appear in the top-K retrieved chunks?
2. **Faithfulness**: Does the LLM-generated answer accurately reflect the provided "ground truth" (evaluated by an LLM-as-a-judge)?
3. **Latency**: p50 retrieval latency.

## Running the Eval

Make sure your local ContextCraft instance is indexed (`contextcraft index .`).

To evaluate baseline RRF performance (no reranker):
```bash
python eval/run_eval.py
```

To evaluate with the Cohere reranker enabled:
```bash
python eval/run_eval.py --rerank
```

## Adding Test Cases

Open `test_cases.json` and add an object:

```json
{
  "question": "What does the get_pool function do?",
  "expected_sources": ["src/contextcraft/db/connection.py"],
  "ground_truth": "It returns a global asyncpg connection pool, creating it with exponential backoff on the first call."
}
```
