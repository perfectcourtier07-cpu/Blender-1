# Blender Kit: standing rules for Claude

This folder is the user's Blender Kit: Claude builds 3D shots in Blender here and hands back video files. These rules apply to every request made in this folder and to any helper or agent Claude starts. If the user asks for something different for one job, follow the user for that job. These rules are the defaults.

## Setup and tools
- The setup skill (`.claude/skills/blender-setup`) installs and checks the tools. Run `python tools/doctor.py` at the start of any job, or whenever a tool seems missing, instead of guessing. Its `--json` form is what the skills read.
- **Plain commands:** run the kit's commands from this folder, exactly as the docs write them, one command per call: no `cd ... &&` in front, no `&&` or `;` chains, no pipes or heredocs around the kit's own scripts. Read files with the file-reading tool, not `cat` or `grep` pipelines. Why: the kit pre-approves its own scripts, but a chained command can't be pre-approved, so the user would be asked every time.
- **Installing the skill:** when the user says "Install the Blender skill from <path to zip>", run `python tools/install_pack.py "<path>"`. Never copy, merge or replace the Blender Kit folder by hand, and never delete this folder or `shots/`.
- **Updating the kit:** only when the user says "Update the kit from <path>", run `python tools/install_pack.py "<path>" --upgrade-kit`. Without the flag a Setup pack is refused. It replaces `CLAUDE.md`, `START-HERE.md`, `tools/*`, the blender-setup skill and `.claude/settings.json`, copying each old file to `.kit/backups/<time>/` first, and never touches `shots/` or `.kit/`.
- **Python:** 3.9 or newer. Commands say `python`; on a Mac read that as `python3`. If `python` is missing or only opens the Microsoft Store, the setup skill installs Python 3.12 and uses its full path until the one restart; after that, `py -3` or `python` works. If `doctor.py` prints "use this Python for the kit: <path>" (the running Python is too old), use that path. On Windows the kit's scripts add the registry PATH and winget's folders to their own PATH, so a tool installed a minute ago is found without restarting Claude Desktop. On a Mac they add Homebrew's folders themselves.
- Paths here contain a space ("Blender Kit"): always quote them.
- **Folders:** one folder per shot, `shots/<short-name>/`, holding the scene script (`<short-name>.py`), the stills (`<short-name>-still-NNNN.png`) and the finished clip (`<short-name>.mp4`, or `.mov` for an overlay). Never write outside this folder unless the user gives a path. Test renders from setup go in `renders/`.

## Blender
- The `blender-shots` skill (`.claude/skills/blender-shots`) is how shots get made. Read its `SKILL.md` and `references/BLENDER.md` before the first shot of a session. If it is not installed, tell the user to download the second ZIP and say "Install the Blender skill from <path>"; don't improvise your own Blender setup.
- **Render settings: 1 sample, and 2 motion-blur steps when motion blur is on.** Every scene script gets this through `blender_kit.setup()` and the runner applies it again. Never raise them because a render looks noisy or "could look better", and never run sample comparisons. Only the user can ask for more, for one job, in their own words. Make the shot look good with lighting, depth, camera motion and grading instead. Why: see the skill's `references/RENDER-RULES.md`.
- **Always render through the skill's `scripts/render_blender.py`. Never call `blender` yourself**, not for a test, not for a "quick" render. The runner forces EEVEE at the requested `--size` (1920x1080 by default; `1080x1920` for a vertical Short), caps a shot at 30 seconds, stops a render projected over 15 minutes, keeps one render at a time on this computer, runs Blender in the background at below-normal priority, and never opens its window.
- **Stills first.** Render 2 or 3 still frames, look at them, fix, then render the clip. A clip is one render; don't render it again unless something changed.
- Long renders run in the background or with no timeout, and you wait for them: a timeout kills a render half-way.
- On a computer that `tools/doctor.py` rates "slow", keep shots short (3 to 5 seconds) and simple, and say so.

## Money, uploads and the computer
- Never spend money, start a paid service, buy assets or upload anything without the user saying yes in chat first.
- Never install software beyond what the setup skill lists without asking. Never change security settings. Never ask for or type a password.
- Keep the computer usable: one render at a time, at below-normal priority. When a job is done, cancelled or fails, stop the processes you started and check they exited. Don't leave renders running. To stop a render, stop the runner process you started (it stops its own Blender); never stop Blender by name, which would also close a Blender the user has open.
- Don't permanently delete the user's files. Test files you yourself created in this same job (setup checks in `renders/`, stills you replaced) may be deleted when you're done. Anything else needs the user's OK first, and goes to the Recycle Bin/Trash.

## Honesty
- Tell the user what you looked at by eye (the stills), what you only checked by machine (the file exists, its length) and what is unverified.
- Check every word and number in a shot against what the user gave you. Never invent facts, logos or "illustrations" presented as real.
