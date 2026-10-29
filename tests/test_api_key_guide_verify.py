"""T20 (независимая проверка): инструкция по ключу YouTube Data API, по критериям приёмки.

Тесты только читают README и docs, без сети; `.env` и `.env.*` не открываются.
"""

import re
from pathlib import Path

from produce.core import virals

ROOT = Path(__file__).parent.parent
GUIDE_PATH = ROOT / "docs" / "api-key-guide.md"
GUIDE = GUIDE_PATH.read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _idx(text: str, needle: str) -> int:
    i = text.find(needle)
    assert i >= 0, f"нет в тексте: {needle}"
    return i


def _section(text: str, title_start: str) -> str:
    m = re.search(rf"^## {re.escape(title_start)}.*?(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет раздела {title_start}"
    return m.group(0)


def _code_lines(text: str) -> list[str]:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            out.append(line)
    return out


# --- критерий 1: шаги по порядку ---

def test_steps_present_in_order():
    order = [
        "## Шаг 1", "## Шаг 2", "## Шаг 3", "## Шаг 4", "## Шаг 5",
    ]
    pos = [_idx(GUIDE, h) for h in order]
    assert pos == sorted(pos)
    step1 = _section(GUIDE, "Шаг 1")
    assert "New project" in step1
    step2 = _section(GUIDE, "Шаг 2")
    assert "YouTube Data API v3" in step2 and "Enable" in step2
    step3 = _section(GUIDE, "Шаг 3")
    assert "Create credentials" in step3 and "API key" in step3
    step4 = _section(GUIDE, "Шаг 4")
    assert "Restrict key" in step4 and "Application restrictions" in step4
    step5 = _section(GUIDE, "Шаг 5")
    assert ".env" in step5


def test_readme_links_to_existing_guide_and_all_relative_links_resolve():
    assert "(docs/api-key-guide.md)" in README
    assert GUIDE_PATH.exists()
    for text, base in ((README, ROOT), (GUIDE, GUIDE_PATH.parent)):
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            assert (base / target).exists(), f"битая ссылка: {target}"


# --- критерий 2: подводные камни ---

def test_pitfalls_block_has_all_four_warnings():
    block = _section(GUIDE, "Главные подводные камни").lower()
    assert "банковская карта не нужна" in block
    assert "start free" in block and "активировать бесплатно" in block
    assert "api restrictions" in block and "restrict key" in block
    assert "только" in block and "youtube data api v3" in block
    assert "application restrictions" in block and "none" in block
    assert "ip" in block  # объяснено почему


def test_start_free_never_a_call_to_action():
    # враждебно: «нажмите Start free» не должно встречаться нигде
    for name, text in (("guide", GUIDE), ("readme", README)):
        for line in text.splitlines():
            if "start free" in line.lower():
                low = line.lower()
                assert re.search(r"не нажимайте|пропустите|не нажимать|не нужна", low), (
                    name, line)
                assert not re.search(r"(?<!не )нажмите\s*[«\"]?start free", low), (name, line)


def test_application_restrictions_never_told_to_set_something_else():
    for text in (GUIDE, README):
        for line in text.splitlines():
            if "Application restrictions" in line:
                assert re.search(r"None|«Нет»", line), line
                assert not re.search(r"выберите\s+[«\"]?(IP addresses|Websites)", line, re.IGNORECASE)


def test_card_not_required_everywhere_no_contradiction():
    for text in (GUIDE, README):
        low = text.lower()
        assert "карта не нужна" in low or "карта не требуется" in low or "карт" in low
        # нигде не сказано, что карта нужна/обязательна
        assert not re.search(r"(привяжите|добавьте|введите) (банковскую )?карт", low)
        assert not re.search(r"карта (нужна|обязательна|требуется)", low)


# --- критерий 3: .env, cp, ! ---

def test_cp_commands_use_full_paths_in_guide():
    cp_lines = [ln for ln in _code_lines(GUIDE) if re.match(r"\s*(!\s*)?cp\s", ln)]
    assert cp_lines, "нет команды cp"
    for ln in cp_lines:
        args = ln.replace("!", "", 1).split()[1:]
        assert len(args) == 2, ln
        for a in args:
            assert a.startswith("/"), f"путь не полный: {ln}"
        assert args[0].endswith(".env.example") and args[1].endswith("/.env")


def test_ls_check_after_cp_and_without_printing_content():
    step5 = _section(GUIDE, "Шаг 5")
    i_cp = _idx(step5, "! cp ")
    i_ls = step5.find("ls -l", i_cp)
    assert i_ls > i_cp, "после cp нет проверки ls -l"
    for ln in _code_lines(step5):
        # проверка не должна печатать содержимое .env
        assert not re.search(r"\b(cat|head|tail|less|more|grep|source)\b.*\.env\b(?!\.example)", ln), ln


def test_bang_explained_before_first_bang_command():
    step5 = _section(GUIDE, "Шаг 5")
    first_cmd = step5.find("! ")
    explain = step5.find("в этом же окне Claude Code")
    assert 0 <= explain < first_cmd or explain < step5.find("```")


def test_key_never_in_chat_and_no_real_keys():
    assert re.search(r"в чат не вставляйте|не вставляйте ключ в чат", GUIDE.lower())
    assert re.search(r"не вставляйте ключ в чат", README.lower())
    for text in (GUIDE, README):
        assert not re.search(r"AIza", text)
        assert not re.search(r"\bAIza[0-9A-Za-z_\-]{10,}", text)
        for m in re.finditer(r"YOUTUBE_API_KEY\s*=\s*(\S*)", text):
            assert m.group(1) in ("ваш_ключ", ""), m.group(0)
    # ключ не вписывается в команду с «!»
    for ln in _code_lines(GUIDE):
        if ln.lstrip().startswith("!"):
            assert "YOUTUBE_API_KEY" not in ln, ln


def test_no_long_random_tokens_looking_like_keys():
    for text in (GUIDE, README):
        for tok in re.findall(r"[A-Za-z0-9_\-]{35,}", text):
            # допускаем только пути/слова-ссылки: у ключа смесь букв и цифр без дефисов слов
            assert not (re.search(r"\d", tok) and re.search(r"[A-Z]", tok)
                        and re.search(r"[a-z]", tok)), tok


# --- критерий 4: views_multiplier ---

def test_views_multiplier_hint_matches_code_default():
    section = _section(GUIDE, "Если залётов")
    assert "views_multiplier" in section and "settings.yaml" in section
    assert "с 3 до 7" in section
    assert virals.DEFAULTS["views_multiplier"] == 3  # подсказка «по умолчанию 3» правдива
    assert "По умолчанию 3" in section
    assert "человек" in section.lower() and "не агент" in section.lower()
    assert "virals" in section and "report" in section
    assert "квота не тратится" in section.lower()


def test_virals_hint_does_not_spend_quota_or_ask_agent_to_edit():
    section = _section(GUIDE, "Если залётов")
    assert "--confirm" not in section
    assert "collect" not in " ".join(_code_lines(section))
    assert not re.search(r"(попросите|скажите) агент\w* (поправить|изменить|отредактировать)", section.lower())


def test_virals_and_report_commands_exist_in_cli():
    cli = (ROOT / "src" / "produce" / "cli.py").read_text(encoding="utf-8")
    assert "def virals(" in cli and 'name="report"' in cli


# --- критерий 5: README не противоречит ---

def test_readme_sections_1_2_consistent_with_guide():
    s1 = _section(README, "1. Ключ YouTube")
    s2 = _section(README, "2. Куда положить")
    assert "docs/api-key-guide.md" in s1
    assert "YouTube Data API v3" in s1 and "None" in s1
    assert "карта" in s1.lower()
    assert "YOUTUBE_API_KEY=ваш_ключ" in s2
    assert "не вставляйте ключ в чат" in s2.lower()
    # README и инструкция называют один и тот же файл и одну и ту же переменную
    assert ".env.example" in s2 and ".env.example" in GUIDE
    # README не просит ограничения, которых нет в инструкции, и наоборот
    assert "ограничьте" in s1.lower() and "ограничьте" in GUIDE.lower()


def test_readme_old_readme_phrases_do_not_conflict():
    # старый текст разрешал любое ограничение приложения; новый требует None
    assert "Application restrictions" in README
    assert not re.search(r"Application restrictions[^.\n]*(IP|Websites)\b[^.\n]*(выберите|поставьте)",
                         README)
