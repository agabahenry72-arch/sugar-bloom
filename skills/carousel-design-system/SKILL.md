---
name: carousel-design-system
description: Agency-wide carousel design system. Turns a copy brief into on-brand 4:5 social carousel slides (1080x1350 PNGs plus a PDF) for any client, using a shared library of preset styles and each client's brand kit (colours, fonts, logo), with an automated QA check before export and versioned revisions. Use whenever someone asks to design, build, render, export, preview, revise or restyle an Instagram/LinkedIn carousel or slide post for a client; to set up or update a client's brand kit for carousels; to preview carousel styles for a client; or to add a new carousel style from reference designs.
---

# Carousel design system

One skill for every client. **Styles** (layouts) and **brand kits** (colours, fonts, logo) are separate, so any style renders in any client's branding. Copy comes in a fixed **brief** format. Every render goes through **automated QA**; only carousels that pass are exported, into a new numbered version.

All commands run from this skill's folder:

```bash
python scripts/carousel.py <command> ...
```

## First time in a session

Run `python scripts/carousel.py env`. If it says NOT READY, install what it names: `pip install -r requirements.txt`, then `python -m playwright install chromium`. If neither is possible (no network), tell the user that rendering isn't available in this environment. Don't try to hand-draw slides instead.

**Where to save output:** pass `--out <folder>` pointing at the place the user can open or download files from (for example the session's outputs folder). If you don't, files go to `./carousel-output/`.

## Workflow

### 1. Find the client's brand kit
`python scripts/carousel.py brands` lists clients. Use the client id in the brief.

If the client isn't there, **don't invent brand colours or fonts.** Ask for their hex colours, font files (or exact font names) and logo files (a version for light backgrounds plus one for dark backgrounds). Then:
`new-brand <client-id> --name "Client Name"`, put the files in the new folder, fill in `brand.yaml` (see reference/brand-kits.md) and run `brand-check <client-id>` until it says OK. Read the `notes` field in `brand.yaml` before touching any copy.

### 2. Choose a style
`python scripts/carousel.py styles` lists the library with descriptions. If the user hasn't chosen one, suggest the best fit from the descriptions, or run `showcase --brand <client-id>` and show the contact sheets so they can choose with their own branding.

### 3. Write the brief
Accept either format (full spec in reference/brief-format.md):
- **Copy brief** (`.md`): what copywriters fill in from `templates/brief-template.md`
- **YAML brief** (`.yaml`): the structured version

If the user gives raw copy instead, structure it into a brief yourself. Pick a layout per slide (`cover`, `text`, `list`, `quote`, `stat`, `image`, `cta`), starting with a `cover` and usually ending with a `cta`.

**Keep the client's approved wording exactly.** Your job is to split the copy into slides and fields, not to rewrite it. Only edit copy when the user asks or approves. Use `**double asterisks**` to highlight a key phrase (at most one per headline). Save the brief as a file next to the output so revisions can edit it.

### 4. Render
```bash
python scripts/carousel.py render <brief> --out <folder>
```
Exit code 0 means it was exported. Exit code 2 means QA failed and nothing was exported. Exit code 1 means the brief or brand kit is invalid, and the message lists every problem with the slide and field.

### 5. If QA fails
Read `qa-report.md` and look at `qa-sheet.png` in the `_qa-failed` folder. Each issue names the slide, the field and the fix.
- **Fix layout issues yourself:** change a slide's `tone`, split a long list or paragraph across two slides, or switch layout.
- **Copy issues** (too long, placeholders like `[CLIENT]` or `TODO`): propose specific trims or replacements and get the user's OK, unless they've already told you to tighten copy as needed.
- Never use `--force` unless the user has seen the specific errors and explicitly accepts them.

Then render again. Use `check <brief>` for fast QA-only iterations that don't export anything.

### 6. Deliver
Show the user `contact-sheet.png` from the new version folder (`<out>/<client>/<carousel>/vNN/`). Give them the PNG slides (in posting order, `-01`, `-02`, …) and the PDF (for LinkedIn document posts). Mention any QA **warnings** in one line each.

### 7. Revisions
Revisions always go through the brief, never by editing PNGs. Edit the brief file, re-render, and a new version (`v02`, `v03`, …) is created. Older versions are kept, and the command prints what changed since the last version. Quick mappings:

| Request | Change |
|---|---|
| "Change the headline on slide 3" | that slide's `headline` |
| "Make slide 4 darker / use the brand colour" | slide `tone: dark` / `tone: brand` (also `light`, `accent`) |
| "Too much text on slide 2" | trim (with approval) or split into two slides |
| "Try it in another style" | `--style <id>` (or edit `style:` in the brief) |
| "Add a slide" | insert it in `slides`; numbering updates automatically |
| "Hide slide numbers / swipe arrow / logo" | `slide_numbers: no`, `swipe_hint: no`, `logo: no` |
| "Their brand colour / logo changed" | edit `brands/<client>/brand.yaml` (affects all future renders for that client; confirm first) |

## Commands

| Command | What it does |
|---|---|
| `env` | Check that rendering works here |
| `brands` / `brand-check <id>` | List clients / validate a brand kit and show its derived colour tones |
| `new-brand <id> --name "…"` | Create a brand kit folder from the template |
| `styles` | List styles with descriptions |
| `showcase --brand <id> [--styles a,b]` | Preview styles in a client's branding |
| `convert <brief.md> [-o x.yaml]` | Validate a copy brief and convert it to YAML |
| `check <brief>` | QA only: previews and report, nothing exported |
| `render <brief> [--style] [--brand] [--out] [--scale 2] [--force]` | QA, then export a new version |
| `style-check <style>` | Lint a style and stress-test it with the example brands |

Add `--json` to `render`, `check`, `styles` and `brands` for machine-readable output.

## Reference (read when needed)
- `reference/brief-format.md`: every field per layout, inline formatting, both formats
- `reference/brand-kits.md`: brand.yaml fields, fonts, logos, how colour tones are derived
- `reference/qa-checks.md`: what each QA check means and how to fix it
- `reference/style-authoring.md`: adding a new style from the agency's reference designs
