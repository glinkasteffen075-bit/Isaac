from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    page = browser.new_page()
    page.goto("https://example.com")
    page.screenshot(path="/root/Isaac/example.png", full_page=True)
    browser.close()
