"""Command-line interface: python scripts/carousel.py <command> ..."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path

from . import brand as brand_mod
from . import brief as brief_mod
from . import render as render_mod
from . import style as style_mod
from .paths import SKILL_ROOT, CarouselError, default_output_root

EXIT_OK, EXIT_ERROR, EXIT_QA_FAILED = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CarouselError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="carousel.py", description="Agency carousel design system: brief -> QA -> PNG + PDF.")
    sub = p.add_subparsers(dest="command", required=True)

    for name, help_text in (("render", "QA-check and export a carousel (PNG + PDF), as a new version"),
                            ("check", "QA-check only: previews + report, nothing exported")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("brief", help="brief file (.yaml or copy brief .md/.txt)")
        cmd.add_argument("--style", help="override the brief's style")
        cmd.add_argument("--brand", help="override the brief's client brand")
        cmd.add_argument("--out", help=f"output root (default: {default_output_root()})")
        cmd.add_argument("--json", action="store_true", help="print a JSON summary")
        if name == "render":
            cmd.add_argument("--force", action="store_true", help="export even if QA finds errors (report is kept)")
            cmd.add_argument("--scale", type=int, default=1, choices=(1, 2), help="2 = 2160x2700 PNGs")
        cmd.set_defaults(func=_cmd_render, mode="export" if name == "render" else "check")

    cmd = sub.add_parser("convert", help="convert a copy brief (.md/.txt) to YAML, validating it")
    cmd.add_argument("brief")
    cmd.add_argument("-o", "--output", help="where to write the YAML (default: next to the brief)")
    cmd.set_defaults(func=_cmd_convert)

    cmd = sub.add_parser("styles", help="list the style library")
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(func=_cmd_styles)

    cmd = sub.add_parser("brands", help="list client brand kits")
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(func=_cmd_brands)

    cmd = sub.add_parser("brand-check", help="validate a brand kit and show its derived tones")
    cmd.add_argument("brand")
    cmd.set_defaults(func=_cmd_brand_check)

    cmd = sub.add_parser("new-brand", help="create a brand kit folder from the template")
    cmd.add_argument("id", help="client id, e.g. acme-coffee (lowercase, dashes)")
    cmd.add_argument("--name", required=True, help='client display name, e.g. "Acme Coffee"')
    cmd.add_argument("--dir", help="brands folder to create it in (default: the skill's brands/)")
    cmd.set_defaults(func=_cmd_new_brand)

    cmd = sub.add_parser("showcase", help="preview every style (or some) in a client's brand")
    cmd.add_argument("--brand", required=True)
    cmd.add_argument("--styles", help="comma-separated style ids (default: all)")
    cmd.add_argument("--brief", help="brief to preview with (default: briefs/showcase.yaml)")
    cmd.add_argument("--out", help="output root")
    cmd.set_defaults(func=_cmd_showcase)

    cmd = sub.add_parser("style-check", help="lint a style and stress-test it with the example brands")
    cmd.add_argument("style")
    cmd.add_argument("--out", help="output root")
    cmd.set_defaults(func=_cmd_style_check)

    cmd = sub.add_parser("env", help="check that rendering works on this machine")
    cmd.set_defaults(func=_cmd_env)
    return p


# ---------------------------------------------------------------- render / check


def _cmd_render(args) -> int:
    result = render_mod.run(
        args.brief, style=args.style, brand=args.brand, out_root=args.out, mode=args.mode,
        force=getattr(args, "force", False), scale=getattr(args, "scale", 1),
    )
    if args.json:
        print(json.dumps(_summary(result), indent=2))
    else:
        _print_result(result)
    if result.status == "qa_failed" or (result.status == "checked" and not result.report.passed):
        return EXIT_QA_FAILED
    return EXIT_OK


def _summary(result: render_mod.Result) -> dict:
    return {
        "status": result.status,
        "forced": result.forced,
        "version": result.version,
        "client": result.brand.id,
        "style": result.style.id,
        "out_dir": str(result.out_dir),
        "pngs": [str(p) for p in result.pngs],
        "pdf": str(result.pdf) if result.pdf else None,
        "contact_sheet": str(result.sheet) if result.sheet else None,
        "qa_report": str(result.out_dir / "qa-report.md"),
        "errors": [_issue(i) for i in result.report.errors],
        "warnings": [_issue(i) for i in result.report.warnings],
        "changes": result.changes,
    }


def _issue(issue) -> dict:
    return {"slide": issue.slide, "field": issue.field, "check": issue.check, "message": issue.message, "fix": issue.hint}


def _print_result(result: render_mod.Result) -> None:
    report = result.report
    head = {
        "exported": f"EXPORTED {result.version}" + (" (FORCED despite QA errors)" if result.forced else ""),
        "qa_failed": "QA FAILED: nothing exported",
        "checked": "QA PASSED (check only, nothing exported)" if report.passed else "QA FAILED (check only)",
    }[result.status]
    print(f"{head}  ·  {result.brand.name} · {result.style.name} · {len(result.pngs)} slides")
    print(f"  {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    for n, issue in enumerate(report.issues, start=1):
        tag = "ERROR  " if issue.severity == "error" else "warning"
        print(f"  #{n} {tag} [{issue.label()}] {issue.message}")
        if issue.hint:
            print(f"           fix: {issue.hint}")
    for change in result.changes:
        print(f"  change: {change}")
    print(f"  folder: {result.out_dir}")
    if result.pdf:
        print(f"  pdf:    {result.pdf}")
    print(f"  sheet:  {result.sheet}")


# ---------------------------------------------------------------- other commands


def _cmd_convert(args) -> int:
    source = Path(args.brief).expanduser().resolve()
    the_brief = brief_mod.load(source)
    target = Path(args.output).expanduser().resolve() if args.output else source.with_suffix(".yaml")
    if target == source:
        raise CarouselError("Refusing to overwrite the source brief; pass -o")
    target.write_text(the_brief.to_yaml(base_dir=target.parent), encoding="utf-8")
    print(f"Wrote {target} ({len(the_brief.slides)} slides)")
    return EXIT_OK


def _cmd_styles(args) -> int:
    rows = []
    for style_id, _ in style_mod.list_all():
        s = style_mod.load(style_id)
        preview = s.dir / "preview.png"
        rows.append({"id": s.id, "name": s.name, "description": s.description, "best_for": s.best_for,
                     "preview": str(preview) if preview.exists() else None})
    if args.json:
        print(json.dumps(rows, indent=2))
        return EXIT_OK
    for row in rows:
        print(f"{row['id']:<18} {row['name']}")
        print(f"{'':<18} {row['description']}")
        if row["best_for"]:
            print(f"{'':<18} best for: {', '.join(row['best_for'])}")
    return EXIT_OK


def _cmd_brands(args) -> int:
    rows = []
    for brand_id, folder in brand_mod.list_all():
        try:
            b = brand_mod.load(brand_id)
            rows.append({"id": b.id, "name": b.name, "handle": b.handle, "folder": str(folder), "ok": True,
                         "warnings": b.warnings})
        except CarouselError as exc:
            rows.append({"id": brand_id, "name": None, "folder": str(folder), "ok": False, "error": str(exc)})
    if args.json:
        print(json.dumps(rows, indent=2))
        return EXIT_OK
    if not rows:
        print("No brand kits yet. Create one with: carousel.py new-brand <id> --name \"Client\"")
    for row in rows:
        status = "" if row["ok"] else "  [BROKEN: run brand-check]"
        print(f"{row['id']:<24} {row.get('name') or ''} {row.get('handle') or ''}{status}")
    return EXIT_OK


def _cmd_brand_check(args) -> int:
    from . import colors as C

    b = brand_mod.load(args.brand)
    print(f"OK  {b.name} ({b.id})  {b.dir}")
    print(f"  fonts: heading {b.fonts['heading']['family']} {b.fonts['heading']['weight']}, "
          f"body {b.fonts['body']['family']} {b.fonts['body']['weight']}/{b.fonts['body']['bold_weight']}"
          f"  ({len(b.faces)} embedded font file(s))")
    print(f"  logos: {', '.join(f'{k}={v.name}' for k, v in b.logos.items()) or 'none'}")
    print("  tones (text on background, contrast):")
    for tone, t in b.tones.items():
        print(f"    {tone:<7} bg {C.to_hex(t['bg'])}  text {C.to_hex(t['fg'])} {C.contrast(t['fg'], t['bg']):.1f}:1  "
              f"highlight {C.to_hex(t['hl'])} {C.contrast(t['hl'], t['bg']):.1f}:1  logo={t['logo']}")
    for warning in b.warnings:
        print(f"  warning: {warning}")
    return EXIT_OK


def _cmd_new_brand(args) -> int:
    import re

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.id):
        raise CarouselError("Brand id must be lowercase letters/numbers with dashes, e.g. acme-coffee")
    root = Path(args.dir).expanduser() if args.dir else SKILL_ROOT / "brands"
    folder = root / args.id
    if folder.exists():
        raise CarouselError(f"{folder} already exists")
    (folder / "fonts").mkdir(parents=True)
    template = (SKILL_ROOT / "templates" / "brand-template.yaml").read_text(encoding="utf-8")
    (folder / "brand.yaml").write_text(template.replace("Client Name", args.name.replace('"', "'")), encoding="utf-8")
    print(f"Created {folder}")
    print("Next: put logo.svg (+ logo-inverse.svg) and font files in it, fill in brand.yaml, then run:")
    print(f"  python scripts/carousel.py brand-check {args.id}")
    return EXIT_OK


def _cmd_showcase(args) -> int:
    brief_path = Path(args.brief) if args.brief else SKILL_ROOT / "briefs" / "showcase.yaml"
    the_brand = brand_mod.load(args.brand)
    ids = args.styles.split(",") if args.styles else [s for s, _ in style_mod.list_all()]
    out_root = Path(args.out).expanduser() if args.out else default_output_root()
    showcase_dir = out_root / the_brand.id / "_showcase"
    failed = False
    for style_id in ids:
        the_brief = brief_mod.load(brief_path)
        the_brief.data["client"], the_brief.data["style"] = the_brand.id, style_id.strip()
        the_style = style_mod.load(style_id.strip())
        result = render_mod.render(the_brief, the_brand, the_style, showcase_dir / the_style.id, mode="check")
        target = showcase_dir / f"{the_style.id}.png"
        shutil.copyfile(result.sheet, target)
        status = "ok" if result.report.passed else f"{len(result.report.errors)} QA error(s)"
        failed |= not result.report.passed
        print(f"{the_style.id:<18} {status:<14} {target}")
    return EXIT_QA_FAILED if failed else EXIT_OK


def _cmd_style_check(args) -> int:
    the_style = style_mod.load(args.style)
    problems = style_mod.lint(the_style)
    for problem in problems:
        print(f"lint: {problem}")
    out_root = Path(args.out).expanduser() if args.out else default_output_root()
    brands = [b for b, _ in brand_mod.list_all() if b.startswith("example-")]
    if not brands:
        raise CarouselError("style-check needs the example-* brand kits")
    failures = 0
    for brief_name in ("showcase.yaml", "stress.yaml"):
        for brand_id in brands:
            the_brief = brief_mod.load(SKILL_ROOT / "briefs" / brief_name)
            the_brief.data["client"], the_brief.data["style"] = brand_id, the_style.id
            the_brand = brand_mod.load(brand_id)
            project = out_root / "_style-check" / the_style.id / f"{Path(brief_name).stem}-{brand_id}"
            result = render_mod.render(the_brief, the_brand, the_style, project, mode="check")
            failures += len(result.report.errors)
            print(f"{brief_name:<14} {brand_id:<20} {len(result.report.errors)} error(s) "
                  f"{len(result.report.warnings)} warning(s)  {result.sheet}")
            for issue in result.report.errors:
                print(f"    [{issue.label()}] {issue.message}")
    ok = not problems and failures == 0
    print("STYLE OK" if ok else "STYLE NEEDS WORK")
    return EXIT_OK if ok else EXIT_QA_FAILED


def _cmd_env(args) -> int:
    print(f"python      {platform.python_version()}")
    ok = True
    for module in ("jinja2", "yaml", "PIL", "pypdf", "playwright"):
        found = importlib.util.find_spec(module) is not None
        ok &= found
        print(f"{module:<11} {'ok' if found else 'MISSING  -> pip install -r requirements.txt'}")
    if ok:
        from . import browser

        try:
            with browser.chromium() as chrome:
                print(f"chromium    ok ({chrome.version})")
        except CarouselError as exc:
            ok = False
            print(f"chromium    MISSING  -> {exc}")
    print(f"styles      {', '.join(s for s, _ in style_mod.list_all()) or 'none'}")
    print(f"brands      {len(brand_mod.list_all())} kit(s)")
    print(f"output      {default_output_root()}")
    print("READY" if ok else "NOT READY")
    return EXIT_OK if ok else EXIT_ERROR
