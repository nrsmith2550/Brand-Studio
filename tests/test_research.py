from studio import research


class FakeResp:
    def __init__(self, content=b"", data=None, text=""):
        self.content, self._data, self.text = content, data, text

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def fake_get(url, **kwargs):
    if "reddit" in url:
        return FakeResp(data={"data": {"children": [{"data": {
            "title": "Hot take", "permalink": "/r/x/1", "selftext": "", "score": 100, "num_comments": 50}}]}})
    if "feed" in url:
        return FakeResp(content=b"<rss><channel><item><title>A &amp; B</title><link>https://a/1</link>"
                                b"<description>&lt;p&gt;desc&lt;/p&gt;</description></item></channel></rss>")
    return FakeResp(text="<html><title>Page</title><script>x()</script><body>Hello</body></html>")


def test_gather_parses_sources_and_caches(monkeypatch):
    monkeypatch.setattr(research.requests, "get", fake_get)
    calls = []
    monkeypatch.setattr(research, "web_search", lambda q, n=8, news=False: calls.append(q) or
                        [{"source": "web", "title": q, "url": f"https://w/{q}{news}", "snippet": ""}])
    args = (["kw"], ["sub"], ["https://x/feed"], ["https://page"])
    first = research.gather(*args)
    titles = [f["title"] for f in first["findings"]]
    assert "Hot take" in titles and "A & B" in titles and "Page" in titles and "kw" in titles
    assert first["findings"][0]["title"] == "Hot take"  # engagement-ranked first
    assert first["errors"] == []

    second = research.gather(*args)
    assert second["cached"] == 5 and second["fetched"] == 0
    assert len(calls) == 2  # web + news only on the first run

    fresh = research.gather(*args, cache_hours=0)
    assert fresh["fetched"] == 5


def test_failures_are_reported_not_raised(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("offline")
    monkeypatch.setattr(research.requests, "get", boom)
    out = research.gather([], ["sub"], [], [], use_web=False, use_news=False, cache_hours=0)
    assert out["findings"] == [] and len(out["errors"]) == 1


def test_digest_respects_budget():
    findings = [{"source": "web", "title": "t" * 50, "snippet": "s" * 200} for _ in range(100)]
    assert len(research.findings_digest(findings, 1000)) <= 1000
