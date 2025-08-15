import argparse
from datetime import datetime, timedelta, UTC
from jinja2 import Environment, PackageLoader, StrictUndefined
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys


INFO_JSON_SUFFIX = ".info.json"
PROGRAM_NAME = "yt2feed"
YT_DLP_ARGS_COMMON = [
    "yt-dlp",
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


def is_dir_empty(path):
    not any(path.iterdir())


def ee(msg, code=1):
    logger.error(msg)
    sys.exit(code)


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
            ee(f"Found two possible media files: '{media_filename}' and '{filename}'")
        media_filename = filename

    if media_filename is None:
        ee(f"no media file found for '{basename}'")
    return media_filename


def parse_timestamp(mdjs, fullpath):
    if "timestamp" in mdjs:
        return mdjs["timestamp"]
    if "upload_date" in mdjs:
        return datetime.strptime(mdjs["upload_date"], "%Y%m%d").timestamp()
    return fullpath.stat().st_ctime


def parse_info_json(working_path, info_json_file, sub_config):
    fullpath = working_path / info_json_file
    mdjs = json.load(fullpath.open())
    basename = info_json_file.name.removesuffix(INFO_JSON_SUFFIX)
    thumbnail_filename = get_thumbnail_filename(working_path, basename)

    if mdjs.get("_type") == "playlist":
        return ("playlist",{
            'description' : mdjs.get("description", sub_config.get_or("description", None)),
            'subscription_url': sub_config.get("url"),
            'title': mdjs.get("title", sub_config.get_or("title", sub_config.path.name)),
            'thumbnail_filename': thumbnail_filename,
        })

    media_filename = get_media_filename(working_path, basename, thumbnail_filename)

    updated = datetime \
        .strptime(mdjs["upload_date"], "%Y%m%d") \
        .replace(tzinfo=UTC) \
        .isoformat(timespec="seconds") \
        if mdjs.get("upload_date") is not None else None

    return (mdjs.get("_type"), {
        "title": mdjs["title"],
        "id": mdjs["id"],
        "timestamp": parse_timestamp(mdjs, fullpath),
        "updated": updated,
        "description": mdjs.get("description"),
        "thumbnail_filename": thumbnail_filename,
        "media_filename": media_filename,
        "media_file_stat": (working_path / media_filename).stat(),
        "duration": str(timedelta(seconds=mdjs["duration"])) if mdjs.get("duration") is not None else None,
        "original_url": mdjs.get("url"),
        "media_type": "audio/*", # TODO: just add file extension after slash?
    })


def get_template_data(working_path, sub_config):
    entries = []
    pl_info = None
    newest_media_file_timestamp = 0
    for file in working_path.iterdir():
        if not file.name.endswith(INFO_JSON_SUFFIX):
            continue

        (t, parsed_info_json) = parse_info_json(working_path, file, sub_config)
        if t == "playlist":
            if pl_info == None:
                pl_info = parsed_info_json
                continue
            else:
                ee(f"Found a second playlist .info.json file for {working_path.name}: {file.name}")

        newest_media_file_timestamp = max(parsed_info_json["media_file_stat"].st_mtime, newest_media_file_timestamp)
        entries.append(parsed_info_json)

    if pl_info == None:
        ee("Error: No playlist .info.json file found!")

    entries.sort(reverse=True, key=lambda x: x["timestamp"])
    return pl_info | {
        'entries': entries,
        'newest_media_file_timestamp': newest_media_file_timestamp,
        'updated': datetime.fromtimestamp(newest_media_file_timestamp, UTC).isoformat(timespec="seconds"),
        'working_path_name': working_path.name,
    }


def render(out_file, template_data):
    environment = Environment(
        loader=PackageLoader(__name__),
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


def do_download(subscription_path, working_path, force_plthumb):
    sub_config = Config(subscription_path)
    yt_dlp_args = sub_config.get_or("yt-dlp-args", "").splitlines()
    url = sub_config.get("url")

    full_args = [] + YT_DLP_ARGS_COMMON

    if logger.isEnabledFor(logging.DEBUG):
        full_args.append("--verbose")

    # avoid re-downloading playlist thumbnails after first download
    if not force_plthumb and not is_dir_empty(working_path):
        full_args += ("-o", "pl_thumbnail:")

    full_args += yt_dlp_args
    full_args.append(url)

    logger.info(f"starting download for {subscription_path.name}")
    p = subprocess.run(full_args, cwd=working_path)
    if not p.returncode in [0, 101]:
        ee(f"yt-dlp returned error code {p.returncode}")


def do_render_feed(common_template_data, working_path, sub_config, force):
    template_data = common_template_data | get_template_data(working_path, sub_config)
    out_path = working_path / template_data["feed_file_name"]

    if force or file_needs_update(out_path, template_data["newest_media_file_timestamp"]):
        logger.warning(f"rendering {working_path.name}")
        render(out_path, template_data)
    else:
        logger.info(f"no rendering needed for {working_path.name}")


class Config():
    def __init__(self, path):
        self.path = path

    @classmethod
    def get_config(cls, config_argument):
        if config_argument is not None:
            if not config_argument.is_dir():
                logger.warning(f"not a directory '{config_argument}'")
            return cls(config_argument)

        p = Path("/etc") / PROGRAM_NAME
        if p.is_dir():
            return cls(p)
        _home = os.path.expanduser('~')
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or os.path.join(_home, '.config')
        p = Path(xdg_config_home) / PROGRAM_NAME
        p.mkdir(parents=True, exist_ok=True)
        return cls(p)


    def get(self, name):
        p = self.path / name
        return p.read_text().strip()

    def get_or(self, name, default=None):
        p = self.path / name
        if p.is_file():
            return self.get(name)
        return default

    def iter(self, name):
        p = self.path / name
        return p.iterdir()


def create_argsparser():
    def regex(pattern):
        def validate(arg_value):
            if not re.match(pattern, arg_value):
                raise argparse.ArgumentTypeError("invalid value")
            return arg_value

        return validate

    parser = argparse.ArgumentParser(
        prog = PROGRAM_NAME,
        description = "Create podcast feeds from video channels via yt-dlp",
    )
    parser.add_argument('--config', '-c', type=Path, metavar="PATH")
    parser.add_argument('--loglevel', '-l', metavar="LEVEL", default="warning", choices=[
        "debug", "info", "warning", "error"
    ])
    action_choices = ["download", "render"]
    parser.add_argument('--action', '-a', choices=action_choices, default=action_choices, nargs='*')
    parser.add_argument('--include', '-i', metavar="REGEX")
    parser.add_argument('--force-render', action=argparse.BooleanOptionalAction)
    parser.add_argument('--force-plthumb', action=argparse.BooleanOptionalAction, help="force re-download of playlist thumbnail")

    subparsers = parser.add_subparsers(required=False, dest="sub")

    sub_add = subparsers.add_parser("add", help = "add video channel")
    sub_add.add_argument("--dateafter", help="Download only videos uploaded on or after this date", metavar="YYYYMMDD", type=regex("^\\d{8}$"))
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


def do_run(config, args):
    action = args.action

    webroot_path = Path(config.get("webroot_path"))
    common_template_data = {
        'webroot_url': config.get("webroot_url").removesuffix("/") + "/",
        'stylesheet_url': config.get_or("stylesheet_url"),
        'feed_file_name': config.get_or("feed_file_name", "feed.xml"),
    }

    for subscription_path in iter_subscriptions(config, args.include):
        working_path = webroot_path / (subscription_path.name)
        working_path.mkdir(parents=True, exist_ok=True)

        if 'download' in action:
            do_download(subscription_path, working_path, args.force_plthumb)
        if 'render' in action:
            do_render_feed(common_template_data, working_path, Config(subscription_path), args.force_render)


def do_list(config, include):
    for subscription_path in iter_subscriptions(config, include):
        print(subscription_path.name)


def do_add(config, name, url, args):
    dir = config.path / "subscriptions" / name
    if dir.is_dir():
        ee(f"Subscription with name '{name}' already exists.")
    dir.mkdir(parents=True, exist_ok=True)
    (dir / "url").write_text(url)

    yt_dlp_args = ""
    if args.dateafter:
        yt_dlp_args += f"--break-match-filters\nupload_date>={args.dateafter}\n"

    (dir / "yt-dlp-args").write_text(yt_dlp_args)


def main():
    args = create_argsparser().parse_args()
    logging.basicConfig(
        level=args.loglevel.upper(),
        stream=sys.stderr,
        format="{levelname[0]}: {message}",
        style='{',
    )
    config = Config.get_config(args.config)
    logger.debug(f"Using config at {config.path}")

    match args.sub:
        case None:
            do_run(config, args)
        case "add":
            do_add(config, args.name, args.url, args)
        case "list":
            do_list(config, args.include)


logger = logging.getLogger(__name__)
if __name__ == '__main__':
    main()
