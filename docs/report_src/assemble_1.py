"""Stage 1: assemble docs/REPORT.md from the 1 Oct version plus the later section files.

    python docs/report_src/assemble_1.py && python docs/report_src/assemble_2.py
"""
import io

import os
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/") + "/"
rd = lambda p: io.open(R + p, encoding="utf-8", newline="").read().replace("\r\n", "\n")
s = rd("docs/report_src/REPORT_v1.md")


def between(a, b):
    i = s.index(a)
    return s[i:s.index(b, i)]


def must_replace(text, old, new, count=1):
    assert text.count(old) == count, (text.count(old), old[:70])
    return text.replace(old, new)


sec2 = between("## 2. The competition contract: what counts", "## 3. Architecture of the submission")
sec2 = must_replace(sec2, "| **Dev board**: self-reported `wall_clock_sec`, consistency-checked against `n_events` | Our timing scope must be honest and well defined (§2.1). |",
                    "| **Dev board until the scoring change**: self-reported `wall_clock_sec`, consistency-checked against `n_events` | Our timing scope must be honest and well defined (§2.1). |\n| **Dev board since the scoring change**: events ÷ container time measured by the harness | The whole process is timed (§2.2). |")
sec2 = must_replace(sec2, "### 2.1 Timing scope (honesty rule)", "### 2.1 Timing scope under the old rule (honesty rule)")
sec2 = must_replace(sec2, "| **Final**: host-measured `docker run` wall clock, median of repeats |",
                    "| **Final**: Docker `State.StartedAt → FinishedAt`, five runs per unit, median of the four counted (§2.2) |")
sec2 = sec2.rstrip().rstrip("-").rstrip() + "\n\n"

sec4to6 = between("## 4. Method: how decisions were made", "## 7. Phase B: the bit-exact native engine")
sec4to6 = must_replace(sec4to6, "All three rounds together used about 5,100 tokens.",
    "| 4 | | Next step under the new scoring: ship the launcher / cut large-unit time / cut small-unit fixed cost / refresh the stale rules checkout; which units drive the mean; is shipping before refreshing an acceptable risk? | Values: ship 2.67, large units 1.69, small-unit cost 1.02, refresh 0.52. **First step: refresh, 47%** (ship 40%). Acceptable risk: 0.38. Mean driven by small units: 0.95 | Refreshed the checkout (unchanged scenarios), validated with the upstream harness, then pushed sub4. We did not adopt the \"small units drive the mean\" answer (§15, H31) | 1,349 / 157 |\n\nThe first four rounds together used about 6,600 tokens; rounds 5 to 8 are in §9.7.5, §9.9.6 and §9.10.4.")
sec4to6 = must_replace(sec4to6, "All three rounds", "All four rounds", 0) if False else sec4to6
sec4to6 = must_replace(sec4to6, "| Fuzzer | `native/fuzz/` | 2,416 differential cases; 2 bug classes found and fixed (§8) |",
    "| Fuzzer | `native/fuzz/` | 2,416 differential cases; 2 bug classes found and fixed (§8) |\n| Rules and leaderboard research | Report on the live board, the scoring rules in the upstream repositories, the reference timing code, and which techniques are allowed | Its headline finding (scoring changed partway through the Development phase; local checkout stale) was confirmed by reading the organizer post, the upstream README and the board directly (§2.2, §16.5) |\n| Low-latency code review (read-only) | Ranked list of exact-output-preserving optimisations and a bug check of the rewritten engine | No bug found; the blocked-queue equivalence was derived independently (§7.7) |")

sec7 = between("## 7. Phase B: the bit-exact native engine", "## 8. Robustness: differential fuzzing")
sec7 = must_replace(sec7, "### 7.6 End-to-end container time (the Final metric)", "### 7.6 End-to-end container time (sub1–sub3 measurements; since the scoring change also the Development metric)")
sec7 = must_replace(sec7, "stays numpy's own", "stays numpy's own (Python paths only; the launcher uses glibc's `log` with a guard, §7.8)")
sec7 = sec7.rstrip().rstrip("-").rstrip() + "\n\n" + rd("docs/report_src/_rep_s7.md").rstrip() + "\n" + rd("docs/report_src/_rep_s7b.md") + "\n---\n\n"

sec8 = between("## 8. Robustness: differential fuzzing", "## 9. Submission rounds: sub1 → sub2 → sub3")
sec9 = between("## 9. Submission rounds: sub1 → sub2 → sub3", "## 10. Complete experiment log")
sec9 = must_replace(sec9, "## 9. Submission rounds: sub1 → sub2 → sub3", "## 9. Submission rounds: sub1 to the Final")
sec9 = must_replace(sec9, "### 9.3 sub3 → pushed; projected 8.7–8.8M", "### 9.3 sub3 → pushed, never uploaded (projection of 8.7–8.8M applied to the old rule)")
sec9 = sec9.rstrip().rstrip("-").rstrip() + "\n\n" + rd("docs/report_src/_rep_s9.md").rstrip() + "\n\n" + rd("docs/report_src/_rep_s9b.md").rstrip() + "\n\n" + rd("docs/report_src/_rep_s9c.md").rstrip() + "\n\n" + rd("docs/report_src/_rep_s9d.md").rstrip() + "\n\n" + rd("docs/report_src/_rep_s9e.md").rstrip() + "\n\n---\n\n"

sec10 = between("## 10. Complete experiment log", "## 11. Limitations, risks and open work")
sec10 = sec10.rstrip().rstrip("-").rstrip() + "\n" + rd("docs/report_src/_rep_s10s11.md")

sec12 = between("## 12. Reproduction guide", "## 13. File map")
sec13to14 = s[s.index("## 13. File map"):]

out = (rd("docs/report_src/_rep_head.md") + sec2 + rd("docs/report_src/_rep_s2s3.md") + sec4to6 + sec7 + sec8 + sec9 + sec10
       + "@@SEC12@@" + "@@SEC13@@")
io.open(R + "docs/report_src/_report_stage1.md", "w", encoding="utf-8", newline="\n").write(out)
io.open(R + "docs/report_src/_rep_s12_old.md", "w", encoding="utf-8", newline="\n").write(sec12)
io.open(R + "docs/report_src/_rep_s13_old.md", "w", encoding="utf-8", newline="\n").write(sec13to14)
print("stage1 chars", len(out), "sec12", len(sec12), "sec13-14", len(sec13to14))
