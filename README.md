# yt2feed

Convert video site playlists to a podcast feeds.

## Configuration

Configuration uses folders and files as a hierarchical configuration format,
inspired by [S6](https://skarnet.org/software/s6/). Each file name and file
content pair represents a key value pair.

Configuration is looked up in XDG basedir locations (/etc/yt2feed,
~/.config/yt2feed) or as specified on the command line.

This is the configurations directory structure:

```
├── subscriptions
│   ├── $NAME            - a subscription with name $NAME
│   │   ├── url          - url of the video playlist
│   │   └── yt-dlp-args  - (optional) arguments for yt-dlp, one arg per line
│   ├── ...
├── webroot_path         - CWD to execute yt-dlp in
└── webroot_url          - base url to use in the rendered feed xml file
```

Do not use a youtube channel's frontpage as url but either the /video subpage
or a playlist!

The yt-dlp-args file can be used to filter videos to be downloaded, e.g.:

```
--break-match-filters
upload_date>20250728
--match-filters
title~='^\d+ .*$'
```

The above downloads videos uploaded after Juli 2025, stopping after
encountering an earlier video and filters videos by titles starting with a
number and a space. See the manpage of yt-dlp for other possible filters and
check the YT_DLP_ARGS_COMMON variable in the source code of yt2feed.py for
arguments already provided.

## Recommended usage

Execute yt2feed on a home internet connection and sync the webroot_path
directory to a web server. Youtube knows the ip ranges of server providers and
might block requests more eagerly with 429 or even 403 replies from those ips.

Recommended rsync options:

```
rsync --recursive --progress --links --times \
  --exclude=download-archive --exclude=\*.info.json \
  $WEBROOT_PATH $DEST
```

The webserver can be configured to list directory contents to allow browsing
the feeds. It might be advisable to protect the folder with a password or at
least deny indexing (e.g. with robots.txt).

## TODO

- setup feed rendering with xsl stylesheet like ydl-podcast does
- create config and subscriptions folders in add action if they don't exist
- add command to generate opml file?
- decide on feed xml filename, probably index.xml
- maybe add a command to call rsync
- see TODO statements in code

## Similar projects

- [yt2podcast](https://github.com/unkn0w/yt2podcast)
  PHP, 8y, dead
- [yt2podcast](https://pypi.org/project/yt2podcast)
  Python, 2024, no docs at all, no repo, seems to not actually download the video
- [ydl-podcast](https://github.com/nbr23/ydl-podcast)
  Python, 2025, more complex than necessary
