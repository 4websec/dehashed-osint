from src.api.web.pages import reuse_color


def test_reuse_color_is_deterministic():
    assert reuse_color("hunter2") == reuse_color("hunter2")


def test_reuse_color_differs_for_different_inputs():
    # Not a hard guarantee across all inputs, but these two must differ.
    assert reuse_color("hunter2") != reuse_color("Summer2019!")


def test_reuse_color_returns_css_color():
    val = reuse_color("hunter2")
    assert val.startswith("hsl(")
