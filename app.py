"""Brand Studio — run with:  python app.py   (then open http://127.0.0.1:7860)"""
from __future__ import annotations

import faulthandler
import json
import os
import shutil
import sys
import traceback

import gradio as gr
from PIL import Image

from studio import analytics, composer, research, store, strategist, visuals
from studio.config import (DATA_DIR, load_brand, load_settings, save_brand, save_settings,
                           split_list)
from studio.llm import SPEED_MODES, LLMError, health, list_models, speed, warmup

PLATFORMS = ["Instagram", "TikTok", "YouTube", "Pinterest", "X", "Facebook"]
GOALS = ["Grow engagement", "Grow followers", "Launch a new drop", "Drive website sales",
         "Build hype before a drop", "Sell remaining stock", "Build community / UGC", "Brand awareness"]


def _err(e: Exception):
    if isinstance(e, LLMError):
        raise gr.Error(str(e))
    traceback.print_exc()
    raise gr.Error(f"{type(e).__name__}: {e}")


def status_md():
    ok, img = visuals.available()
    return f"{health()}  \n{'✅ ' if ok else '⚠️ '}{img}"


# ------------------------------------------------------------------ brand tab
def save_brand_ui(name, handle, one_liner, products, price, audience, voice, avoid, values, competitors,
                  platforms, tags, c1, c2, c3, vstyle, font_path, logo_file, ollama_url, text_model, image_model):
    b = load_brand()
    b.update(name=name, handle=handle, one_liner=one_liner, products=products, price_point=price,
             audience=audience, voice=voice, words_to_avoid=avoid, values=values, competitors=competitors,
             platforms=platforms, core_hashtags=tags, colors={"primary": c1, "secondary": c2, "accent": c3},
             visual_style=vstyle, font_path=font_path.strip())
    if logo_file:
        dest = DATA_DIR / ("logo" + ("." + logo_file.split(".")[-1] if "." in logo_file else ".png"))
        shutil.copy(logo_file, dest)
        b["logo_path"] = str(dest)
    save_brand(b)
    s = load_settings()
    s.update(ollama_url=ollama_url.strip(), text_model=text_model.strip(), image_model=image_model)
    save_settings(s)
    return "✅ Saved. Every tool now uses this profile.", status_md()


# ------------------------------------------------------------------ research tab
def run_research(keywords, subs, feeds, urls, use_web, use_news, use_reddit, use_rss, csv_file, notes, speed_mode,
                 reuse, prev_report, progress=gr.Progress()):
    """Runs in 3 stages and streams updates so the progress bar and the brief fill in live."""
    try:
        s = load_settings()
        s.update(research_keywords=keywords, subreddits=subs, rss_feeds=feeds, speed=speed_mode)
        save_settings(s)
        brand = load_brand()
        mode = speed()

        # Stage 1 (0-60%): gather sources
        progress(0, desc="Step 1 of 3 · Gathering sources…")
        yield "⏳ **Step 1 of 3:** gathering sources…", "", "", prev_report
        data = research.gather(split_list(keywords), split_list(subs), split_list(feeds), split_list(urls),
                               use_web, use_news, use_reddit, use_rss,
                               progress=lambda f, desc="": progress(0.6 * f, desc=f"Step 1 of 3 · {desc}"),
                               per_source=mode["per_source"], cache_hours=6 if reuse else 0)
        raw = research.findings_markdown(data["findings"])
        if data["errors"]:
            raw += "\n\n**Sources that failed (skipped):**\n" + "\n".join(f"- {e}" for e in data["errors"][:15])

        # Stage 2 (60-65%): your analytics
        a_text, a_md = "", ""
        if csv_file:
            progress(0.6, desc="Step 2 of 3 · Analysing your account…")
            res = analytics.analyze(analytics.load(csv_file))
            a_text, a_md = analytics.summary_text(res), analytics.summary_markdown(res)
        n = len(data["findings"])
        yield f"⏳ **Step 3 of 3:** the AI is reading {n} findings. The first words can take up to a minute…", raw, a_md, prev_report

        # Stage 3 (65-100%): write the brief, streaming
        progress(0.65, desc=f"Step 3 of 3 · AI is reading {n} findings…")
        reused = f" ({data['cached']} sources reused from the last 6 hours)" if data.get("cached") else ""
        header = f"_Based on {n} findings gathered {data['when']}{reused} · {speed_mode} mode._\n\n"
        report, shown, expected = "", 0, 3000 if speed_mode == "Fast" else 3500  # typical brief length
        for piece in strategist.research_report_stream(brand, research.findings_digest(data["findings"], mode["digest_chars"]), a_text, notes):
            report += piece
            if len(report) - shown >= 120:
                shown = len(report)
                pct = min(len(report) / expected, 0.97)
                progress(0.65 + 0.35 * pct, desc=f"Step 3 of 3 · Writing your brief… {int(pct * 100)}%")
                yield header + report + " ▍", raw, a_md, prev_report
        progress(1.0, desc="Done")
        store.save("report", f"Research {data['when']}", report)
        yield header + report, raw, a_md, report
    except Exception as e:  # noqa: BLE001
        _err(e)


# ------------------------------------------------------------------ ideas tab
def run_ideas(report, n, platform, goal, extra, avoid_used, use_favs, progress=gr.Progress()):
    try:
        report = report or store.latest("report")
        avoid = store.titles_with_status("Used") if avoid_used else None
        favs = store.titles_with_status("Favorite", 10) if use_favs else None
        progress(0, desc="AI is reading your brief and past ideas…")
        yield "⏳ The AI is reading your brief. The first words can take a little while…", [], gr.update()
        expected = int(n) * 900  # roughly 900 characters of JSON per idea
        ideas = []
        for kind, val in strategist.post_ideas_stream(load_brand(), report, int(n), platform, goal, extra, avoid, favs):
            if kind == "progress":
                pct = min(val / expected, 0.97)
                done = min(int(pct * int(n)), int(n) - 1)
                progress(pct, desc=f"Writing idea {done + 1} of {int(n)}… {int(pct * 100)}%")
            else:
                ideas = val
        ids = store.save_ideas(ideas, platform, goal)
        store.save("ideas", f"{n} ideas · {platform} · {goal}", ideas)
        choices = [f"{i + 1}. {d.get('title', 'Idea')}" for i, d in enumerate(ideas)]
        saved = (f"_💾 Saved to your **Ideas library** as #{ids[0]}–#{ids[-1]}. Star the ones you like there._\n\n"
                 if ids else "")
        yield saved + strategist.ideas_markdown(ideas), ideas, gr.update(choices=choices, value=choices[0] if choices else None)
    except Exception as e:  # noqa: BLE001
        _err(e)


def _pick(ideas, choice):
    if not ideas or not choice:
        raise gr.Error("Generate ideas first, then pick one.")
    return ideas[int(choice.split(".")[0]) - 1]


def _visual_from(d):
    return (d.get("image_prompt", ""), d.get("overlay_text", "") or d.get("title", ""), gr.update(selected="visual"))


def _caption_from(d):
    return f"{d.get('title')}: {d.get('concept')} (format: {d.get('format')})", gr.update(selected="captions")


def idea_to_visual(ideas, choice):
    return _visual_from(_pick(ideas, choice))


def idea_to_caption(ideas, choice):
    return _caption_from(_pick(ideas, choice))


# ------------------------------------------------------------------ ideas library
LIB_HEADERS = ["#", "Status", "Idea", "Format", "Platform", "Goal", "Created", "Used on"]


def lib_counts_md():
    c = store.counts()
    total = sum(c.values())
    return (f"**{total} ideas saved** · ⭐ {c.get('Favorite', 0)} favorites · 🆕 {c.get('New', 0)} new · "
            f"✅ {c.get('Used', 0)} used · 🗄 {c.get('Archived', 0)} archived")


def lib_list(status, query):
    rows = store.list_ideas(status, query)
    return rows, [r[0] for r in rows], lib_counts_md()


def lib_select(ids, evt: gr.SelectData):
    if not ids or evt.index is None:
        return gr.update(), gr.update(), gr.update()
    row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    return lib_show(ids[row])


def lib_show(idea_id):
    d = store.get_idea(idea_id)
    if not d:
        return idea_id, "_Pick an idea from the list (click a row) or type its number._", ""
    m = d["_meta"]
    head = (f"**#{m['id']} · {m['status']}** · saved {str(m['created'])[:10]}"
            + (f" · used {m['used_on']}" if m.get("used_on") else "")
            + (f" · {m['platform']}" if m.get("platform") else "") + (f" · goal: {m['goal']}" if m.get("goal") else ""))
    return m["id"], head + "\n\n" + strategist.ideas_markdown([d]).replace("### 1. ", "### ", 1), m.get("notes", "")


def _need(idea_id):
    if not idea_id or not store.get_idea(idea_id):
        raise gr.Error("Pick an idea first: click a row in the list.")
    return int(idea_id)


def lib_set(idea_id, status, filt, query):
    store.set_status(_need(idea_id), status)
    rows, ids, counts = lib_list(filt, query)
    _, detail, notes = lib_show(idea_id)
    return rows, ids, counts, detail


def lib_save_notes(idea_id, notes):
    store.set_notes(_need(idea_id), notes)
    gr.Info("Notes saved")


def lib_to_visual(idea_id):
    return _visual_from(store.get_idea(_need(idea_id)))


def lib_to_caption(idea_id):
    return _caption_from(store.get_idea(_need(idea_id)))


def lib_remix(idea_id, direction, platform, filt, query, progress=gr.Progress()):
    try:
        d = store.get_idea(_need(idea_id))
        progress(0.2, desc="Remixing with a fresh angle…")
        new = strategist.remix_idea(load_brand(), d, direction, platform)
        new["title"] = str(new.get("title", "Remix"))
        [new_id] = store.save_ideas([new], platform or d["_meta"].get("platform", ""), "Remix of #" + str(d["_meta"]["id"]))
        rows, ids, counts = lib_list(filt, query)
        nid, detail, notes = lib_show(new_id)
        return rows, ids, counts, nid, f"_🔁 New remix saved as #{new_id}._\n\n" + detail, notes
    except gr.Error:
        raise
    except Exception as e:  # noqa: BLE001
        _err(e)


# ------------------------------------------------------------------ visual tab
def refine_prompt(prompt):
    try:
        return strategist.improve_image_prompt(load_brand(), prompt)
    except Exception as e:  # noqa: BLE001
        _err(e)


def run_generate(prompt, style, negative, preset, aspect, n, seed, steps, low_vram, init_img, strength,
                 progress=gr.Progress()):
    ok, msg = visuals.available()
    if not ok:
        raise gr.Error(msg)
    if not prompt.strip():
        raise gr.Error("Write (or send over) an image prompt first.")
    try:
        progress(0, desc="Loading image model (first run downloads it — this can take a while)…")
        paths = visuals.generate(prompt, style, negative, preset, aspect, int(n), int(seed),
                                 int(steps) if steps else None, init_img, float(strength), low_vram, progress)
        return paths, paths, paths[0]
    except Exception as e:  # noqa: BLE001
        _err(e)


def gallery_select(paths, evt: gr.SelectData):
    return paths[evt.index] if paths and evt.index is not None else None


def run_compose(src, headline, subtext, layout, size_key, uppercase, show_handle):
    b = load_brand()
    img = Image.open(src) if isinstance(src, str) else (src or composer.placeholder(b["colors"]))
    return composer.compose(img, headline, subtext, b.get("handle", "") if show_handle else "", size_key, layout,
                            b["colors"], b.get("font_path", ""), b.get("logo_path", ""), uppercase)


def run_slides(text, size_key):
    b = load_brand()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        raise gr.Error("One slide per line.")
    return [composer.carousel_slide(l, i + 1, len(lines), b["colors"], size_key, b.get("font_path", ""),
                                    b.get("handle", "")) for i, l in enumerate(lines)]


# ------------------------------------------------------------------ captions tab
def run_captions(desc, platform, tone, n, tags, report):
    try:
        out = strategist.captions(load_brand(), desc, platform, tone, int(n), tags, report or store.latest("report"))
        store.save("captions", desc[:80], out)
        return out
    except Exception as e:  # noqa: BLE001
        _err(e)


def run_bios(platform, n, focus):
    try:
        out = strategist.bios(load_brand(), platform, int(n), focus)
        store.save("bios", f"{platform} bios", out)
        return out
    except Exception as e:  # noqa: BLE001
        _err(e)


# ------------------------------------------------------------------ performance tab
def run_analytics(f):
    if not f:
        raise gr.Error("Upload your analytics export (CSV or XLSX).")
    try:
        res = analytics.analyze(analytics.load(f))
        empty = None
        return (analytics.summary_markdown(res), res["by_type"], res.get("by_weekday", empty),
                res.get("by_hour", empty), res["hashtags"], res["top_posts"])
    except Exception as e:  # noqa: BLE001
        _err(e)


# ------------------------------------------------------------------ page load
def on_page_load():
    report = store.latest("report")
    try:
        ideas = json.loads(store.latest("ideas") or "[]")
    except json.JSONDecodeError:
        ideas = []
    choices = [f"{i + 1}. {d.get('title', 'Idea')}" for i, d in enumerate(ideas)]
    ideas_view = ("_Your most recent ideas. Every idea you've generated is also in the 💡 **Ideas library** tab._\n\n"
                  + strategist.ideas_markdown(ideas)) if ideas else ""
    rows, ids, counts = lib_list("All active", "")
    return (report or "_Run research to get your first brief._", report, ideas_view, ideas,
            gr.update(choices=choices, value=choices[0] if choices else None), rows, ids, counts, store.history())


# ------------------------------------------------------------------ UI
def build():
    b, s = load_brand(), load_settings()
    with gr.Blocks(title="Brand Studio", theme=gr.themes.Soft(primary_hue="orange")) as demo:
        report_state, ideas_state, gallery_state = gr.State(store.latest("report")), gr.State([]), gr.State([])
        gr.Markdown(f"# 🧵 Brand Studio\nLocal social media research, post ideas, visuals and captions — running on your machine, no API keys.")
        status = gr.Markdown(status_md())

        with gr.Tabs() as tabs:
            # ---------------- Brand
            with gr.Tab("1 · Brand profile", id="brand"):
                gr.Markdown("Fill this in once. Everything the studio writes and designs is based on it.")
                with gr.Row():
                    name = gr.Textbox(b["name"], label="Brand name")
                    handle = gr.Textbox(b["handle"], label="Handle")
                    price = gr.Textbox(b["price_point"], label="Price point")
                one_liner = gr.Textbox(b["one_liner"], label="What the brand is (one line)")
                products = gr.Textbox(b["products"], label="Products")
                audience = gr.Textbox(b["audience"], label="Audience", lines=2)
                voice = gr.Textbox(b["voice"], label="Brand voice", lines=2)
                with gr.Row():
                    avoid = gr.Textbox(b["words_to_avoid"], label="Words to never use")
                    values = gr.Textbox(b["values"], label="Values")
                competitors = gr.Textbox(b["competitors"], label="Competitors / brands you admire")
                with gr.Row():
                    platforms = gr.CheckboxGroup(PLATFORMS, value=b["platforms"], label="Platforms")
                    tags = gr.Textbox(b["core_hashtags"], label="Core hashtags")
                with gr.Row():
                    c1 = gr.ColorPicker(b["colors"]["primary"], label="Primary colour")
                    c2 = gr.ColorPicker(b["colors"]["secondary"], label="Secondary colour")
                    c3 = gr.ColorPicker(b["colors"]["accent"], label="Accent colour")
                vstyle = gr.Textbox(b["visual_style"], label="Visual style (used for every AI image)", lines=2)
                with gr.Row():
                    font_path = gr.Textbox(b.get("font_path", ""), label="Brand font file path (.ttf/.otf, optional)")
                    logo = gr.File(label="Logo (PNG with transparency, optional)", type="filepath",
                                   file_types=["image"])
                with gr.Accordion("Engine settings", open=False):
                    ollama_url = gr.Textbox(s["ollama_url"], label="Ollama URL")
                    text_model = gr.Dropdown(list_models() or [s["text_model"]], value=s["text_model"],
                                             allow_custom_value=True, label="Text model (any model pulled in Ollama)")
                    image_model = gr.Dropdown(list(visuals.PRESETS), value=s["image_model"], label="Default image model")
                    gr.Markdown("\n".join(f"- **{k}** — {v['note']}" for k, v in visuals.PRESETS.items()))
                save_btn = gr.Button("Save profile", variant="primary")
                save_msg = gr.Markdown()
                save_btn.click(save_brand_ui, [name, handle, one_liner, products, price, audience, voice, avoid, values,
                                               competitors, platforms, tags, c1, c2, c3, vstyle, font_path, logo,
                                               ollama_url, text_model, image_model], [save_msg, status])

            # ---------------- Research
            with gr.Tab("2 · Research", id="research"):
                gr.Markdown("Pulls fresh trend signals from the web, news, Reddit and fashion press, combines them with "
                            "your own analytics and notes, and writes a strategy brief.")
                with gr.Row():
                    with gr.Column():
                        kw = gr.Textbox(s["research_keywords"], label="Search topics (comma separated)", lines=2)
                        subs = gr.Textbox(s["subreddits"], label="Subreddits")
                        feeds = gr.Textbox(s["rss_feeds"], label="RSS feeds (one per line)", lines=2)
                        urls = gr.Textbox("", label="Specific pages to read (competitor sites, articles) — one per line", lines=2)
                        with gr.Row():
                            use_web = gr.Checkbox(True, label="Web")
                            use_news = gr.Checkbox(True, label="News")
                            use_reddit = gr.Checkbox(True, label="Reddit")
                            use_rss = gr.Checkbox(True, label="Fashion press")
                    with gr.Column():
                        csv = gr.File(label="Your analytics export (optional, CSV/XLSX)", type="filepath")
                        notes = gr.Textbox(label="Your notes — paste competitor captions, what you've seen trending on "
                                           "IG/TikTok, upcoming drops, goals", lines=8)
                with gr.Row():
                    speed_mode = gr.Radio(list(SPEED_MODES), value=s.get("speed", "Fast"), label="Speed (applies everywhere)",
                                          info=" · ".join(f"{k}: {v['note']}" for k, v in SPEED_MODES.items()))
                    reuse = gr.Checkbox(True, label="Reuse sources fetched in the last 6 hours (much faster re-runs)")
                go = gr.Button("Run research", variant="primary")
                with gr.Tabs():
                    with gr.Tab("Strategy brief"):
                        report_md = gr.Markdown(store.latest("report") or "_Run research to get your first brief._")
                    with gr.Tab("Raw findings"):
                        raw_md = gr.Markdown()
                    with gr.Tab("Your analytics"):
                        a_md = gr.Markdown()
                go.click(run_research, [kw, subs, feeds, urls, use_web, use_news, use_reddit, use_rss, csv, notes, speed_mode, reuse,
                                        report_state],
                         [report_md, raw_md, a_md, report_state], show_progress="full")

            # ---------------- Ideas
            with gr.Tab("3 · Post ideas", id="ideas"):
                gr.Markdown("Ranked post ideas built from your latest research brief — each with hook, shot list, caption, "
                            "hashtags, timing and an image prompt.")
                with gr.Row():
                    n_ideas = gr.Slider(3, 12, 6, step=1, label="How many")
                    platform = gr.Dropdown(PLATFORMS, value=(b["platforms"] or ["Instagram"])[0], label="Platform")
                    goal = gr.Dropdown(GOALS, value=GOALS[0], allow_custom_value=True, label="Goal")
                extra = gr.Textbox(label="Extra direction (e.g. 'new olive cargo pants drop Friday', 'holiday gift angle')")
                with gr.Row():
                    avoid_used = gr.Checkbox(True, label="Don't repeat ideas I've marked as used")
                    use_favs = gr.Checkbox(True, label="Take inspiration from my ⭐ favorites")
                ideas_btn = gr.Button("Generate post ideas", variant="primary")
                with gr.Row():
                    pick = gr.Dropdown([], label="Pick an idea", interactive=True)
                    to_vis = gr.Button("→ Make the visual")
                    to_cap = gr.Button("→ Write more captions")
                ideas_md = gr.Markdown()

            # ---------------- Ideas library
            with gr.Tab("💡 Ideas library", id="library"):
                gr.Markdown("Every idea you generate is saved here automatically. ⭐ Star the good ones, mark ideas ✅ used "
                            "once you post them (so new ideas won't repeat them), and 🔁 remix old ideas into fresh posts.")
                lib_counts = gr.Markdown(lib_counts_md())
                with gr.Row():
                    lib_filter = gr.Dropdown(["All active", "Favorite", "New", "Used", "Archived", "Everything"],
                                             value="All active", label="Show")
                    lib_query = gr.Textbox(label="Search (title, caption, notes…)", scale=2)
                    lib_refresh = gr.Button("🔄 Refresh", scale=0)
                _rows = store.list_ideas()
                lib_ids = gr.State([r[0] for r in _rows])
                lib_table = gr.Dataframe(value=_rows, headers=LIB_HEADERS, interactive=False, wrap=True,
                                         label="Click a row to open it")
                with gr.Row():
                    with gr.Column(scale=3):
                        lib_detail = gr.Markdown("_Click a row above to open an idea._")
                    with gr.Column(scale=2):
                        lib_id = gr.Number(label="Idea #", precision=0)
                        with gr.Row():
                            fav_btn = gr.Button("⭐ Favorite")
                            used_btn = gr.Button("✅ Mark used")
                        with gr.Row():
                            new_btn = gr.Button("🆕 Back to new")
                            arch_btn = gr.Button("🗄 Archive")
                        with gr.Row():
                            lib_vis = gr.Button("→ Make the visual", variant="primary")
                            lib_cap = gr.Button("→ Write captions")
                        lib_notes = gr.Textbox(label="Your notes (results, what to change next time…)", lines=3)
                        lib_notes_btn = gr.Button("Save notes")
                        with gr.Accordion("🔁 Remix into a fresh post", open=True):
                            remix_dir = gr.Textbox(label="Direction (optional)",
                                                   placeholder="e.g. 'make it a Reel', 'tie it to the Super 32 weekend', 'funnier'")
                            remix_plat = gr.Dropdown(PLATFORMS, value=(b["platforms"] or ["Instagram"])[0], label="Platform")
                            remix_btn = gr.Button("🔁 Remix this idea")

                lib_filter.change(lib_list, [lib_filter, lib_query], [lib_table, lib_ids, lib_counts])
                lib_query.submit(lib_list, [lib_filter, lib_query], [lib_table, lib_ids, lib_counts])
                lib_refresh.click(lib_list, [lib_filter, lib_query], [lib_table, lib_ids, lib_counts])
                lib_table.select(lib_select, lib_ids, [lib_id, lib_detail, lib_notes])
                lib_id.submit(lib_show, lib_id, [lib_id, lib_detail, lib_notes])
                for btn, st in [(fav_btn, "Favorite"), (used_btn, "Used"), (new_btn, "New"), (arch_btn, "Archived")]:
                    btn.click(lambda i, f, q, st=st: lib_set(i, st, f, q), [lib_id, lib_filter, lib_query],
                              [lib_table, lib_ids, lib_counts, lib_detail])
                lib_notes_btn.click(lib_save_notes, [lib_id, lib_notes], None)
                remix_btn.click(lib_remix, [lib_id, remix_dir, remix_plat, lib_filter, lib_query],
                                [lib_table, lib_ids, lib_counts, lib_id, lib_detail, lib_notes])

            # ---------------- Visual studio
            with gr.Tab("4 · Visual studio", id="visual"):
                with gr.Row():
                    with gr.Column(scale=3):
                        prompt = gr.Textbox(label="Image prompt", lines=3,
                                            placeholder="model in an oversized washed-black hoodie leaning on a graffiti wall at golden hour…")
                        refine = gr.Button("✨ Rewrite prompt with AI (brand style)")
                        style = gr.Textbox(b["visual_style"], label="Style added to every prompt")
                        negative = gr.Textbox(visuals.DEFAULT_NEGATIVE, label="Avoid (negative prompt, SDXL only)")
                    with gr.Column(scale=2):
                        preset = gr.Dropdown(list(visuals.PRESETS), value=s["image_model"], label="Model")
                        aspect = gr.Dropdown(list(visuals.ASPECTS), value="4:5 (IG portrait)", label="Shape")
                        with gr.Row():
                            n_img = gr.Slider(1, 4, 2, step=1, label="Images")
                            seed = gr.Number(-1, label="Seed (-1 random)", precision=0)
                            steps = gr.Number(0, label="Steps (0 = default)", precision=0)
                        low_vram = gr.Checkbox(False, label="Low VRAM mode (GPUs under 8 GB)")
                        with gr.Accordion("Start from your product photo (img2img)", open=False):
                            init = gr.Image(type="pil", label="Product / reference photo")
                            strength = gr.Slider(0.2, 0.9, 0.55, step=0.05,
                                                 label="How much to change it (low = keep garment, high = reimagine)")
                gen = gr.Button("Generate images", variant="primary")
                gallery = gr.Gallery(label="Results (click one to use it below)", columns=4, height=420)

                gr.Markdown("### Turn it into a post graphic\nAdds your brand colours, headline, handle and logo at the exact platform size. "
                            "Works with any photo — upload your own product shots here too.")
                with gr.Row():
                    with gr.Column():
                        src = gr.Image(type="filepath", label="Image to use")
                        headline = gr.Textbox(label="Headline")
                        subtext = gr.Textbox(label="Subtext (e.g. 'Drops Friday 6PM · Link in bio')")
                        with gr.Row():
                            layout = gr.Dropdown(composer.LAYOUTS, value="Bottom band", label="Layout")
                            size_key = gr.Dropdown(list(composer.SIZES), value="4:5 (IG portrait)", label="Size")
                        with gr.Row():
                            upper = gr.Checkbox(True, label="Uppercase headline")
                            show_handle = gr.Checkbox(True, label="Show handle")
                        comp_btn = gr.Button("Compose post", variant="primary")
                    final = gr.Image(label="Finished post (download with the button in the corner)", type="filepath")
                with gr.Accordion("Carousel text slides", open=False):
                    slides_txt = gr.Textbox(lines=5, label="One slide per line")
                    slides_btn = gr.Button("Make slides")
                    slides = gr.Gallery(columns=5, height=300)

                refine.click(refine_prompt, prompt, prompt)
                gen.click(run_generate, [prompt, style, negative, preset, aspect, n_img, seed, steps, low_vram, init, strength],
                          [gallery, gallery_state, src])
                gallery.select(gallery_select, gallery_state, src)
                comp_btn.click(run_compose, [src, headline, subtext, layout, size_key, upper, show_handle], final)
                slides_btn.click(run_slides, [slides_txt, size_key], slides)

            # ---------------- Captions & bios
            with gr.Tab("5 · Captions & bios", id="captions"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Captions")
                        cap_desc = gr.Textbox(label="What's the post?", lines=3)
                        with gr.Row():
                            cap_plat = gr.Dropdown(PLATFORMS, value="Instagram", label="Platform")
                            cap_tone = gr.Dropdown(["On-brand", "Hype / urgent", "Funny", "Story-driven", "Minimal",
                                                    "Educational", "Heartfelt"], value="On-brand",
                                                   allow_custom_value=True, label="Tone")
                        with gr.Row():
                            cap_n = gr.Slider(1, 6, 3, step=1, label="Options")
                            cap_tags = gr.Checkbox(True, label="Hashtags")
                        cap_btn = gr.Button("Write captions", variant="primary")
                        cap_out = gr.Markdown()
                    with gr.Column():
                        gr.Markdown("### Profile bios")
                        bio_plat = gr.Dropdown(PLATFORMS, value="Instagram", label="Platform")
                        bio_focus = gr.Textbox(label="Current focus (optional, e.g. 'Fall drop live now')")
                        bio_n = gr.Slider(3, 8, 5, step=1, label="Options")
                        bio_btn = gr.Button("Write bios", variant="primary")
                        bio_out = gr.Markdown()
                cap_btn.click(run_captions, [cap_desc, cap_plat, cap_tone, cap_n, cap_tags, report_state], cap_out)
                bio_btn.click(run_bios, [bio_plat, bio_n, bio_focus], bio_out)

            # ---------------- Performance
            with gr.Tab("6 · My performance", id="perf"):
                gr.Markdown("Upload an export from Instagram (Meta Business Suite → Insights → Content → Export) or TikTok "
                            "(Analytics → Content → Download). See `sample_data/` for the format.")
                perf_file = gr.File(type="filepath", label="Analytics CSV / XLSX")
                perf_btn = gr.Button("Analyse", variant="primary")
                perf_md = gr.Markdown()
                with gr.Row():
                    t1 = gr.Dataframe(label="By format")
                    t2 = gr.Dataframe(label="By weekday")
                    t3 = gr.Dataframe(label="By hour")
                with gr.Row():
                    t4 = gr.Dataframe(label="Hashtags")
                    t5 = gr.Dataframe(label="Top posts")
                perf_btn.click(run_analytics, perf_file, [perf_md, t1, t2, t3, t4, t5])

            # ---------------- History
            with gr.Tab("History", id="history"):
                hist = gr.Dataframe(headers=["id", "kind", "created", "title"], value=store.history(), interactive=False)
                with gr.Row():
                    hid = gr.Number(label="Open item id", precision=0)
                    open_btn = gr.Button("Open")
                    refresh = gr.Button("Refresh")
                hist_md = gr.Markdown()
                open_btn.click(lambda i: store.get(i), hid, hist_md)
                refresh.click(lambda: store.history(), None, hist)

        ideas_btn.click(run_ideas, [report_state, n_ideas, platform, goal, extra, avoid_used, use_favs],
                        [ideas_md, ideas_state, pick], show_progress="full").then(
            lib_list, [lib_filter, lib_query], [lib_table, lib_ids, lib_counts])
        # Every time the page is opened or refreshed, load the latest saved data (not the startup snapshot)
        demo.load(on_page_load, None, [report_md, report_state, ideas_md, ideas_state, pick,
                                       lib_table, lib_ids, lib_counts, hist])
        lib_vis.click(lib_to_visual, lib_id, [prompt, headline, tabs])
        lib_cap.click(lib_to_caption, lib_id, [cap_desc, tabs])
        to_vis.click(idea_to_visual, [ideas_state, pick], [prompt, headline, tabs])
        to_cap.click(idea_to_caption, [ideas_state, pick], [cap_desc, tabs])
    return demo


if __name__ == "__main__":
    # If startup ever hangs, print exactly where after 60 s (goes to logs/last_run.log)
    faulthandler.dump_traceback_later(60, exit=False, file=sys.stderr)
    print("1/3 Checking the text AI (Ollama)…", flush=True)
    warmup()  # load the text model in the background so the first click is quick
    print("2/3 Building the interface…", flush=True)
    demo = build().queue()
    print("3/3 Starting the web server…", flush=True)
    # BRAND_STUDIO_HOST=0.0.0.0 makes it reachable from other devices on your network (use with care)
    host = os.environ.get("BRAND_STUDIO_HOST", "127.0.0.1")
    port = int(os.environ.get("BRAND_STUDIO_PORT", "7860"))
    demo.launch(inbrowser=True, server_name=host, server_port=port, prevent_thread_lock=True)
    faulthandler.cancel_dump_traceback_later()
    print(f"✅ Brand Studio is running: open http://127.0.0.1:{port} if a browser tab didn't open.", flush=True)
    demo.block_thread()
