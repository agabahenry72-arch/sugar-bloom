"""Find and launch a headless Chromium for rendering."""

from __future__ import annotations

import glob
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from .paths import CarouselError

LAUNCH_ARGS = ["--font-render-hinting=none", "--disable-gpu", "--hide-scrollbars"]


def _candidates() -> list[str]:
    found = []
    if os.environ.get("CAROUSEL_CHROMIUM"):
        found.append(os.environ["CAROUSEL_CHROMIUM"])
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), str(Path.home() / ".cache/ms-playwright"), "/opt/pw-browsers"]
    for root in filter(None, roots):
        found.append(os.path.join(root, "chromium"))
        found += sorted(glob.glob(os.path.join(root, "chromium-*/chrome-linux*/chrome")), reverse=True)
        found += sorted(glob.glob(os.path.join(root, "chromium_headless_shell-*/chrome-*/chrome-headless-shell")), reverse=True)
        found += sorted(glob.glob(os.path.join(root, "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium")), reverse=True)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        path = shutil.which(name)
        if path:
            found.append(path)
    found.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return [p for p in dict.fromkeys(found) if os.path.isfile(p) and os.access(p, os.X_OK)]


@contextmanager
def chromium():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CarouselError(
            "Playwright isn't installed. Run: pip install playwright && python -m playwright install chromium"
        ) from None

    with sync_playwright() as p:
        browser = None
        problems = []
        try:
            browser = p.chromium.launch(args=LAUNCH_ARGS)
        except PlaywrightError as exc:
            problems.append(str(exc).splitlines()[0])
            for path in _candidates():
                try:
                    browser = p.chromium.launch(executable_path=path, args=LAUNCH_ARGS)
                    break
                except PlaywrightError as inner:
                    problems.append(f"{path}: {str(inner).splitlines()[0]}")
        if browser is None:
            raise CarouselError(
                "Couldn't start Chromium. Install it with `python -m playwright install chromium`, "
                "or point CAROUSEL_CHROMIUM at a Chrome/Chromium binary.\n  " + "\n  ".join(problems)
            )
        try:
            yield browser
        finally:
            browser.close()
