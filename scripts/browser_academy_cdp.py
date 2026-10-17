"""Headless Chrome smoke of the live HR and employee Academy screens via CDP."""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[1]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def env_value(key):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.partition("=")[2].strip()
    raise RuntimeError(f"Missing {key}")


class CDP:
    def __init__(self, socket):
        self.socket = socket
        self.number = 0
        self.errors = []

    async def call(self, method, params=None):
        self.number += 1
        number = self.number
        await self.socket.send(json.dumps({"id": number, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("method") == "Runtime.exceptionThrown":
                self.errors.append(message.get("params", {}).get("exceptionDetails", {}).get("text", "JavaScript error"))
            if message.get("id") == number:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    async def js(self, expression):
        result = await self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"]["text"])
        return result.get("result", {}).get("value")

    async def wait(self, expression, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if await self.js(expression):
                return
            await asyncio.sleep(0.25)
        raise AssertionError(f"Browser condition not met: {expression}")


async def scenario(port, web_url, password):
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    socket_url = next(target["webSocketDebuggerUrl"] for target in targets if target["type"] == "page")
    async with websockets.connect(socket_url, max_size=4_000_000) as socket:
        page = CDP(socket)
        await page.call("Runtime.enable")
        await page.call("Page.enable")

        async def screenshot(name):
            image = await page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            directory = ROOT / "frontend" / ".qa" / "academy-authoring"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / name).write_bytes(base64.b64decode(image["data"]))

        async def type_duration(selector):
            assert await page.js(f"(function(){{const el=document.querySelector({json.dumps(selector)});el.focus();return !!el}})()")
            await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
            await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
            await page.wait(f"document.querySelector({json.dumps(selector)}).value === ''")
            await page.call("Input.insertText", {"text": "50"})
            await page.wait(f"document.querySelector({json.dumps(selector)}).value === '50'")

        async def navigate():
            await page.call("Page.navigate", {"url": web_url})
            await page.wait("!!document.querySelector('#email')")

        async def login(email):
            await navigate()
            await asyncio.sleep(1)
            script = """(function(){
              const set=(selector,value)=>{const el=document.querySelector(selector);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));};
              set('#email',EMAIL);set('#password',PASSWORD);document.querySelector('.login-submit').click();return true;
            })()""".replace("EMAIL", json.dumps(email)).replace("PASSWORD", json.dumps(password))
            assert await page.js(script)
            try:
                await page.wait("!!document.querySelector('[aria-label=\"Выйти из аккаунта\"]')")
            except AssertionError:
                raise AssertionError("Login did not complete: " + str(await page.js("document.body.innerText.slice(0,500)")))

        async def academy():
            assert await page.js("(function(){const x=[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('Jana Academy')); if(!x)return false; x.click(); return true})()")
            await page.wait("document.body.innerText.includes('Ваш следующий шаг')")

        await login("hr@example.com")
        await academy()
        await page.wait("document.body.innerText.includes('Управление курсами')")
        assert await page.js("document.body.innerText.includes('Создать черновик') && document.body.innerText.includes('Каталог курсов')")
        await page.wait("document.body.innerText.includes('Демо · статусы отправлений')")
        await type_duration(".academy-admin > form input[type=number]")
        await screenshot("hr.png")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.academy-admin-item')].find(b=>b.textContent.includes('Демо · статусы отправлений'));x.click();return true})()")
        await page.wait("!!document.querySelector('.academy-editor')")
        await type_duration(".academy-editor input[type=number]")
        await page.wait("document.querySelectorAll('.academy-assignment-person input[type=checkbox]').length >= 2")
        assert await page.js("(function(){const boxes=[...document.querySelectorAll('.academy-assignment-person input[type=checkbox]')];boxes[0].click();boxes[1].click();return true})()")
        await page.wait("document.querySelector('.academy-assignment > button').innerText.includes('(2)')")
        await page.js("document.querySelector('.academy-editor').scrollIntoView({block:'start'})")
        await screenshot("hr-editor.png")
        await page.js("document.querySelector('.academy-assignment').scrollIntoView({block:'center'})")
        await screenshot("hr-assignment.png")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        await asyncio.sleep(0.5)
        assert await page.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
        await page.js("document.querySelector('.academy-assignment').scrollIntoView({block:'center'})")
        await screenshot("hr-assignment-mobile.png")
        await page.call("Emulation.clearDeviceMetricsOverride")
        assert await page.js("(function(){document.querySelector('.academy-assignment > button').click();return true})()")
        await page.wait("document.querySelector('.toast')?.innerText.includes('Назначено:')")
        await page.wait("document.querySelector('.academy-assignment > button').innerText.includes('(0)')")
        assert await page.js("!document.querySelector('.academy-editor .error-box')")
        root = (await page.call("DOM.getDocument"))["root"]["nodeId"]
        file_input = (await page.call("DOM.querySelector", {"nodeId": root, "selector": "#knowledge-document-file"}))["nodeId"]
        assert file_input
        await page.call("DOM.setFileInputFiles", {"nodeId": file_input, "files": [str(ROOT / "knowledge_base_docs" / "LOG-01.pdf")]})
        await page.wait("document.querySelector('.knowledge-file-name').innerText.includes('LOG-01.pdf')")
        assert await page.js("document.querySelector('label[for=knowledge-document-file]').innerText === 'Выбрать файл'")
        await page.js("document.querySelector('.knowledge-admin').scrollIntoView({block:'start'})")
        await screenshot("hr-file-picker.png")
        await page.js("document.querySelector('[aria-label=\"Выйти из аккаунта\"]').click()")
        await page.wait("!!document.querySelector('#email')")

        await login("manager@example.com")
        await academy()
        await page.wait("[...document.querySelectorAll('.course-card')].some(c=>c.innerText.includes('Демо · статусы отправлений'))")
        await page.js("document.querySelector('[aria-label=\"Выйти из аккаунта\"]').click()")
        await page.wait("!!document.querySelector('#email')")

        await login("employee@example.com")
        await academy()
        await page.wait("[...document.querySelectorAll('.course-card')].some(c=>c.innerText.includes('Демо · статусы отправлений'))")
        assert await page.js("(function(){const card=[...document.querySelectorAll('.course-card')].find(c=>c.innerText.includes('Демо · статусы отправлений')); card.querySelector('button').click(); return true})()")
        await page.wait("!!document.querySelector('.course-documents') && document.body.innerText.includes('OPS-02.docx')")
        assert await page.js("!!document.querySelector('.course-objectives') && !!document.querySelector('.course-success')")
        assert await page.js("document.querySelector('.course-reader-heading progress').value === 100")
        await screenshot("employee.png")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.course-ai button')].find(b=>b.textContent.includes('Спросить AI Jana'));x.click();return true})()")
        assert await page.js("(function(){const el=document.querySelector('.course-ai input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'Что отражает статус отправления?');el.dispatchEvent(new Event('input',{bubbles:true}));return true})()")
        assert await page.js("(function(){const x=[...document.querySelectorAll('.course-ai form button')].find(b=>b.textContent.includes('Спросить'));x.click();return true})()")
        await page.wait("!!document.querySelector('.course-ai-answer details')")
        assert await page.js("document.querySelector('.course-ai-answer').innerText.includes('OPS-02.docx')")

        assert await page.js("(function(){document.querySelector('.course-back').click();const card=[...document.querySelectorAll('.course-card')].find(c=>c.innerText.includes('Знакомство с JanaМен'));card.querySelector('button').click();return true})()")
        await page.wait("[...document.querySelectorAll('.course-documents button')].some(b=>b.textContent.includes('Открыть PDF'))")
        point = await page.js("(function(){const el=[...document.querySelectorAll('.course-documents button')].find(b=>b.textContent.includes('Открыть PDF'));el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
        await page.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1})
        await page.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(1)
        targets = (await page.call("Target.getTargets"))["targetInfos"]
        pdf_opened = any(info.get("url", "").startswith("blob:") for info in targets)
        assert pdf_opened, [(info.get("type"), info.get("url", "")[:70]) for info in targets]

        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        await asyncio.sleep(0.5)
        assert await page.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
        await screenshot("mobile.png")
        await page.call("Emulation.clearDeviceMetricsOverride")

        await navigate()  # Token is memory-only; sign in again after refresh.
        await login("employee@example.com")
        await academy()
        await page.wait("[...document.querySelectorAll('.course-card')].some(c=>c.innerText.includes('Демо · статусы отправлений'))")
        assert await page.js("[...document.querySelectorAll('.course-card')].find(c=>c.innerText.includes('Демо · статусы отправлений')).querySelector('progress').value === 100")
        assert not page.errors, page.errors
        print(json.dumps({"hr_course_management_visible": True, "employee_material_visible": True,
            "duration_keyboard_entry": 50, "multiple_course_assignments": 2, "manager_course_visible_after_login": True,
            "styled_file_picker": True,
            "pdf_opened_in_browser": pdf_opened, "mobile_horizontal_overflow": False,
            "ai_citation_visible": True, "progress_after_refresh": 100, "javascript_errors": page.errors}, ensure_ascii=False))


def main():
    if not CHROME.exists():
        raise SystemExit("Chrome not installed")
    profile = Path(tempfile.mkdtemp(prefix="jana-browser-", dir=tempfile.gettempdir())).resolve()
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
        asyncio.run(scenario(port, f"http://127.0.0.1:{env_value('WEB_PORT')}", env_value("DEMO_PASSWORD")))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if profile.parent == temp_root and profile.name.startswith("jana-browser-"):
            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
