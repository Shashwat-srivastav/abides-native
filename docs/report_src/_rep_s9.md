### 9.4 sub4 → 153,825 (rank 9 of 17)

Built for the new rule (§2.2). Contents: the rewritten engine (§7.7) and the no-Python launcher for both verbs (§7.8); the Python native path and the ABIDES reference path are unchanged from sub3 and remain in the image as fallbacks.

Validation performed on the image `agenthon-track3:sub4` (= `slashalpha/agenthon-track3:native-v4`, `sha256:697ae5de6d95b1fce2bd467375060a10f4f343a04a00d00a989b38e5869d85c7`):

| Check | Result |
|---|---|
| Official regression, upstream harness `bffb572` + toolkit v2.5.1, reference traces from the local checkout, 1 worker | **65 passed, 0 failed, 0 errored** (8 minutes) |
| Trace files written by that run, re-hashed from disk | 65/65 equal to the baseline image's hashes; the ledger hashes sub4 reports also equal the baseline's 65/65 (this harness version does not keep the ledger file, so the ledger was not re-hashed from disk in this run) |
| Organizers' runtime restrictions (`--read-only`, `--user 65534:65534`, `--pids-limit 256`, `--cpus 4`, 64 MiB noexec `/tmp`, `--network none`) | `simulate` on `mp07` succeeded and wrote all three files; `simulate-batch` on `t3-gbatch-homog-8` succeeded with per-sub hashes equal to the verified sub2 outputs; the Python fallback (`T3_NO_LAUNCHER=1`) succeeded |
| Host `docker run` time vs sub3, 4 scenarios × 3 interleaved rounds | sub4 faster on all 4 (§1.4), same hashes |
| Image metadata | Label `qfbench2.interface_version=2.0` present; no `VOLUME` |
| Registry | Anonymous manifest fetch by digest returned HTTP 200 |

Three earlier attempts at the official regression produced no verdict, for reasons unrelated to sub4 (§16.6): the upstream harness needs toolkit v2.5.1 (`cannot import name 'digest_members'` with the older copy); a fresh upstream checkout has no `reference_traces` directory; and the harness worker process died when the host ran out of memory (`OpenBLAS error: Memory allocation still failed`). The successful run limited BLAS threads to 1.

**Score.** Two uploads (CodaBench): submission 968635 → **151,386.9550**, submission 968642 → **153,825.0187**. The board then showed S2WISH 9th of 17 scored teams, between 181,826 (8th) and 129,722 (10th); the leader was at 231,024. The team reports both as uploads of the sub4 submission; which digest each zip carried was not independently checked by us.

*(Later note: later sections read the 1.6% between these two uploads as the host's run-to-run variation (§9.5, §9.8.2, §9.8.4, §9.8.15). The organizers have since stated that Development runs on one machine that takes only Track 3 runs, one submission at a time, and another team reports two runs agreeing to within 0.1% (issue #34, §9.9.2). Because the two zips were never checked to carry the same image, the 1.6% is not evidence of noise of that size.)*

Reading the score: it sits above the cluster at 127–130K and below the cluster at 182–231K. We have no per-unit breakdown from the platform, so we cannot say from the score alone which units cost us the gap to the leaders; §7.8 and §11.2 list the candidates (large-unit output pipeline, library load time), none of them confirmed as the cause.

What was *not* done for sub4 before pushing: the 6 batch units were not all run through the image (all 6 through the launcher binary in the dev container, 1 through the image); the differential fuzz corpus was not re-run against the rewritten engine before the push (a re-check was planned for afterwards and has still not been run); no interleaved multi-round timing of all 65 scenarios.

*(Superseded later: the stored corpus of 1,318 cases was replayed on sub6 and on later builds, 1,318 of 1,318 each time (§9.7.2). sub4's own image was never replayed.)*

