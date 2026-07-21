from playwright.sync_api import sync_playwright
import os, json, time
from pathlib import Path

OUT_DIR = Path('scripts')
OUT_DIR.mkdir(exist_ok=True)
VID_DIR = OUT_DIR / 'videos'
VID_DIR.mkdir(exist_ok=True)
FRONTEND_URL = os.environ.get('FRONTEND_URL','http://localhost:3000')
QUESTION = 'Please summarise the project purpose.'

result = {"ok": False, "error": None, "captured_text": None, "screenshot": None, "html_path": None, "video": None}

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(record_video_dir=str(VID_DIR), record_video_size={"width":1280, "height":720})
        page = context.new_page()
        page.goto(FRONTEND_URL, timeout=60000)
        time.sleep(1)

        # Fill input
        try:
            if page.query_selector('input[aria-label="Message the assistant"]'):
                page.fill('input[aria-label="Message the assistant"]', QUESTION)
            elif page.query_selector('textarea[aria-label="Message the assistant"]'):
                page.fill('textarea[aria-label="Message the assistant"]', QUESTION)
            elif page.query_selector('[contenteditable]'):
                page.fill('[contenteditable]', QUESTION)
        except Exception:
            pass

        # Click send button using aria-label
        clicked = False
        try:
            if page.query_selector('button[aria-label="Send message"]'):
                page.click('button[aria-label="Send message"]')
                clicked = True
        except Exception:
            pass

        if not clicked:
            # fallback to pressing Enter
            try:
                if page.query_selector('input[aria-label="Message the assistant"]'):
                    page.press('input[aria-label="Message the assistant"]','Enter')
                elif page.query_selector('textarea'):
                    page.press('textarea','Enter')
            except Exception:
                pass

        # Wait for assistant response: look for last message bubble in aria-live container
        locator = page.locator('div[aria-live="polite"] .rounded-xl').last
        try:
            locator.wait_for(state='visible', timeout=20000)
            content = locator.inner_text()
        except Exception:
            # fallback: take last 2000 chars of body
            body = page.inner_text('body')
            content = body[-2000:]

        # Save artifacts
        timestamp = int(time.time())
        screenshot_path = OUT_DIR / f'assistant_dom_adjusted_{timestamp}.png'
        html_path = OUT_DIR / f'assistant_dom_adjusted_{timestamp}.html'
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

        # Close context to finalize video file
        context.close()
        # Find the most recent video file in VID_DIR
        videos = sorted(VID_DIR.glob('**/*'), key=lambda p: p.stat().st_mtime, reverse=True)
        video_path = str(videos[0]) if videos else None
        result['video'] = video_path

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
