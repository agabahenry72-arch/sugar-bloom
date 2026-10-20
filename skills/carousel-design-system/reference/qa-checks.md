# QA checks

Every `render` and `check` runs these checks. **Errors** block export unless you pass `--force`, and the report records that it was forced. **Warnings** are reported but don't block. Results go to `qa-report.md`, `qa-report.json` and the annotated `qa-sheet.png` or `contact-sheet.png`, where issues are numbered boxes on the slides.

| Check | Level | What it catches | Usual fix |
|---|---|---|---|
| `placeholders` | error | `[CLIENT NAME]`, `TODO`, `TBD`, `XXX`, `lorem ipsum`, `{{ }}`, `<…>` left in copy | Replace with final copy |
| `overflow` | error | Copy that doesn't fit its area even at the smallest allowed size, or a single word too long for its line | Shorten, or split across two slides |
| `contrast` | error | Text below WCAG AA: 4.5:1, or 3:1 for large text (≥64px, or ≥48px and bold). Measured on the rendered pixels behind each line, so it works on images, gradients and decorative shapes | Change the slide `tone`, or fix the brand colours |
| `safe-zone` | error | Copy outside the style's safe margin, which risks being cropped in feeds or overlapped by app UI | Shorten the copy, or fix the style |
| `overlap` | error | Two pieces of copy, or copy and the logo, colliding | Shorten one of them |
| `fonts` | error | A brand font that is unavailable or fails to load, which would mean a fallback font in the export | Add the font files to the brand kit |
| `fonts` | warning | A style using a weight the brand kit doesn't include (faux bold) | Add that weight, or change the weight in brand.yaml |
| `logo` | error | Logo file that won't load | Fix the logo file |
| `images` | error / warning | Image that won't load (error) / image shown more than 1.15× its real size, so it looks soft (warning) | Use a larger image |
| `text-shrink` | warning | Copy auto-shrunk below 82% of the design size | Fine to ship; trim if it should match the other slides |
| `copy-length` | warning | Field longer than the style's designed limit, or more list items than designed for | Trim, or split |
| `orphans` | warning | Headline ending with a lone short word on its own line | Reword slightly, or add a line break |
| `slide-count` | warning | Only one slide | Add slides, or confirm a single image |
| `export-png` | error | PNG not exactly 1080×1350 (or 2160×2700 with `--scale 2`) | Indicates a broken style; report it |
| `export-pdf` | error | PDF page count or 4:5 page size wrong | Indicates a broken style; report it |

## Reading a failure

```text
QA FAILED: nothing exported  ·  Kite Finance · Card Stack · 3 slides
  #1 ERROR   [slide 1 · headline] Placeholder text '[CLIENT]' left in the copy.
           fix: Replace it with final copy.
```

`slide 1 · headline` is the exact brief field to edit. Fix the brief and run `render` again.

## How auto-fit works

Styles mark each copy area as a *fit box*. Before QA runs, text in a fit box shrinks in small steps, down to the style's minimum (65% by default), until nothing overflows. QA then measures the result. So a little extra copy is absorbed automatically, and far too much copy is caught instead of being silently clipped.
