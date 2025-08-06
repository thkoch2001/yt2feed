#!/usr/bin/env bash

# no set -e here, because yt-dlp exists with 101 on break conditions

ARGSFILE="yt-dlp-args"
ARGSDIR="$1"
ARGSPATH=$ARGSDIR/$ARGSFILE

if [[ -r "$ARGSPATH" && -f "$ARGSPATH" ]]; then
    yt_dlp_args=$(cat "$ARGSPATH")
else
    echo "ARGSFILE not readable: $ARGSPATH"
    exit 1
fi

# TODO use different folders for download_archive, ARGSFILE, info.json and public web files
cd "$ARGSDIR"
# TODO use --m-time?
yt-dlp --verbose --ignore-config \
  --print after_move:filepath,filename --restrict-filenames \
  --break-on-existing \
  --write-thumbnail --convert-thumbnails jpg \
  --write-info-json --write-playlist-metafiles \
  --extract-audio --download-archive download-archive \
  ${yt_dlp_args}
exit_code=$?
if [ $exit_code -eq 101 ]; then
    # echo "expected 101 error code"
    exit 0
fi
exit $exit_code

