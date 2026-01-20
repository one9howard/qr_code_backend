# Git Push to GitHub - Step by Step Guide

## Overview
This guide shows how to push a local folder to a new GitHub repository.

---

## Prerequisites
- Git installed on your computer
- A GitHub account
- An empty repository created on GitHub (e.g., `https://github.com/username/repo-name`)

---

## The 5 Steps

### Step 1: Initialize Git Repository
```bash
cd /path/to/your/project
git init
```
This creates a hidden `.git` folder that tracks your project.

---

### Step 2: Add Remote Origin
```bash
git remote add origin https://github.com/username/repo-name.git
```
This links your local repo to the GitHub repo.

---

### Step 3: Stage All Files
```bash
git add -A
```
This stages all files to be committed. Use `git add filename` for specific files.

---

### Step 4: Commit Changes
```bash
git commit -m "Your commit message here"
```
This saves a snapshot of your staged files with a description.

---

### Step 5: Push to GitHub
```bash
git branch -M main
git push -u origin main
```
- `branch -M main` renames the branch to "main"
- `push -u origin main` uploads to GitHub and sets up tracking

---

## Quick Reference (All Commands)
```bash
git init
git remote add origin https://github.com/username/repo-name.git
git add -A
git commit -m "Initial commit"
git branch -M main
git push -u origin main
```

---

## Common Errors

| Error | Solution |
|-------|----------|
| "not a git repository" | Run `git init` first |
| "remote origin already exists" | Use `git remote set-url origin URL` |
| "authentication failed" | Set up GitHub credentials or use SSH |
| "rejected - non-fast-forward" | Pull first: `git pull origin main --allow-unrelated-histories` |

---

## Future Pushes
Once set up, pushing new changes is just:
```bash
git add -A
git commit -m "Description of changes"
git push
```

---

*To save as PDF: Open this file in a browser or VS Code, then Print → Save as PDF*
