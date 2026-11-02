# AI Producer for a YouTube Channel

[Русская версия](README.md) · English

A set of instructions, templates and a small data-collection script. You open the project folder in an AI agent that reads `AGENTS.md` and say: "Read AGENTS.md and start the month." The agent then walks you through the steps. **You always decide and publish yourself.**

Repository: https://github.com/ozerova152-lab/youtube-producer · Showcase page: https://ozerova152-lab.github.io/youtube-producer/

## What you get

One "month" of work produces files on your own computer in `data/<channel>/runs/<month>_<segment>_v<N>/`:

- Viral videos in your niche for the last 30 days, plus your own best and weakest videos (`report.md`).
- A breakdown of why they took off, based on viewer comments (`analysis.md`).
- The niche and competitor candidates (`niche.md`, `candidates.md`).
- A content strategy (`strategy.md`): the agent writes a draft, you approve it.
- Briefs with packaging for a long video, Shorts and a Community post, plus a monthly plan built from accepted briefs (`briefs/`, `plan.md`).

The project **never publishes anything and never writes to YouTube**. It helps you choose topics; you film and upload.

## How it works

1. **Setup.** You describe the channel in `data/<channel>/settings.yaml`: niche, region and language, search words.
2. **Collection.** The agent calculates the YouTube quota cost and waits for your "yes". Without an API key you can import videos from a file.
3. **Virals.** The script finds videos with far more views than usual for the channel.
4. **Reasons.** The agent reads comments on those videos and summarizes what viewers say.
5. **Niche and strategy.** The agent drafts the strategy and stops until you mark it "approved".
6. **Briefs and plan.** You mark each brief "accepted", "rejected" or "later"; accepted ones become the plan.
7. **Next month.** The agent remembers past runs: rejected ideas do not return, "later" ones can.

## What is inside

- `AGENTS.md`: the general agent instruction; `playbooks/`: step-by-step scenarios, starting with `playbooks/00-month.md`
- `templates/`: sample files (strategy, briefs, plan); `examples/demo/`: a demo channel with sample results
- `src/produce/`: the data-collection script (`produce`); `site/`: the showcase page

## Install and run

**Requirements:** Linux, macOS or Windows (on Windows, work inside WSL, which is Linux inside Windows), Python 3.12+ with `venv`, `make`, `git`, and an AI agent that reads `AGENTS.md` (AI steps use your agent subscription; no separate paid AI key is needed).

```bash
git clone https://github.com/ozerova152-lab/youtube-producer.git
cd youtube-producer
make setup
```

Open the folder in your agent and say: **"Read AGENTS.md and start the month."** To resume: **"Read AGENTS.md and continue the month."**

On Windows, a step-by-step WSL guide is in the Russian README. Keep the project in the Ubuntu home folder (for example `~/youtube-producer`), not under `/mnt/c`.

### Agents

- **Claude Code:** open a terminal in the project folder and run `claude`. This is the main, fully tested path.
- **Codex:** run `codex` in the project folder. Tested on a real channel (30 Oct 2026) from setup to briefs.
- **Claude Cowork:** open the folder in Claude Desktop. Not tested; the same `AGENTS.md` is used.

## YouTube Data API key (free, needed for real collection)

The free quota is 10,000 units per day, usually plenty for a month. No bank card is required. Create a project in Google Cloud Console, enable YouTube Data API v3, create an API key and restrict it to that API. Do not press "Start free". Details: `docs/api-key-guide.md`.

Store the key only in the local `.env` file (it is in `.gitignore`). The easiest way is:

```bash
make add-key
```

It asks for the key with hidden input and creates `.env` for you only. **Never paste the key into a chat.** If a key leaks, reissue it in Google Cloud.

## No key? Import from a file

The agent can load videos from a CSV/JSON file you prepare (format: `docs/import-format.md`, sample: `examples/demo/import.csv`). Import makes no network calls and spends no quota.

## Demo without a key or network

```bash
mkdir -p data
cp -r examples/demo data/demo
.venv/bin/produce --channel data/demo start --segment ru --brief-lang ru
.venv/bin/produce --channel data/demo import examples/demo/import_comments.json --segment ru
.venv/bin/produce --channel data/demo virals --segment ru
```

Expected: 11 videos and 2 channels loaded with 0 YouTube requests, and 2 viral videos found. Reset with `make reset`.

## Limitations

- Does not publish and does not write to YouTube. A human decides and publishes.
- Public numbers only: no private analytics (retention, revenue).
- Official API or your own file only; no scraping of YouTube pages.
- Not autonomous: no scheduling, a human confirms each step (quota, strategy, brief statuses).
- Free quota is limited; progress is saved and collection continues the next day.
- Windows works through WSL only.
- Main path is Claude Code; Codex is tested; Cowork is not.

## Security

The YouTube key lives only in local `.env`. The ban on reading `.env` in `.claude/settings.json` works only in Claude Code; in other agents it relies on the instruction in `AGENTS.md`, so do not paste the key into chat. Do not enable auto-approval of commands, and read each command before agreeing: video titles and comments from YouTube end up in reports, and foreign text may try to push the agent into unwanted actions.

## License

MIT, see `LICENSE`.
