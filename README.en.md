![YouTube Producer](assets/cover-producer.jpg)

# AI Producer for a YouTube Channel

[Русская версия](README.md) · English

A set of instructions, templates and a small data-collection script. You open the project folder in an AI agent that reads `AGENTS.md` and say: "Read AGENTS.md and start the month." The agent then walks you through the steps. **You always decide and publish yourself.**

Repository: https://github.com/ozerova152-lab/youtube-producer · Showcase page: https://ozerova152-lab.github.io/youtube-producer/

## What you get

One "month" of work produces files on your own computer in `data/<channel>/runs/<month>_<segment>_v<N>/`:

- **Run overview** (`00-overview.md`): a good place to start; it lists the run files in working order, what is in each and why, and the start and last collection dates.
- Viral videos in your niche for the last 30 days, plus your own best and weakest videos (`report.md`).
- A breakdown of why they took off, based on viewer comments (`analysis.md`).
- An optional **cover analysis** of the viral videos (`covers.md`): what their covers have in common (text, faces, color, composition). It is the agent's guess from the pictures, not a measurement.
- The niche and competitor candidates (`niche.md`, `candidates.md`).
- A content strategy (`strategy.md`): the agent writes a draft, you approve it.
- Briefs with packaging for a long video, Shorts and a Community post, plus a monthly plan built from accepted briefs (`briefs/`, `plan.md`).

The project **never publishes anything and never writes to YouTube**. It helps you choose topics; you film and upload.

## How it works

1. **Setup.** You describe the channel in `data/<channel>/settings.yaml`: niche, region and language, search words.
2. **Collection.** The agent calculates the YouTube quota cost and waits for your "yes". Without an API key you can import videos from a file.
3. **Virals.** The script finds videos with far more views than usual for the channel.
4. **Reasons.** The agent reads comments on those videos and summarizes what viewers say. Optionally it also analyzes the covers of the viral videos (step 3b; you can say "skip").
5. **Niche and strategy.** The agent drafts the strategy and stops until you mark it "approved".
6. **Briefs and plan.** You mark each brief "accepted", "rejected" or "later"; accepted ones become the plan.
7. **Next month.** The agent remembers past runs: rejected ideas do not return, "later" ones can.

## How the project remembers past months

The project's memory is just ordinary folders on your computer. Each run (one month, one segment) lives in its own folder, and the agent never changes old folders:

```
data/my-channel/runs/
├── 2026-09_ru_v1/   ← last month: report.md, strategy.md, briefs/01.md, 02.md…
└── 2026-10_ru_v1/   ← this month
```

When you say "start the month", the agent reads only past runs of the same segment (`ru` and `en` are not mixed), all their versions (v1, v2). From old briefs it takes the statuses: "rejected" (the topic does not return), "later" (the agent shows these topics and asks which to bring back) and "accepted" (the topic was already offered and will not be repeated). To bring back a rejected topic, change the `- Статус:` line in the old brief yourself.

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

Run `make setup` once inside the `youtube-producer` folder: it downloads everything needed (internet required; after that the demo and file import work offline). Chromium (about 120 MB) is not downloaded by `make setup`: it is only needed by developers (`make setup-dev`). You do not need `make check`.

If you only have an ordinary AI chat (no terminal, no access to the project folder), you need to install nothing: see "If you only have a chat" below.

### Windows: how to install WSL (once)

WSL is Linux inside Windows; the project runs in it. **This is a single one-time step, about 20-30 minutes.** You need Windows 10 version 2004 or newer, or Windows 11 ([Microsoft guide](https://learn.microsoft.com/windows/wsl/install)).

- **Step 1.** Click "Start", find PowerShell, right-click it and choose "Run as administrator".
- **Step 2.** Run `wsl --install` (it installs Ubuntu, which is Linux).
- **Step 3.** Restart the computer.
- **Step 4.** Open Ubuntu (it usually opens by itself after the restart; if not, find it in the Start menu). On first launch choose a user name and password (the password is not shown while you type, that is normal) and remember it.
- **Step 5.** In the Ubuntu window run `sudo apt update && sudo apt install -y git make python3-venv python3-pip`, then `python3 --version`: it must be 3.12 or newer.

**Do not want to figure it out yourself?** Open any AI agent and tell it: "I am on Windows and understand nothing about the terminal. Help me install WSL and get to running the project, explain every step."

**If you get stuck:**

- **The password is not shown while typing.** No dots or stars: that is normal, just type it and press Enter.
- **`wsl --install` mentions virtualization.** On some computers it must be turned on in the BIOS (look for Virtualization, Intel VT-x or AMD-V). How to enter the BIOS depends on the model: search for "enable virtualization BIOS" and your computer's name.
- **How to tell you are in the Ubuntu window.** The line starts with name@computer (for example `anna@pc:~$`). If it shows `PS C:\...>`, that is PowerShell: close it and open Ubuntu from the Start menu.

Do all the steps in the Ubuntu window: `git clone`, `make setup` and starting the agent. **Keep the project in the Ubuntu home folder** (for example `~/youtube-producer`), not under `/mnt/c`: running from the Windows disk also works through WSL, but installing Python packages there may break off and leave locked files. Run `cd ~`, then `git clone https://github.com/ozerova152-lab/youtube-producer.git`. Check where you are with `pwd`; if the path starts with `/mnt/c`, copy the project to the home folder, and do not run `make setup` in the old folder.

### Agents

- **Claude Code:** open a terminal in the project folder and run `claude`. This is the main, fully tested path.
- **Codex:** run `codex` in the project folder. Tested on a real channel (30 Oct 2026) from setup to briefs.
- **Claude Cowork:** open the folder in Claude Desktop. Not tested; the same `AGENTS.md` is used.

**The main path is Claude Code, fully tested.** Codex was tested on a real channel (30 Oct 2026) from setup to briefs: setup, key, data collection, virals, niche and candidates, strategy, briefs. We did not test Cowork: use the same `AGENTS.md` and write to [Issues](https://github.com/ozerova152-lab/youtube-producer/issues). An ordinary chat without a terminal (no-terminal mode, scenario `playbooks/no-terminal.md`) has also not been tested on a real channel.

Only for Claude Code there is an optional bonus: mini-skills `/start-month`, `/continue-month`, `/demo`, `/setup-check` (described in `CLAUDE.md`). Without them everything works by phrases.

**Cover analysis (step 3b).** The agent looks at pictures only at `https://i.ytimg.com/` addresses. Tested only in Claude Code: it downloads the cover file and opens it as an image. Other agents have not tried this step yet, the result is unknown. If the agent cannot see images or there are no cover links (old cache, import without covers), it asks you to put files into `data/<channel>/runs/<run>/thumbs/` named `<video id>.jpg` (`.png` and `.webp` also work) and waits for "done"; you can say "skip", the other steps do not depend on it. The script does not download images itself, and `data/` and `*.jpg`, `*.png`, `*.jpeg`, `*.webp` files stay out of git.

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

## If you only have a chat

Sometimes all you have is an ordinary AI chat: no terminal, no access to the project folder. The project works that way too, but differently, and we are honest about what is worse. We have not tested this mode on a real channel: the `playbooks/no-terminal.md` scenario is checked against the code by automated tests, but not run end to end.

**How it works.** Open the chat, give it the `AGENTS.md` file (or paste its text) and write "start the month". The agent understands it cannot run commands and says so once. Then it works from data you paste or attach: a table or file in the format of [`docs/import-format.md`](docs/import-format.md) (CSV, JSON or a Google Sheets table). Each channel needs 5-20 recent videos, otherwise there is no "norm" and the videos are skipped.

**How it differs from the usual mode:**

- Collecting from YouTube by key is unavailable. Do not paste the key into the chat (it must stay only with you). Data comes from a file.
- The agent counts virals and your results by hand, using the formulas in `playbooks/no-terminal.md`, so it marks every number "counted by hand, approximate" and shows a calculation table you can check. It takes at most 60 videos at a time: send more in parts.
- The agent saves nothing to files. Results (`strategy.md`, briefs, `plan.md`) arrive as blocks with file names, and you save them: copy the block and put it in the run folder.
- The chat has no memory of past months: in a new month the agent asks you to paste last briefs with the statuses "accepted / rejected / later", so it does not offer rejected topics again.
- The pauses stay the same: you approve the strategy with the word "approved" and name the brief statuses in the chat. The agent publishes nothing.

When you can, switch to the usual mode with a terminal (section "Install and run"): it is more accurate because the script counts the numbers and saves the files itself.

## If something went wrong

- **`make: command not found` or `python3: command not found`:** install `make` and Python 3.12+ with venv (Ubuntu/WSL: `sudo apt install -y make python3-venv python3-pip`).
- **`make setup` fails and `pwd` starts with `/mnt/c`:** copy the project to the Ubuntu home folder (see the WSL section) and run `make setup` there.
- **`wsl --install` hangs at 0%:** in PowerShell as administrator run `wsl --install --web-download -d Ubuntu`.
- **The agent says it cannot see covers and asks for files:** put the covers into `data/<channel>/runs/<run>/thumbs/` as `<video id>.jpg` (or `.png`, `.webp`) and write "done", or write "skip".

## Limitations

- Does not publish and does not write to YouTube. A human decides and publishes.
- Public numbers only: no private analytics (retention, revenue).
- Official API or your own file only; no scraping of YouTube pages.
- Not autonomous: no scheduling, a human confirms each step (quota, strategy, brief statuses).
- Free quota is limited; progress is saved and collection continues the next day.
- Windows works through WSL only.
- Main path is Claude Code, fully tested. Codex was tested on a real channel (30 Oct 2026) from setup to briefs; we did not test Cowork; an ordinary chat without a terminal (no-terminal mode) has not been tested on a real channel either. The same `AGENTS.md` is used for all, with no separate settings or mini-skills.

## Security

The YouTube key lives only in local `.env`. The ban on reading `.env` in `.claude/settings.json` works only in Claude Code; in other agents it relies on the instruction in `AGENTS.md`, so do not paste the key into chat. Do not enable auto-approval of commands, and read each command before agreeing: video titles and comments from YouTube end up in reports, and foreign text may try to push the agent into unwanted actions.

## License

MIT, see `LICENSE`.
