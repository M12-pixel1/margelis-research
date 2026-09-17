"""Static web pages for Margelis Research (no JavaScript: the host CSP sets script-src 'none')."""
from __future__ import annotations

import html
import json
from pathlib import Path
from string import Template

from . import mdparse
from .common import FONTS, Note, human_date, license_display_html, slugify, write_text

CSS = """
:root{
  --bg:#fbfaf7;--panel:#f3efe6;--ink:#1c2127;--muted:#58606b;--rule:#ddd6c8;
  --accent:#7a5418;--link:#1f4f8f;--code:#f1ede4;
  --serif:"Iowan Old Style","Charter","Georgia","Cambria","Times New Roman",serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SFMono-Regular","Cascadia Mono",Consolas,"Liberation Mono",monospace;
  color-scheme:light dark;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#121417;--panel:#1b1e22;--ink:#e6e3dc;--muted:#a4aab2;--rule:#34383e;
        --accent:#d6a85a;--link:#8fb8f5;--code:#1d2024;}
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.62 var(--serif)}
a{color:var(--link);text-underline-offset:.15em}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.skip{position:absolute;left:-999px}
.skip:focus{left:16px;top:8px;background:var(--panel);padding:6px 10px}
.bar{border-bottom:1px solid var(--rule);font:600 13px/1.4 var(--sans)}
.bar .in{max-width:48rem;margin:0 auto;padding:12px 16px;display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;justify-content:space-between}
.brand{letter-spacing:.14em;text-transform:uppercase;color:var(--accent);text-decoration:none}
.bar nav a{margin-left:14px;color:var(--muted);text-decoration:none}
.bar nav a:first-child{margin-left:0}
.bar nav a:hover{color:var(--ink)}
main{max-width:48rem;margin:0 auto;padding:28px 16px 64px}
.kicker{font:700 12px/1.4 var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}
h1{font:700 clamp(1.9rem,5.2vw,2.6rem)/1.15 var(--sans);margin:0 0 8px;letter-spacing:-.01em}
.subtitle{font-style:italic;color:var(--muted);font-size:clamp(1.1rem,3vw,1.3rem);margin:0 0 18px}
.byline{margin:0 0 18px}
.byline strong{font-weight:700}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0 0 20px;padding:14px 16px;background:var(--panel);border:1px solid var(--rule);border-radius:6px;font:14px/1.5 var(--sans)}
dl.facts dt{color:var(--muted)}
dl.facts dd{margin:0;overflow-wrap:anywhere}
.badge{display:inline-block;font:700 12px/1.3 var(--sans);letter-spacing:.04em;padding:3px 8px;border-radius:999px;border:1px solid var(--accent);color:var(--accent)}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 26px;font:600 14px/1.3 var(--sans)}
.actions a{display:inline-block;padding:8px 12px;border:1px solid var(--rule);border-radius:6px;text-decoration:none;background:var(--bg)}
.actions a.primary{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.note{border-left:3px solid var(--accent);background:var(--panel);padding:10px 14px;margin:0 0 26px;font:15px/1.55 var(--sans)}
h2{font:700 1.3rem/1.3 var(--sans);margin:2.2em 0 .6em;scroll-margin-top:12px}
h2 a.anchor{color:inherit;text-decoration:none}
.abstract p{margin:.4em 0 0}
nav.toc{font:15px/1.6 var(--sans);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:10px 0;margin:26px 0}
nav.toc ol{margin:.3em 0 0;padding-left:1.2em;columns:2 16rem}
.body p,.body li{overflow-wrap:break-word}
.body ul,.body ol{padding-left:1.4em}
.body li{margin:.15em 0}
code{font:.86em var(--mono);background:var(--code);padding:.08em .3em;border-radius:3px}
pre{background:var(--code);border:1px solid var(--rule);border-radius:6px;padding:12px 14px;overflow-x:auto;font:14px/1.5 var(--mono)}
pre code{background:none;padding:0;font:inherit}
.table-wrap{overflow-x:auto;margin:1em 0;border:1px solid var(--rule);border-radius:6px}
table{border-collapse:collapse;width:100%;font:15px/1.45 var(--sans)}
th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--rule)}
thead th{background:var(--panel)}
tbody tr:last-child td{border-bottom:0}
hr{border:0;border-top:1px solid var(--rule);margin:2.4em 0}
.hash{font:12.5px/1.45 var(--mono);overflow-wrap:anywhere;word-break:break-all}
footer{border-top:1px solid var(--rule);font:13px/1.6 var(--sans);color:var(--muted)}
footer .in{max-width:48rem;margin:0 auto;padding:18px 16px 40px}
.list{list-style:none;padding:0;margin:0}
.list li{border-top:1px solid var(--rule);padding:16px 0}
.list h2{margin:.2em 0 .2em;font-size:1.2rem}
.meta{font:14px/1.5 var(--sans);color:var(--muted)}
@media (max-width:520px){body{font-size:16px}dl.facts{grid-template-columns:1fr}dl.facts dt{margin-top:6px}}
@media print{.bar,.actions,nav.toc,.skip{display:none}body{background:#fff;color:#000}a{color:#000}}
""".strip()

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$page_title</title>
<meta name="description" content="$description">
$head_extra
<style>
$css
</style>
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="bar"><div class="in">
<a class="brand" href="$index_href">$series</a>
<nav aria-label="Publication links"><a href="$index_href">All notes</a><a href="$repo_url">GitHub</a></nav>
</div></header>
<main id="content">
$main
</main>
<footer><div class="in">
$footer
</div></footer>
</body>
</html>
""")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def _meta(name: str, content: str, prop: bool = False) -> str:
    attr = "property" if prop else "name"
    return f'<meta {attr}="{esc(name)}" content="{esc(content)}">'


def _json_ld(obj) -> str:
    data = json.dumps(obj, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{data}\n</script>'


def render_body(note: Note) -> tuple[str, list[tuple[str, str]]]:
    """Render the note body (without the Markdown title block) to HTML; return (html, toc)."""
    md = mdparse.parser()
    tokens = md.parse(note.md_path.read_text(encoding="utf-8"))
    _, body = mdparse.split_title_block(tokens)
    toc = []
    for i, tok in enumerate(body):
        if tok.type == "heading_open":
            text = mdparse.inline_text(body[i + 1])
            slug = slugify(text)
            tok.attrSet("id", slug)
            if tok.tag == "h2":
                toc.append((slug, text))
        elif tok.type == "th_open":
            tok.attrSet("scope", "col")
    out = md.renderer.render(body, md.options, {})
    out = out.replace("<table>", '<div class="table-wrap" role="region" aria-label="Table" tabindex="0"><table>')
    out = out.replace("</table>", "</table></div>")
    return out, toc


def citation_text(note: Note, doi: str | None) -> str:
    a = note.authors[0]
    text = (f"{a['family_name']}, {a['given_name'][0]}. ({note.date[:4]}). {note.full_title} "
            f"({note.series_name} Note {note.number}, Version {note.version}). {note.publisher}.")
    if doi:
        text += f" https://doi.org/{doi}"
    else:
        text += f" {note.canonical_url}"
    return text


def bibtex(note: Note, doi: str | None) -> str:
    a = note.authors[0]
    inst = note.publisher.replace("ū", r"{\=u}").replace("ė", r"{\.e}")
    key = f"{a['family_name'].lower()}{note.date[:4]}note{note.number}"
    month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][int(note.date[5:7]) - 1]
    lines = [
        f"@techreport{{{key},",
        f"  author      = {{{a['family_name']}, {a['given_name']}}},",
        f"  title       = {{{note.full_title}}},",
        f"  institution = {{{inst}}},",
        f"  type        = {{{note.series_name} Note}},",
        f"  number      = {{{note.number}}},",
        f"  year        = {{{note.date[:4]}}},",
        f"  month       = {month},",
        f"  note        = {{Version {note.version}. Status: {note.meta['status']}}},",
        f"  url         = {{{note.canonical_url}}},",
    ]
    if doi:
        lines.append(f"  doi         = {{{doi}}},")
    lines.append("}")
    return "\n".join(lines)


def _fmt_bytes(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n >= 1024 else f"{n} B"


def render_note_page(note: Note, metadata: dict, sums: dict[str, str]) -> str:
    doi = note.doi()
    body_html, toc = render_body(note)
    author = note.authors[0]
    author_name = f"{author['given_name']} {author['family_name']}"
    ver = f"v{note.version}"
    pdf_name = note.pdf_path.name
    md_name = note.md_path.name
    pdf_file = next(f for f in metadata["files"] if f["path"] == pdf_name)
    og_url = f"{note.canonical_url}{note.og_image_name}"
    lic = note.license
    license_text = license_display_html(lic)
    doi_html = (f'<a href="https://doi.org/{esc(doi)}">{esc(doi)}</a>' if doi
                else "Pending: the archival (Zenodo) record has not been published yet.")
    unproven = next((slug for slug, text in toc if "What remains unproven" in text), "")
    archive_clause = (" and to the Zenodo record" if doi
                      else "; the archival (Zenodo) record, once published, carries the same files")

    head = [
        f'<link rel="canonical" href="{esc(note.canonical_url)}">',
        _meta("author", author_name),
        _meta("keywords", ", ".join(note.meta["web_keywords"])),
        _meta("robots", "index,follow"),
        _meta("og:type", "article", True),
        _meta("og:site_name", note.series_name, True),
        _meta("og:title", note.full_title, True),
        _meta("og:description", note.meta["abstract"], True),
        _meta("og:url", note.canonical_url, True),
        _meta("og:image", og_url, True),
        _meta("og:image:width", "1200", True),
        _meta("og:image:height", "630", True),
        _meta("og:image:alt", f"{note.series_name} Note {note.number}: {note.title}", True),
        _meta("og:locale", "en_US", True),
        _meta("article:published_time", note.date, True),
        _meta("article:author", author_name, True),
        _meta("twitter:card", "summary_large_image"),
        _meta("twitter:title", note.full_title),
        _meta("twitter:description", note.meta["abstract"]),
        _meta("twitter:image", og_url),
        _meta("citation_title", note.full_title),
        _meta("citation_author", f"{author['family_name']}, {author['given_name']}"),
        _meta("citation_author_institution", author["affiliation"]),
        _meta("citation_publication_date", note.date.replace("-", "/")),
        _meta("citation_technical_report_institution", note.publisher),
        _meta("citation_technical_report_number", f"{note.series_name} Note {note.number}"),
        _meta("citation_pdf_url", note.pdf_url),
        _meta("citation_language", note.meta.get("language", "en")),
    ]
    if doi:
        head.append(_meta("citation_doi", doi))
    ld = {
        "@context": "https://schema.org",
        "@type": "Report",
        "@id": f"{note.canonical_url}#report",
        "name": note.full_title,
        "headline": note.full_title,
        "alternativeHeadline": note.subtitle,
        "reportNumber": f"{note.series_name} Note {note.number}",
        "version": note.version,
        "datePublished": note.date,
        "inLanguage": note.meta.get("language", "en"),
        "abstract": note.meta["abstract"],
        "keywords": note.meta["web_keywords"],
        "creativeWorkStatus": note.meta["status"],
        "author": [{"@type": "Person", "name": author_name,
                    "affiliation": {"@type": "Organization", "name": author["affiliation"]}}],
        "publisher": {"@type": "Organization", "name": note.publisher, "url": "https://rupestelisholding.com/"},
        "isPartOf": {"@type": "CreativeWorkSeries", "name": note.series_name,
                     "url": note.series["site"]["canonical_base"]},
        "url": note.canonical_url,
        "mainEntityOfPage": note.canonical_url,
        "image": og_url,
        "encoding": [{"@type": "MediaObject", "encodingFormat": "application/pdf", "contentUrl": note.pdf_url,
                      "contentSize": f"{pdf_file['bytes']} bytes", "sha256": pdf_file["sha256"]}],
        "citation": [r["url"] for r in _references(note)],
        "isBasedOn": note.repo_url,
    }
    if doi:
        ld["identifier"] = {"@type": "PropertyValue", "propertyID": "DOI", "value": doi}
        ld["sameAs"] = f"https://doi.org/{doi}"
    if note.license_granted:
        ld["license"] = f"https://spdx.org/licenses/{lic['spdx']}.html"
    head.append(_json_ld(ld))

    toc_html = "\n".join(f'<li><a href="#{esc(s)}">{esc(t)}</a></li>' for s, t in toc)
    files_rows = "\n".join(
        f'<tr><td><a href="{esc(ver)}/{esc(name)}">{esc(name)}</a></td><td class="hash">{esc(digest)}</td></tr>'
        for name, digest in sums.items())
    versions_rows = "\n".join(
        "<tr><td>{v}</td><td>{d}</td><td>{s}</td><td><a href=\"v{v}/{pdf}\">PDF</a> · "
        "<a href=\"{repo}/releases/tag/research-note-{num}-v{v}\">release</a></td></tr>".format(
            v=esc(h["version"]), d=esc(human_date(str(h["date"]))), s=esc(h["summary"]), pdf=esc(pdf_name),
            repo=esc(note.repo_url), num=esc(note.number))
        for h in reversed(note.meta["version_history"]))

    main = f"""<article>
<p class="kicker">{esc(note.series_name)} · Research Note {esc(note.number)}</p>
<h1>{esc(note.title)}</h1>
<p class="subtitle">{esc(note.subtitle)}</p>
<p class="byline"><strong>{esc(author_name)}</strong> · {esc(author['affiliation'])}<br>
<span class="meta">{esc(note.label)}</span></p>
<dl class="facts">
<dt>Status</dt><dd><span class="badge">{esc(note.meta['status'])}</span></dd>
<dt>Version</dt><dd>{esc(note.version)}</dd>
<dt>Published</dt><dd><time datetime="{esc(note.date)}">{esc(human_date(note.date))}</time></dd>
<dt>Series</dt><dd>{esc(note.series_name)} · Research Note {esc(note.number)}</dd>
<dt>DOI</dt><dd>{doi_html}</dd>
<dt>License</dt><dd>{license_text}</dd>
<dt>Source</dt><dd><a href="{esc(note.repo_url)}">{esc(note.repo_slug)}</a> · <a href="{esc(note.release_url)}">release {esc(note.tag)}</a></dd>
</dl>
<p class="actions">
<a class="primary" href="{esc(ver)}/{esc(pdf_name)}">Download PDF ({esc(_fmt_bytes(pdf_file['bytes']))})</a>
<a href="{esc(ver)}/{esc(md_name)}">Markdown source</a>
<a href="{esc(ver)}/metadata.json">metadata.json</a>
<a href="{esc(ver)}/SHA256SUMS">SHA256SUMS</a>
</p>
<p class="note"><strong>Status: {esc(note.meta['status'])}.</strong> This note defines an evaluation framework; it reports no benchmark results.
Its limitations are listed under <a href="#{esc(unproven)}">What remains unproven</a>.</p>
<section class="abstract" aria-labelledby="abstract"><h2 id="abstract">Abstract</h2>
<p>{esc(note.meta['abstract'])}</p></section>
<nav class="toc" aria-label="Contents"><strong>Contents</strong>
<ol>
{toc_html}
</ol></nav>
<div class="body">
{body_html}
</div>
<h2 id="cite">Cite this note</h2>
<pre><code>{esc(citation_text(note, doi))}</code></pre>
<pre><code>{esc(bibtex(note, doi))}</code></pre>
<h2 id="versions">Version history</h2>
<div class="table-wrap" role="region" aria-label="Version history" tabindex="0"><table>
<thead><tr><th scope="col">Version</th><th scope="col">Date</th><th scope="col">Changes</th><th scope="col">Files</th></tr></thead>
<tbody>
{versions_rows}
</tbody></table></div>
<p>Published versions are never overwritten. A correction is issued as a new version (v1.1); a major conceptual change as v2.0.</p>
<h2 id="integrity">Integrity</h2>
<p>SHA-256 digests of the files of version {esc(note.version)}. The same bytes are published on this page and attached to the GitHub release{archive_clause}.</p>
<div class="table-wrap" role="region" aria-label="SHA-256 digests" tabindex="0"><table>
<thead><tr><th scope="col">File</th><th scope="col">SHA-256</th></tr></thead>
<tbody>
{files_rows}
</tbody></table></div>
<p>To verify downloaded files:</p>
<pre><code>sha256sum -c SHA256SUMS
# Windows PowerShell
Get-FileHash .\\{esc(pdf_name)} -Algorithm SHA256
# GitHub release attestation (immutable release)
gh release verify {esc(note.tag)} -R {esc(note.repo_slug)}
gh release verify-asset {esc(note.tag)} {esc(pdf_name)} -R {esc(note.repo_slug)}</code></pre>
</article>"""

    footer = (f"<p>{esc(note.series_name)} is published by {esc(note.publisher)}. "
              f"Canonical address of this note: <a href=\"{esc(note.canonical_url)}\">{esc(note.canonical_url)}</a>. "
              f"Source, metadata and history: <a href=\"{esc(note.repo_url)}\">{esc(note.repo_slug)}</a>.</p>")
    return PAGE.substitute(
        page_title=esc(f"{note.title}: {note.subtitle} · {note.series_name} Note {note.number}"),
        description=esc(note.meta["abstract"]),
        head_extra="\n".join(head),
        css=CSS,
        index_href="../",
        series=esc(note.series_name),
        repo_url=esc(note.repo_url),
        main=main,
        footer=footer,
    )


def _references(note: Note) -> list[dict]:
    if note.references_path.exists():
        return json.loads(note.references_path.read_text(encoding="utf-8"))["references"]
    return []


def render_index(notes: list[Note], series: dict) -> str:
    items = []
    for n in sorted(notes, key=lambda x: x.number, reverse=True):
        items.append(f"""<li>
<p class="meta">Research Note {esc(n.number)} · v{esc(n.version)} · <time datetime="{esc(n.date)}">{esc(human_date(n.date))}</time> · <span class="badge">{esc(n.meta['status'])}</span></p>
<h2><a href="{esc(n.number)}/">{esc(n.title)}</a></h2>
<p>{esc(n.subtitle)}</p>
<p class="meta">{esc(', '.join(n.author_names))} · {esc(n.authors[0]['affiliation'])}</p>
</li>""")
    base = series["site"]["canonical_base"]
    head = "\n".join([
        f'<link rel="canonical" href="{esc(base)}">',
        _meta("robots", "index,follow"),
        _meta("og:type", "website", True),
        _meta("og:site_name", series["series"], True),
        _meta("og:title", series["series"], True),
        _meta("og:url", base, True),
        _json_ld({"@context": "https://schema.org", "@type": "CreativeWorkSeries", "name": series["series"],
                  "url": base, "publisher": {"@type": "Organization", "name": series["publisher"]}}),
    ])
    main = f"""<p class="kicker">{esc(series['series'])}</p>
<h1>Research notes</h1>
<p class="subtitle">Technical research notes and benchmark specifications published by {esc(series['publisher'])}.</p>
<ul class="list">
{''.join(items)}
</ul>"""
    footer = (f"<p>{esc(series['series'])} is published by {esc(series['publisher'])}. "
              f"Source and history: <a href=\"{esc(series['repository']['url'])}\">"
              f"{esc(series['repository']['owner'])}/{esc(series['repository']['name'])}</a>.</p>")
    return PAGE.substitute(page_title=esc(series["series"]),
                           description=esc(f"Technical research notes published by {series['publisher']}."),
                           head_extra=head, css=CSS, index_href="./", series=esc(series["series"]),
                           repo_url=esc(series["repository"]["url"]), main=main, footer=footer)


def render_root_redirect(series: dict) -> str:
    base = series["site"]["canonical_base"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(series['series'])}</title>
<link rel="canonical" href="{esc(base)}">
<meta http-equiv="refresh" content="0; url=research/">
<meta name="robots" content="noindex">
</head>
<body>
<p><a href="research/">{esc(series['series'])}: research notes</a></p>
</body>
</html>
"""


def render_sitemap(notes: list[Note], series: dict) -> str:
    base = series["site"]["canonical_base"]
    last = max(n.date for n in notes)
    urls = [f"  <url><loc>{esc(base)}</loc><lastmod>{last}</lastmod></url>"]
    for n in sorted(notes, key=lambda x: x.number):
        urls.append(f"  <url><loc>{esc(n.canonical_url)}</loc><lastmod>{n.date}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")


def render_og_image(note: Note, path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#161a1f")
    d = ImageDraw.Draw(img)
    sans_b = str(FONTS / "DejaVuSans-Bold.ttf")
    serif_i = str(FONTS / "DejaVuSerif-Italic.ttf")
    serif = str(FONTS / "DejaVuSerif.ttf")
    d.rectangle([0, 0, 14, H], fill="#d6a85a")
    kicker = f"{note.series_name.upper()}  ·  RESEARCH NOTE {note.number}"
    d.text((80, 70), kicker, font=ImageFont.truetype(sans_b, 26), fill="#d6a85a")
    title_font = ImageFont.truetype(sans_b, 64)
    y = 140
    for line in _wrap(d, note.title, title_font, W - 160):
        d.text((80, y), line, font=title_font, fill="#f2efe8")
        y += 78
    sub_font = ImageFont.truetype(serif_i, 34)
    y += 8
    for line in _wrap(d, note.subtitle, sub_font, W - 160):
        d.text((80, y), line, font=sub_font, fill="#b9bec5")
        y += 46
    info = ImageFont.truetype(serif, 28)
    d.text((80, H - 130), f"{', '.join(note.author_names)} · {note.authors[0]['affiliation']}", font=info, fill="#f2efe8")
    d.text((80, H - 84), f"v{note.version} · {human_date(note.date)} · Status: {note.meta['status']}",
           font=ImageFont.truetype(serif, 24), fill="#b9bec5")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def write_site(notes: list[Note], series: dict, per_note: dict[str, tuple[dict, dict]], site_root: Path) -> list[Path]:
    """Write all pages. per_note maps number -> (metadata, sums)."""
    written = []
    root_index = site_root / "index.html"
    write_text(root_index, render_root_redirect(series))
    write_text(site_root / "research" / "index.html", render_index(notes, series))
    write_text(site_root / "research" / "sitemap.xml", render_sitemap(notes, series))
    written += [root_index, site_root / "research" / "index.html", site_root / "research" / "sitemap.xml"]
    for n in notes:
        metadata, sums = per_note[n.number]
        page = n.site_dir / "index.html"
        write_text(page, render_note_page(n, metadata, sums))
        written.append(page)
    return written
