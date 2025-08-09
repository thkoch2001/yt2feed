from pprint import pprint

import argparse
import datetime
from jinja2 import Environment, PackageLoader, StrictUndefined
import json
import os
from pathlib import Path
import re
import subprocess
import sys

INFO_JSON_SUFFIX = ".info.json"
PROGRAM_NAME = "yt2feed"
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
    "--download-archive", "download-archive",
    "--retry-sleep", "http:exp=1:100:3",
    "--retry-sleep", "fragment:exp=1:20",
]

def get_thumbnail_filename(dir_path, basename):
    extension = "jpg"
    filename = ".".join([basename, extension])
    if (dir_path / filename).is_file():
      return filename


def get_media_filename(dir_path, basename, thumbnail_filename):
    media_filename = None
    for file in dir_path.iterdir():
        filename = file.name
        if not filename.startswith(basename):
            continue
        if filename.endswith(INFO_JSON_SUFFIX):
            continue
        if filename == thumbnail_filename:
            continue
        if media_filename is not None:
            print(f"Error: Found two possible media files: '{media_filename}' and '{filename}'")
            sys.exit(1)
        media_filename = filename

    if media_filename is None:
        print(f"Error: no media file found for '{basename}'")
        sys.exit(1)
    return media_filename


def parse_pl_info_json(working_path, mdjs):
#TODO!!!!
    return {
        'description' : None,
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
    return fullpath.stat().st_ctime


def parse_info_json(working_path, info_json_file):
    fullpath = working_path / info_json_file
    mdjs = json.load(fullpath.open())
    if mdjs.get("_type") == "playlist":
        return ("playlist", parse_pl_info_json(working_path, mdjs))
    basename = info_json_file.name.removesuffix(INFO_JSON_SUFFIX)
    thumbnail_filename = get_thumbnail_filename(working_path, basename)
    media_filename = get_media_filename(working_path, basename, thumbnail_filename)

    return (mdjs.get("_type"), {
        "title": mdjs["title"],
        "id": mdjs["id"],
        "timestamp": parse_timestamp(mdjs, fullpath),
        "pub_date": datetime.datetime.strptime(mdjs["upload_date"], "%Y%m%d").strftime("%a, %d %b %Y %H:%M:%S +0000") if mdjs.get("upload_date") is not None else None,
        "description": mdjs.get("description"),
        "thumbnail_filename": thumbnail_filename,
        "media_filename": media_filename,
        "media_file_stat": (working_path / media_filename).stat(),
        "duration": str(datetime.timedelta(seconds=mdjs["duration"])) if mdjs.get("duration") is not None else None,
        "original_url": mdjs.get("url"),
        "media_type": "audio", # TODO: just add file extension after slash?
    })


def get_template_data(working_path):
    entries = []
    pl_info = None
    newest_media_file_timestamp = 0
    for file in working_path.iterdir():
        if not file.name.endswith(INFO_JSON_SUFFIX):
            continue

        (t, parsed_info_json) = parse_info_json(working_path, file)
        if t == "playlist":
            if pl_info == None:
                pl_info = parsed_info_json
                continue
            else:
                print("Error: Found a second playlist .info.json file. exiting")
                sys.exit(1)

        newest_media_file_timestamp = max(parsed_info_json["media_file_stat"].st_mtime, newest_media_file_timestamp)
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
    if not path.exists():
        return True
    path_timestamp = path.stat().st_mtime
    return path_timestamp < newest_timestamp


def do_download(subscription_path, working_path):
    sub_config = Config(subscription_path)
    yt_dlp_args = sub_config.get("yt-dlp-args").splitlines()
    full_args = YT_DLP_ARGS_COMMON + yt_dlp_args
    # TODO: put url in separate url file

    p = subprocess.run(full_args, cwd=working_path)
    if not p.returncode in [0, 101]:
        sys.exit(p.returncode)


def do_render_feed(webroot_url, working_path):
    template_data = get_template_data(working_path)
    template_data["base_url"] = webroot_url.removesuffix("/") + "/" + working_path.name
    out_path = working_path / "feed.xml"
    if file_needs_update(out_path, template_data["newest_media_file_timestamp"]):
        render(out_path, template_data)
    else:
        print("Noting to do")


class Config():
    def __init__(self, path):
        self.path = path

    @classmethod
    def get_config(cls, config_argument):
        if config_argument is not None:
            if not config_argument.is_dir():
                print(f"Error: not a directory '{config_argument}'")
                exit(1)
            return config_argument

        p = Path("/etc") / PROGRAM_NAME
        if p.is_dir():
            return cls(p)
        _home = os.path.expanduser('~')
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or os.path.join(_home, '.config')
        p = Path(xdg_config_home) / PROGRAM_NAME
        if p.is_dir():
            return cls(p)
        print("No config dir found")
        sys.exit(1)

    def get(self, name):
        p = self.path / name
        return p.read_text().strip()

    def iter(self, name):
        p = self.path / name
        return p.iterdir()

# TODO:
# - logging
# - provide title, description
# - don't download channel thumbnail on every update

def create_argsparser():
    parser = argparse.ArgumentParser(
        prog = PROGRAM_NAME,
        description = "Create podcast feeds from video channels via yt-dlp",
    )
    parser.add_argument('--config', '-c', type=Path, metavar="PATH")
    action_choices = ["download", "render"]
    parser.add_argument('--action', '-a', choices=action_choices, default=action_choices, nargs='*')
    parser.add_argument('--include', '-i', metavar="REGEX")

    subparsers = parser.add_subparsers(required=False, dest="sub")

    sub_add = subparsers.add_parser("add", help = "add video channel")
    sub_add.add_argument("name", help="Name to be used for the feed's folder and url")
    sub_add.add_argument("url", help="vidoe channel url")

    sub_list = subparsers.add_parser("list", help = "list video channels, respect include filter")

    return parser


def iter_subscriptions(config, include):
    pattern = re.compile(include, re.IGNORECASE) if include else None

    for subscription_path in config.iter("subscriptions"):
        if not subscription_path.is_dir():
            continue

        if not pattern or pattern.search(subscription_path.name):
            yield(subscription_path)


def do_run(config, action, include):
    webroot_path = Path(config.get("webroot_path"))
    webroot_url = config.get("webroot_url")
    for subscription_path in iter_subscriptions(config, include):
        working_path = webroot_path / (subscription_path.name)
        if not working_path.is_dir():
            working_path.mkdir()

        if 'download' in action:
            do_download(subscription_path, working_path)
        if 'render' in action:
            do_render_feed(webroot_url, working_path)


def do_list(config, include):
    for subscription_path in iter_subscriptions(config, include):
        print(subscription_path.name)


def do_add(config, name, url):
    dir = config.path / name
    dir.mkdir()
    (dir / "yt-dlp-args").write_text(url)


def main():
    args = create_argsparser().parse_args()
    pprint(args)
    config = Config.get_config(args.config)

    match args.sub:
        case None:
            do_run(config, args.action, args.include)
        case "add":
            do_add(config, args.name, args.url)
        case "list":
            do_list(config, args.include)

main()
