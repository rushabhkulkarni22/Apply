"""Browser acceptance check against a running local demo server."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url',default='http://localhost:8000')
    parser.add_argument('--browser',default=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    parser.add_argument('--require-built',action='store_true')
    args = parser.parse_args()
    artifacts = Path('artifacts')
    artifacts.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser,headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url)
        if args.require_built:
            assert page.locator('script[src^="/static/app-"]').count() == 1, 'Server is not using the production frontend build'
        expect(page.get_by_role('heading',name='Your skills. Your next chapter.')).to_be_visible()
        page.get_by_role('button',name='Explore the demo').click()
        expect(page.get_by_role('heading',name='A new chapter, Alex')).to_be_visible()
        page.screenshot(path=str(artifacts/'overview-desktop.png'),full_page=True)
        page.locator('a[data-route="profile"]').click()
        expect(page.locator('#profile-form')).to_be_visible()
        from backend.app.demo import sample_pdf
        page.locator('#resume-upload').set_input_files({'name':'Smoke resume.pdf','mimeType':'application/pdf','buffer':sample_pdf()})
        expect(page.get_by_text('Smoke resume.pdf',exact=True)).to_be_visible()
        page.locator('input[name="notice_days"]').fill('45')
        page.locator('input[name="confirmed"]').check()
        page.get_by_role('button',name='Save profile & see matches').click()
        expect(page.get_by_role('heading',name='Find the right kind of next.')).to_be_visible()
        page.get_by_role('button',name='Needs review / excluded').click()
        expect(page.get_by_role('heading',name='Machine Learning Engineer')).to_be_visible()
        page.screenshot(path=str(artifacts/'matches-desktop.png'),full_page=True)
        page.get_by_role('button',name='Add a job',exact=False).click()
        page.locator('#job-form input[name="title"]').fill('Data Engineer')
        page.locator('#job-form input[name="company"]').fill('Browser Test Company')
        page.locator('#job-form input[name="url"]').fill('https://example.com/browser-test')
        page.locator('#job-form input[name="minimum_experience"]').fill('2')
        page.locator('#job-form textarea[name="description"]').fill('Build data pipelines with Python, SQL, AWS and PySpark.')
        page.get_by_role('button',name='Add and check match').click()
        expect(page.locator('#import-dialog')).not_to_be_visible()
        page.get_by_role('button',name='Start a run').click()
        page.locator('#run-form input[name="authorized"]').check()
        page.get_by_role('button',name='Start this run').click()
        expect(page.get_by_role('heading',name='Every step, in one place.')).to_be_visible()
        expect(page.locator('td .badge').filter(has_text='Simulated')).to_have_count(10,timeout=60000)
        page.locator('a[data-route="billing"]').click()
        page.get_by_role('button',name='Activate demo pass').click()
        expect(page.get_by_role('button',name='Your pass is active')).to_be_visible()
        page.screenshot(path=str(artifacts/'billing-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.locator('a[data-route="overview"]').click()
        page.screenshot(path=str(artifacts/'overview-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile layout overflows'
        page.locator('a[data-route="profile"]').click()
        page.get_by_role('button',name='Delete workspace data',exact=True).click()
        page.locator('#delete-form input[type="checkbox"]').check()
        page.locator('#delete-form button[type="submit"]').click()
        expect(page.get_by_role('heading',name='Your skills. Your next chapter.')).to_be_visible()
        assert not errors, errors
        print('Browser journey passed: login, resume upload, profile save, job import, exclusions, 10 simulations, demo pass, mobile layout, account deletion.')
        browser.close()


if __name__ == '__main__':
    main()
