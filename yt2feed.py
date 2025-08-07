from pprint import pprint

import argparse
import datetime
from jinja2 import Environment, PackageLoader, StrictUndefined
import json
import os
import subprocess
import sys

INFO_JSON_SUFFIX = b".info.json"
YT_DLP_ARGS_COMMON = [
    "yt-dlp",
    "--verbose",
    "--ignore-config",
    "--print", "after_move:filepath,filename",
    "--restrict-filenames",
    "--break-on-existing",
    "--write-thumbnail",
    "--convert-thumbnails", "jpg",
    "--write-info-json",
    "--write-playlist-metafiles",
    "--extract-audio",
    "--download-archive", "download-archive"
]

def get_thumbnail_filename(directory, basename):
    extension = b"jpg"
    filename = b".".join([basename, extension])
    fullpath = os.path.join(directory, filename)
    if os.path.isfile(fullpath):
      return filename


def get_media_filename(directory, basename, thumbnail_filename):
    media_filename = None
    for file in os.listdir(directory):
        if not file.startswith(basename):
            continue
        if file.endswith(INFO_JSON_SUFFIX):
            continue
        if file == thumbnail_filename:
            continue
        if media_filename is not None:
            print(f"Error: Found two possible media files: '{media_filename}' and '{filename}'")
            sys.exit(1)
        media_filename = file

    if media_filename is None:
        print(f"Error: no media file found for '{basename}'")
        sys.exit(1)
    return media_filename


def parse_pl_info_json(directory, mdjs):

    return {
        'icon_url' : None,
        'link': "LINK",
        'title': "TITLE",
        'original_url': mdjs.get("original_url"),
    }


def parse_timestamp(mdjs, fullpath):
    if "timestamp" in mdjs:
        return mdjs["timestamp"]
    if "upload_date" in mdjs:
        return datetime.datetime.strptime(mdjs["upload_date"], "%Y%m%d").timestamp()
    return os.stat(fullpath).st_ctime


def parse_info_json(directory, info_json_file):
    fullpath = os.path.join(directory, info_json_file)
    with open(fullpath) as handle:
        mdjs = json.load(handle)
        if mdjs.get("_type") == "playlist":
            return ("playlist", parse_pl_info_json(directory, mdjs))
        basename = info_json_file.removesuffix(INFO_JSON_SUFFIX)
        thumbnail_filename = get_thumbnail_filename(directory, basename)
        media_filename = get_media_filename(directory, basename, thumbnail_filename)

        return (mdjs.get("_type"), {
            "title": mdjs["title"],
            "id": mdjs["id"],
            "timestamp": parse_timestamp(mdjs, fullpath),
            "pub_date": datetime.datetime.strptime(mdjs["upload_date"], "%Y%m%d").strftime("%a, %d %b %Y %H:%M:%S +0000") if mdjs.get("upload_date") is not None else None,
            "description": mdjs.get("description"),
            "thumbnail_filename": os.fsdecode(thumbnail_filename),
            "media_filename": os.fsdecode(media_filename),
            "media_file_timestamp": os.stat(os.path.join(directory, media_filename)).st_mtime,
            "duration": str(datetime.timedelta(seconds=mdjs["duration"])) if mdjs.get("duration") is not None else None,
            "url": None,
            "original_url": mdjs.get("url"),
            "media_type": None,
        })


def get_template_data(directory):
    entries = []
    pl_info = None
    newest_media_file_timestamp = 0
    for file in os.listdir(directory):
        if not file.endswith(INFO_JSON_SUFFIX):
            continue

        (t, parsed_info_json) = parse_info_json(directory, file)
        if t == "playlist":
            if pl_info == None:
                pl_info = parsed_info_json
                continue
            else:
                print("Error: Found a second playlist .info.json file. exiting")
                sys.exit(1)
        if parsed_info_json["media_file_timestamp"] > newest_media_file_timestamp:
            newest_media_file_timestamp = parsed_info_json["media_file_timestamp"]
        entries.append(parsed_info_json)

    if pl_info == None:
        print("Error: No playlist .info.json file found!")
        sys.exit(1)

    entries.sort(reverse=True, key=lambda x: x["timestamp"])
    pl_info["entries"] = entries
    pl_info["newest_media_file_timestamp"] = newest_media_file_timestamp
    return pl_info


def render(out_file, template_data):
    environment = Environment(
        loader=PackageLoader(__package__ or "__main__"),
        undefined=StrictUndefined,
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("feed.xml.jinja")
    feed_content = template.render(template_data)

    with open(out_file, "w") as o:
        o.write(feed_content)


def file_needs_update(path, newest_timestamp):
    if not os.path.isfile(path):
        return True
    path_timestamp = os.stat(path).st_mtime
    return path_timestamp < newest_timestamp


def create_argsparser():
    parser = argparse.ArgumentParser(
        prog = "yt2feed",
        description = "Create podcast feeds from video channels via yt-dlp",
    )
    subparsers = parser.add_subparsers(required=True, description = "action")

    rf = subparsers.add_parser("renderfeed", help = "render feed.xml for one video playlist")
    rf.add_argument("dir", help="working directory")
    rf.set_defaults(func=lambda args: do_render_feed(os.fsencode(args.dir)))

    dl = subparsers.add_parser("download", help = "download one playlist and any new videos")
    dl.add_argument("input_dir", help="input directory for one playlist")
    dl.add_argument("working_dir", help="working directory")
    dl.set_defaults(func=lambda args: do_download(os.fsencode(args.input_dir), os.fsencode(args.working_dir)))

    dl = subparsers.add_parser("all", help = "download and render all playlists")
    dl.add_argument("input_dir", help="input directory with sub-dirs with yt-dlp-args files")
    dl.add_argument("webroot_dir", help="webroot directory")
    dl.set_defaults(func=lambda args: do_all(os.fsencode(args.input_dir), os.fsencode(args.webroot_dir)))

    return parser


def do_all(input_dir, webroot_dir):
    for dir in os.listdir(input_dir):
        if not os.path.isdir(dir):
            continue
        fulldir = os.path.join(input_dir, dir)
        working_dir = os.path.join(webroot_dir, dir)
        if not os.path.isdir(working_dir):
            os.mkdir(working_dir)
        do_download(fulldir, working_dir)
        do_render_feed(working_dir)


def do_download(input_dir, working_dir):
    input_file = os.path.join(input_dir, b"yt-dlp-args")
    with open(input_file, "r") as argsfile:
        yt_dlp_args = argsfile.read().splitlines()
    full_args = YT_DLP_ARGS_COMMON + yt_dlp_args
    p = subprocess.run(full_args, cwd=working_dir)
    if not p.returncode in [0, 101]:
        sys.exit(p.returncode)


def do_render_feed(podcast_directory):
    template_data = get_template_data(podcast_directory)
    pprint(template_data)
    out_file = os.path.join(podcast_directory, b"feed.xml")
    if file_needs_update(out_file, template_data["newest_media_file_timestamp"]):
        render(out_file, template_data)
    else:
        print("Noting to do")


def main():
    args = create_argsparser().parse_args()
    args.func(args)


main()
