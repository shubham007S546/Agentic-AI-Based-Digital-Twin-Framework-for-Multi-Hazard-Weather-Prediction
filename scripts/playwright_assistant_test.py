from playwright.sync_api import sync_playwright
import os, json, time

FRONTEND_URL = os.environ.get('FRONTEND_URL','http://localhost:3000')
QUESTION = 'Please summarise the project purpose.'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(FRONTEND_URL, timeout=30000)
    time.sleep(2)
    try:
        if page.query_selector('textarea'):
            page.fill('textarea', QUESTION)
        elif page.query_selector('input[type="text"]'):
            page.fill('input[type="text"]', QUESTION)
        else:
            el = page.query_selector('[contenteditable]')
            if el:
                el.fill(QUESTION)
    except Exception:
        pass
    clicked = False
    for selector in ['button:has-text("Send")','button:has-text("Ask")','button:has-text("Submit")','button']:
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        try:
            if page.query_selector('textarea'):
                page.press('textarea','Enter')
            elif page.query_selector('input[type="text"]'):
                page.press('input[type="text"]','Enter')
        except Exception:
            pass
    time.sleep(3)
    content = ''
    possibles = [".assistant-answer", "#assistant-answer", "[data-testid=assistant-answer]", "article", "div.answer", "div.result"]
    for sel in possibles:
        try:
            el = page.query_selector(sel)
            if el:
                content = el.inner_text()
                break
        except Exception:
            continue
    if not content:
        content = page.inner_text('body')[:2000]
    print(json.dumps({"ok": True, "captured_text": content}, ensure_ascii=False))
    browser.close()
