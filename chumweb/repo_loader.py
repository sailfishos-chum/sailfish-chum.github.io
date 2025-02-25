"""
This module performs finding package repos, downloading indexes and parsing metadata.
"""
from dataclasses import dataclass
from functools import reduce
from gzip import GzipFile
from os import makedirs
from pathlib import Path
from typing import List, TypedDict, NotRequired, Unpack, Tuple, Dict, Optional
from urllib.parse import urljoin

from . import CONFIG
from .package import Package, ChangelogEntry

import requests
import xml.dom.minidom as minidom

from .progress import begin_step, step_progress, StepHandle

DEFAULT_HEADERS = {
    "User-Agent": f"{CONFIG.user_agent} ({CONFIG.public_url}/about-generator.html)"
}

OBS_API_HEADERS = DEFAULT_HEADERS | {
    "Accept": "application/xml;charset=utf-8"
}


@dataclass
class RepoInfo:
    packages: List[Package]
    repos: List[str]
    version: str  # SFOS version

    def repo_archs(self):
        """
        :return: the CPU architectures for which a repository provides packages.
        """
        return [repo.split("_")[1] for repo in self.repos]


# OBS API: https://api.opensuse.org/apidocs/index#/Search/get_search_package
def list_obs_project_repos(obs_url: str, project: str, auth):
    """
    List available repos on an Open Build Service (OBS) instance for a specified OBS project,
    using the provided authentication.
    """
    r = requests.get(urljoin(obs_url, f"build/{project}"), headers=OBS_API_HEADERS, auth=auth)
    doc = minidom.parseString(r.content)
    repos = [el.getAttribute("name") for el in doc.getElementsByTagName("entry")]
    return repos


def filter_newest_repos(repos: List[str]):
    """
    Return the list of repos with the newest version number(s).

    Example:
        `get_newest_repos(["4.5.0.24_i486", "4.5.0.24_aarch64", "4.4.0.72_i486", "4.4.0.72_aarch64"])` returns
        `["4.5.0.24_i486", "4.5.0.24_aarch64"]`
    """

    def cmp_repo_version(left: str, right: str) -> str:
        """
        Compare two repository names `left` and `right`, return the one with the newer version number,
        or return `left` if the versions are equal.
        """

        def ver_nos(repo_name: str):
            ver = repo_name.split("_")[0]
            return [int(part) for part in ver.split(".")]

        ver_l = ver_nos(left)
        ver_r = ver_nos(right)

        for (l, r) in zip(ver_l, ver_r):
            if l > r:
                return left
            elif l < r:
                return right
            else:
                continue

        return left

    # Find the repo with the highest version number (ignore the architecture)
    newest_version = reduce(cmp_repo_version, repos).split("_")[0] + "_"
    return [repo for repo in repos if repo.startswith(newest_version)]


class LoadRepoOptions(TypedDict):
    data_path: NotRequired[Path]
    repos: List[str]


def load_repo(obs_url: str, obs_project: str, obs_auth: Tuple[str, str], repo_url: str,
              out_dir: Path, **kwargs: Unpack[LoadRepoOptions]) -> RepoInfo:
    if "repos" in kwargs:
        repos = kwargs["repos"]
    else:
        begin_step("Listing repos")
        repos = filter_newest_repos(list_obs_project_repos(obs_url, obs_project, obs_auth))

    data_paths: List[Dict[str, Path]]
    if "data_path" in kwargs:
        data_paths = [{
                'primary': Path(kwargs["data_path"], f"{repo}-primary.xml.gz"),
                'other': Path(kwargs["data_path"], f"{repo}-other.xml.gz")
            } for repo in repos]
    else:
        begin_step("Downloading repos")
        data_paths = [save_repo_data(urljoin(repo_url, repo_name + "/"), repo_name, out_dir) for repo_name in repos]

    all_pkgs = {}

    parse_step = begin_step("Parsing repo index")
    repo_count = len(repos)
    i = 1
    for data_path, repo_name in zip(data_paths, repos):
        step_progress(parse_step, repo_name, i, repo_count)
        arch = repo_name.split("_")[1]
        all_pkgs[arch] = read_repo_data(urljoin(repo_url, repo_name), data_path, repo_name)
        link_debug_packages(all_pkgs[arch])
        i += 1

    all_pkg_list: Dict[str, Package] = {}

    begin_step("Combining repos")
    for arch, pkg_list in all_pkgs.items():
        for pkg in pkg_list.values():
            if pkg.name in all_pkg_list:
                all_pkg_list[pkg.name].merge_arch(pkg)
            else:
                all_pkg_list[pkg.name] = pkg

    if CONFIG.download_extra_metadata:
        remote_desc_step = begin_step("Loading remote descriptions")
        load_remote_descriptions(all_pkg_list.values(), remote_desc_step)

    result = RepoInfo(list(all_pkg_list.values()), repos, repos[0].split('_')[0])

    return result


def save_repo_data(repo_url: str, repo_name: str, out_dir: Path):
    """
    For a given a `repo_url`, find and download the `primary.xml.gz` file to `out_dir`.
    """

    files_to_download = ["primary", "other"]
    data_urls = {}
    data_paths = {}

    def download_file(url: str, destination: Path):
        """
        Downloads the file at `url` to the given `destination`
        """
        with open(destination, "wb") as gzFile:
            r = requests.get(url, headers=DEFAULT_HEADERS)

            for chunk in r.iter_content(8096):
                gzFile.write(chunk)

    makedirs(out_dir, exist_ok=True)
    r = requests.get(urljoin(repo_url, "repodata/repomd.xml"), headers=DEFAULT_HEADERS)
    xml = minidom.parseString(r.content)

    data_elements = xml.getElementsByTagName("data")

    for dataElement in data_elements:
        data_type = dataElement.getAttribute("type")
        if data_type in files_to_download:
            locations = dataElement.getElementsByTagName("location")
            if len(locations) > 0:
                data_urls[data_type] = locations[0].getAttribute("href")

    if "primary" not in data_urls:
        return

    for (data_type, data_url) in data_urls.items():
        data_url = urljoin(repo_url, data_url)
        data_path = out_dir.joinpath(f"{repo_name}-{data_type}.xml.gz")
        download_file(data_url, data_path)
        data_paths[data_type] = data_path

    return data_paths


def read_repo_data(repo_url, repo_info: Dict[str, Path], repo_name: str) -> Dict[str, Package]:
    """
    Read all package data from a `primary.xml.gz` file.
    """
    pkgs = {}
    with GzipFile(repo_info["primary"]) as gz:
        xml = minidom.parse(gz)
        for xmlPkg in xml.getElementsByTagName("package"):
            pkg = Package.from_node(xmlPkg, repo_name)
            if pkg.name in pkgs:
                pkgs[pkg.name].merge_arch(pkg)
            else:
                pkgs[pkg.name] = pkg

    if "other" in repo_info:
        with GzipFile(repo_info["other"]) as gz:
            xml = minidom.parse(gz)
            for xmlPkg in xml.getElementsByTagName("package"):
                name = xmlPkg.getAttribute("name")
                entries = ChangelogEntry.from_node(name, xmlPkg)
                pkgs[name].changelog_entries = entries

    return pkgs


def link_debug_packages(pkgs: Dict[str, Package]) -> None:
    """
    Link debug packages to their corresponding package.
    """

    last_pkg = None

    for (name, pkg) in pkgs.items():
        if name.endswith("-debuginfo"):
            base_name = name.removesuffix("-debuginfo")
            pkgs[base_name].debuginfo_package = pkg
            pass
        elif pkg.name.endswith("-debugsource"):
            base_name = name.removesuffix("-debugsource")
            pkgs[base_name].debugsource_package = pkg


def load_remote_descriptions(pkgs: List[Package], step: StepHandle):
    """
    Load remote descriptions of the given packages and modify them in place
    with their description.
    """
    from markdown import markdown
    from markupsafe import Markup
    pkgs_with_markdown = [pkg for pkg in pkgs if pkg.markdown_url]
    total_pkgs_with_markdown = len(pkgs_with_markdown)
    i = 1
    for pkg in pkgs_with_markdown:
        step_progress(step, pkg.name, i, total_pkgs_with_markdown)
        r = requests.get(pkg.markdown_url, headers=DEFAULT_HEADERS, allow_redirects=True)
        if r.ok:
            pkg.description = Markup(markdown(r.text, output_format="html"))
        i += 1
