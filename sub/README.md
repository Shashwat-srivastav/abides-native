# Submission image

The build context for the Track 3 submission image.

| File | Purpose |
|---|---|
| `Dockerfile` | Full image: compiles the native engine and the static launcher, and installs the reference ABIDES stack as the fallback path |
| `Dockerfile.min` | Minimal image: the launcher alone on an empty base (one layer, about 2 MB, no fallback) |
| `simulate`, `simulate-batch` | Entry points of the full image |
| `abides_fork/`, `patches/` | Reference adapter and compatibility patches from the organizers' baseline (MIT) |
| `perf/` | Build-time rewrites that speed up the Python fallback path without changing its output |
| `submission_dev.template.json` | Template of the submission descriptor |
| `build_submission.py` | Seals the descriptor and builds `submission.zip` |

`native/` and `t3native/` in this directory are copies made by `sh lab/sync_sub.sh`; the sources live in [../native/](../native/). Run the sync before every build.

```sh
sh lab/sync_sub.sh
docker build -t agenthon-track3:<tag> sub/
docker build -f sub/Dockerfile.min --build-arg BASE=agenthon-track3:<tag> -t agenthon-track3:<tag>s sub/
```

## Descriptor and team key

`submission.json`, the sealed `submission/` directory and `submission.zip` are not tracked: they hold the team identifier and a claim signed with the team key.

`build_submission.py` asks for the team key at an interactive prompt. Run it yourself in a terminal; do not pass the key on a command line, store it in a file, or run the script through a tool that logs input.
