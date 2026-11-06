from pathlib import Path

import pandas as pd

from studio import analytics

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "sample_instagram_export.csv"


def test_sample_export_loads_and_ranks():
    res = analytics.analyze(analytics.load(str(SAMPLE)))
    assert res["posts"] == 60
    assert res["metric"] == "eng_rate"
    assert set(res["by_type"]["type"]) == {"Reel", "Carousel", "Image"}
    assert "by_weekday" in res and len(res["by_weekday"])
    md = analytics.summary_markdown(res)
    assert "Best format" in md


def test_loose_column_matching():
    df = pd.DataFrame({"Date posted": ["2026-01-01 18:00", "2026-01-02 09:00"], "Format": ["Reel", "Image"],
                       "Caption": ["hi #a?", "yo #a"], "Hearts": ["1,200", "10"], "Views": [10000, 500]})
    out = analytics.normalize(df)
    assert out["likes"].tolist() == [1200, 10]
    assert out["reach"].tolist() == [10000, 500]
    assert out["type"].tolist() == ["Reel", "Image"]
