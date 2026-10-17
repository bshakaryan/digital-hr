"""Read-only Chrome check of populated Academy and HR learning profiles."""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

from browser_academy_cdp import CDP, CHROME, ROOT, env_value


async def scenario(port, web_url, password):
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    socket_url = next(item["webSocketDebuggerUrl"] for item in targets if item["type"] == "page")
    async with websockets.connect(socket_url, max_size=4_000_000) as socket:
        page = CDP(socket)
        await page.call("Runtime.enable")
        await page.call("Page.enable")

        async def shot(name):
            image = await page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            folder = ROOT / "frontend" / ".qa" / "learning-analytics"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(base64.b64decode(image["data"]))

        async def login(email):
            await page.call("Page.navigate", {"url": web_url})
            await page.wait("!!document.querySelector('#email')")
            await asyncio.sleep(0.4)
            script = """(function(){const set=(s,v)=>{const e=document.querySelector(s);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));};set('#email',EMAIL);set('#password',PASSWORD);document.querySelector('.login-submit').click();return true})()"""
            assert await page.js(script.replace("EMAIL", json.dumps(email)).replace("PASSWORD", json.dumps(password)))
            try:
                await page.wait("!!document.querySelector('[aria-label=\"Выйти из аккаунта\"]')")
            except AssertionError:
                print("LOGIN_DEBUG", await page.js("document.body.innerText.slice(0,700)"), page.errors)
                raise
            assert await page.js("(function(){const x=[...document.querySelectorAll('#workspace-navigation .nav-item')].find(b=>b.innerText.includes('Jana Academy'));if(!x)return false;x.click();return true})()")
            await page.wait("!!document.querySelector('.academy-banner')")

        await login("hr@example.com")
        await page.wait("document.querySelector('.learning-kpis')?.innerText.includes('37')")
        assert await page.js("document.querySelector('.learning-monitoring')?.querySelectorAll('tbody tr').length === 27")
        assert await page.js("(function(){document.querySelector('.learning-filter-row input[type=search]').focus();return true})()")
        await page.call("Input.insertText", {"text": "айдана демо"})
        await page.wait("document.querySelectorAll('.learning-directory-grid .learning-person-card').length === 1")
        assert await page.js("document.querySelector('.learning-directory-grid .learning-person-card')?.innerText.includes('Айдана Демо')")
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
        await page.wait("document.querySelectorAll('.learning-directory-grid .learning-person-card').length === 4")
        assert await page.js("(function(){const e=document.querySelectorAll('.learning-filter-row select')[1];const o=[...e.options].find(x=>x.innerText.includes('Как учиться в Jana Academy'));if(!o)return false;e.value=o.value;e.dispatchEvent(new Event('change',{bubbles:true}));return true})()")
        assert await page.js("(function(){document.querySelector('.learning-filter-row input[type=search]').focus();return true})()")
        await page.call("Input.insertText", {"text": "айдана демо"})
        await page.wait("!!document.querySelector('.learning-filter-explanation')")
        assert await page.js("document.querySelector('.learning-directory-grid .learning-person-card')?.innerText.includes('Айдана Демо')")
        await page.js("document.querySelector('.learning-directory').scrollIntoView({block:'start'})")
        await shot("name-search-filter-conflict.png")
        assert await page.js("(function(){document.querySelector('.learning-directory-tools button').click();return true})()")
        await page.wait("document.querySelectorAll('.learning-directory-grid .learning-person-card').length === 4")
        await shot("hr-dashboard.png")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        assert await page.js("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        await shot("hr-dashboard-mobile.png")
        await page.call("Emulation.clearDeviceMetricsOverride")
        assert await page.js("(function(){const e=document.querySelectorAll('.learning-filter-row select')[2];if(!e)return false;e.value='overdue';e.dispatchEvent(new Event('change',{bubbles:true}));return true})()")
        await page.wait("document.querySelector('.learning-monitoring')?.querySelectorAll('tbody tr').length === 6")
        assert await page.js("[...document.querySelectorAll('.learning-monitoring tbody tr')].every(r=>r.innerText.includes('Просрочен'))")
        assert await page.js("(function(){const x=document.querySelector('.learning-directory-grid .learning-person-card');if(!x)return false;x.click();return true})()")
        await page.wait("!!document.querySelector('.learning-analytics-profile .learning-kpis')")
        await shot("employee-profile.png")
        assert await page.js("(function(){document.querySelector('.learning-analytics-profile > button').click();return true})()")
        await page.wait("!!document.querySelector('.learning-directory-grid')")
        assert await page.js("document.querySelectorAll('.learning-filter-row select')[2]?.value === 'overdue'")
        assert await page.js("(function(){document.querySelector('[aria-label=\"Выйти из аккаунта\"]').click();return true})()")
        await page.wait("!!document.querySelector('#email')")

        await login("employee@example.com")
        await page.wait("document.querySelectorAll('.academy-my-courses .course-card').length >= 6")
        assert await page.js("(function(){const text=[...document.querySelectorAll('.academy-my-courses .course-card')].map(c=>c.innerText).join(' ');return ['Завершён','В процессе','Не начат','Просрочен'].every(s=>text.includes(s))})()")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        assert await page.js("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        await shot("employee-dashboard-mobile.png")
        await page.call("Emulation.clearDeviceMetricsOverride")
        assert await page.js("document.querySelector('.academy-public-catalog')?.innerText.includes('Общий каталог')")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.academy-filter-tabs button')].find(b=>b.innerText.includes('Просрочены'));x.click();return true})()")
        await page.wait("document.querySelectorAll('.academy-my-courses .course-card').length >= 1")
        assert await page.js("[...document.querySelectorAll('.academy-my-courses .course-card')].every(c=>c.innerText.includes('Просрочен'))")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.academy-filter-tabs button')].find(b=>b.innerText.includes('В процессе'));x.click();return true})()")
        await page.wait("[...document.querySelectorAll('.academy-my-courses .course-card')].some(c=>c.innerText.includes('Продолжить'))")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.academy-my-courses .course-card')].find(c=>c.innerText.includes('Продолжить'));x.querySelector('button').click();return true})()")
        await page.wait("!!document.querySelector('.learning-outline')")
        await shot("employee-course.png")
        assert await page.js("document.querySelector('.course-reader-heading')?.innerText.includes('70%')")
        await page.call("Page.navigate", {"url": web_url})
        await page.wait("!!document.querySelector('#email')")
        await login("employee@example.com")
        await page.wait("document.querySelectorAll('.academy-my-courses .course-card').length >= 6")
        await page.wait("document.querySelector('.academy-rewards')?.innerText.includes('600 XP')")
        assert await page.js("[...document.querySelectorAll('.academy-my-courses .course-card')].some(c=>c.innerText.includes('Заявка на отпуск в прототипе') && c.innerText.includes('70%'))")
        assert await page.js("[...document.querySelectorAll('.academy-my-courses .course-card')].some(c=>c.innerText.includes('Первый день в JanaМен') && c.innerText.includes('100%'))")
        assert await page.js("(function(){const x=[...document.querySelectorAll('#workspace-navigation .nav-item')].find(b=>b.innerText.includes('AI Jana'));if(!x)return false;x.click();return true})()")
        await page.wait("document.querySelector('.assistant-page .assistant-panel-header strong')?.innerText === 'AI Jana'")
        assert await page.js("document.querySelector('.assistant-page .page-heading h1')?.innerText === 'AI Jana'")
        assert await page.js("(function(){const main=document.querySelector('.assistant-page').getBoundingClientRect();const panel=document.querySelector('.assistant-panel').getBoundingClientRect();return Math.abs((panel.left+panel.right)-(main.left+main.right))<3})()")
        await shot("ai-jana-centered-desktop.png")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        assert await page.js("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        await shot("ai-jana-centered-mobile.png")
        await page.call("Emulation.clearDeviceMetricsOverride")
        assert not page.errors, page.errors
        print(json.dumps({"hr_dashboard": True, "name_search_and_filter_conflict": True, "sql_backed_overdue_filter": True, "profile_and_back_filters": True,
            "employee_catalog": True, "employee_status_filters": True, "continue_course": True,
            "progress_and_xp_after_reload": True,
            "mobile_390_no_horizontal_overflow": True, "ai_jana_named_and_centered": True,
            "javascript_errors": page.errors}, ensure_ascii=False))


def main():
    if not CHROME.exists():
        raise SystemExit("Chrome not installed")
    profile = Path(tempfile.mkdtemp(prefix="jana-learning-browser-", dir=tempfile.gettempdir())).resolve()
    process = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run",
        "--remote-debugging-port=0", "--remote-allow-origins=*", "--window-size=1360,900",
        f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        active = profile / "DevToolsActivePort"
        deadline = time.monotonic() + 20
        while not active.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not active.exists():
            raise RuntimeError("Chrome debugging port not available")
        asyncio.run(scenario(int(active.read_text().splitlines()[0]), f"http://127.0.0.1:{env_value('WEB_PORT')}", env_value("DEMO_PASSWORD")))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if profile.parent == temp_root and profile.name.startswith("jana-learning-browser-"):
            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
