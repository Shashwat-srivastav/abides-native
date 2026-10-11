"""Stage 2: put sections 12-17 into the staged report and write REPORT.md (one-off helper)."""
import io

import os
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/") + "/"
rd = lambda p: io.open(R + p, encoding="utf-8", newline="").read().replace("\r\n", "\n")
out = rd("docs/report_src/_report_stage1.md")
s12 = rd("docs/report_src/_rep_s12.md")
assert s12.count("@@REPRO@@") == 1
s12 = s12.replace("@@REPRO@@", rd("docs/report_src/_rep_repro.md").strip())
assert out.count("@@SEC12@@@@SEC13@@") == 1
out = out.replace("@@SEC12@@@@SEC13@@", s12.rstrip() + "\n" + rd("docs/report_src/_rep_tail.md").rstrip() + "\n")
assert "@@" not in out
io.open(R + "docs/REPORT.md", "w", encoding="utf-8", newline="\n").write(out)
print("docs/REPORT.md written:", len(out), "chars,", out.count("\n"), "lines")
