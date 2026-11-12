"""Visual regression guard (requires a running Streamlit app and Playwright Chromium).

Usage:
 python -m playwright install chromium
 python -m streamlit run scripts/markdown_fixture.py
 python scripts/visual_qa.py --fixture
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SIZES = [(375,812),(768,1024),(1280,800),(1920,1080)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://localhost:8501')
    parser.add_argument('--output',default='docs/screenshots')
    parser.add_argument('--fixture',action='store_true')
    parser.add_argument('--history',action='store_true',help='Assert P6 DB reload and conversation restore')
    parser.add_argument('--actions',action='store_true',help='Assert P7 copy/edit menu and reload')
    opts=parser.parse_args()
    dest=Path(opts.output)
    dest.mkdir(parents=True,exist_ok=True)
    report=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        for width,height in SIZES:
            page=browser.new_page(viewport={'width':width,'height':height}, device_scale_factor=1)
            page.goto(opts.url,wait_until='domcontentloaded',timeout=30000)
            # Wait for the Streamlit websocket and first actual title.
            page.locator('h1').first.wait_for(state='visible',timeout=30000)
            page.wait_for_timeout(500)
            dims=page.evaluate('''() => ({vw:window.innerWidth, doc:document.documentElement.scrollWidth,
                body:document.body.scrollWidth, visibleTitle:document.querySelector('h1').getBoundingClientRect().top>=0})''')
            assert page.get_by_text('Deploy',exact=True).count()==0,'Developer Deploy button visible'
            screenshot=dest/f'{width}x{height}.png'
            page.screenshot(path=str(screenshot),full_page=True)
            has_horizontal=dims['doc'] > dims['vw']+1
            if opts.fixture:
                assert page.locator('pre code').count()>0,'fenced code block not rendered'
                assert page.locator('table').count()>0,'Markdown table not rendered'
                assert page.locator('h2').count()>0,'heading h2 not rendered'
                assert page.locator('h3').count()>0,'heading h3 not rendered'
                if width == 375:
                    md=page.locator('[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"]').first
                    metrics=md.evaluate('el => ({width:el.clientWidth, scrollWidth:el.scrollWidth})')
                    assert metrics['scrollWidth'] > metrics['width']+5, f'Long table not scrollable: {metrics}'
                    md.evaluate('el => {el.scrollLeft=100}')
                    assert md.evaluate('el => el.scrollLeft')>0, 'Cannot horizontally scroll Markdown table'
            else:
                # Chat input must exist and be visible on main app.
                input_el=page.locator('[data-testid="stChatInput"]').first
                input_el.wait_for(state='visible',timeout=10000)
                assert input_el.bounding_box()['y'] < height,'chat input is below viewport'
                if width==1280:
                    # Mirror Streamlit's official Playwright E2E workflow:
                    # click the actual file-upload button, then file chooser.
                    upload_button = input_el.locator('[data-testid="stChatInputFileUploadButton"]')
                    upload_button.wait_for(state='visible', timeout=10000)
                    with page.expect_file_chooser() as chooser:
                        upload_button.click()
                    chooser.value.set_files([
                        {'name':'qa_alpha.txt','mimeType':'text/plain','buffer':b'alpha'},
                        {'name':'qa_beta.txt','mimeType':'text/plain','buffer':b'beta'},
                    ])
                    page.keyboard.press('Escape')
                    page.locator('[data-testid="stApp"]').click(
                        position={'x':0,'y':0}, force=True)
                    # Upload processing is asynchronous. Pressing Enter too early
                    # intermittently posts text without its file attachments.
                    # Require both native-composer previews before submitting.
                    for filename in ('qa_alpha.txt', 'qa_beta.txt'):
                        page.locator('[data-testid="stChatInput"]').get_by_text(
                            filename, exact=False
                        ).first.wait_for(state='visible', timeout=20000)
                    # The browser preview appears before the file payload is
                    # necessarily acknowledged by the Streamlit websocket.
                    page.wait_for_timeout(1000)
                chat_editor=page.locator('[data-testid="stChatInput"] textarea').first
                chat_editor.fill('UI 회귀 테스트 메시지')
                if width==1280:
                    # Use the same Send button as Streamlit's E2E file-upload tests.
                    input_el.locator('[data-testid="stChatInputSubmitButton"]').click()
                else:
                    chat_editor.press('Enter')
                page.locator('[data-testid="stChatMessage"]').filter(has_text='UI 회귀 테스트 메시지').first.wait_for(state='visible',timeout=15000)
                if width==1280 and opts.history:
                    # A full browser reload resets Streamlit session state.
                    # The previous message must still be present from SQLite.
                    page.reload(wait_until='domcontentloaded',timeout=30000)
                    page.locator('[data-testid="stChatMessage"]').filter(has_text='UI 회귀 테스트 메시지').first.wait_for(
                        state='visible',timeout=30000)
                if width==1280:
                    # Diagnose actual chat content rather than only a timeout
                    # if an uploaded file does not reach the persisted message.
                    for filename in ('qa_alpha.txt', 'qa_beta.txt'):
                        try:
                            page.locator('[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"]').filter(
                                has_text=filename
                            ).first.wait_for(state='visible',timeout=15000)
                        except Exception:
                            visible_text = page.locator(
                                '[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"]'
                            ).all_inner_texts()
                            page.screenshot(path=str(dest/'attachment_failure.png'),full_page=True)
                            raise AssertionError(
                                f'File {filename!r} missing from chat message. '
                                f'Actual Markdown text: {visible_text[:8]}'
                            )
                user_avatar=page.locator('[data-testid="stChatMessageAvatarUser"]').first
                user_avatar.wait_for(state='visible',timeout=10000)
                bubble=user_avatar.locator('xpath=ancestor::*[@data-testid="stChatMessage"][1]')
                bg=bubble.evaluate('el => getComputedStyle(el).backgroundImage')
                assert 'linear-gradient' in bg, f'User bubble styling lost: {bg}'
                page.screenshot(path=str(dest/f'{width}x{height}_interactions.png'),full_page=True)
                if width==1280 and opts.actions:
                    # The actions menu is compact and only appears when invoked.
                    user_message = page.locator('[data-testid="stChatMessage"]').filter(
                        has_text='UI 회귀 테스트 메시지').first
                    action_button = user_message.get_by_role('button', name='작업')
                    action_button.click()
                    page.get_by_text('질문 수정',exact=True).first.wait_for(
                        state='visible',timeout=10000)
                    # Streamlit changes code-block DOM markup between versions.
                    # Assert the user-visible copy instruction; app source tests
                    # separately verify this menu renders st.code with its native copy.
                    page.get_by_text(
                        '복사: 아래 원문 오른쪽 위의 복사 아이콘을 사용하세요.', exact=True
                    ).wait_for(state='visible', timeout=10000)
                    page.get_by_role('textbox', name='질문 수정').fill('P7 수정된 질문')
                    page.get_by_role('button', name='수정 후 다시 질문').click()
                    page.locator('[data-testid="stChatMessage"]').filter(
                        has_text='P7 수정된 질문').first.wait_for(state='visible',timeout=15000)
                    page.reload(wait_until='domcontentloaded',timeout=30000)
                    page.locator('[data-testid="stChatMessage"]').filter(
                        has_text='P7 수정된 질문').first.wait_for(state='visible',timeout=30000)
                    page.screenshot(path=str(dest/'p7_edit_restored.png'),full_page=True)

            report.append({'viewport':f'{width}x{height}','horizontal_overflow':has_horizontal,
                           'title_visible':dims['visibleTitle'],'screenshot':str(screenshot)})
            assert not has_horizontal,f'Full-page horizontal scroll at {width}: {dims}'
            assert dims['visibleTitle'],f'Title offscreen at {width}'
            page.close()
        browser.close()
    output=dest/'qa_report.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output)

if __name__=='__main__':
    main()