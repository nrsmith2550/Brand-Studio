# Brand Studio: local AI social media marketer

**Research what works on social media, plan posts, design graphics and write captions for a brand, all on your own computer.**
No API keys, no subscriptions and no per-use cost. Brand Studio runs open-source models locally: text through [Ollama](https://ollama.com) and images through Stable Diffusion / FLUX via 🤗 [diffusers](https://github.com/huggingface/diffusers). The web interface is built with [Gradio](https://gradio.app).

It was built for an independent clothing brand, but nothing in the code is tied to one brand or niche. You describe your brand once, and every feature adapts to it.

> **Building on this?** Start with [`docs/DEVELOPERS.md`](docs/DEVELOPERS.md): the architecture, the data model, and step-by-step recipes for adding research sources, platforms, image models and tabs.

---

## What it does

| Tab | What you get |
|---|---|
| **1 · Brand profile** | Voice, audience, products, colours, visual style and logo. Every prompt is built from this. |
| **2 · Research** | Pulls trends from web and news search (DuckDuckGo), Reddit, RSS feeds and any pages you link, then combines them with your own analytics and notes. A local model writes a strategy brief live, with a progress bar. |
| **3 · Post ideas** | Ranked post ideas, each with a hook, shot list, caption, hashtags, CTA, timing and an image prompt. It skips ideas you've already posted and learns from your favourites. |
| **💡 Ideas library** | Every idea is saved automatically. You can star, mark as used, archive, search, add notes, send an idea to the visual studio or captions tab, or **remix** an old idea into a fresh post. |
| **4 · Visual studio** | Generate images locally (text-to-image, or img2img from your own product photo). Then compose finished, on-brand graphics with your headline, colours, handle and logo, sized for each platform. It can also make carousel text slides. |
| **5 · Captions & bios** | Caption options in your brand voice, plus profile bios kept within each platform's character limit. |
| **6 · My performance** | Upload an Instagram or TikTok analytics export to see your best formats, days, hours, hashtags and caption styles. |
| **History** | Everything generated, stored in a local SQLite file. |

Platforms: Instagram, TikTok, YouTube, Pinterest, X and Facebook.

---

## Quick start

### 1. Install the prerequisites
- **Python 3.11 or 3.12** ([python.org](https://www.python.org/downloads/))
- **Ollama** ([ollama.com](https://ollama.com)), then pull a text model:

```bash
ollama pull llama3.1:8b      # 16 GB RAM or more
ollama pull llama3.2:3b      # 8 GB machines
```

### 2. Run it

| OS | One-time setup | Every day |
|---|---|---|
| **macOS** | Double-click `Setup Brand Studio.command`. It installs everything, picks models for your RAM, and handles PyTorch on macOS 14. | `Start Brand Studio.command` |
| **Windows** | `start.bat`, then `install-images.bat` for image generation | `start.bat` |
| **Linux / manual** | `./start.sh`, then `./install-images.sh` | `./start.sh` |

The app opens at **http://127.0.0.1:7860**.

To start with an example brand instead of an empty one:

```bash
cp brand.example.json brand.json
```

### 3. Image generation hardware

| Preset | Needs | Notes |
|---|---|---|
| `sdxl-turbo` | 8 GB RAM / any Apple Silicon | Fast drafts. Check Stability AI's licence for commercial use. |
| `sdxl-base` | 16 GB RAM or 8 GB VRAM | Best all-rounder, OpenRAIL++ licence (commercial use allowed). |
| `flux-schnell` | 24 GB RAM or 16 GB+ VRAM | Highest quality, Apache-2.0 licence. |

The app blocks presets that won't fit in your computer's memory, because running them could freeze it. On 8 GB machines it also unloads the text model before generating images and frees memory afterwards. The post composer works on any machine, so you can use it with your own photos without generating anything.

---

## Good to know

- **Instagram and TikTok have no free data access** and block scraping. Brand Studio relies on your own analytics export, your pasted notes, and public sources (search, Reddit, RSS) instead.
- **AI images won't reproduce your exact product.** For product posts, use img2img at low strength (0.3–0.45) or your real photos in the composer.
- **Local models can be wrong.** Treat the brief as a smart first draft. Bigger models give noticeably better strategy.
- **macOS 14:** PyTorch 2.15+ needs macOS 15 for Apple's GPU, so the Mac setup pins PyTorch 2.14 on macOS 14. If you installed manually and image generation crashes, run `Fix Image Engine.command`.
- **Troubleshooting:** the Mac launcher writes everything it prints to `logs/last_run.log`. Open that file first when something fails.

## Your data stays local

Your brand profile (`brand.json`), settings, database (`studio.db`), generated images (`outputs/`), research cache and logs are all kept out of git by `.gitignore`. To keep them outside the project folder, set `BRAND_STUDIO_DATA=/path/to/folder`.

| Environment variable | Default | Purpose |
|---|---|---|
| `BRAND_STUDIO_DATA` | project folder | Where your profile, database, images and cache are stored |
| `BRAND_STUDIO_PORT` | `7860` | Port the web app listens on |
| `BRAND_STUDIO_HOST` | `127.0.0.1` | Set `0.0.0.0` to reach the app from other devices on your network (anyone on that network can then use it) |

## Contributing

Pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, tests and code style. Ideas for what to build next are in [`docs/DEVELOPERS.md#roadmap-ideas`](docs/DEVELOPERS.md#roadmap-ideas).

## License

[MIT](LICENSE). Model weights downloaded at runtime have their own licences (see the image table above, and each Ollama model's page).
