# Final Design: Web Search Fact-Checking (RAG) & Social Media Uploads

## 1. Understanding Summary
* **What is being built**: Integration of dynamic web search (RAG) for factual script grounding and direct uploads to YouTube Shorts & Instagram Reels via official APIs.
* **Why it exists**: To prevent LLM hallucinations by verifying concepts online and to enable a direct, seamless local workflow to publish videos.
* **Who it is for**: Creators generating viral shorts locally.
* **Key constraints**:
  * Uploading uses official Google & Facebook/Instagram APIs.
  * Instagram's API requires a public URL, resolved using an automated temporary ngrok tunnel.
  * Web search is dynamically decided by the LLM and runs via DuckDuckGo or Tavily/Google API.
* **Explicit non-goals**:
  * Avoid browser automation (Playwright/Selenium) for uploading.
  * No external database setup or user management (single-user local execution).

## 2. Assumptions
* The user will store credentials (`client_secrets.json`, `.env` parameters) locally.
* The user will manually review the generated video and edit titles/captions/hashtags before clicking the "Upload" button.
* Fast, local video hosting via a temporary ngrok tunnel is sufficient for Instagram's video retrieval step.

## 3. Decision Log
| Decision | Alternatives | Reason |
| :--- | :--- | :--- |
| **Dynamic Web Search** | Query search for all prompts | Preserves speed for creative/philosophical prompts, restricts search to factual/scientific prompts. |
| **Official APIs (OAuth & Graph API)** | Playwright/Browser automation | Offical APIs are secure, robust, and safe from account flags/bans, whereas browser automation breaks easily and is risky. |
| **ngrok Tunneling for Instagram** | S3/Cloud Storage Hosting | Automated local ngrok tunnel keeps hosting local, free, zero-setup, and closes immediately after upload. |

## 4. Final Design Specification

### A. Web Search Grounding
1. **Classifier**: Send a classification query to Ollama:
   * Prompt: Evaluate if the topic `{topic}` requires real-world research.
   * Expected output: `{ "requires_search": true/false, "search_query": "..." }`
2. **Searcher**:
   * If `requires_search` is true, use `duckduckgo_search` library (or Tavily if `TAVILY_API_KEY` is present) to run `search_query`.
   * Extract top 3–5 snippets.
3. **Generator**: Feed snippets into the script generator prompt as grounding context.
4. **Metadata Generation**: The script generator prompt will be updated to output optimized social media metadata in the JSON response:
   * **YouTube Metadata**: Title (max 100 chars, catchy), description (including tags), and tags (as list).
   * **Instagram Metadata**: Reel caption (including relevant hashtags).
   This metadata will auto-populate the UI fields when video generation completes.

### B. YouTube Uploader (`uploader_youtube.py`)
1. Uses `google-api-python-client` and `google-auth-oauthlib`.
2. Reads `client_secrets.json` and creates a local credentials store `token_youtube.json`.
3. Calls `youtube.videos().insert(part="snippet,status", body={...}, media_body=MediaFileUpload(...))` to upload local file.

### C. Instagram Uploader (`uploader_instagram.py`)
1. Uses `pyngrok` to launch a tunnel on port 8000: `public_url = ngrok.connect(8000).public_url`.
2. Creates an upload container on Instagram:
   * POST to `https://graph.facebook.com/v19.0/{instagram_business_account_id}/media` with `video_url=f"{public_url}/outputs/{video_filename}"`, `caption`.
3. Polls status of container `/container_id` until status is `FINISHED`.
4. Publishes container:
   * POST to `https://graph.facebook.com/v19.0/{instagram_business_account_id}/media_publish` with `creation_id=container_id`.
5. Closes ngrok tunnel: `ngrok.disconnect(public_url)`.

### D. UI Layout
* Gradio (`app.py`) & Next.js (`page.tsx`) get a **"Verify facts via Web Search"** checkbox.
* A **"Publish Video"** section is appended after rendering:
  * Checkboxes: `[ ] YouTube Shorts`, `[ ] Instagram Reels`
  * Text inputs: `Title` & `Caption`
  * Button: `Upload Now`
  * Log display terminal showing progress.
