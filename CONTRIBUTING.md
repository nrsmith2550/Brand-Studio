# Contributing

Thanks for helping improve Brand Studio. Read [`docs/DEVELOPERS.md`](docs/DEVELOPERS.md) first: it explains how the code is laid out and has step-by-step recipes for the most common changes.

## Setup

```bash
git clone https://github.com/nrsmith2550/Brand-Analyze-Social-Media-Marketer.git
cd Brand-Analyze-Social-Media-Marketer
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                                                # offline, takes a few seconds
python app.py                                            # needs Ollama running for AI features
```

Image generation is optional: see `install-images.sh` / `install-images.bat`.

## Guidelines

- **Keep it local and key-free.** New features should work without API keys. Optional connectors for paid services are fine if they're off by default.
- **Fail soft.** A broken source, model or file should show a message, not crash the app.
- **Keep heavy imports lazy.** Don't import `torch` or `diffusers` at module level outside `visuals.generate()`.
- **Mind small machines.** Test on an 8 GB laptop if you can, or at least think about memory. Many users have one.
- **Logic goes in `studio/`, wiring in `app.py`.**
- **Write offline tests** for new logic, mocking HTTP and the LLM (see `tests/`).
- **Never commit personal data.** `brand.json`, `settings.json`, `studio.db`, `outputs/`, `my_data/` and `logs/` are ignored by git, so keep them that way. Use `brand.example.json` for examples.
- **Keep the style plain:** Python 3.10+ type hints, short functions, and comments that explain *why*.

## Pull requests

1. Open an issue first for anything big, so we can agree on the approach.
2. Keep each PR focused on one feature or fix.
3. Make sure `pytest -q` passes and the app starts (`python app.py`).
4. Describe how you tested it, including OS, RAM and model.
