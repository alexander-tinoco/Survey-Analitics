"""Guards on the cat illustrations that carry the visual identity.

These files live in ``static/img/`` because that is the only place Django's
static finder looks. A file kept outside it has no URL, is skipped by
``collectstatic``, and every template referencing it renders a broken image —
a failure that only shows up in a browser, never in a normal test run.
"""

import pytest
from django.contrib.staticfiles import finders

CAT_ASSETS = [
    "img/catHomePage.png",
    "img/catLogin.png",
    "img/catRegister.png",
    "img/cat400.png",
    "img/cat401.png",
    "img/cat404.png",
]


@pytest.mark.parametrize("asset", CAT_ASSETS)
def test_cat_illustration_is_resolvable_by_the_static_finder(asset: str) -> None:
    """Every cat referenced by a template must resolve to a real file."""
    assert finders.find(asset) is not None, (
        f"{asset} is not reachable by the static finder. "
        "Cat illustrations belong in static/img/."
    )
