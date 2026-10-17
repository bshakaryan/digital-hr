"""Real Chrome check of HR course authoring and employee learning on local Compose."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

from browser_academy_cdp import CDP, CHROME, ROOT, env_value


async def scenario(port: int, web_url: str, password: str) -> None:
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    socket_url = next(target["webSocketDebuggerUrl"] for target in targets if target["type"] == "page")
    async with websockets.connect(socket_url, max_size=4_000_000) as socket:
        page = CDP(socket)
        await page.call("Runtime.enable")
        await page.call("Page.enable")
        title = f"UX проверка · {int(time.time())}"

        async def shot(name: str) -> None:
            image = await page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            directory = ROOT / "frontend" / ".qa" / "academy-redesign"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / name).write_bytes(base64.b64decode(image["data"]))

        async def click(selector: str) -> None:
            assert await page.js(f"(function(){{const el=document.querySelector({json.dumps(selector)});if(!el)return false;el.click();return true}})()"), selector

        async def set_value(selector: str, value: str, element: str = "HTMLInputElement", event_name: str = "input") -> None:
            script = """(function(){const el=document.querySelector(SELECTOR);if(!el)return false;
                Object.getOwnPropertyDescriptor(ELEMENT.prototype,'value').set.call(el,VALUE);
                el.dispatchEvent(new Event(EVENT,{bubbles:true}));return true})()"""
            script = script.replace("SELECTOR", json.dumps(selector)).replace("ELEMENT", element).replace("VALUE", json.dumps(value)).replace("EVENT", json.dumps(event_name))
            assert await page.js(script), selector

        async def login(email: str) -> None:
            await page.call("Page.navigate", {"url": web_url})
            await page.wait("!!document.querySelector('#email')")
            await asyncio.sleep(0.5)
            await set_value("#email", email)
            await set_value("#password", password)
            await click(".login-submit")
            await page.wait("!!document.querySelector('[aria-label=\"Выйти из аккаунта\"]')")

        async def academy() -> None:
            assert await page.js("(function(){const x=[...document.querySelectorAll('#workspace-navigation .nav-item')].find(b=>b.innerText.includes('Jana Academy'));if(!x)return false;x.click();return true})()")
            await page.wait("!!document.querySelector('.academy-banner')")

        async def step(label: str) -> None:
            assert await page.js(f"(function(){{const x=[...document.querySelectorAll('.academy-step')].find(b=>b.innerText.includes({json.dumps(label)}));if(!x)return false;x.click();return true}})()"), label

        async def lesson(label: str) -> None:
            assert await page.js(f"(function(){{const x=[...document.querySelectorAll('.learning-outline-item')].find(b=>b.innerText.includes({json.dumps(label)}));if(!x)return false;x.click();return true}})()"), label

        await login("hr@example.com")
        await academy()
        await page.wait("!!document.querySelector('.academy-admin-heading')")
        await shot("hr-overview.png")
        assert await page.js("!!document.querySelector('header.navigation-bar .nav-item.active')")

        await click(".academy-admin-heading .button")
        await page.wait("!!document.querySelector('section[aria-label=\"Новый курс\"]')")
        await set_value(".academy-admin-content .academy-admin-grid input:nth-of-type(1)", title)
        await set_value(".academy-admin-content .academy-admin-grid input[type=number]", "12")
        await set_value(".academy-admin-content .academy-admin-grid label.academy-admin-wide input", "Учебный курс о подтверждённых событиях отслеживания")
        await set_value(".academy-admin-content .academy-admin-grid textarea", "Отличать подтверждённый статус отправления от предположения", "HTMLTextAreaElement")
        await click(".academy-admin-content .academy-admin-grid button")
        await page.wait(f"document.querySelector('.academy-editor-title h3')?.innerText === {json.dumps(title)}")
        await page.wait("document.querySelector('.academy-step.is-active')?.innerText.includes('Материалы')")

        await page.wait("[...document.querySelectorAll('.academy-step-content select option')].some(o=>o.innerText.includes('OPS-02.docx'))")
        option_id = await page.js("[...document.querySelectorAll('.academy-step-content select option')].find(o=>o.innerText.includes('OPS-02.docx')).value")
        await set_value(".academy-step-content select", option_id, "HTMLSelectElement", "change")
        await click(".academy-step-content form.academy-inline .button")
        await page.wait("document.querySelector('.academy-material-list')?.innerText.includes('OPS-02.docx')")
        await shot("hr-materials.png")

        await step("Тест")
        await set_value(".academy-quiz-editor label input", "Что отражает статус отправления?")
        await set_value(".academy-option-editor:nth-of-type(1) input:not([type=radio])", "Подтверждённое событие")
        await set_value(".academy-option-editor:nth-of-type(2) input:not([type=radio])", "Непроверенное предположение")
        await click(".academy-quiz-editor button.button-secondary")
        await page.wait("document.querySelector('.toast')?.innerText.includes('Тест сохранён')")
        await step("Предпросмотр")
        await page.wait(f"document.querySelector('.academy-preview-card')?.innerText.includes({json.dumps(title)})")
        assert await page.js("document.querySelector('.academy-preview-card').innerText.includes('OPS-02.docx')")
        await shot("hr-preview.png")

        await step("Публикация")
        await page.wait("!!document.querySelector('.academy-step-content > button.button-primary:not(:disabled)')")
        await click(".academy-step-content > button.button-primary")
        await page.wait("!!document.querySelector('.academy-published')")
        await page.wait("document.querySelectorAll('.academy-assignment-person').length >= 2")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.academy-assignment-person')].find(e=>e.innerText.includes('Айдана'));if(!x)return false;x.querySelector('input').click();return true})()")
        await page.wait("document.querySelector('.academy-assignment > button')?.innerText.includes('(1)')")
        await click(".academy-assignment > button")
        await page.wait("document.querySelector('.toast')?.innerText.includes('Назначено: 1')")
        await shot("hr-published.png")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        await asyncio.sleep(0.3)
        assert await page.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
        await page.js("document.querySelector('.academy-step-content').scrollIntoView({block:'start'})")
        await shot("hr-publish-mobile.png")
        await click(".menu-button")
        await page.wait("!!document.querySelector('.workspace-navigation.navigation-open')")
        await shot("hr-mobile-menu.png")
        await click(".mobile-menu-close")
        await page.wait("!document.querySelector('.workspace-navigation.navigation-open')")
        await page.call("Emulation.clearDeviceMetricsOverride")
        await click('[aria-label="Выйти из аккаунта"]')
        await page.wait("!!document.querySelector('#email')")

        await login("employee@example.com")
        await academy()
        await page.wait(f"[...document.querySelectorAll('.course-card')].some(c=>c.innerText.includes({json.dumps(title)}))")
        await page.wait("!!document.querySelector('.academy-rewards strong')")
        xp_before = await page.js("Number(document.querySelector('.academy-rewards strong').innerText.match(/[0-9]+ XP/)[0].split(' ')[0])")
        assert await page.js(f"(function(){{const c=[...document.querySelectorAll('.course-card')].find(x=>x.innerText.includes({json.dumps(title)}));c.querySelector('button').click();return true}})()")
        await page.wait("!!document.querySelector('.learning-outline')")
        await shot("employee-overview.png")
        await lesson("Тест")
        assert await page.js("!!document.querySelector('.learning-locked')")
        await lesson("Материалы")
        await page.wait("document.querySelector('.course-documents')?.innerText.includes('OPS-02.docx')")
        await shot("employee-materials.png")
        download_dir = Path(tempfile.mkdtemp(prefix="jana-course-download-", dir=tempfile.gettempdir())).resolve()
        try:
            await page.call("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(download_dir)})
            await click(".course-documents li button")
            deadline = time.monotonic() + 10
            while not (download_dir / "OPS-02.docx").exists() and time.monotonic() < deadline:
                await asyncio.sleep(0.25)
            assert (download_dir / "OPS-02.docx").stat().st_size > 0
        finally:
            shutil.rmtree(download_dir, ignore_errors=True)
        await lesson("AI Jana")
        await set_value(".course-ai input", "Что отражает статус отправления?")
        await click(".course-ai form button")
        await page.wait("document.querySelector('.course-ai-answer details')?.innerText.includes('OPS-02.docx')")
        await shot("employee-ai.png")
        await lesson("Материалы")
        await click(".material-read")
        await page.wait("!!document.querySelector('.course-test')")
        await click(".course-test .answer-option:first-of-type input")
        await click(".course-test > button")
        await page.wait("!!document.querySelector('.learning-result')")
        await page.wait("document.querySelector('.course-reader-heading progress').value === 100")
        await shot("employee-completed.png")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        await asyncio.sleep(0.3)
        assert await page.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
        await shot("employee-mobile.png")
        await page.call("Emulation.clearDeviceMetricsOverride")

        await login("employee@example.com")  # Refresh: token is kept only in memory.
        await academy()
        await page.wait(f"[...document.querySelectorAll('.course-card')].some(c=>c.innerText.includes({json.dumps(title)}))")
        await page.wait("!!document.querySelector('.academy-rewards strong')")
        progress_after = await page.js(f"[...document.querySelectorAll('.course-card')].find(c=>c.innerText.includes({json.dumps(title)})).querySelector('progress').value")
        xp_after = await page.js("Number(document.querySelector('.academy-rewards strong').innerText.match(/[0-9]+ XP/)[0].split(' ')[0])")
        assert progress_after == 100 and xp_after == xp_before + 100, (progress_after, xp_before, xp_after)
        assert not page.errors, page.errors
        print(json.dumps({"course": title, "hr_created_published_assigned": True, "employee_citation": "OPS-02.docx",
                          "quiz_locked_before_material": True, "progress_after_refresh": progress_after,
                          "xp_before": xp_before, "xp_after": xp_after, "top_navigation": True,
                          "mobile_horizontal_overflow": False, "javascript_errors": page.errors}, ensure_ascii=False))


async def form_scenario(port: int, web_url: str, password: str) -> None:
    """Check the restored top navigation and new-course form without creating data."""
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    socket_url = next(target["webSocketDebuggerUrl"] for target in targets if target["type"] == "page")
    async with websockets.connect(socket_url, max_size=4_000_000) as socket:
        page = CDP(socket)
        await page.call("Runtime.enable")
        await page.call("Page.enable")
        await page.call("Page.navigate", {"url": web_url})
        await page.wait("!!document.querySelector('#email')")
        await asyncio.sleep(0.5)
        login_script = """(function(){const set=(selector,value)=>{const el=document.querySelector(selector);
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);
            el.dispatchEvent(new Event('input',{bubbles:true}));};
            set('#email',EMAIL);set('#password',PASSWORD);document.querySelector('.login-submit').click();return true})()"""
        assert await page.js(login_script.replace("EMAIL", json.dumps("hr@example.com")).replace("PASSWORD", json.dumps(password)))
        await page.wait("!!document.querySelector('[aria-label=\"Выйти из аккаунта\"]')")
        assert await page.js("!!document.querySelector('header.navigation-bar #workspace-navigation')")
        assert await page.js("(function(){const x=[...document.querySelectorAll('#workspace-navigation .nav-item')].find(b=>b.innerText.includes('Jana Academy'));if(!x)return false;x.click();return true})()")
        await page.wait("!!document.querySelector('.academy-admin-heading')")
        assert await page.js("(function(){document.querySelector('.academy-admin-heading .button').click();return true})()")
        await page.wait("!!document.querySelector('section[aria-label=\"Новый курс\"]')")
        async def check_form(width: int, filename: str) -> None:
            if width != 1280:
                await page.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False})
                await asyncio.sleep(0.3)
            result = await page.js("""(function(){const card=document.querySelector('.academy-admin-content');
                const form=document.querySelector('section[aria-label="Новый курс"] form');
                const inputs=[...form.querySelectorAll('input,textarea,button')];
                const c=card.getBoundingClientRect();const f=form.getBoundingClientRect();
                return {pageOverflow:document.documentElement.scrollWidth>innerWidth+1,
                    formInside:f.left>=c.left+12&&f.right<=c.right-12,
                    fieldsInside:inputs.every(el=>{const r=el.getBoundingClientRect();return r.left>=c.left+12&&r.right<=c.right-12}),
                    topNavigation:!!document.querySelector('header.navigation-bar')};})()""")
            assert all((result["formInside"], result["fieldsInside"], result["topNavigation"])) and not result["pageOverflow"], result
            await page.js("document.querySelector('section[aria-label=\"Новый курс\"]').scrollIntoView({block:'start'})")
            await asyncio.sleep(0.1)
            image = await page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            directory = ROOT / "frontend" / ".qa" / "academy-redesign"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / filename).write_bytes(base64.b64decode(image["data"]))
        await check_form(1280, "hr-new-course-top-nav.png")
        await check_form(390, "hr-new-course-mobile-top-nav.png")
        await page.call("Emulation.clearDeviceMetricsOverride")
        await page.wait("!!document.querySelector('.academy-admin-item')")
        assert await page.js("(function(){document.querySelector('.academy-admin-item').click();return true})()")
        await page.wait("!!document.querySelector('.academy-stepper')")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.academy-step')].find(b=>b.innerText.includes('Материалы'));if(!x)return false;x.click();return true})()")
        await page.wait("!!document.querySelector('.academy-document-trigger:not(:disabled)')")
        assert await page.js("(function(){document.querySelector('.academy-document-trigger').click();return true})()")
        await page.wait("document.activeElement?.classList.contains('academy-document-options')")
        assert await page.js("document.querySelectorAll('.academy-document-option').length > 0")
        await page.js("document.querySelector('.academy-document-trigger').scrollIntoView({block:'center'})")
        image = await page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        directory = ROOT / "frontend" / ".qa" / "academy-redesign"
        (directory / "hr-document-picker-desktop.png").write_bytes(base64.b64decode(image["data"]))
        previous = await page.js("document.querySelector('.academy-document-options').getAttribute('aria-activedescendant')")
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40})
        assert await page.js("document.querySelector('.academy-document-options').getAttribute('aria-activedescendant')") != previous
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
        await page.wait("!document.querySelector('.academy-document-options')")
        assert await page.js("!!document.querySelector('.academy-inline > button.button-secondary:not(:disabled)')")
        assert await page.js("(function(){document.querySelector('.academy-document-trigger').click();return true})()")
        await page.wait("!!document.querySelector('.academy-document-options')")
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        await page.wait("!document.querySelector('.academy-document-options')")
        assert await page.js("document.activeElement?.classList.contains('academy-document-trigger')")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        await page.js("document.querySelector('.academy-document-trigger').scrollIntoView({block:'start'})")
        assert await page.js("(function(){document.querySelector('.academy-document-trigger').click();return true})()")
        await page.wait("!!document.querySelector('.academy-document-options')")
        await asyncio.sleep(0.1)
        assert await page.js("document.documentElement.scrollWidth <= innerWidth + 1")
        image = await page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        directory = ROOT / "frontend" / ".qa" / "academy-redesign"
        (directory / "hr-document-picker-mobile.png").write_bytes(base64.b64decode(image["data"]))
        await page.call("Emulation.clearDeviceMetricsOverride")
        assert await page.js("(function(){const button=document.querySelector('.academy-step-actions .button');if(!button||button.disabled)return false;button.click();return true})()")
        await page.wait("document.querySelector('.academy-step.is-active')?.innerText.includes('Тест')")
        assert await page.js("!!document.querySelector('.academy-quiz-editor')")
        assert not page.errors, page.errors
        print(json.dumps({"top_navigation_restored": True, "new_course_form_contained": True,
                          "document_picker_keyboard_selection": True, "document_picker_escape": True,
                          "materials_next_to_quiz": True, "mobile_horizontal_overflow": False,
                          "javascript_errors": page.errors}))


async def pdf_scenario(port: int, web_url: str, password: str) -> None:
    """Read-only check that the redesigned material action opens an authorized PDF."""
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    socket_url = next(target["webSocketDebuggerUrl"] for target in targets if target["type"] == "page")
    async with websockets.connect(socket_url, max_size=4_000_000) as socket:
        page = CDP(socket)
        await page.call("Runtime.enable")
        await page.call("Page.enable")
        await page.call("Page.navigate", {"url": web_url})
        await page.wait("!!document.querySelector('#email')")
        await asyncio.sleep(0.5)
        login_script = """(function(){const set=(selector,value)=>{const el=document.querySelector(selector);
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);
            el.dispatchEvent(new Event('input',{bubbles:true}));};
            set('#email',EMAIL);set('#password',PASSWORD);document.querySelector('.login-submit').click();return true})()"""
        assert await page.js(login_script.replace("EMAIL", json.dumps("employee@example.com")).replace("PASSWORD", json.dumps(password)))
        await page.wait("!!document.querySelector('[aria-label=\"Выйти из аккаунта\"]')")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        assert await page.js("(function(){document.querySelector('.menu-button').click();return true})()")
        await page.wait("!!document.querySelector('.workspace-navigation.navigation-open')")
        assert await page.js("(function(){document.querySelector('.mobile-menu-close').click();return true})()")
        await page.wait("!document.querySelector('.workspace-navigation.navigation-open')")
        await page.call("Emulation.clearDeviceMetricsOverride")
        assert await page.js("(function(){const x=[...document.querySelectorAll('#workspace-navigation .nav-item')].find(b=>b.innerText.includes('Jana Academy'));if(!x)return false;x.click();return true})()")
        await page.wait("[...document.querySelectorAll('.course-card')].some(c=>c.innerText.includes('Знакомство с JanaМен'))")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.course-card')].find(c=>c.innerText.includes('Знакомство с JanaМен'));x.querySelector('button').click();return true})()")
        await page.wait("!!document.querySelector('.learning-outline')")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.learning-outline-item')].find(b=>b.innerText.includes('Материалы'));x.click();return true})()")
        await page.wait("[...document.querySelectorAll('.course-documents button')].some(b=>b.innerText.includes('Открыть PDF'))")
        point = await page.js("(function(){const el=[...document.querySelectorAll('.course-documents button')].find(b=>b.innerText.includes('Открыть PDF'));el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
        await page.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1})
        await page.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(1)
        targets = (await page.call("Target.getTargets"))["targetInfos"]
        assert any(info.get("url", "").startswith("blob:") for info in targets)
        assert not page.errors, page.errors
        print(json.dumps({"authorized_pdf_opened": True, "mobile_menu_opened_and_closed": True, "javascript_errors": page.errors}))


def main() -> None:
    if not CHROME.exists():
        raise SystemExit("Chrome not installed")
    profile = Path(tempfile.mkdtemp(prefix="jana-ux-browser-", dir=tempfile.gettempdir())).resolve()
    process = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run",
        "--remote-debugging-port=0", "--remote-allow-origins=*", "--window-size=1280,900",
        f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        active = profile / "DevToolsActivePort"
        deadline = time.monotonic() + 20
        while not active.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not active.exists():
            raise RuntimeError("Chrome debugging port not available")
        port = int(active.read_text().splitlines()[0])
        check = form_scenario if "--form-only" in sys.argv else pdf_scenario if "--pdf-only" in sys.argv else scenario
        asyncio.run(check(port, f"http://127.0.0.1:{env_value('WEB_PORT')}", env_value("DEMO_PASSWORD")))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if profile.parent == temp_root and profile.name.startswith("jana-ux-browser-"):
            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
