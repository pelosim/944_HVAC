# Setting Up Git + GitHub for the 944S HVAC Project
*Written for a complete Git beginner. Do these steps in order.*

---

## THE BIG PICTURE

```
   Your Pi  ──push──▶  GitHub (cloud backup)  ◀──pull──  (any other computer)
  (you edit
   & run here)
```

- You edit files on the Pi and run the HVAC.
- `git push` uploads your changes to GitHub for safekeeping + history.
- If the Pi's SD card ever dies, everything is safe on GitHub.
- New Claude files: download → drop into the Pi's project folder → commit → push.

---

## PART 1 — MAKE A GITHUB ACCOUNT (one time, ~3 min)

1. Go to **https://github.com** and click **Sign up**.
2. Pick a username, email, password.
3. Verify your email when GitHub sends the confirmation.
4. That's it — don't create a repository on the website yet. We'll do it from
   the Pi in Part 4.

---

## PART 2 — SET UP GIT ON THE PI (one time, ~5 min)

SSH into the Pi (or use its terminal), then:

```bash
# Install git (probably already there, but just in case)
sudo apt update && sudo apt install -y git

# Tell git who you are (use your GitHub email)
git config --global user.name "Mark Pelosi"
git config --global user.email "your-github-email@example.com"

# Make 'main' the default branch name
git config --global init.defaultBranch main
```

---

## PART 3 — CREATE A SECURE LOGIN TOKEN (one time, ~4 min)

GitHub no longer accepts your password from the command line. Instead you use
a **Personal Access Token** (PAT) — think of it as an app-specific password.

1. On GitHub website, click your **profile picture (top-right)** → **Settings**.
2. Scroll to the very bottom → **Developer settings** (left sidebar).
3. Click **Personal access tokens** → **Tokens (classic)**.
4. Click **Generate new token** → **Generate new token (classic)**.
5. Give it a name like `pi-hvac`.
6. Set **Expiration** to `No expiration` (or 1 year).
7. Check the box next to **repo** (this checks all the sub-boxes — that's what you want).
8. Scroll down, click **Generate token**.
9. **COPY THE TOKEN NOW** — it's a long string like `ghp_xxxxxxxx`. You will
   NEVER see it again after leaving this page. Paste it somewhere safe
   temporarily (a note). You'll use it as your "password" when git asks.

To make the Pi remember it so you only type it once:
```bash
git config --global credential.helper store
```

---

## PART 4 — TURN YOUR HVAC FOLDER INTO A REPOSITORY (one time)

```bash
cd ~/hvac

# Initialize git in this folder
git init

# Add the .gitignore file first (see below for getting it here)
# — this tells git to skip node_modules, build, etc.

# Stage all your real files (git respects .gitignore)
git add .

# Take the first snapshot ("commit")
git commit -m "Initial commit — working HVAC system"
```

**Getting the .gitignore file onto the Pi:** Download it from Claude, then
either scp it or just create it by hand:
```bash
nano ~/hvac/.gitignore
```
Paste the contents Claude gave you, save with Ctrl+O, Enter, Ctrl+X.

*(Do the .gitignore step BEFORE `git add .` so the junk folders never get tracked.)*

---

## PART 5 — CREATE THE REPO ON GITHUB AND CONNECT IT (one time)

1. On GitHub website, click the **+** (top-right) → **New repository**.
2. **Repository name:** `944s-hvac`
3. Choose **Private** (you can flip to public later).
4. **DON'T** check "Add a README" or ".gitignore" — leave it empty.
5. Click **Create repository**.
6. GitHub shows you a page with commands. Ignore most of it — use these on the Pi:

```bash
cd ~/hvac

# Connect your local folder to the GitHub repo
# (replace YOUR-USERNAME with your actual GitHub username)
git remote add origin https://github.com/YOUR-USERNAME/944s-hvac.git

# Push your files up for the first time
git push -u origin main
```

When it asks:
- **Username:** your GitHub username
- **Password:** paste the TOKEN from Part 3 (not your real password!)

Because you set `credential.helper store`, it remembers the token after this.
Refresh your GitHub repo page — your files are now in the cloud.

---

## PART 6 — YOUR EVERYDAY WORKFLOW (this is all you need going forward)

### When you change something on the Pi (or drop in a new Claude file):

```bash
cd ~/hvac

# See what changed
git status

# Stage everything you changed
git add .

# Snapshot it with a message describing what you did
git commit -m "Added state persistence and bigger fonts"

# Upload to GitHub
git push
```

That's the whole loop: **add → commit → push.** Three commands.

### Deploying a new Claude dashboard file with git:

```bash
# 1. On your Mac: download the file, scp it to the Pi's src folder
scp /Users/markpelosi/Downloads/HVACDashboard_5.jsx mark@192.168.1.142:/home/mark/hvac/dashboard/src/HVACDashboard.jsx

# 2. On the Pi: rebuild, commit, push, run
cd ~/hvac/dashboard && npm run build
cd ~/hvac
git add .
git commit -m "New dashboard layout"
git push
pkill -f hvac_backend && python3 hvac_backend.py
```

Now GitHub has every version. No more `_2`, `_3`, `_FIXED` files piling up.

---

## PART 7 — GETTING IT BACK IF THE PI DIES (disaster recovery)

On a fresh Pi (or your Mac), one command clones everything back:

```bash
git clone https://github.com/YOUR-USERNAME/944s-hvac.git
cd 944s-hvac
# Reinstall dependencies (these were gitignored, so re-fetch them)
cd dashboard && npm install && npm run build
```

Your code, history, and settings structure — all restored.

---

## COMMON GIT COMMANDS CHEAT SHEET

| Command | What it does |
|---|---|
| `git status` | Show what's changed since last commit |
| `git add .` | Stage all changes for the next commit |
| `git commit -m "message"` | Snapshot staged changes |
| `git push` | Upload commits to GitHub |
| `git pull` | Download commits from GitHub |
| `git log --oneline` | See your history of commits |
| `git diff` | See exact line-by-line changes |
| `git checkout -- file.py` | Undo changes to a file (revert to last commit) |

---

## IF SOMETHING GOES WRONG

| Problem | Fix |
|---|---|
| `git push` asks for password every time | Run `git config --global credential.helper store`, push once more with token |
| "Authentication failed" | Your token is wrong/expired — make a new one (Part 3) |
| "remote origin already exists" | `git remote remove origin` then re-add it |
| Accidentally committed node_modules | Check `.gitignore` exists and has `dashboard/node_modules/`, then `git rm -r --cached dashboard/node_modules` |
| Want to undo last commit (keep changes) | `git reset --soft HEAD~1` |

---

## WHY THIS IS WORTH IT

- **One source of truth** — no guessing which `_FIXED` file is current.
- **Full history** — every version saved; roll back anytime.
- **Off-site backup** — SD card death no longer loses your work.
- **Clean deploys** — `git pull` instead of hunting through Downloads.
