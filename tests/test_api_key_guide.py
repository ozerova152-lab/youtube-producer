"""T20: инструкция по ключу YouTube Data API: ключевые подводные камни и ссылка из README."""

from pathlib import Path

ROOT = Path(__file__).parent.parent
GUIDE = (ROOT / "docs" / "api-key-guide.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_links_to_guide():
    assert "docs/api-key-guide.md" in README


def test_guide_steps_and_pitfalls():
    for needle in ["YouTube Data API v3", "Enable", "Create credentials", "Restrict key",
                   "Application restrictions", "None", "Start free", "Активировать бесплатно",
                   "карта не нужна", "cp /путь/к/youtube-producer/.env.example",
                   "ls -l", "в этом же окне Claude Code", "в чат не вставляйте",
                   "views_multiplier", "с 3 до 7", "virals", "report", "квота не тратится"]:
        assert needle.lower() in GUIDE.lower(), needle


def test_no_real_keys():
    import re
    for text in (GUIDE, README):
        assert not re.search(r"AIza[0-9A-Za-z_\-]{35}", text)
