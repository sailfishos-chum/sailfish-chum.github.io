"""
This module generates the static website
"""
import json
import os
import random
from urllib.parse import urljoin

from jinja2 import Environment, PackageLoader, Template, select_autoescape, pass_eval_context
from jinja2.nodes import EvalContext
from markupsafe import Markup
from os import makedirs, mkdir
from pathlib import Path
from shutil import copy2, rmtree
from typing import List, Dict

from . import CONFIG
from .package import Package

from datetime import datetime
import importlib.resources as resources

from .progress import begin_step, step_progress
from .repo_loader import RepoInfo

ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def gen_site(repo_info: RepoInfo, out_dir: Path):
    """
    Generates the static website given a list of packages
    :param repo_info: The repository info and packages to generate the website for
    :param out_dir: The directory to output the generated website in
    """
    sitegen_step = begin_step("Generating site")
    www_path = out_dir.joinpath("www")
    www_pkgs_path = www_path.joinpath("pkgs")
    www_apps_path = www_path.joinpath("apps")
    updated = datetime.today()

    sorted_pkgs = sorted([pkg for pkg in repo_info.packages if not pkg.is_debug()], key=lambda pkg: str(pkg.title).lower())
    recently_updated_pkgs = sorted(
        [pkg for pkg in repo_info.packages if pkg.is_app()],
        reverse=True, key=lambda pkg: pkg.updated
    )[:CONFIG.updated_apps_count]

    def render_template(template: Template, out_file: str | Path, **kwargs):
        kwargs["updated"] = updated
        kwargs["chum_installer"] = "sailfishos-chum-gui-installer"
        kwargs["config"] = CONFIG
        kwargs["repo_version"] = repo_info.version
        kwargs["recently_updated_pkgs"] = recently_updated_pkgs
        template.stream(**kwargs).dump(str(out_file))

    def _copy_dir(source, dest: Path):
        """
        Copies a resource directory, obtained via `resource.files()`, to the specified destination `dest` on the filesystem
        """
        child = dest.joinpath(source.name)
        if source.is_dir():
            mkdir(child)
            for entry in source.iterdir():
                _copy_dir(entry, child)
        else:
            # source is a file
            child.write_bytes(source.read_bytes())

    def copy_static_dirs() -> None:
        static_dir = resources.files(__package__ + ".www.static")
        _copy_dir(static_dir, www_path)

    def recreate_directory_skeleton() -> None:
        rmtree(www_path, onerror=print)
        makedirs(www_path, exist_ok=True)
        makedirs(www_apps_path)
        makedirs(www_pkgs_path)



    def pkgs_buckets() -> Dict[str, List[Package]]:
        dict: Dict[str, List[Package]] = {}
        for letter in ALPHABET + "?":
            dict[letter] = []

        for pkg in sorted_pkgs:
            first_letter = pkg.title.lower()[0]
            if first_letter.isalpha():
                dict[first_letter].append(pkg)
            else:
                dict["?"].append(pkg)
        return dict

    def create_package_page(pkg: Package):
        pkg_template = env.get_template("pages/package.html")
        pkg_dir = www_pkgs_path.joinpath(pkg.name)
        out_file = pkg_dir.joinpath("index.html")
        os.makedirs(pkg_dir, exist_ok=True)

        if pkg.is_app():
            app_dir = www_apps_path.joinpath(pkg.name)
            os.symlink(pkg_dir.absolute(), app_dir.absolute(), True)

        render_template(pkg_template, str(out_file), pkg=pkg)

    total_sitegen_steps = 5
    step_progress(sitegen_step, "Creating directory structure", 1, total_sitegen_steps)
    recreate_directory_skeleton()
    copy_static_dirs()

    pkgs_by_letter = pkgs_buckets()

    env = Environment(
        loader=PackageLoader(__package__ + ".www", "views"),
        autoescape=select_autoescape(),
    )
    env.filters["bytes"] = _bytes_filter
    env.filters["paragraphise"] = _paragraphise_filter
    env.filters["fallback_icon"] = _fallback_icon_filter
    env.filters["format_datetime"] = _format_datetime
    env.filters["to_public_url"] = _to_absolute_url_filter

    step_progress(sitegen_step, "Generating static pages", 2, total_sitegen_steps)

    home_template = env.get_template("pages/index.html")
    featured_apps = random.sample([pkg for pkg in sorted_pkgs if pkg.is_app()], CONFIG.featured_apps_count)
    render_template(home_template, www_path.joinpath("index.html"), featured_apps=featured_apps)

    about_template = env.get_template("pages/about.html")
    render_template(about_template, www_path.joinpath("about.html"))

    about_generator = env.get_template("pages/about-generator.html")
    render_template(about_generator, www_path.joinpath("about-generator.html"),
                    pkgs=[pkg for pkg in repo_info.packages if pkg.caused_requests()])

    search_generator = env.get_template("pages/search.html")
    render_template(search_generator, www_path.joinpath("search.html"))

    step_progress(sitegen_step, "Generating package pages", 3, total_sitegen_steps)

    for pkg in repo_info.packages:
        create_package_page(pkg)

    letter_map = {l: {"display": l.upper(), "file": f"-{l}"} for l in ALPHABET}
    letter_map["?"] = {"display": "?", "file": "-other"}
    letter_map["*"] = {"display": "ALL", "file": ""}

    pkg_lists = [
        {
            "name": "All apps",
            "file": "apps/index.html",
            "pkgs": filter(lambda pkg: pkg.is_app(), sorted_pkgs),
            "current_letter": "*",
            "current_filter": "apps"
        },
        {
            "name": "All packages",
            "file": "pkgs/index.html",
            "pkgs": sorted_pkgs,
            "current_letter": "*",
            "current_filter": "pkgs"
        },
    ]

    pkg_filters = ["pkgs", "apps"]
    for pkg_filter in pkg_filters:
        for letter in ALPHABET + "?":
            if pkg_filter == "apps":
                filtered_pkg_list = filter(lambda pkg: pkg.is_app(), pkgs_by_letter[letter])
                filter_name = "apps"
            else:
                filtered_pkg_list = pkgs_by_letter[letter]
                filter_name = "packages"

            other = "other"
            disp = f"'{letter.upper()}'" if letter.isalpha() else "other characters"
            pkg_lists.append({
                "name": f"All {filter_name} starting with {disp}",
                "file": f"{pkg_filter}/index-{letter if letter.isalpha() else other}.html",
                "pkgs": filtered_pkg_list,
                "current_letter": letter,
                "current_filter": pkg_filter
            })

    step_progress(sitegen_step, "Generating package lists", 4, total_sitegen_steps)
    for pkg_list in pkg_lists:
        pkg_list_template = env.get_template("pages/package-index.html")
        template_args = pkg_list
        template_args["letter_map"] = letter_map
        render_template(pkg_list_template, www_path.joinpath(pkg_list["file"]), **template_args)

    # Generate search index
    step_progress(sitegen_step, "Generating search index", 5, total_sitegen_steps)
    search_index, search_documents = create_search_index(sorted_pkgs)

    with open(www_path.joinpath("packages-index.json"), "w") as search_index_file:
        json.dump(search_index.serialize(), search_index_file)

    with open(www_path.joinpath("packages.json"), "w") as packages_file:
        json.dump(search_documents, packages_file)


def _bytes_filter(size: str) -> str:
    """
    Converts `size` in bytes to a human readable unit, such as KiB, MiB and GiB
    """
    from math import log2

    amount = 0
    unit = "bytes"
    try:
        amount = int(size)
    except (ValueError, TypeError):
        return "??? bytes"

    order_of_magnitude = log2(amount) / 10 if amount > 0 else 0

    if order_of_magnitude >= 3:
        amount /= 1024 ** 3
        unit = "GiB"
    elif order_of_magnitude >= 2:
        amount /= 1024 ** 2
        unit = "MiB"
    elif order_of_magnitude >= 1:
        amount /= 1024
        unit = "KiB"
    else:
        unit = "bytes"

    amount = round(amount, 1)

    return f"{amount} {unit}"


def create_search_index(pkgs: List[Package]):
    """
    Generates a search index that can be used in the front-end with the Lunr library
    :param pkgs:
    :return:
    """
    import lunr
    documents = [pkg.to_search_dict() for pkg in pkgs]
    index = lunr.lunr(
        ref="name",
        fields=(
            {"field_name": "name", "boost": 5},
            {"field_name": "title", "boost": 3},
            {"field_name": "summary", "boost": 2},
            {"field_name": "description", "boost": 1}
        ),
        documents=documents
    )
    return index, documents


@pass_eval_context
def _paragraphise_filter(eval_ctx: EvalContext, value: str):
    """
    Converts paragraphs in plain-text seperated by double newlines into p tags
    """
    result = Markup("<p>\n")
    empty_lines: int = 0

    for line in value.splitlines(True):
        if len(line) == 0:
            empty_lines += 1
            if empty_lines >= 2:
                result += Markup("\n</p><p>\n")
                empty_lines = 0
        else:
            result += Markup.escape(line)

        result += Markup("</p>")
    return Markup(result) if eval_ctx.autoescape else result


def _fallback_icon_filter(value: str):
    if value and value.strip():
        return value
    else:
        return urljoin(CONFIG.public_url, "static/img/pkg-fallback.png")


def _format_datetime(value: datetime, format_str=None):
    if format_str:
        return value.strftime(format_str)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _to_absolute_url_filter(path: str) -> str:
    """
    Resolves a path to an absolute URL  based on the public URL in the configuration.

    This way, we do not care whether the site gets deployed on a subdirectory or not
    """
    return urljoin(CONFIG.public_url, path)
