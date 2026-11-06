# Developer guide

This guide covers everything you need to understand, change and extend Brand Studio. The codebase is about 2,000 lines of plain Python with no framework magic, apart from Gradio for the UI.

- [Architecture](#architecture)
- [Module reference](#module-reference)
- [Data model](#data-model)
- [How a request flows](#how-a-request-flows)
- [Recipes](#recipes)
- [Testing & debugging](#testing--debugging)
- [Gotchas we've hit](#gotchas-weve-hit)
- [Roadmap ideas](#roadmap-ideas)

---

## Architecture

```
                          ┌──────────────────────────── app.py (Gradio UI) ────────────────────────────┐
                          │  tabs · event handlers · progress bars · demo.load() refresh on page open    │
                          └───────┬──────────┬───────────┬────────────┬────────────┬────────────┬──────┘
                                  │          │           │            │            │            │
                       research.py   analytics.py  strategist.py   visuals.py   composer.py    store.py
                       web/news/      your CSV/XLSX  all prompts     SDXL/FLUX    Pillow post    SQLite:
                       Reddit/RSS/    → best format/ (brief, ideas,  via          graphics &     history +
                       pages, cached  day/hour/tags  captions, bios, diffusers    carousel       ideas library
                       in parallel                   remix)                       slides
                                                          │
                                                       llm.py ── HTTP ──► Ollama (localhost:11434)
                                                          │
                                                    config.py: brand profile, settings, paths, RAM detection
```

**Design rules:**

1. **Everything runs locally and fails soft.** Any network source can fail without breaking a research run, and each failure is listed under *Raw findings*.
2. **Heavy imports are lazy.** `torch` and `diffusers` are imported only when an image is generated. Importing them at startup made the app hang on 8 GB Macs.
3. **The brand profile is injected into every prompt** through `config.brand_brief()`, so no feature has its own copy of the brand.
4. **The UI layer is thin.** `app.py` only wires inputs to `studio/*` functions, and all logic lives in `studio/`, so you can reuse it from a CLI, a scheduler or another UI.

## Module reference

| Module | Key functions | Notes |
|---|---|---|
| `studio/config.py` | `load_brand()`, `save_brand()`, `load_settings()`, `brand_brief()`, `total_ram_gb()`, `split_list()` | JSON files in `DATA_DIR`. Defaults are merged in, so new keys never break old files. |
| `studio/llm.py` | `chat()`, `chat_stream()`, `chat_json()`, `parse_json()`, `warmup()`, `unload()`, `speed()`, `health()` | The only file that talks to Ollama. `SPEED_MODES` sets context size and prompt budget. |
| `studio/research.py` | `web_search()`, `reddit_top()`, `rss()`, `fetch_page()`, `gather()`, `findings_digest()` | `gather()` runs sources in a thread pool and caches results in `research_cache.json`. |
| `studio/analytics.py` | `load()`, `normalize()`, `analyze()`, `summary_text()`, `summary_markdown()` | Column names are matched loosely through `ALIASES`. |
| `studio/strategist.py` | `research_report_stream()`, `post_ideas_stream()`, `remix_idea()`, `captions()`, `bios()`, `improve_image_prompt()`, `ideas_markdown()` | All prompts live here. `IDEA_SCHEMA` is the contract for idea JSON. |
| `studio/visuals.py` | `generate()`, `release()`, `available()`, `check_compat()` | `PRESETS` and `MIN_RAM` define the models. Includes memory guards for small machines. |
| `studio/composer.py` | `compose()`, `carousel_slide()`, `placeholder()` | Pure Pillow, no GPU. `SIZES` and `LAYOUTS` drive the UI dropdowns. |
| `studio/store.py` | `save()`, `latest()`, `history()`, `save_ideas()`, `list_ideas()`, `get_idea()`, `set_status()`, `titles_with_status()` | SQLite, created and migrated on first connect. |

### The idea contract

Ideas are dicts that follow `strategist.IDEA_SCHEMA`:

```json
{"title": "", "format": "", "pillar": "", "hook": "", "concept": "", "shot_list": [],
 "image_prompt": "", "overlay_text": "", "caption": "", "hashtags": [], "cta": "",
 "best_time": "", "why_it_works": ""}
```

Small local models sometimes leave fields out, so read them with `.get()` and never index keys directly. Everything that renders ideas (`ideas_markdown`, the library, *→ Make the visual*) follows that rule.

## Data model

All of this lives in `DATA_DIR`, which is the project folder unless you set `BRAND_STUDIO_DATA`.

| File | Contents |
|---|---|
| `brand.json` | Brand profile (see `brand.example.json`) |
| `settings.json` | Ollama URL, text model, image preset, speed mode, research sources |
| `studio.db` | SQLite: `items` (history: reports, captions, bios, idea batches), `ideas` (library), `meta` (one-time migration flags) |
| `research_cache.json` | `{"kind\|arg": {"t": unix_time, "rows": [...]}}` |
| `outputs/` | Generated PNGs, each with a `.json` sidecar holding the prompt, seed, steps and size |

```sql
CREATE TABLE ideas (
  id INTEGER PRIMARY KEY, created TEXT, title TEXT, format TEXT, platform TEXT, goal TEXT,
  status TEXT DEFAULT 'New',   -- New | Favorite | Used | Archived
  notes TEXT DEFAULT '', used_on TEXT DEFAULT '', data TEXT  -- data = full idea JSON
);
```

**Schema changes:** add columns with `ALTER TABLE ... ADD COLUMN` inside `store._conn()`, guarded by a `meta` flag the way `ideas_migrated` is. People have existing databases, so never drop or rename columns.

## How a request flows

**Run research** (`app.run_research`, a generator):
1. `research.gather()` fetches sources in parallel and reuses cached ones. Progress runs 0–60%.
2. If you uploaded a CSV, `analytics.analyze()` reads it.
3. `strategist.research_report_stream()` streams tokens from Ollama. The handler `yield`s partial markdown, so the brief appears live, and progress is estimated from the number of characters written.
4. The finished report is saved with `store.save("report", …)` and becomes the input for post ideas.

**Generate ideas**: `post_ideas_stream()` asks for JSON (`format: json` in Ollama), streams it for the progress bar, then parses it. The prompt includes titles of ideas marked *Used* (so they aren't repeated) and *Favorite* (as inspiration). Every idea is stored as its own library row.

**Page load**: `demo.load(on_page_load)` re-reads the latest brief, ideas batch and library. Gradio component `value=`s are fixed when the UI is built, so without this a refresh would show stale data.

## Recipes

### Add a research source
1. In `research.py`, write a function that returns a list of dicts with `source`, `title`, `url` and `snippet`, plus optional `score`/`comments` for ranking and `date`. On failure, return `[{"source": ..., "error": "..."}]` instead of raising.
2. Register it in `_fetch()` and `_label()`, and add `("yourkind", arg)` steps in `gather()`.
3. In `app.py`, add a checkbox in the Research tab and pass it through `run_research` → `gather()`.
4. Add a test in `tests/test_research.py` that mocks the HTTP call.

Good candidates: YouTube channel RSS (`https://www.youtube.com/feeds/videos.xml?channel_id=…`), Bluesky search, Google Trends, Pinterest trends.

### Add a platform
Add it to `PLATFORMS` in `app.py`, `PLATFORM_NOTES` (caption and hashtag conventions) and `BIO_LIMITS` in `strategist.py`. If it needs a new canvas size, also add it to `composer.SIZES` and `visuals.ASPECTS`.

### Add an image model
Add an entry to `visuals.PRESETS` (`repo`, `steps`, `guidance`, `base` resolution and `note`) and its memory need to `MIN_RAM`. Anything `AutoPipelineForText2Image` can load will work. For a LoRA trained on your products, load it in `_load()` with `pipe.load_lora_weights(...)`.

### Use a different LLM server (LM Studio, llama.cpp, vLLM…)
Only `llm.py` talks to the model. Keep the public functions (`chat`, `chat_stream`, `chat_json`, `unload`, `warmup`, `list_models`, `health`) and swap what's inside them, for example to call an OpenAI-compatible `/v1/chat/completions` endpoint. Nothing else needs to change.

### Change the strategy or tone
Edit `SYSTEM` and the prompt builders in `strategist.py`. Keep the JSON schema stable, or update `IDEA_SCHEMA`, `ideas_markdown()` and the library together.

### Add a composer layout
Add a name to `composer.LAYOUTS` and a branch in `compose()`. Use `_fit_text()` so long headlines shrink to fit instead of overflowing.

### Support another analytics export
Add column-name variants to `analytics.ALIASES`. Matching is exact first, then by substring, and case is ignored.

### Add a tab
In `app.build()`, add a `with gr.Tab("…", id="…"):` block and put its handler functions above `build()`. Long-running handlers should be generators that take `progress=gr.Progress()` and `yield` updates. If the tab shows saved data, add it to `on_page_load()`.

## Testing & debugging

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

The tests run offline. They need no Ollama, GPU or network, because HTTP and the LLM are mocked and `BRAND_STUDIO_DATA` points at a temp folder. Please keep it that way, so tests run anywhere and in CI.

**Debugging the running app:**
- On Mac, the launcher writes everything to `logs/last_run.log`, unbuffered.
- If startup takes over 60 s, `faulthandler` writes every thread's stack to the log, which shows exactly where it hung.
- Gradio prints handler exceptions in the terminal and shows a short message in the UI through `gr.Error`.
- To check Ollama on its own, run `curl localhost:11434/api/tags`.

## Gotchas we've hit

| Symptom | Cause | Fix in code |
|---|---|---|
| App hangs at startup on 8 GB Macs | Importing `torch` at startup | `visuals.available()` uses `importlib.util.find_spec` |
| Mac freezes or reboots during image generation | Text model (≈2.5 GB, kept loaded) plus SDXL (≈7 GB) on an 8 GB machine | `llm.unload()` before generating, `release()` afterwards, `MIN_RAM` guard |
| `NSInvalidArgumentException … arrayViewWithShape:strides:` | PyTorch 2.15+ uses Metal APIs that only exist on macOS 15+ | `check_compat()` plus pinned `torch<2.15` on macOS 14 |
| Refreshing the page loses ideas | Gradio values are fixed when the UI is built | `demo.load(on_page_load)` |
| `.command` won't open in Finder | Executable bit lost after a file was rewritten | `chmod +x *.command` |
| Blank page in Safari after a restart | Safari kept a page cached from before the server started | Hard reload (Cmd+Option+R) |

**Gradio version:** the app targets Gradio 5 (`gradio>=5,<6`). Gradio 6 moves `theme=` from `gr.Blocks()` to `launch()`, which is the only change we know of. A deprecation warning about it appears at startup.

## Roadmap ideas

Good first issues are marked ⭐.

- ⭐ **More research sources:** YouTube RSS, Bluesky, Google Trends.
- ⭐ **Export a content calendar** from the Ideas library as CSV or `.ics`.
- ⭐ **Background removal** for product photos with `rembg`, then compose them onto generated scenes.
- **Scheduling:** push ideas to a scheduler (Buffer, Metricool or Later) through their APIs, as an optional connector.
- **Performance feedback loop:** import results for posts marked *Used* and rank ideas by real engagement.
- **Video:** Reel or TikTok script generator with shot timings, and captions burned into video with ffmpeg.
- **Fine-tuning:** train a LoRA on your product photos so generated images show your real garments.
- **Multiple brands:** several brand profiles, chosen from a dropdown.
- **Packaging:** Docker image, a Homebrew or winget package, or a PyInstaller app.
- **Gradio 6 migration** and a small CLI (`python -m studio ideas --n 6`) for automation.
