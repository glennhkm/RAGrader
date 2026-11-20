# Moodle Plugin Setup & Configuration

## 1. Compatibility

- **Moodle Version:** `mod_airagmaterial` and `mod_airagassign` require Moodle 4.4+ / 5.x (`$plugin->requires = 2024042200`). `local_assign_ai_rag` and `aiprovider_rag` require Moodle 4.5+ / 5.x (`$plugin->requires = 2024100700`) because they depend on the Core AI subsystem.
- **PHP Version:** PHP 8.1+ (tested with PHP 8.3 lint)
- **Moodle Cron:** Required for background material vectorization (`mod_airagmaterial`) and queued grading (`mod_airagassign`, `local_assign_ai_rag`). Ensure Moodle cron runs every minute:
  ```cron
  * * * * * /usr/bin/php /path/to/moodle/admin/cli/cron.php > /dev/null 2>&1
  ```

## 2. Build & Install Order

Generate the installable ZIP packages from the repository root:

```bash
./scripts/build-plugins.sh
```

Install in **Site administration → Plugins → Install plugins** in this dependency order:

1. `dist/airagmaterial.zip` (`mod_airagmaterial`)
2. `dist/airagassign.zip` (`mod_airagassign` — depends on `mod_airagmaterial`)
3. `dist/aiprovider_rag.zip` (`aiprovider_rag`)
4. `dist/local_assign_ai_rag.zip` (`local_assign_ai_rag` — depends on `aiprovider_rag`)

*(Alternatively, mount or symlink each folder under `moodle-plugins/` into your Moodle `public/mod/`, `public/local/`, and `public/ai/provider/rag/` paths.)*

### Upgrading an existing installation

1. **Upgrade the backend to 1.4.0 first, before any Moodle plugin.** The current plugins send an owner id (`material_id`) that only backend 1.4.0+ understands. An older backend ignores it: plugin deletes would remove other activities' vectors of the same filename, and materials vectorized there would be stored without an owner and not be found by owner-scoped grading after a later backend upgrade.
2. Upgrade the plugins (same order as above). The upgrade only queues re-vectorization of all AI RAG Materials and reference files; Moodle cron does the work, and grading of affected assignments is refused until it finishes. Retry gradings that failed in the meantime once cron has finished.
3. The activity modules call the RAG server through Moodle's HTTP client, which honours `$CFG->proxyhost`. If a proxy is configured, add the RAG server host to `$CFG->proxybypass`.
4. Vectors of files removed before the upgrade may remain in the course collection. AI RAG Assignment grading ignores them (it is owner-scoped), but `local_assign_ai_rag` grades against the whole course collection; clear the course collection and re-vectorize if that matters.

## 3. Configure Server URL & API Key

Set **Server URL** (e.g., `http://127.0.0.1:8000` or your internal backend URL) and **API Key** (matching `API_AUTH_TOKEN` in `backend/.env`, if enabled) in all four plugin settings pages:

- **AI RAG Material:** Site administration → Plugins → Activity modules → AI RAG Material (`mod_airagmaterial/serverurl`, `mod_airagmaterial/apikey`)
- **AI RAG Assignment:** Site administration → Plugins → Activity modules → AI RAG Assignment (`mod_airagassign/serverurl`, `mod_airagassign/apikey`)
- **Assign AI RAG (Local):** Site administration → Plugins → Local plugins → Assign AI RAG (`local_assign_ai_rag/server_url`, `local_assign_ai_rag/api_key`)
- **RAG AI Provider:** Site administration → Plugins → AI providers → RAG AI Provider (`aiprovider_rag/serverurl`, `aiprovider_rag/apikey`)

After saving settings, purge Moodle caches (**Site administration → Development → Purge all caches**).

