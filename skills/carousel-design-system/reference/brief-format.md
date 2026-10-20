# Brief format

A brief is the single source of truth for a carousel: client, style, and the copy for every slide. There are two interchangeable formats. Both are validated the same way, and a typo such as `headine` is reported with a suggestion.

## Copy brief (`.md` or `.txt`): for copywriters

Blank template: `templates/brief-template.md`.

```text
CLIENT: example-kite
STYLE: bold-minimal
TITLE: The 50/30/20 budget, explained

## 1. cover
EYEBROW: Money basics
HEADLINE: The **50/30/20** budget, explained in 60 seconds
SUBHEAD: The simplest budgeting rule there is.

## 2. list
HEADLINE: Split every paycheck three ways
- 50% Needs | Rent, groceries, bills
- 30% Wants | Eating out, trips, hobbies
- 20% Future you

## 3. text
TONE: dark
HEADLINE: Over budget on wants?
BODY:
That's normal. Don't cut everything at once.

Pick one category this month and trim it by 10%.
```

Rules:
- The header lines (`CLIENT`, `STYLE`, `TITLE`, plus the optional settings below) come before the first slide.
- Each slide starts with `## <number>. <layout>`. The number is optional and only there to help humans.
- Fields are `KEY: value`, and keys aren't case-sensitive. A value can continue over the following lines until the next `KEY:` or slide heading. A blank line inside a value starts a new paragraph.
- On `list` slides, every bullet (`-`, `*`, `•` or `1.`) is an item. Write `Title | body` for an item with supporting copy.
- Lines starting with `//` are comments. A single `# Title` line is ignored.
- Pasting from Google Docs or Notion works, as long as the keys stay at the start of their lines.

## YAML brief (`.yaml`)

```yaml
client: example-roastery
style: bold-minimal
title: 5 ways to brew better coffee at home
slides:
  - layout: cover
    headline: 5 ways to brew **better** coffee
  - layout: list
    items:
      - Buy whole beans                       # title only
      - title: Grind just before brewing      # title + body
        body: A burr grinder gives an even grind.
```

`carousel.py convert brief.md` validates a copy brief and writes the YAML version.

## Top-level fields

| Field | Required | Meaning |
|---|---|---|
| `client` | yes | Brand kit id (folder under `brands/`) or a path to a brand folder |
| `style` | yes | Style id (`carousel.py styles`) |
| `title` | yes | Internal name; also the output folder and file names |
| `handle` | no | Overrides the footer handle from the brand kit |
| `footer` | no | Custom footer text (wins over `handle`) |
| `slide_numbers` | no | `yes`/`no` (default yes) |
| `swipe_hint` | no | `yes`/`no` (default yes); the arrow on every slide except the last |
| `logo` | no | `yes`/`no` (default yes) |
| `lang` | no | Language code for the page (default `en`) |
| `notes` | no | Free text; ignored by the renderer |

At most 20 slides (the Instagram and LinkedIn limit).

## Layouts and their fields

Every slide also accepts `tone` (`light`, `brand`, `dark`, `accent`), which overrides the style's default background for that slide, and `notes` (ignored).

| Layout | Required | Optional | Use for |
|---|---|---|---|
| `cover` | `headline` | `eyebrow`, `subhead` | First slide / hook |
| `text` | `body` | `eyebrow`, `headline` | One idea, a short paragraph |
| `list` | `items` | `eyebrow`, `headline`, `numbered` (default yes) | Tips, steps, checklists (max 10 items; styles are designed for 4–5) |
| `quote` | `quote` | `author`, `role` | Testimonials, expert quotes |
| `stat` | `stat`, `label` | `eyebrow`, `body`, `source` | One big number |
| `image` | `image` | `headline`, `caption`, `fit` (`cover`/`contain`), `focus` (`center`/`top`/`bottom`/`left`/`right`) | Photos and product shots (path relative to the brief) |
| `cta` | `headline` | `eyebrow`, `body`, `button` | Final slide: follow, save, shop, visit |

## Inline formatting

| Write | Get |
|---|---|
| `**words**` | Highlighted in the slide's highlight colour (readable contrast is chosen automatically) |
| `*words*` | Italic |
| A new line | A line break |
| A blank line | A new paragraph |

Everything else is shown exactly as written. HTML is escaped. An unmatched `**` or a stray `*` is an error rather than a stray asterisk on the slide.

## Copy length

Each style declares soft character limits per field (in its `style.yaml`). Going over produces a QA **warning**, not an error. Text automatically shrinks a little to fit, and QA only **fails** if copy still doesn't fit at the smallest allowed size.
