"""Conflicting edits are shown instead of silently overwriting decisions."""

import subprocess
import sys


def test_concurrent_decision_is_not_overwritten(tmp_path):
    script = r"""
import json, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from produce.board import BoardServer, BoardStore
root = Path(sys.argv[1]); name='2026-10_ru_v1'
run = root / 'demo' / 'runs' / name
run.mkdir(parents=True)
(run / 'run.json').write_text(json.dumps({'stage':'настроен'},ensure_ascii=False),encoding='utf-8')
(run / 'ideas.json').write_text(json.dumps({'version':1,'ideas':[{'id':'a','title':'Идея','source':'демо','status':''}]},ensure_ascii=False),encoding='utf-8')
store=BoardStore(root); server=BoardServer(store,0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':375,'height':850})
        page.goto('http://127.0.0.1:' + str(server.server_port) + '/',wait_until='networkidle')
        page.get_by_text('Идея', exact=True).wait_for()
        for label in ['Идеи','Конкуренты','Ниша','Аналитика ниши','Контент-план','Видео']:
            assert page.get_by_role('button',name=label,exact=True).is_visible()
        revision=store.snapshot('demo',name)['ideas_revision']
        store.decide('demo',name,'idea','a','отклонён',revision)
        page.get_by_role('button',name='Принять',exact=True).click()
        page.get_by_text('Файл изменился.',exact=False).wait_for()
        assert store.snapshot('demo',name)['ideas'][0]['status'] == 'отклонён'
        page.get_by_role('button',name='Обновить данные').click()
        page.get_by_text('Отклонено',exact=True).wait_for()
        browser.close()
finally:
    server.shutdown(); server.server_close(); thread.join()
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr
