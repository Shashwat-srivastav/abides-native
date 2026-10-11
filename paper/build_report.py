"""Build the Zenodo report: Markdown -> self-contained HTML (figures embedded) -> PDF (Edge headless).

    python paper/build_report.py
Outputs: paper/zenodo_report.html, paper/zenodo_report.pdf
"""
import base64
import pathlib
import re
import subprocess

import markdown

P = pathlib.Path(__file__).resolve().parent
src = (P / "zenodo_report.md").read_text(encoding="utf-8")
assert "@@" not in src, "unfilled placeholder in zenodo_report.md"
html = markdown.markdown(src, extensions=["tables", "fenced_code", "sane_lists"])


def embed(m):
    path = P / m.group(1)
    data = base64.b64encode(path.read_bytes()).decode()
    return 'src="data:image/png;base64,%s"' % data


html = re.sub(r'src="(figures/[^"]+\.png)"', embed, html)
# figure captions: an italic paragraph that follows an image paragraph
html = re.sub(r'<p>(<img[^>]+>)</p>\s*<p><em>(Figure .*?)</em></p>', r'<figure>\1<figcaption>\2</figcaption></figure>', html, flags=re.S)
html = re.sub(r"<table>", '<div class="tw"><table>', html).replace("</table>", "</table></div>")

CSS = """
:root { --ink:#16161a; --ink2:#4a4a52; --rule:#dcdbd5; --surface:#ffffff; --accent:#2a78d6; --tint:#f4f6fa; }
* { box-sizing: border-box; }
html { font-size: 15.5px; }
body { margin: 0; background: var(--surface); color: var(--ink); font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; line-height: 1.55; }
main { max-width: 860px; margin: 0 auto; padding: 44px 28px 80px; }
h1 { font-size: 1.9rem; line-height: 1.22; margin: 0 0 14px; letter-spacing: -0.01em; }
h2 { font-size: 1.32rem; margin: 46px 0 12px; padding-top: 14px; border-top: 2px solid var(--ink); }
h3 { font-size: 1.05rem; margin: 28px 0 8px; }
p, li { color: var(--ink); }
blockquote { margin: 14px 0; padding: 8px 14px; border-left: 3px solid var(--rule); color: var(--ink2); background: var(--tint); }
hr { border: 0; border-top: 1px solid var(--rule); margin: 26px 0; }
code { font-family: Consolas, "SF Mono", monospace; font-size: 0.86em; background: var(--tint); padding: 1px 4px; border-radius: 3px; }
pre { background: var(--tint); padding: 12px 14px; border-radius: 6px; overflow-x: auto; font-size: 0.84rem; line-height: 1.45; }
pre code { background: none; padding: 0; }
.tw { overflow-x: auto; margin: 14px 0 18px; }
table { border-collapse: collapse; width: 100%; font-size: 0.86rem; }
th { text-align: left; border-bottom: 1.5px solid var(--ink); padding: 6px 10px 6px 0; vertical-align: bottom; }
td { border-bottom: 1px solid var(--rule); padding: 6px 10px 6px 0; vertical-align: top; }
td[align=right], th[align=right] { text-align: right; padding-right: 0; padding-left: 10px; font-variant-numeric: tabular-nums; }
figure { margin: 22px 0 26px; page-break-inside: avoid; break-inside: avoid; }
figure img { width: 100%; height: auto; display: block; border: 1px solid var(--rule); border-radius: 6px; }
figcaption { font-size: 0.86rem; color: var(--ink2); margin-top: 8px; }
strong { font-weight: 650; }
@media print {
  html { font-size: 10.6pt; }
  main { max-width: none; padding: 0; }
  h2 { page-break-after: avoid; break-after: avoid; }
  h3 { page-break-after: avoid; break-after: avoid; }
  tr, pre, blockquote { page-break-inside: avoid; break-inside: avoid; }
  .tw { overflow: visible; }
  a { color: inherit; text-decoration: none; }
}
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
"""
doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
       "<title>When the Container Is the Benchmark</title><style>%s</style></head><body><main>%s</main></body></html>" % (CSS, html))
(P / "zenodo_report.html").write_text(doc, encoding="utf-8")
print("html bytes", len(doc.encode("utf-8")))

edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
pdf = P / "zenodo_report.pdf"
r = subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + str(pdf),
                    (P / "zenodo_report.html").as_uri()], capture_output=True, text=True, timeout=180)
print("edge rc", r.returncode, "pdf bytes", pdf.stat().st_size if pdf.exists() else 0)
