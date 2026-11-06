import json

from studio import store, strategist
from studio.llm import parse_json


def test_ideas_library_lifecycle():
    ids = store.save_ideas([{"title": "Fit check", "hook": "Which one?"}, {"title": "BTS"}], "Instagram", "Grow")
    assert len(ids) == 2
    store.set_status(ids[0], "Used")
    store.set_status(ids[1], "Favorite")
    assert store.titles_with_status("Used") == ["Fit check: Which one?"]
    assert store.get_idea(ids[0])["_meta"]["used_on"]
    store.set_notes(ids[1], "did great")
    assert store.list_ideas("Everything", "did great")[0][0] == ids[1]
    store.set_status(ids[1], "Archived")
    assert all(r[0] != ids[1] for r in store.list_ideas("All active"))


def test_history():
    store.save("report", "r", "## Brief")
    assert store.latest("report") == "## Brief"


def test_parse_json_tolerates_prose():
    assert parse_json('Sure! {"ideas": [{"title": "x"}]} hope that helps') == {"ideas": [{"title": "x"}]}


def test_post_ideas_stream_uses_memory(monkeypatch):
    seen = {}

    def fake_stream(system, user, temperature=0.7, json_mode=False, num_ctx=None):
        seen["prompt"] = user
        text = json.dumps({"ideas": [{"title": f"Idea {i}"} for i in range(3)]})
        for i in range(0, len(text), 20):
            yield text[i:i + 20]

    monkeypatch.setattr(strategist, "chat_stream", fake_stream)
    events = list(strategist.post_ideas_stream({"name": "B", "colors": {}}, "brief", 3, "Instagram", "Grow", "",
                                               avoid=["Old used idea"], build_on=["Loved idea"]))
    kind, ideas = events[-1]
    assert kind == "done" and [d["title"] for d in ideas] == ["Idea 0", "Idea 1", "Idea 2"]
    assert "Old used idea" in seen["prompt"] and "Loved idea" in seen["prompt"]


def test_ideas_markdown_handles_missing_fields():
    md = strategist.ideas_markdown([{"title": "Bare"}])
    assert "Bare" in md
