# Brand kits

One folder per client in `brands/<client-id>/`:

```text
brands/acme-coffee/
  brand.yaml
  logo.svg            # for light backgrounds
  logo-inverse.svg    # for dark / brand-colour backgrounds
  fonts/
    AcmeSerif-Bold.otf
    Inter-Variable.ttf
```

Create one with `carousel.py new-brand acme-coffee --name "Acme Coffee"`, then validate it with `carousel.py brand-check acme-coffee`. Folders starting with `_` are ignored. Extra brand folders, such as a shared drive, can be added with the `CAROUSEL_BRANDS_DIR` environment variable. They're searched first.

## brand.yaml

```yaml
name: Acme Coffee
handle: "@acmecoffee"
website: acme.coffee

colors:            # hex, quoted
  primary: "#B4441B"
  secondary: "#2B1D16"   # optional
  accent: "#F2B544"      # optional
  background: "#FBF4EA"
  surface: "#FFFFFF"     # optional
  text: "#2B1D16"
  # optional overrides: dark, on_primary, on_accent, on_dark

fonts:
  heading:
    family: DM Serif Display
    weight: 400
    files: [fonts/DMSerifDisplay-Regular.ttf]
    fallback: Georgia, serif     # optional
    letter_spacing: -0.01em      # optional
    uppercase: false             # optional
    line_height: 1.05            # optional
  body:
    family: DM Sans
    weight: 400
    bold_weight: 700
    files: [fonts/DMSans-Variable.ttf]

logo:
  default: logo.svg
  inverse: logo-inverse.svg
  height: 56

notes: Tone of voice, spelling, words to avoid…
```

### Colours
Only `primary`, `background` and `text` are required. The rest default sensibly: `accent` falls back to `secondary`, which falls back to `primary`. `dark` is the darkest of secondary/text/primary, or near-black.

### Fonts
- Font files are **embedded** in every export, so the brand typeface shows up even on machines that don't have it installed. Accepted formats: `.ttf`, `.otf`, `.woff`, `.woff2`.
- Variable fonts (file name containing `[` or `Variable`, or `variable: true`) cover all weights. For static files, the weight is read from the file name (`-Bold` is 700, `-SemiBold` 600, and so on). You can also list files explicitly: `- {path: fonts/X.otf, weight: 600, style: italic}`.
- If you leave out `files`, the font must be installed on the rendering machine. QA **fails** if it isn't, rather than silently using a fallback.
- QA warns if a style uses a weight the kit doesn't include, because the browser would fake it.
- Check the font licence allows embedding in images and PDFs. Most commercial licences need a desktop and/or ePub/PDF embedding licence.

### Logos
SVG is best; transparent PNG also works. Provide `inverse` for dark and brand-colour backgrounds. Which logo is used depends on how dark each slide's background is.

## How colours become tones

Styles never use brand colours directly. Each slide has a **tone**, and the engine works out readable colours for it:

| Tone | Background | Text | Highlight (for large text) |
|---|---|---|---|
| `light` | background | text | first of primary → accent → secondary with ≥3:1 contrast |
| `brand` | primary | on_primary (auto) | accent → secondary → background |
| `dark` | dark | on_dark (auto) | accent → primary → background |
| `accent` | accent | on_accent (auto) | primary → dark → secondary |

Each tone also gets:
- `--muted`: softer secondary text that still keeps 4.5:1 contrast.
- `--hl-small`: the highlight for small text, which needs 4.5:1. It falls back to the text colour.
- `--line`: for hairlines.
- `--card`, `--on-card`, `--card-muted`, `--card-hl`, `--card-hl-small`: for panels.

`brand-check` prints the result. If a pair can't reach the required contrast, it warns, and QA will catch any text that's actually affected.
