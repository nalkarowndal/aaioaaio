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
            screenshot=dest/f'{width}x{height}.png'
            page.screenshot(path=str(screenshot),full_page=True)
            has_horizontal=dims['doc'] > dims['vw']+1
            if opts.fixture:
                assert page.locator('pre code').count()>0,'fenced code block not rendered'
                assert page.locator('table').count()>0,'Markdown table not rendered'
                assert page.locator('h2').count()>0,'heading h2 not rendered'
                assert page.locator('h3').count()>0,'heading h3 not rendered'
            else:
                # Chat input must exist and be visible on main app.
                input_el=page.locator('[data-testid="stChatInput"]').first
                input_el.wait_for(state='visible',timeout=10000)
                assert input_el.bounding_box()['y'] < height,'chat input is below viewport'
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