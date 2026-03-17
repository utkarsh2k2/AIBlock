# Resolving PR merge conflicts

## 1. See which branch is the base of your PR

On GitHub, open your PR. The **base** branch (e.g. `main` or `claude/ai-content-detection-mvp`) is the one you're merging into. Note its name.

## 2. Merge the base into your branch locally

In your repo folder, with your PR branch checked out (e.g. `claude/ai-content-detection-mvp-If5BB`):

```bash
git fetch origin
git merge origin/BASE_BRANCH
```

Replace `BASE_BRANCH` with the actual base branch name (e.g. `main` or `claude/ai-content-detection-mvp`).

If Git reports "Already up to date", there are no conflicts from that base. If it says "Automatic merge failed; fix conflicts", continue below.

## 3. Find conflicted files

```bash
git status
```

Files listed as "both modified" have conflicts.

## 4. Edit conflicted files

Open each conflicted file. You'll see:

```
<<<<<<< HEAD
your branch's version
=======
base branch's version
>>>>>>> origin/BASE_BRANCH
```

- Keep the correct version (or combine both).
- Delete the conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) and any code you don't want.

## 5. Mark as resolved and push

```bash
git add .
git commit -m "Resolve merge conflicts with BASE_BRANCH"
git push origin YOUR_BRANCH
```

Replace `YOUR_BRANCH` with your PR branch name (e.g. `claude/ai-content-detection-mvp-If5BB`).

## 6. Refresh the PR on GitHub

The PR will update. If all conflicts are fixed, you can merge it.
