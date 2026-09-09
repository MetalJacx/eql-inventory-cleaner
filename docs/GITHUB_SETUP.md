# GitHub Setup Guide

## Recommended repository name

`eql-inventory-cleaner`

## Repository description

> Extensible desktop inventory-cleanup utility for EverQuest Legends. Finds merge candidates today, with additional cleaning tools planned. Windows, Linux, and Bazzite friendly.

## Suggested GitHub topics

- everquest
- everquest-legends
- eql
- inventory
- item-upgrades
- inventory-cleaner
- tkinter
- python
- bazzite
- linux
- windows

## About section

Use the repository description above. Enable **Releases**. A project website is optional; leave it blank unless you later create one.

## First push

From inside this folder:

```bash
git init
git add .
git commit -m "Initial public release v1.5"
git branch -M main
git remote add origin git@github.com:YOUR-USERNAME/eql-inventory-cleaner.git
git push -u origin main
```

If you use HTTPS instead of SSH:

```bash
git remote add origin https://github.com/YOUR-USERNAME/eql-inventory-cleaner.git
```

## Create the v1.5 release

After the `main` branch is on GitHub:

```bash
git tag -a v1.5 -m "EQL Inventory Cleaner v1.5"
git push origin v1.5
```

The included GitHub Actions workflow builds Windows and Linux standalone binaries. On a version tag, it also creates the GitHub Release and attaches the generated binaries.

## Bazzite portable `.run`

If you have the separately built Bazzite `.run` file, attach it to the v1.5 Release manually as an additional release asset.

Suggested filename:

`EQL-Inventory-Cleaner-Bazzite-x86_64-v1.5.run`

## Suggested release title

`EQL Inventory Cleaner v1.5`

## Suggested release summary

> First public release of EQL Inventory Cleaner: an extensible read-only desktop utility for cleaning EverQuest Legends inventory exports. The first tool focuses on duplicate gear and item merging, with merge XP projections, persistent filters, and Windows/Linux/Bazzite support.

Full release notes are in `RELEASE_NOTES.md`.
