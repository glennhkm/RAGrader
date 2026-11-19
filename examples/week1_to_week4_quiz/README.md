# Example: Weeks 1–3 Materials → Week 4 Quiz

This kit reproduces the canonical scenario from the PRD: an instructor uploads
Week 1–4 networking notes into one namespace, then grades a Week 4 quiz whose
scope is **only** Weeks 1–3. Week 4 (TLS) is ingested on purpose so you can see
that scoped retrieval never cites it.

| File | Purpose |
| :--- | :--- |
| `materials/week-1.txt` … `week-4.txt` | Short original lecture notes (layers, TCP/UDP, IP/DNS, TLS) |
| `rubric.json` | Accuracy (50) + Completeness (30) + Clarity (20) |
| `answers.csv` | Four student answers (`student_id,question,answer`), one in Indonesian |
| `run_demo.sh` | Ingests Weeks 1–4 with `module` tags and grades the CSV scoped to `week-1..week-3` |

## Run it

1. Start the API without cloud keys (Ollama bundled):

   ```bash
   cd backend
   cp .env.dev.example .env.dev
   docker compose -f docker-compose.dev.yml --profile local up -d --build
   docker compose -f docker-compose.dev.yml exec ollama ollama pull qwen2.5:7b-instruct
   docker compose -f docker-compose.dev.yml exec ollama ollama pull bge-m3
   ```

   Any other OpenAI-compatible endpoint works too: set `LLM_BASE_URL` / `EMBEDDING_BASE_URL`
   (and keys, if needed) in `.env.dev`.

2. From the repository root (needs `pip install -r backend/requirements.txt` for the CLI):

   ```bash
   RAG_API_URL=http://127.0.0.1:8000 ./examples/week1_to_week4_quiz/run_demo.sh
   ```

   Set `RAG_API_TOKEN` if `API_AUTH_TOKEN` is configured.

3. Open `examples/week1_to_week4_quiz/graded.csv`. Each row gains `score`, `confidence`,
   `needs_review` (confidence below `--review-threshold`, default 0.6, or an error),
   `language`, `feedback`, `citations` (`source#page`) and `error`.

## What to expect

- Citations only reference `week-1.txt`, `week-2.txt` or `week-3.txt`, never `week-4.txt`.
  Grade the same TLS question without `--module` filters to see `week-4.txt` appear.
- Student `s02` gives a vague answer and should score lower than `s01`.
- Student `s04` answers in Indonesian; with `PROMPT_LANGUAGE=auto` the feedback is Indonesian.
- Small local models sometimes return malformed JSON; such rows get a low score and
  `confidence = 0.5` from the fallback parser. Instruction-tuned models of 7B+ parameters
  are recommended.

## Timing

The ingest + grading round trip itself takes a few seconds; on a CPU-only machine most of
the time is spent in the model (expect roughly 10–60 s per answer with a 7B model).
The first run also downloads the Ollama models.

## Clean up

```bash
curl -X DELETE http://127.0.0.1:8000/v1/namespaces/net-101-demo
```
