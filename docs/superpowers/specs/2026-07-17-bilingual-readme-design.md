# Bilingual README Design

## Goal

Provide an operator-ready Vietnamese and English README for 3D Scanner without
embedding any machine-specific user profile path.

## Structure

- `README.md` remains the Vietnamese default shown by Git hosting services.
- `README.en.md` is the English equivalent with the same section order and
  operational meaning.
- Both files begin with a compact language switcher:

  ```markdown
  🇻🇳 [Tiếng Việt](README.md) · 🇬🇧 [English](README.en.md)
  ```

## Portable paths

- Refer to the saved RTAB-Map database location as
  `%USERPROFILE%\Documents\RTAB-Map`, not a named Windows account path.
- Use `$ProjectRoot` in PowerShell setup and launch examples. Show how to set
  it with `Get-Location` after changing to the cloned project directory.
- Keep repository-relative paths (for example `scripts\17_3d_scanner.py` and
  `outputs\scanner_3d`) relative and portable.

## Content parity

Each language version covers the same workflow: requirements, Git LFS setup,
launching, saving a session, exporting a raw OBJ, cropping, auto-pause safety,
file locations, and prototype scope. Button labels and executable names stay
literal where they are part of the user interface.

## Verification

- Both files contain a reciprocal language link.
- Neither file contains a `C:\Users\<name>` path.
- Both files mention the portable RTAB-Map location and the launch script.
- Review the Markdown headings, fenced PowerShell blocks, and links manually.
