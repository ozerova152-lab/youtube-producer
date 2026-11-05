![YouTube Producer](assets/cover-producer.jpg)

[Русская версия](README.md) · English

# AI Producer for a YouTube Channel

A helper that finds videos in your topic that got a lot of views, explains why, and suggests what to film.

Repository: https://github.com/ozerova152-lab/youtube-producer · Showcase page: https://ozerova152-lab.github.io/youtube-producer/

## Install with one phrase

Open any AI agent that can work with your computer, paste this message (the block has a "copy" icon) and answer "yes" to its questions. It installs everything and leads you further. The message is in Russian because the agent talks to you in Russian:

```text
Установи мне проект «AI-продюсер YouTube-канала» и помоги запустить.
Адрес: https://github.com/ozerova152-lab/youtube-producer
Я не разбираюсь в терминале, поэтому объясняй простыми словами.
Перед каждой командой, которая что-то ставит или скачивает, спрашивай моё «да».
Скачай проект в домашнюю папку, потом прочитай в нём AGENTS.md, раздел «Установка по ссылке», и действуй по нему.
Ничего не публикуй.
```

All that is left for you is to answer "yes" and get a YouTube key (free). Enter the key yourself and never paste it into a chat.

<details>
<summary>If something went wrong</summary>

- **I am on Windows.** If you run a terminal agent (Claude Code or Codex) on Windows, you need to install WSL once: it is Linux inside Windows, 20-30 minutes. For work in an ordinary chat WSL is not needed. The agent does not install WSL itself: it needs administrator rights and a restart, so it explains the steps and waits. Guide: [docs/windows-wsl.en.md](docs/windows-wsl.en.md).
- **Python, make or git is missing.** These are small programs the project needs. The agent says what is missing and suggests the command. Enter commands that need an administrator password yourself.
- **I only have a chat, no terminal.** No install needed: [chat mode](docs/chat-mode.md) (in Russian).
- **How to open a terminal.** It is a window where you type commands instead of clicking. Mac: Cmd+Space and the word "Terminal". Linux: Ctrl+Alt+T. Windows: "Start" and Ubuntu (after installing WSL).
- **The agent did not manage.** Follow the same steps by hand: the "Quick start" section below.

</details>

## What you get

One "month" of work produces files on your own computer in `data/<channel>/runs/<month>_<segment>_v<N>/`:

- a list of **virals**: videos in your niche from the last 30 days with far more views than usual, plus your own best and weakest videos (`report.md`);
- a breakdown of why they took off, based on viewer comments (`analysis.md`), and an optional cover analysis (`covers.md`);
- the niche and competitor candidates, then a **strategy**: what to film and in which format (`strategy.md`); the agent writes a draft, you approve it;
- **briefs** (an assignment for one video: title, cover, structure) and a monthly plan (`briefs/`, `plan.md`);
- `00-overview.md`: an overview of all run files; a good place to start.

The project **never publishes anything and never writes to YouTube**. You decide and upload.

## What you need

- A computer with Windows, macOS or Linux.
- An AI agent that can run commands on your computer ([list and status](docs/compatibility.md), in Russian). You need a subscription to it. The project needs no separate paid AI key.
- A little time: the agent installs everything itself and asks for your "yes".
- A YouTube key comes later. You will get it yourself.
- Only an ordinary AI chat where programs cannot be run? Install nothing: [chat mode](docs/chat-mode.md) (in Russian).

## Quick start

If the agent did not manage or you prefer step by step, here are the same steps by hand.

**Terminal** is a window where you type commands instead of clicking. Mac: Cmd+Space, type "Terminal". Linux: Ctrl+Alt+T. Windows: "Start" → Ubuntu (after step 1). Copy a command whole, paste it (in a terminal usually Ctrl+Shift+V) and press Enter.

### Step 1. Windows only: install WSL

**What to do:** follow the [WSL guide](docs/windows-wsl.en.md) (once). On Mac and Linux skip this step.
**What you will see:** a black Ubuntu window; the line starts with something like `anna@pc:~$`.
**If it did not work:** the line starts with `PS C:\…`, so you are in PowerShell, not Ubuntu. Open Ubuntu from the Start menu. Anything else: "If you get stuck" at the end of the guide.

### Step 2. Download the project

**What to do:** in the terminal run two commands: `git clone https://github.com/ozerova152-lab/youtube-producer.git`, then `cd youtube-producer`.
**What you will see:** the word "Cloning…" and then the input line again. The `ls` command lists files, including `AGENTS.md`.
**If it did not work:** "git: command not found". On Ubuntu run `sudo apt install -y git`. On Mac the terminal offers to install developer tools: agree and repeat the command.

### Step 3. Check Python and prepare the project

**What to do:** first find out the Python version (the language the project script is written in): run `python3 --version`. Then run `make setup`: it downloads everything needed (internet required, it may take a few minutes).
**What you will see:** the first command answers like `Python 3.12.3`: 3.12 or higher is fine (3.13 too). The second prints scrolling installation lines; the word "Error" does not appear at the end.
**If it did not work:**

- The version is below 3.12 (for example `Python 3.9.6`). **Mac:** the built-in Python is old. Open <https://www.python.org/downloads/>, download the Python 3.12 or newer installer, run it (keep pressing "Continue"), close the terminal, open a new one and run `python3 --version` again: it must show 3.12 or higher. **Ubuntu:** you need a newer Ubuntu (24.04 comes with Python 3.12); on Windows that is `wsl --install -d Ubuntu-24.04`, see the [WSL guide](docs/windows-wsl.en.md).
- "python3: command not found" or "make: command not found". Ubuntu: `sudo apt install -y make python3-venv python3-pip`. Mac: `make` comes with the developer tools (see step 2), Python is installed from python.org as above. Then run `make setup` again.
- Other cases: [table below](#if-something-went-wrong).

### Check that everything works

Here you can make sure everything is installed. A test channel is already in the project; no internet or key is needed. Run three commands in order:

```bash
mkdir -p data && cp -r examples/demo data/demo && .venv/bin/produce --channel data/demo start --segment ru --brief-lang ru
.venv/bin/produce --channel data/demo import examples/demo/import_comments.json --segment ru
.venv/bin/produce --channel data/demo virals --segment ru
```

Expected: the second command loads 11 videos and 2 channels with 0 YouTube requests, the third finds 2 viral videos. The date in the demo is fixed (27 October 2026), so the result is the same on any day. If `data/demo` already exists, run `make reset` first.

### Step 4. Open the folder in the agent

**What to do:** in the same folder start the agent: `claude` (Claude Code) or `codex` (Codex). For Claude Cowork open the project folder in the Claude Desktop app.
**What you will see:** the agent's input window.
**If it did not work:** the agent is not installed or you have no subscription: the project does not work without an agent. How to start each one: [agents](docs/compatibility.md) (in Russian).

### Step 5. Say the phrase

**What to do:** write to the agent: "Read AGENTS.md and start the month."
**What you will see:** the agent says how it will work and asks about your channel. Then it leads you itself and waits for your word at each stop ("yes", "done", "approved").
**If it did not work:** the agent answers off topic. Check that the `youtube-producer` folder itself is open (it contains `AGENTS.md`) and start the phrase with "Read AGENTS.md and…".

To resume after a pause: "Read AGENTS.md and continue the month."

## Your own channel

Two ways to start.

**YouTube Data API key.** It is free (10,000 quota units per day, no bank card). Detailed guide: `docs/api-key-guide.md` (in Russian). In short:

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project. Do not press "Start free".
2. Enable **YouTube Data API v3** in the project.
3. Create an API key and restrict it to that API ("Application restrictions" stays None).
4. Open an ordinary terminal in the project folder (in Windows the Ubuntu window, not the agent chat) and run `make add-key`. No text editor needed.
5. Paste the key when asked and repeat it. Nothing is shown while you type, that is normal. The command creates `.env` for you only and prints nothing. **Never paste the key into a chat.** If a key leaks, reissue it in Google Cloud.
6. Tell the agent "key added".

**A file instead of a key.** Prepare a table of videos as CSV/JSON (columns: `docs/import-format.md`, sample: `examples/demo/import.csv`). Import makes no network calls and spends no quota:

```bash
.venv/bin/produce --channel data/<channel> import path/to/file.csv
```

## If something went wrong

- **`make: command not found` or `python3: command not found`:** install `make` and Python 3.12+ with venv (Ubuntu/WSL: `sudo apt install -y make python3-venv python3-pip`).
- **`make setup` fails and `pwd` starts with `/mnt/c`:** copy the project to the Ubuntu home folder (see the [WSL guide](docs/windows-wsl.en.md)) and run `make setup` there.
- **`wsl --install` hangs at 0%:** in PowerShell as administrator run `wsl --install --web-download -d Ubuntu`.
- **`make setup` fails with "ensurepip is not available":** `sudo apt install python3-venv`, then `make setup` again.
- **`make setup` fails with "No space left on device":** free some disk space and repeat; if `.venv` was created, delete it (`rm -rf .venv`).
- **"Key rejected" (YouTube refused it):** a typo or a key for another service; check it against `docs/api-key-guide.md` (in Russian) and reissue it if it leaked.
- **"Settings file not found":** you need `data/<channel>/settings.yaml`; copy the sample `examples/demo/settings.yaml`.
- **The agent says it cannot see covers and asks for files:** put the covers into `data/<channel>/runs/<run>/thumbs/` as `<video id>.jpg` (or `.png`, `.webp`) and write "done", or write "skip".

## More

All files in `docs/` below are in Russian for now.

- [How the project works](docs/how-it-works.md): steps of the month, how the project remembers past months, folders, sample phrases.
- [Agents](docs/compatibility.md): how to start Claude Code, Cowork, Codex and the status of each.
- [Chat only, no terminal](docs/chat-mode.md) · [Glossary](docs/glossary.md) · [Limits and security](docs/limits-and-security.md).
- [YouTube key guide](docs/api-key-guide.md) · [Import file format](docs/import-format.md).

## License

MIT, see `LICENSE`.
