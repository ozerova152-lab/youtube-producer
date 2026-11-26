"""User-facing local board, driven through a real browser and sample files."""

import subprocess
import sys


def test_board_workspace_user_journey(tmp_path):
    script = r"""
import json, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from produce.board import BoardServer, BoardStore
root = Path(sys.argv[1])
run = root / 'demo' / 'runs' / '2026-10_ru_v1'
(run / 'briefs').mkdir(parents=True)
other = root / 'another' / 'runs' / '2026-11_en_v2'
other.mkdir(parents=True)
(other / 'run.json').write_text(json.dumps({'stage':'настроен'},ensure_ascii=False),encoding='utf-8')
(run / 'run.json').write_text(json.dumps({'stage':'брифы на решение'},ensure_ascii=False),encoding='utf-8')
(run / 'ideas.json').write_text(json.dumps({'version':1,'ideas':[{'id':'a1','title':'Новая идея <img src=x onerror=alert(1)>','source':'На основе анализа','status':''}]},ensure_ascii=False),encoding='utf-8')
(run / 'niche.md').write_text('# Ниша\nТестовая ниша', encoding='utf-8')
(run / 'strategy.md').write_text('# Стратегия\nСтатус: черновик\nДетали', encoding='utf-8')
(run / 'candidates.md').write_text('# Конкуренты\nТестовый конкурент', encoding='utf-8')
(run / 'report.md').write_text('# Аналитика\nРезультаты теста', encoding='utf-8')
(run / 'plan.md').write_text('# План\n## Неделя 1\nТема теста', encoding='utf-8')
(run / 'briefs' / '01.md').write_text('# Мой ролик\n- Статус: \nТекст сценария', encoding='utf-8')
server = BoardServer(BoardStore(root), 0)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1366,'height':900})
        page.goto('http://127.0.0.1:' + str(server.server_port) + '/', wait_until='networkidle')
        page.get_by_label('Канал', exact=True).select_option('demo')
        page.get_by_label('Запуск', exact=True).select_option('2026-10_ru_v1')
        page.get_by_test_id('agent-prompt').wait_for(timeout=5000)
        assert 'продолжи месяц с доской' in page.get_by_test_id('agent-prompt').inner_text().lower()
        assert 'demo' in page.get_by_test_id('agent-prompt').inner_text()
        assert '2026-10_ru_v1' in page.get_by_test_id('agent-prompt').inner_text()
        page.get_by_role('button',name='Идеи',exact=True).click()
        assert page.get_by_text('Новая идея <img src=x onerror=alert(1)>',exact=True).count() == 1
        assert page.locator('img').count() == 0
        page.get_by_role('button',name='Принять',exact=True).first.click()
        page.get_by_text('Принято',exact=True).first.wait_for(state='visible')
        port = server.server_port
        server.shutdown(); server.server_close(); thread.join()
        server = BoardServer(BoardStore(root), port)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        page.reload(wait_until='networkidle')
        page.get_by_role('button',name='Идеи',exact=True).click()
        page.get_by_text('Принято',exact=True).first.wait_for(state='visible')
        for label, text in [('Конкуренты','Тестовый конкурент'),('Ниша','Тестовая ниша'),('Аналитика ниши','Результаты теста'),('Контент-план','Тема теста'),('Видео','Мой ролик')]:
            page.get_by_role('button',name=label,exact=True).click()
            assert page.get_by_text(text,exact=False).count() >= 1
        page.get_by_role('button',name='Ниша',exact=True).click()
        page.get_by_role('button',name='Утвердить',exact=True).click()
        page.get_by_text('Утверждена',exact=True).first.wait_for(state='visible')
        page.get_by_role('button',name='Видео',exact=True).click()
        page.get_by_role('button',name='Принять',exact=True).first.click()
        page.get_by_text('Принято',exact=True).first.wait_for(state='visible')
        page.get_by_label('Канал',exact=True).select_option('another')
        page.get_by_text('настроен',exact=True).wait_for()
        assert 'another' in page.get_by_test_id('agent-prompt').inner_text()
        assert '2026-11_en_v2' in page.get_by_test_id('agent-prompt').inner_text()
        page.set_viewport_size({'width':375,'height':850})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert page.get_by_text('продолжи месяц',exact=False).count() >= 1
        browser.close()
finally:
    server.shutdown(); server.server_close(); thread.join()
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr
