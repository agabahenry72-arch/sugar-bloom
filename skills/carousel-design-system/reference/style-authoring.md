# Adding a style from reference designs

A style is a **layout**, not a colour scheme. When the agency supplies a reference carousel, extract its structure: grid, type scale, where the logo and page numbers sit, decorative elements, and how each slide type is arranged. Then express every colour and font as a token, so the style works for all clients.

## 1. Copy a starter

```bash
cp -r styles/bold-minimal styles/<new-style-id>
```
Then edit `style.yaml`: `name`, `description` (people choose styles from this text, so describe the look and when to use it), `best_for`, `safe_margin`, `meta_margin`, default `tones` per layout, and copy `limits`.

## 2. Templates: `slides.html.j2`

One Jinja macro per layout, each taking `(s, c)`:
- `s` is the slide's fields from the brief, with optional fields set to `None`. Use `s["items"]` for list items (each has `title` and `body`), and `s.image_src` for the image data.
- `c` is the context: `index`, `total`, `is_first`, `is_last`, `tone`, `logo_src`, `brand_name`, `footer`, `slide_numbers`, `swipe_hint`.

Required macros: `cover`, `text`, `list`, `quote`, `stat`, `image`, `cta`.

Use the shared helpers in `scripts/engine/templates/_ui.html.j2` (`{% import "_ui.html.j2" as ui %}`):

```jinja
{{ ui.text("h2", s.headline, "headline", role="headline", cls="h my-title") }}
{{ ui.logo(c) }}  {{ ui.page_number(c) }}  {{ ui.handle(c) }}  {{ ui.swipe(c) }}  {{ ui.progress(c) }}
```

**Every visible piece of copy must have** `data-qa="text"`, `data-qa-role` (`headline`, `body` or `meta`) and `data-field`. `ui.text` adds all three, and copy without them escapes QA. Images need `data-qa="image"`.

Wrap each slide's main copy area in a **fit box**:
```html
<main class="..." data-fit-box data-field="body"> ... </main>
```
The box needs a constrained height, for example `flex: 1 1 auto` inside the slide's flex column. Write every font size and gap inside it as `calc(<size>px * var(--fit, 1))` so auto-fit can shrink it. You can set `data-fit-min="0.7"` to change the minimum (default 0.65).

## 3. CSS: `style.css`

The slide is a 1080×1350 flex column (`.slide`), with classes `tone-*`, `layout-*`, `is-first` and `is-last`.

Use **only** these tokens:

| Token | Use |
|---|---|
| `--bg`, `--fg`, `--muted`, `--line` | Slide background, text, secondary text, hairlines |
| `--hl` | Highlight for large text, rules, shapes (≥3:1) |
| `--hl-small` | Highlight for small text such as eyebrows and numbers (≥4.5:1) |
| `--on-hl` | Text on a `--hl` fill (buttons, badges) |
| `--card`, `--on-card`, `--card-muted`, `--card-hl`, `--card-hl-small` | Panels and cards |
| `--font-heading`, `--font-body`, `--heading-weight`, `--body-weight`, `--body-bold-weight` | Typography (the `.h` class applies the heading font and settings) |
| `--brand-primary`, `--brand-accent`, … | Raw brand colours: decoration only, never text |

`color-mix(in srgb, var(--hl) 20%, transparent)` is fine for decorative tints. Hard-coded hex colours or font families fail `style-check`.

## 4. Test

```bash
python scripts/carousel.py style-check <new-style-id>
```
This lints the CSS and template, then renders `briefs/showcase.yaml` and `briefs/stress.yaml` (long copy in every tone) with both example brands. The style is ready when it prints **STYLE OK**. Look at the contact sheets it prints, too: QA proves the style is *correct*, but only a human can judge whether it looks right.

Finally, regenerate the preview the team sees in the style list:
```bash
python scripts/carousel.py showcase --brand example-roastery --styles <new-style-id> --out /tmp/preview
cp /tmp/preview/example-roastery/_showcase/<new-style-id>.png styles/<new-style-id>/preview.png
```
