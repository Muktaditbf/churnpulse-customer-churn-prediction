"""Capture screenshots of every page in light and dark mode (needs the running stack).

    python scripts/screenshots.py            # README screenshots (dark + light key pages)
    python scripts/screenshots.py --qa       # every page in both themes, into /tmp for review
"""

import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000"
QA = "--qa" in sys.argv
OUT = Path("/tmp/churnpulse-qa") if QA else Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    risky = httpx.get(f"{BASE}/api/customers", params={"band": "high", "sort": "value", "limit": 1}).json()["items"][0]
    pages = {
        "overview": "/", "customers": "/customers", "customer": f"/customers/{risky['customer_id']}",
        "add-customer": "/customers/new", "actions": "/actions", "import": "/import", "models": "/model",
    }
    themes = ["dark", "light"] if QA else ["dark"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in themes:
            ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.5)
            ctx.add_init_script(f"localStorage.setItem('churnpulse-theme', '{theme}')")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
            page.on("console", lambda m, errs=errors: errs.append(m.text) if m.type == "error" else None)
            for name, path in pages.items():
                page.goto(BASE + path)
                page.wait_for_load_state("networkidle")
                time.sleep(3)
                page.screenshot(path=OUT / f"{name}-{theme}.png", full_page=True)
            if QA:  # walk the add-customer wizard to the last step
                page.goto(BASE + "/customers/new")
                page.wait_for_load_state("networkidle")
                page.fill("input[name='contact.name']", "QA Walkthrough")
                for _ in range(5):
                    page.get_by_role("button", name="Next").click()
                    time.sleep(0.6)
                time.sleep(1.5)
                page.screenshot(path=OUT / f"wizard-last-{theme}.png", full_page=True)
            print(theme, "console/page errors:", errors[:5] or "none")
            ctx.close()
        browser.close()
    print("saved to", OUT)


if __name__ == "__main__":
    main()
