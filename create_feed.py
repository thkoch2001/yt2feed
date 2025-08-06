from pprint import pprint

import datetime
from jinja2 import Environment, FileSystemLoader, StrictUndefined#, Template
import json
import os
import sys

INFO_JSON_SUFFIX = b".info.json"


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


def render(script_dir, out_file, template_data):
    templates_dir = os.path.join(script_dir, "templates")
    environment = Environment(
        loader=FileSystemLoader(templates_dir),
        undefined=StrictUndefined
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


def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    podcast_directory = os.fsencode(sys.argv[1])
    template_data = get_template_data(podcast_directory)
    pprint(template_data)
    out_file = os.path.join(podcast_directory, b"feed.xml")
    if file_needs_update(out_file, template_data["newest_media_file_timestamp"]):
        render(script_dir, out_file, template_data)
    else:
        print("Noting to do")


main()
