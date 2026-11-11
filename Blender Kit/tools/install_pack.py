"""Install the Blender Kit skill pack (the second download) into this Blender Kit folder, safely.

  python tools/install_pack.py PATH_TO.zip [--dry-run]
  python tools/install_pack.py PATH_TO_UNZIPPED_FOLDER [--dry-run]     (when Safari or Finder already unzipped the download)
  python tools/install_pack.py PATH_TO_SETUP.zip --upgrade-kit      (only when the user asked to update the kit itself)

The pack ZIP holds a top "Blender Kit/" folder. This copies its contents into the kit root (the folder that holds
CLAUDE.md and tools/doctor.py), without the top folder. Use this instead of dragging the folder over the kit: on a Mac,
Finder's "Replace" deletes the whole kit folder, including your shots.

What it does and never does:
- It only adds or updates files that belong to the pack. It never deletes anything.
- It never overwrites the kit's own files: CLAUDE.md, START-HERE.md, the Setup tools (tools/doctor.py, blender_check.py,
  _render_policy.py, _studio_env.py, install_pack.py), the blender-setup skill, or anything in shots/, .kit/, .venv/ or node_modules/.
  (If one of them is missing it is restored.)
- A Setup pack (it holds CLAUDE.md and tools/doctor.py) is an update of the kit itself: it is refused unless --upgrade-kit is
  given. With the flag, the kit's own files (CLAUDE.md, START-HERE*.md, tools/*, the blender-setup skill, .claude/settings.json)
  are replaced, each one backed up first. shots/, .kit/, .venv/ and node_modules/ are never touched, flag or not.
- A file it replaces with different content is first copied to .kit/backups/<timestamp>/ (same relative path).
- It refuses the whole ZIP, before writing anything, if an entry would land outside the kit folder (absolute path, "..",
  drive letter, link) or if the ZIP is not a Blender Kit pack.
Prints what it installed.
"""
import argparse
import os
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from pathlib import PurePosixPath

TOP = "Blender Kit"
PROTECTED_FILES = {"CLAUDE.md", "START-HERE.md", "tools/doctor.py", "tools/blender_check.py", "tools/_render_policy.py",
                   "tools/_studio_env.py", "tools/install_pack.py", ".claude/settings.json", ".claude/settings.local.json"}
NEVER_DIRS = ("shots/", ".kit/", ".venv/", "node_modules/")          # never touched, even with --upgrade-kit
PROTECTED_DIRS = NEVER_DIRS + (".claude/skills/blender-setup/",)


def studio_root():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    if not (os.path.isfile(os.path.join(root, "CLAUDE.md")) and os.path.isfile(os.path.join(root, "tools", "doctor.py"))):
        sys.exit(f"{root} does not look like the Blender Kit folder (CLAUDE.md or tools/doctor.py is missing). "
                 "Run this from the kit folder: python tools/install_pack.py PATH_TO.zip")
    return root


def clean_name(raw):
    """Entry name -> list of safe path parts below the studio root, or raise ValueError."""
    name = raw.replace("\\", "/")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":") or name.startswith("//"):
        raise ValueError("absolute path")
    parts = [p for p in PurePosixPath(name).parts]
    if any(p == ".." or p == "" or ":" in p for p in parts):
        raise ValueError("path leaves the kit folder")
    if parts[0] != TOP:
        raise ValueError(f"not inside the \"{TOP}/\" folder")
    return parts[1:]


def is_never(rel):
    return any(rel.lower().startswith(d) for d in NEVER_DIRS)


def is_protected(rel, upgrade=False):
    rel = rel.lower()          # macOS and Windows disks ignore letter case: "Tools/Doctor.py" is the same file as tools/doctor.py
    if upgrade:                # --upgrade-kit: the studio's own files may be replaced, the user's work never
        return is_never(rel)
    return rel in {f.lower() for f in PROTECTED_FILES} or any(rel.startswith(d) for d in PROTECTED_DIRS)


def is_junk(raw):
    """Files macOS adds to archives and folders: skipped, never installed."""
    parts = raw.replace("\\", "/").split("/")
    return parts[0] == "__MACOSX" or parts[-1] == ".DS_Store" or parts[-1].startswith("._")


def looks_like_studio(d):
    return os.path.isfile(os.path.join(d, "tools", "doctor.py"))


def looks_like_setup_pack(d):
    """An unzipped Setup pack: the kit's own files, but no shots/ (so it is a download, not somebody's working kit)."""
    return os.path.isfile(os.path.join(d, "CLAUDE.md")) and looks_like_studio(d) and not os.path.exists(os.path.join(d, "shots"))


def looks_like_pack(d):
    """An unzipped pack: has .claude/skills or .claude/effects, and is not a studio itself."""
    return (os.path.isdir(os.path.join(d, ".claude", "skills")) or os.path.isdir(os.path.join(d, ".claude", "effects"))) \
        and not looks_like_studio(d)


def find_pack_folder(folder, root, upgrade=False):
    """The folder to install from, whatever it is called: an unzipped download can be "Blender Kit", "Blender Kit 2"
    (Safari and Finder rename a second one), or the folder that holds it. Never a studio."""
    folder = os.path.abspath(folder)
    if os.path.normcase(folder) == os.path.normcase(os.path.abspath(root)):
        sys.exit("That is the kit folder itself, not a download. Nothing was changed. Give the path of the downloaded ZIP "
                 "or of the folder it unzipped into.")
    if looks_like_studio(folder):
        if looks_like_setup_pack(folder):
            if upgrade:
                return folder
            sys.exit(SETUP_REFUSAL)
        sys.exit(f"{folder} is a Blender Kit folder (it has tools/doctor.py), not a pack to install. Nothing was changed.")
    if looks_like_pack(folder):
        return folder
    hits = []
    for name in sorted(os.listdir(folder)):
        d = os.path.join(folder, name)
        if os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(root)):
            continue
        if os.path.isdir(d) and not name.startswith(".") and (looks_like_pack(d) or (upgrade and looks_like_setup_pack(d))):
            hits.append(d)
    if len(hits) == 1:
        return hits[0]
    if hits:
        sys.exit("More than one pack in that folder: " + ", ".join(os.path.basename(h) for h in hits) +
                 ". Give the path of the one to install.")
    sys.exit(f"{folder} does not look like a Blender Kit pack (no .claude/skills inside). "
             "Give the path of the downloaded ZIP or of the folder it unzipped into.")


SETUP_REFUSAL = ("This is a Setup pack: an update of the kit itself (it holds CLAUDE.md and tools/doctor.py). Nothing was changed. "
                 "If the user asked to update the kit, run the same command again with --upgrade-kit. Otherwise leave it alone.")


def is_setup_pack(zf):
    names = {n.replace("\\", "/") for n in zf.namelist()}
    return TOP + "/CLAUDE.md" in names and TOP + "/tools/doctor.py" in names


NOT_BEFORE = "not installed before"


def display_version(line):
    line = (line or "").strip()
    return line[len("Blender Kit "):] if line.startswith("Blender Kit ") else line


def zip_from_folder(folder, tmpdir, root, upgrade=False):
    """Pack an already-unzipped download into a temporary ZIP with a top "Blender Kit/" folder, so the same safe checks and
    install code run on it."""
    folder = find_pack_folder(folder, root, upgrade)
    out = os.path.join(tmpdir, "pack.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for dp, dns, fns in os.walk(folder):
            for n in dns + fns:
                full = os.path.join(dp, n)
                if os.path.islink(full):
                    sys.exit(f"Refusing this folder; nothing was written: {full} is a link, and links are not allowed.")
            for n in fns:
                full = os.path.join(dp, n)
                arc = TOP + "/" + os.path.relpath(full, folder).replace(os.sep, "/")
                if is_junk(arc):
                    continue
                zi = zipfile.ZipInfo(arc)
                zi.external_attr = (os.stat(full).st_mode & 0o777) << 16
                with open(full, "rb") as f:
                    z.writestr(zi, f.read())
    return out


def same_content(path, zi, zf):
    if os.path.getsize(path) != zi.file_size:
        return False
    with open(path, "rb") as a, zf.open(zi) as b:
        while True:
            x, y = a.read(1 << 20), b.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen and write nothing")
    ap.add_argument("--upgrade-kit", "--upgrade-studio", dest="upgrade_studio", action="store_true",
                    help="a Setup pack only: replace the kit's own files (each backed up first)")
    a = ap.parse_args()
    root = studio_root()
    tmpdir = None
    a.label = os.path.basename(os.path.abspath(a.zip))
    if os.path.isdir(a.zip):
        tmpdir = tempfile.mkdtemp(prefix="studio-pack-")
        a.zip = zip_from_folder(a.zip, tmpdir, root, a.upgrade_studio)
    try:
        install(a, root)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)



def install(a, root):
    if not os.path.isfile(a.zip):
        sys.exit(f"{a.zip} not found. Give the full path to the downloaded ZIP (or to the folder it unzipped into).")
    try:
        zf = zipfile.ZipFile(a.zip)
    except zipfile.BadZipFile:
        sys.exit(f"{a.zip} is not a valid ZIP file. Download it again.")
    plan, problems = [], []
    with zf:
        for zi in zf.infolist():
            if zi.filename.replace("\\", "/").rstrip("/") == TOP or is_junk(zi.filename):
                continue
            try:
                parts = clean_name(zi.filename)
            except ValueError as e:
                problems.append(f"{zi.filename}: {e}")
                continue
            if stat.S_ISLNK(zi.external_attr >> 16):
                problems.append(f"{zi.filename}: links are not allowed")
                continue
            if zi.is_dir() or not parts:
                continue
            rel = "/".join(parts)
            target = os.path.abspath(os.path.join(root, *parts))
            if os.path.commonpath([root, target]) != root:
                problems.append(f"{zi.filename}: path leaves the studio folder")
                continue
            plan.append((zi, rel, target))
        if problems:
            sys.exit("Refusing this ZIP; nothing was written:\n- " + "\n- ".join(problems[:20]))
        if not plan:
            sys.exit("Nothing to install: the ZIP has no files inside a \"Blender Kit/\" folder.")
        setup_pack = is_setup_pack(zf)
        upgrade = bool(a.upgrade_studio and setup_pack)
        if setup_pack and not a.upgrade_studio:
            sys.exit(SETUP_REFUSAL)
        for zi, rel, target in plan:           # refuse the whole install before anything is written
            if os.path.isdir(target):
                problems.append(f"{rel}: a folder with that name exists in the studio")
                continue
            d = os.path.dirname(target)
            while len(d) > len(root) and os.path.commonpath([root, d]) == root:
                if os.path.isfile(d):
                    problems.append(f"{rel}: a file named {os.path.relpath(d, root)} is in the way")
                    break
                d = os.path.dirname(d)
        if problems:
            sys.exit("Refusing this install; nothing was written:\n- " + "\n- ".join(problems[:20]))
        versions = []
        for zi, rel, target in plan:
            parts = rel.split("/")
            if len(parts) == 4 and parts[:2] == [".claude", "skills"] and parts[3] == "VERSION":
                with zf.open(zi) as f:
                    new_v = f.read(300).decode("utf-8-sig", "replace").splitlines()[:1]
                try:
                    with open(target, encoding="utf-8-sig") as f:
                        old_v = f.readline().strip() or "unknown"
                except (OSError, UnicodeDecodeError):        # no (readable) VERSION: a first install if the pack's skill folder is not there either
                    old_v = "unknown" if os.path.isdir(os.path.dirname(target)) else "not installed before"
                versions.append((display_version(new_v[0] if new_v else ""), display_version(old_v)))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_root = os.path.join(root, ".kit", "backups", stamp)
        n = 2
        while os.path.exists(backup_root):        # two installs in the same second must not share (and overwrite) one backup
            backup_root = os.path.join(root, ".kit", "backups", f"{stamp}-{n}")
            n += 1
        new, replaced, same, kept = [], [], [], []
        for zi, rel, target in plan:
            exists = os.path.exists(target)
            if is_never(rel) or (exists and is_protected(rel, upgrade)):
                kept.append(rel)
                continue
            if exists and same_content(target, zi, zf):
                same.append(rel)
                continue
            if a.dry_run:
                (replaced if exists else new).append(rel)
                continue
            if exists:
                b = os.path.join(backup_root, *rel.split("/"))
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(target, b)
                replaced.append(rel)
            else:
                new.append(rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + ".installing"
            with zf.open(zi) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            mode = (zi.external_attr >> 16) & 0o777
            if mode & 0o100:
                os.chmod(tmp, 0o755)
            os.replace(tmp, target)
    tag = "Would install" if a.dry_run else "Installed"
    print(f"{tag} {a.label} into {root}")
    for new_v, old_v in versions:
        print(f"  {new_v} (not installed before)" if old_v == NOT_BEFORE else f"  {new_v} (installed before: {old_v})")
    if a.upgrade_studio and not setup_pack:
        print("  note: --upgrade-kit only applies to a Setup pack; it was ignored.")
    print(f"  new files: {len(new)}   updated: {len(replaced)}   already identical: {len(same)}   kit files kept: {len(kept)}")
    for rel in kept:
        print(f"  kept (not overwritten): {rel}")
    if replaced and not a.dry_run:
        print(f"  the old versions of the {len(replaced)} updated files are in {backup_root}")
    skills = sorted({r.split("/")[2] for _, r, _ in plan if r.startswith(".claude/skills/") and r.count("/") >= 3})
    if skills:
        print("  skills in this pack: " + ", ".join(skills))


if __name__ == "__main__":
    main()
