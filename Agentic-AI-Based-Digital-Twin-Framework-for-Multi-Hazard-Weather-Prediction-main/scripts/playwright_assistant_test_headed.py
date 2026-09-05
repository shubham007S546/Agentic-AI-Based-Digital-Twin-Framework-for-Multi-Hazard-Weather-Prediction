from playwright.sync_api import sync_playwright
import os, json, time
from pathlib import Path

OUT_DIR = Path('scripts')
OUT_DIR.mkdir(exist_ok=True)
FRONTEND_URL = os.environ.get('FRONTEND_URL','http://localhost:3000')
QUESTION = 'Please summarise the project purpose.'

result = {"ok": False, "error": None, "captured_text": None, "screenshot": None, "html_path": None}

with sync_playwright() as p:
    try:
        # Launch headed browser so DOM is visible
        browser = p.chromium.launch(headless=False, slow_mo=200)
        page = browser.new_page()
        page.goto(FRONTEND_URL, timeout=60000)
        time.sleep(2)

        # Try to fill textarea/input/contenteditable
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

        # Click send button heuristically
        clicked = False
        for selector in ['button:has-text("Send")','button:has-text("Ask")','button:has-text("Submit")','button[aria-label="send"]','button']:
            try:
                btn = page.query_selector(selector)
                if btn:
                    btn.scroll_into_view_if_needed()
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

        # Wait for answer text to appear
        time.sleep(4)
        content = ''
        possibles = [".assistant-answer", "#assistant-answer", "[data-testid=assistant-answer]", "article", "div.answer", "div.result", "div.received-message", "div.message-body"]
        for sel in possibles:
            try:
                el = page.query_selector(sel)
                if el:
                    content = el.inner_text()
                    break
            except Exception:
                continue
        if not content:
            # try to find recent message text by looking for elements containing keywords
            body = page.inner_text('body')
            # narrow to last 2000 chars
            content = body[-2000:]

        # Save artifacts
        timestamp = int(time.time())
        screenshot_path = OUT_DIR / f'assistant_dom_{timestamp}.png'
        html_path = OUT_DIR / f'assistant_dom_{timestamp}.html'
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            result['screenshot'] = str(screenshot_path)
        except Exception as e:
            result['screenshot'] = f'screenshot_failed: {e}'
        try:
            html = page.content()
            html_path.write_text(html, encoding='utf-8')
            result['html_path'] = str(html_path)
        except Exception as e:
            result['html_path'] = f'html_save_failed: {e}'

        result['ok'] = True
        result['captured_text'] = content
        browser.close()
    except Exception as exc:
        result['error'] = str(exc)
        try:
            browser.close()
        except Exception:
            pass

print(json.dumps(result, ensure_ascii=False))
