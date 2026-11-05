# Windows: how to install WSL (once)

[← Quick start](../README.en.md#quick-start) · [Русская версия](windows-wsl.md)

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
- **`wsl --install` hangs at 0%.** In PowerShell as administrator run `wsl --install --web-download -d Ubuntu`.
- **How to tell you are in the Ubuntu window.** The line starts with name@computer (for example `anna@pc:~$`). If it shows `PS C:\...>`, that is PowerShell: close it and open Ubuntu from the Start menu.
- **`python3 --version` shows below 3.12.** Install a newer Ubuntu: in PowerShell run `wsl --install -d Ubuntu-24.04`, open it from the Start menu and repeat step 5.

Do all the quick-start steps in the Ubuntu window: `git clone`, `make setup` and starting the agent. You do not need to download a ZIP in Windows. The agent must be available inside Ubuntu: see your agent's documentation for how to install it there.

## Where to keep the project

**Keep the project in the Ubuntu home folder** (for example `~/youtube-producer`), not under `/mnt/c`: running from the Windows disk also works through WSL, but installing Python packages there may break off and leave locked files. Run `cd ~`, then `git clone https://github.com/ozerova152-lab/youtube-producer.git`. Check where you are with `pwd`; if the path starts with `/mnt/c`, copy the project to the home folder, and do not run `make setup` in the old folder.

If you already downloaded the project in Windows, copy it into Ubuntu with `cp -r /mnt/c/Users/YOUR_NAME/Downloads/youtube-producer ~/` (use your Windows user name and the real folder name; in Ubuntu the C: drive is `/mnt/c`), then work only with the copy: `cd ~/youtube-producer`.
