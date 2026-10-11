#!/bin/sh
# Usage (Git Bash on host): sh run.sh <driver args...>
# Docker on Windows needs a drive-letter path for bind mounts (Git Bash: pwd -W).
R=$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$R/native/fuzz:/fz" \
  -v "$R/native/pkg:/native/pkg" \
  -e FZ_OUT -e FZ_TIMEOUT -e T3_ENGINE_LIB t3-native-dev python /fz/driver.py "$@"
