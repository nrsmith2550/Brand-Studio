from PIL import Image

from studio import composer

COLORS = {"primary": "#111111", "secondary": "#F2EDE4", "accent": "rgba(228, 87, 46, 1)"}


def test_every_layout_and_size_renders():
    img = Image.new("RGB", (800, 1000), (120, 130, 125))
    for layout in composer.LAYOUTS:
        for size_key, (w, h) in composer.SIZES.items():
            path = composer.compose(img, "A very long headline that has to wrap nicely", "Sub", "@brand",
                                    size_key, layout, COLORS)
            assert Image.open(path).size == (w, h)


def test_hex_parsing():
    assert composer._hex("#E4572E") == (228, 87, 46)
    assert composer._hex("rgb(1, 2, 3)") == (1, 2, 3)
    assert composer._hex("nonsense", (9, 9, 9)) == (9, 9, 9)


def test_carousel_slide():
    path = composer.carousel_slide("Slide text", 2, 5, COLORS, handle="@brand")
    assert Image.open(path).size == composer.SIZES["4:5 (IG portrait)"]
