"""Verifies real Groq API integration with file attachments and tests Windows and Android viewports."""
from pathlib import Path
from playwright.sync_api import sync_playwright

def test_devices_and_groq():
    dest = Path("docs/screenshots/device_verification")
    dest.mkdir(parents=True, exist_ok=True)

    expected_keyword = "2.5.0"
    file_content = f"제품명: AI Studio\n버전: {expected_keyword}\n핵심 기능: 초고속 멀티모달 추론 및 마크다운 렌더링\n문서 작성자: QA 엔지니어"

    targets = [
        {"name": "windows_desktop", "viewport": {"width": 1920, "height": 1080}, "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"},
        {"name": "android_mobile", "viewport": {"width": 412, "height": 915}, "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/122.0.0.0 Mobile Safari/537.36"},
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        for target in targets:
            print(f"=== Testing {target['name']} ({target['viewport']['width']}x{target['viewport']['height']}) ===")
            page = browser.new_page(
                viewport=target['viewport'],
                user_agent=target['user_agent'],
                device_scale_factor=2 if "mobile" in target['name'] else 1,
            )
            page.goto("http://localhost:8501", wait_until="domcontentloaded", timeout=30000)
            page.locator("h1").first.wait_for(state="visible", timeout=30000)
            page.wait_for_timeout(1000)

            # Ready for chat
            input_el = page.locator('[data-testid="stChatInput"]').first
            input_el.wait_for(state="visible", timeout=10000)

            # Upload file
            upload_btn = input_el.locator('[data-testid="stChatInputFileUploadButton"]')
            upload_btn.wait_for(state="visible", timeout=10000)
            with page.expect_file_chooser() as chooser:
                upload_btn.click()
            chooser.value.set_files([
                {"name": "spec.txt", "mimeType": "text/plain", "buffer": file_content.encode("utf-8")}
            ])
            page.keyboard.press("Escape")

            # Wait for file chip
            page.locator('[data-testid="stChatInput"]').get_by_text(
                "spec.txt", exact=False
            ).first.wait_for(state="visible", timeout=20000)
            page.wait_for_timeout(500)

            # Type question and submit
            chat_editor = page.locator('[data-testid="stChatInput"] textarea').first
            prompt_text = f"[{target['name']}] 첨부 파일 spec.txt에 적힌 제품 버전 번호는 무엇인가요?"
            chat_editor.fill(prompt_text)
            page.wait_for_timeout(500)
            chat_editor.press("Enter")

            # Wait for user message with attachment notice
            user_msg = page.locator('[data-testid="stChatMessage"]').filter(has_text=prompt_text).first
            user_msg.wait_for(state="visible", timeout=25000)
            user_msg.locator('[data-testid="stMarkdownContainer"]').filter(has_text="spec.txt").first.wait_for(
                state="visible", timeout=10000
            )
            print(f"[{target['name']}] User message rendered with attachment confirmation.")

            # Wait for real Groq assistant streaming response containing expected_keyword
            print(f"[{target['name']}] Waiting for Groq model streaming reply...")
            try:
                assistant_msg = page.locator('[data-testid="stChatMessage"]').filter(has_text=expected_keyword).first
                assistant_msg.wait_for(state="visible", timeout=60000)
                reply_text = assistant_msg.locator('[data-testid="stMarkdownContainer"]').all_inner_texts()
                print(f"[{target['name']}] Groq verified response received! Sample: {reply_text[0][:120]}...")
            except Exception as e:
                all_msgs = page.locator('[data-testid="stChatMessage"]').all_inner_texts()
                all_alerts = page.locator('[data-testid="stAlert"]').all_inner_texts()
                page.screenshot(path=str(dest / f"{target['name']}_error.png"), full_page=True)
                print(f"[{target['name']}] Failed waiting for response! Messages: {all_msgs[-2:]} | Alerts: {all_alerts}")
                raise e

            screenshot_path = dest / f"{target['name']}_groq_verified.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[{target['name']}] Screenshot saved to {screenshot_path}")

            page.close()

        browser.close()
    print("ALL DEVICE AND REAL GROQ TESTS PASSED!")

if __name__ == "__main__":
    test_devices_and_groq()

