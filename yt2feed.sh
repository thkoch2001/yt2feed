#!/usr/bin/env bash

set -e

SCRIPTDIR=$(dirname "$(realpath $0)")
PARENTDIR="$1"

while read DIRNAME; do
    FULLDIR="${PARENTDIR}/${DIRNAME}"
    if ! test -d "$FULLDIR"; then
        echo "not a dir: $FULLDIR"
        continue
    fi
    "$SCRIPTDIR"/download.sh "$FULLDIR"
    "$SCRIPTDIR"/create_feed.py "$FULLDIR"
done < <(ls -1 "$PARENTwDIR")
