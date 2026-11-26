"""Поведение хранилища локальной доски на временных данных."""
import json

import pytest

from produce.board import BoardStore, valid_request


def setup_run(tmp_path):
    root = tmp_path / "channels"
    run = root / "first" / "runs" / "2026-10_ru_v1"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"stage": "брифы на решение", "version": 1}), encoding="utf-8")
    (run / "ideas.json").write_text(json.dumps({"version": 1, "ideas": [{"id": "idea-1", "title": "Идея", "source": "Анализ", "status": ""}]}, ensure_ascii=False), encoding="utf-8")
    (run / "briefs").mkdir()
    (run / "briefs" / "01.md").write_text("# Бриф 1: Видео\n\n- Статус:\n\n## Сценарий\nТекст\n", encoding="utf-8")
    return root, run


def test_snapshot_and_decision_persist(tmp_path):
    root, path = setup_run(tmp_path)
    store = BoardStore(root)
    assert store.channels() == ["first"]
    data = store.snapshot("first", "2026-10_ru_v1")
    assert data["stage"] == "брифы на решение"
    assert data["ideas"][0]["title"] == "Идея"
    store.decide("first", "2026-10_ru_v1", "idea", "idea-1", "принят", data["ideas_revision"])
    assert BoardStore(root).snapshot("first", "2026-10_ru_v1")["ideas"][0]["status"] == "принят"
    assert (path / "briefs" / "01.md").read_text(encoding="utf-8").endswith("Текст\n")


def test_stale_brief_and_invalid_path_are_rejected(tmp_path):
    root, path = setup_run(tmp_path)
    store = BoardStore(root)
    data = store.snapshot("first", "2026-10_ru_v1")
    file = path / "briefs" / "01.md"
    file.write_text(file.read_text(encoding="utf-8") + "Правка агента\n", encoding="utf-8")
    with pytest.raises(ValueError, match="измен"):
        store.decide("first", "2026-10_ru_v1", "brief", "01", "принят", data["briefs"][0]["revision"])
    assert "Правка агента" in file.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        store.snapshot("../outside", "2026-10_ru_v1")


def test_malformed_extra_status_refuses_changes(tmp_path):
    root, path = setup_run(tmp_path)
    target = path / "briefs" / "01.md"
    content = target.read_text(encoding="utf-8").replace("- Статус:\n", "- Статус:\n- Статус: ошибочный\n")
    target.write_text(content, encoding="utf-8")
    store = BoardStore(root)
    data = store.snapshot("first", "2026-10_ru_v1")
    with pytest.raises(ValueError, match="Статус"):
        store.decide("first", "2026-10_ru_v1", "brief", "01", "принят", data["briefs"][0]["revision"])
    assert target.read_text(encoding="utf-8") == content


def test_local_request_rejects_cross_origin_wrong_host_and_invalid_tokens():
    assert valid_request("127.0.0.1:8765", "http://127.0.0.1:8765", 8765, True, "token", "token")
    assert not valid_request("attacker.example:8765", "http://attacker.example:8765", 8765, False, None, "token")
    assert not valid_request("127.0.0.1:8765", "https://attacker.example", 8765, True, "token", "token")
    assert not valid_request("127.0.0.1:8765", None, 8765, True, "token", "token")
    assert not valid_request("127.0.0.1:8765", "http://127.0.0.1:8765", 8765, True, "токен", "token")


def test_video_data_and_corrupt_niche_are_isolated(tmp_path):
    root, path = setup_run(tmp_path)
    (path / "virals.json").write_text(json.dumps({"virals": [{"title": "Видео"}]}, ensure_ascii=False), encoding="utf-8")
    (path / "niche.md").write_bytes(b"\xff")
    data = BoardStore(root).snapshot("first", "2026-10_ru_v1")
    assert data["video_data"]["virals"]["virals"][0]["title"] == "Видео"
    assert data["ideas"][0]["title"] == "Идея"
    assert any("niche.md" in x for x in data["warnings"])


def test_linked_brief_directory_is_rejected_without_breaking_other_sections(tmp_path):
    root, path = setup_run(tmp_path)
    original = path / "briefs"
    original.rename(path / "briefs-old")
    original.symlink_to(tmp_path, target_is_directory=True)
    data = BoardStore(root).snapshot("first", "2026-10_ru_v1")
    assert data["briefs"] == []
    assert data["ideas"][0]["title"] == "Идея"
    assert "Список брифов недоступен" in data["warnings"]


def test_brief_and_strategy_decisions_preserve_other_text(tmp_path):
    root, path = setup_run(tmp_path)
    (path / "strategy.md").write_text("# Стратегия\n\nСтатус: черновик\n\nАвторский текст\n", encoding="utf-8")
    store = BoardStore(root)
    before = store.snapshot("first", "2026-10_ru_v1")
    store.decide("first", "2026-10_ru_v1", "brief", "01", "позже", before["briefs"][0]["revision"])
    store.decide("first", "2026-10_ru_v1", "strategy", "strategy", "утверждена", before["documents"]["strategy"]["revision"])
    after = store.snapshot("first", "2026-10_ru_v1")
    assert after["briefs"][0]["status"] == "позже"
    assert after["briefs"][0]["content"].endswith("## Сценарий\nТекст\n")
    assert after["documents"]["strategy"]["status"] == "утверждена"
    assert after["documents"]["strategy"]["content"].endswith("Авторский текст\n")


def test_agent_proposals_preserve_decisions_and_detect_stale_write(tmp_path):
    root, _path = setup_run(tmp_path)
    store = BoardStore(root)
    before = store.snapshot("first", "2026-10_ru_v1")
    first = dict(before["ideas"][0])
    new = {"id": "idea-2", "title": "Другая", "source": "Ниша", "status": ""}
    store.decide("first", "2026-10_ru_v1", "idea", "idea-1", "принят", before["ideas_revision"])
    with pytest.raises(ValueError, match="измен"):
        store.save_ideas("first", "2026-10_ru_v1", [first, new], before["ideas_revision"])
    current = store.snapshot("first", "2026-10_ru_v1")
    with pytest.raises(ValueError):
        store.save_ideas("first", "2026-10_ru_v1", [first, new], current["ideas_revision"])
    store.save_ideas("first", "2026-10_ru_v1", [current["ideas"][0], new], current["ideas_revision"])
    assert [item["status"] for item in store.snapshot("first", "2026-10_ru_v1")["ideas"]] == ["принят", ""]


def test_two_channels_remain_isolated(tmp_path):
    root, first = setup_run(tmp_path)
    second = root / "second" / "runs" / "2026-10_ru_v1"
    second.mkdir(parents=True)
    (second / "run.json").write_text(json.dumps({"stage": "настроен"}), encoding="utf-8")
    (second / "ideas.json").write_text(json.dumps({"version": 1, "ideas": [{"id": "other", "title": "Other", "source": "demo", "status": ""}]}), encoding="utf-8")
    store = BoardStore(root)
    data = store.snapshot("first", "2026-10_ru_v1")
    store.decide("first", "2026-10_ru_v1", "idea", "idea-1", "принят", data["ideas_revision"])
    assert store.channels() == ["first", "second"]
    assert store.snapshot("second", "2026-10_ru_v1")["ideas"][0]["status"] == ""
    assert first.joinpath("ideas.json").is_file()


def test_quoted_duplicate_strategy_status_is_not_approved(tmp_path):
    root, path = setup_run(tmp_path)
    target = path / "strategy.md"
    content = "# Стратегия\nСтатус: черновик\n> Статус: утверждена\n"
    target.write_text(content, encoding="utf-8")
    store = BoardStore(root)
    strategy = store.snapshot("first", "2026-10_ru_v1")["documents"]["strategy"]
    assert strategy["status"] is None
    with pytest.raises(ValueError, match="Статус"):
        store.decide("first", "2026-10_ru_v1", "strategy", "strategy", "утверждена", strategy["revision"])
    assert target.read_text(encoding="utf-8") == content


def test_numeric_brief_filenames_keep_distinct_ids_and_can_be_decided(tmp_path):
    root, path = setup_run(tmp_path)
    folder = path / "briefs"
    (folder / "1.md").write_text("# Бриф: Первый\n- Статус:\n", encoding="utf-8")
    (folder / "1234567.md").write_text("# Бриф: Длинный номер\n- Статус:\n", encoding="utf-8")
    store = BoardStore(root)
    briefs = {item["id"]: item for item in store.snapshot("first", "2026-10_ru_v1")["briefs"]}
    assert set(briefs) == {"1", "01", "1234567"}
    store.decide("first", "2026-10_ru_v1", "brief", "1", "принят", briefs["1"]["revision"])
    after = {item["id"]: item for item in store.snapshot("first", "2026-10_ru_v1")["briefs"]}
    assert after["1"]["status"] == "принят"
    assert after["01"]["status"] == ""


def test_strategy_crlf_keeps_line_endings_and_really_approves(tmp_path):
    root, path = setup_run(tmp_path)
    target = path / "strategy.md"
    target.write_bytes("# Стратегия\r\nСтатус: черновик\r\nТекст\r\n".encode())
    store = BoardStore(root)
    before = store.snapshot("first", "2026-10_ru_v1")["documents"]["strategy"]
    store.decide("first", "2026-10_ru_v1", "strategy", "strategy", "утверждена", before["revision"])
    assert target.read_bytes() == "# Стратегия\r\nСтатус: утверждена\r\nТекст\r\n".encode()
