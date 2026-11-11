# Blender Kit: start here

This folder makes Claude install and check everything it needs to build 3D shots with Blender on your computer. The second download (the Blender skill) teaches Claude how to make the shots. Setup first, skill second.

## 1. Set up (one time)

1. Extract this ZIP (Windows: right-click it, then **Extract All**). Move the **Blender Kit** folder somewhere you'll keep it, like Documents or the Desktop. Extracting may add an outer folder with a similar name: the one you want is the **Blender Kit** folder that has a file called **CLAUDE.md** inside.
2. Open Claude Desktop. Go to **Code**, choose **this computer**, click the folder icon, then **Open folder** and pick the **Blender Kit** folder that contains **CLAUDE.md**. Click **Trust workspace**.
3. Send this:

> Run the Blender setup.

Claude checks your computer, tells you what's missing, and asks once before installing. Say yes. At the end it renders one test frame so you both know Blender works, and asks you to quit Claude Desktop fully and open it again in the same folder, once.

**What gets installed (all free):** Blender (the 3D program), FFmpeg (turns the rendered frames into a video) and, only if your computer has none, Python. About 0.5 GB of downloads. Nothing paid, no accounts.

**Getting Blender yourself instead:** go to blender.org, click Download, run the Windows installer, then tell Claude "continue setup". Claude finds it on its own. Blender 4.2 or newer works; the kit is tested on Blender 5.2.

**What you need:** Windows 10 or 11 (a Mac works too with Homebrew, see below), a graphics card helps a lot, about 5 GB of free space, and a Claude plan with Claude Code.

## 2. Add the Blender skill

Download the second ZIP, **Blender-Kit-2-Blender-Skill.zip**, and leave it where it is. Don't unzip it and don't drag it into this folder. Tell Claude where it is:

> Install the Blender skill from C:\Users\you\Downloads\Blender-Kit-2-Blender-Skill.zip

(Windows: right-click the file, then "Copy as path".) Claude installs it into this folder without touching anything else.

## 3. Make a shot

Open **PROMPTS.md** (it arrives with the skill) and copy a prompt, or just say what you want:

> Make a 5-second 3D title that says MY FIRST 10K. Show me stills first.

Claude writes the scene, shows you still frames, fixes what you ask, renders the clip into `shots/<name>/` and tells you the file to drop into CapCut, Premiere or DaVinci.

## Good to know

- Claude asks before it runs a command. The kit's own tools are pre-approved; for anything else, read the one-line reason and click Allow if it matches what you asked for.
- Renders use **1 sample**. That is on purpose (see the skill's RENDER-RULES.md). Claude will never raise it on its own, so renders stay fast.
- Only one Blender render runs at a time, in the background, so you can keep using your computer.
- **Mac:** install Homebrew first (brew.sh), then the same steps work. Claude tells you if your Mac needs Blender from blender.org instead. The kit was built and tested on Windows only; the Mac path is written but untested.
- **Updating later:** don't delete anything. Say `Update the kit from <path to the new Setup zip>`, then install the new skill zip the same way as in step 2. Your shots stay where they are.
