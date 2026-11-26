"""A successful save does not hide a subsequent reload failure."""
import subprocess
import sys


def test_save_survives_reload_failure_and_explains_it(tmp_path):
    script = r"""
import json, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from produce.board import BoardServer, BoardStore
root = Path(sys.argv[1]); name='2026-10_ru_v1'
run = root / 'demo' / 'runs' / name; run.mkdir(parents=True)
(run / 'run.json').write_text(json.dumps({'stage':'настроен'},ensure_ascii=False),encoding='utf-8')
(run / 'ideas.json').write_text(json.dumps({'version':1,'ideas':[{'id':'a','title':'Идея','source':'демо','status':''}]},ensure_ascii=False),encoding='utf-8')
store=BoardStore(root); server=BoardServer(store,0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(); page=browser.new_page()
        page.goto('http://127.0.0.1:' + str(server.server_port) + '/',wait_until='networkidle')
        page.get_by_text('Идея',exact=True).wait_for()
        page.route('**/api/channels/demo/runs/2026-10_ru_v1',lambda route: route.fulfill(status=500,content_type='application/json',body=json.dumps({'error':'Данные временно недоступны'})))
        page.get_by_role('button',name='Принять',exact=True).click()
        page.get_by_text('Решение сохранено, но обновить данные не удалось',exact=False).wait_for(timeout=5000)
        assert store.snapshot('demo',name)['ideas'][0]['status'] == 'принят'
        browser.close()
finally:
    server.shutdown(); server.server_close(); thread.join()
"""
    result=subprocess.run([sys.executable,"-c",script,str(tmp_path)],capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode == 0, result.stderr
