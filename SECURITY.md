# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not** open a public GitHub issue with exploit details. Instead, report it privately to the repository maintainers so it can be patched before public disclosure.

## Hardening Recommendations for Production

1. **Enable API Bearer Authentication:**
   Set a strong random `API_AUTH_TOKEN` in `backend/.env`, then configure the matching `API Key` in all four Moodle plugins:
   - `mod_airagmaterial` (`mod_airagmaterial/apikey`)
   - `mod_airagassign` (`mod_airagassign/apikey`)
   - `local_assign_ai_rag` (`local_assign_ai_rag/api_key`)
   - `aiprovider_rag` (`aiprovider_rag/apikey`)
   When `API_AUTH_TOKEN` is set, all endpoints except `/` and `/health` enforce `Authorization: Bearer <token>` using constant-time comparison.

2. **Restrict Network Access:**
   Bind `API_BIND_ADDRESS` in `backend/.env` to a private interface and restrict port `8000` via firewall rules so only the Moodle server can reach the HAProxy frontend. Never expose the internal `chroma` or `redis` containers directly to the public internet.

3. **Protect Credentials:**
   Never commit `.env` files or embed LLM provider keys (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `HUGGINGFACE_API_TOKEN`, `PINECONE_API_KEY`) in Moodle plugin settings or source code.

