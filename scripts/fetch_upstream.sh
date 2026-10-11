#!/bin/sh
# Fetch the organizers' repositories that the build, validation and reproduction scripts read.
# They are not redistributed in this repository; their own licences apply.
#
#   sh scripts/fetch_upstream.sh
#
# track3-upstream/                  rules, harness, regression scenarios (pinned commit below)
# track3-simulation-public-clone/   the public units with reference outputs (same repository)
# toolkit-v2.5.1/                   qfbench2_common, tag v2.5.1
set -e
cd "$(dirname "$0")/.."

TRACK3=https://github.com/Agenthon-2026/track3-simulation-public.git
TOOLKIT=https://github.com/Agenthon-2026/Agenthon2026-public.git
UPSTREAM_COMMIT=bffb57227f796f9fa769a23d01fc364bee14a119
UNITS_COMMIT=4cc7882eed85153e9c06667738c87882b2deec90

fetch() {  # dir url ref
    if [ -d "$1/.git" ]; then
        echo "$1: already present"
    else
        git clone "$2" "$1"
    fi
    git -C "$1" checkout -q "$3"
    echo "$1 at $(git -C "$1" rev-parse --short HEAD)"
}

fetch track3-upstream "$TRACK3" "$UPSTREAM_COMMIT"
fetch track3-simulation-public-clone "$TRACK3" "$UNITS_COMMIT"
fetch toolkit-v2.5.1 "$TOOLKIT" v2.5.1
