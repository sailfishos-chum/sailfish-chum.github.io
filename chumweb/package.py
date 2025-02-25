"""
Data classes for package metadata; this also parses metadata of a single package.
"""
import logging
import re
from dataclasses import dataclass, field
import enum
from datetime import datetime, UTC
from enum import StrEnum
from types import NoneType
from typing import List, Dict, Self, Set, Optional

from markupsafe import Markup

from . import CONFIG
from .remote_image import RemoteImage

logger = logging.getLogger(__name__)


def _try_get_str(dom_element, name) -> str | None:
    """Return content of XML tag with `name` or None"""
    try:
        return dom_element.getElementsByTagName(name)[0].firstChild.nodeValue
    except (IndexError, AttributeError):
        return None


def _try_get_attribute_tags(dom_element, name, *args: str):
    """Return a tuple of the given attributes from an XML tag"""
    result = (())
    try:
        el = dom_element.getElementsByTagName(name)[0]

        for attr in args:
            result += (el.getAttribute(attr),)

        return result
    except IndexError:
        return tuple([None for _ in args])

class PackageApplicationCategory(StrEnum):
    """
    Application categories, for their specification(s) and references see entry "Categories:" in
    https://github.com/sailfishos-chum/main/blob/main/Metadata.md#table-of-field-descriptions
    """
    other = "Other"  # SailfishOS:Chum specific, i.e. not part of the Freedesktop.org categories specification(s)
    library = "Library"  # SailfishOS:Chum specific, i.e. not part of the Freedesktop.org categories specification(s)
    audiovideo = "AudioVideo"  # Application for presenting, creating, or processing multimedia (audio/video)
    audio = "Audio"  # An audio application.  Desktop entry must include AudioVideo as well.
    video = "Video"  # A video application.  Desktop entry must include AudioVideo as well.
    development = "Development"  # An application for development
    education = "Education"  # Educational software
    game = "Game"  # A game
    graphics = "Graphics"  # Application for viewing, creating, or processing graphics
    network = "Network"  # Network application such as a web browser
    office = "Office"  # An office type application
    science = "Science"  # Scientific software
    settings = "Settings"  # Settings applications.  Entries may appear in a separate menu or as part of a "Control Center".
    system = "System"  # System application, "System Tools" such as say a log viewer or network monitor
    utility = "Utility"  # Small utility application, "Accessories"
    building = "Building"  # A tool to build applications.  Must also be categorised as Development.
    debugger = "Debugger"  # A tool to debug applications.  Must also be categorised as Development.
    ide = "IDE"  # IDE application.  Must also be categorised as Development.
    guidesigner = "GUIDesigner"  # A GUI designer application.  Must also be categorised as Development.
    profiling = "Profiling"  # A profiling tool.  Must also be categorised as Development.
    revisioncontrol = "RevisionControl"  # Applications like cvs or subversion.  Must also be categorised as Development.
    translation = "Translation"  # A translation tool.  Must also be categorised as Development.
    calendar = "Calendar"  # Calendar application.  Must also be categorised as Office.
    contactmanagement = "ContactManagement"  # E.g. an address book.  Must also be categorised as Office.
    database = "Database"  # Application to manage a database.  Must also be categorised as Office or Development or AudioVideo.
    dictionary = "Dictionary"  # A dictionary.  Must also be categorised as Office or TextTools.
    chart = "Chart"  # Chart application.  Must also be categorised as Office.
    email = "Email"  # Email application.  Must also be categorised as Office or Network.
    finance = "Finance"  # Application to manage your finance.  Must also be categorised as Office.
    flowchart = "FlowChart"  # A flowchart application.  Must also be categorised as Office.
    pda = "PDA"  # Tool to manage your PDA.  Must also be categorised as Office.
    projectmanagement = "ProjectManagement"  # Project management application.  Must also be categorised as Office or Development.
    presentation = "Presentation"  # Presentation software.  Must also be categorised as Office.
    spreadsheet = "Spreadsheet"  # A spreadsheet.  Must also be categorised as Office.
    wordprocessor = "WordProcessor"  # A word processor.  Must also be categorised as Office.
    twodgraphics = "2DGraphics"  # 2D based graphical application.  Must also be categorised as Graphics.
    vectorgraphics = "VectorGraphics"  # Application for viewing, creating, or processing vector graphics.  Must also be categorised as Graphics;2DGraphics.
    rastergraphics = "RasterGraphics"  # Application for viewing, creating, or processing raster (bitmap) graphics.  Must also be categorised as Graphics;2DGraphics.
    threedgraphics = "3DGraphics"  # Application for viewing, creating, or processing 3-D graphics.  Must also be categorised as Graphics.
    scanning = "Scanning"  # Tool to scan a file/text.  Must also be categorised as Graphics.
    ocr = "OCR"  # Optical character recognition application.  Must also be categorised as Graphics;Scanning.
    photography = "Photography"  # Camera tools, etc..  Must also be categorised as Graphics or Office.
    publishing = "Publishing"  # Desktop Publishing applications and Color Management tools.  Must also be categorised as Graphics or Office.
    viewer = "Viewer"  # Tool to view e.g. a graphic or pdf file.  Must also be categorised as Graphics or Office.
    texttools = "TextTools"  # A text tool utility.  Must also be categorised as Utility.
    desktopsettings = "DesktopSettings"  # Configuration tool for the GUI.  Must also be categorised as Settings.
    hardwaresettings = "HardwareSettings"  # A tool to manage hardware components, like sound cards, video cards or printers.  Must also be categorised as Settings.
    printing = "Printing"  # A tool to manage printers.  Must also be categorised as HardwareSettings;Settings.
    packagemanager = "PackageManager"  # A package manager application.  Must also be categorised as Settings.
    dialup = "Dialup"  # A dial-up program.  Must also be categorised as Network.
    instantmessaging = "InstantMessaging"  # An instant messaging client.  Must also be categorised as Network.
    chat = "Chat"  # A chat client.  Must also be categorised as Network.
    ircclient = "IRCClient"  # An IRC client.  Must also be categorised as Network.
    feed = "Feed"  # RSS, podcast and other subscription based contents.  Must also be categorised as Network.
    filetransfer = "FileTransfer"  # Tools like FTP or P2P programs.  Must also be categorised as Network.
    hamradio = "HamRadio"  # HAM radio software.  Must also be categorised as Network or Audio.
    news = "News"  # A news reader or a news ticker.  Must also be categorised as Network.
    p2p = "P2P"  # A P2P program.  Must also be categorised as Network.
    remoteaccess = "RemoteAccess"  # A tool to remotely manage your PC.  Must also be categorised as Network.
    telephony = "Telephony"  # Telephony via PC.  Must also be categorised as Network.
    telephonytools = "TelephonyTools"  # Telephony tools, to dial a number, manage PBX, ....  Must also be categorised as Utility.
    videoconference = "VideoConference"  # Video Conference software.  Must also be categorised as Network.
    webbrowser = "WebBrowser"  # A web browser.  Must also be categorised as Network.
    webdevelopment = "WebDevelopment"  # A tool for web developers.  Must also be categorised as Network or Development.
    midi = "Midi"  # An app related to MIDI.  Must also be categorised as AudioVideo;Audio.
    mixer = "Mixer"  # Just a mixer.  Must also be categorised as AudioVideo;Audio.
    sequencer = "Sequencer"  # A sequencer.  Must also be categorised as AudioVideo;Audio.
    tuner = "Tuner"  # A tuner.  Must also be categorised as AudioVideo;Audio.
    tv = "TV"  # A TV application.  Must also be categorised as AudioVideo;Video.
    audiovideoediting = "AudioVideoEditing"  # Application to edit audio/video files.  Must also be categorised as Audio or Video or AudioVideo.
    player = "Player"  # Application to play audio/video files.  Must also be categorised as Audio or Video or AudioVideo.
    recorder = "Recorder"  # Application to record audio/video files.  Must also be categorised as Audio or Video or AudioVideo.
    discburning = "DiscBurning"  # Application to burn a disc.  Must also be categorised as AudioVideo.
    actiongame = "ActionGame"  # An action game.  Must also be categorised as Game.
    adventuregame = "AdventureGame"  # Adventure style game.  Must also be categorised as Game.
    arcadegame = "ArcadeGame"  # Arcade style game.  Must also be categorised as Game.
    boardgame = "BoardGame"  # A board game.  Must also be categorised as Game.
    blocksgame = "BlocksGame"  # Falling blocks game.  Must also be categorised as Game.
    cardgame = "CardGame"  # A card game.  Must also be categorised as Game.
    kidsgame = "KidsGame"  # A game for kids.  Must also be categorised as Game.
    logicgame = "LogicGame"  # Logic games like puzzles, etc.  Must also be categorised as Game.
    roleplaying = "RolePlaying"  # A role playing game.  Must also be categorised as Game.
    shooter = "Shooter"  # A shooter game.  Must also be categorised as Game.
    simulation = "Simulation"  # A simulation game.  Must also be categorised as Game.
    sportsgame = "SportsGame"  # A sports game.  Must also be categorised as Game.
    strategygame = "StrategyGame"  # A strategy game.  Must also be categorised as Game.
    art = "Art"  # Software to teach arts.  Must also be categorised as Education or Science.
    construction = "Construction"  # Must also be categorised as Education or Science.
    music = "Music"  # Musical software.  Must also be categorised as AudioVideo or Education.
    languages = "Languages"  # Software to learn foreign languages.  Must also be categorised as Education or Science.
    artificialintelligence = "ArtificialIntelligence"  # Artificial Intelligence software.  Must also be categorised as Education or Science.
    astronomy = "Astronomy"  # Astronomy software.  Must also be categorised as Education or Science.
    biology = "Biology"  # Biology software.  Must also be categorised as Education or Science.
    chemistry = "Chemistry"  # Chemistry software.  Must also be categorised as Education or Science.
    computerscience = "ComputerScience"  # ComputerSience software.  Must also be categorised as Education or Science.
    datavisualization = "DataVisualization"  # Data visualization software.  Must also be categorised as Education or Science.
    economy = "Economy"  # Economy software.  Must also be categorised as Education or Science.
    electricity = "Electricity"  # Electricity software.  Must also be categorised as Education or Science.
    geography = "Geography"  # Geography software.  Must also be categorised as Education or Science.
    geology = "Geology"  # Geology software.  Must also be categorised as Education or Science.
    geoscience = "Geoscience"  # Geoscience software, GIS.  Must also be categorised as Education or Science.
    history = "History"  # History software.  Must also be categorised as Education or Science.
    humanities = "Humanities"  # Software for philosophy, psychology and other humanities.  Must also be categorised as Education or Science.
    imageprocessing = "ImageProcessing"  # Image Processing software.  Must also be categorised as Education or Science.
    literature = "Literature"  # Literature software.  Must also be categorised as Education or Science.
    maps = "Maps"  # Software for viewing maps, navigation, mapping, GPS.  Must also be categorised as Education or Science or Utility.
    math = "Math"  # Math software.  Must also be categorised as Education or Science.
    numericalanalysis = "NumericalAnalysis"  # Numerical analysis software.  Must also be categorised as Education;Math or Science;Math.
    medicalsoftware = "MedicalSoftware"  # Medical software.  Must also be categorised as Education or Science.
    physics = "Physics"  # Physics software.  Must also be categorised as Education or Science.
    robotics = "Robotics"  # Robotics software.  Must also be categorised as Education or Science.
    spirituality = "Spirituality"  # Religious and spiritual software, theology.  Must also be categorised as Education or Science or Utility.
    sports = "Sports"  # Sports software.  Must also be categorised as Education or Science.
    parallelcomputing = "ParallelComputing"  # Parallel computing software.  Must also be categorised as Education;ComputerScience or Science;ComputerScience.
    amusement = "Amusement"  # A simple amusement
    archiving = "Archiving"  # A tool to archive/backup data.  Must also be categorised as Utility.
    compression = "Compression"  # A tool to manage compressed data/archives.  Must also be categorised as Utility;Archiving.
    electronics = "Electronics"  # Electronics software, e.g. a circuit designer
    emulator = "Emulator"  # Emulator of another platform, such as a DOS emulator.  Must also be categorised as System or Game.
    engineering = "Engineering"  # Engineering software, e.g. CAD programs
    filetools = "FileTools"  # A file tool utility.  Must also be categorised as Utility or System.
    filemanager = "FileManager"  # A file manager.  Must also be categorised as System;FileTools.
    terminalemulator = "TerminalEmulator"  # A terminal emulator application.  Must also be categorised as System.
    filesystem = "Filesystem"  # A file system tool.  Must also be categorised as System.
    monitor = "Monitor"  # Monitor application/applet that monitors some resource or activity.  Must also be categorised as System or Network.
    security = "Security"  # A security tool.  Must also be categorised as Settings or System.
    accessibility = "Accessibility"  # Accessibility.  Must also be categorised as Settings or Utility.
    calculator = "Calculator"  # A calculator.  Must also be categorised as Utility.
    clock = "Clock"  # A clock application/applet.  Must also be categorised as Utility.
    texteditor = "TextEditor"  # A text editor.  Must also be categorised as Utility.
    documentation = "Documentation"  # Help or documentation
    adult = "Adult"  # Application handles adult or explicit material
    core = "Core"  # Important application, core to the desktop such as a file manager or a help browser
    kde = "KDE"  # Application based on KDE libraries.  Must also be categorised as Qt.
    gnome = "GNOME"  # Application based on GNOME libraries.  Must also be categorised as GTK.
    xfce = "XFCE"  # Application based on XFCE libraries.  Must also be categorised as GTK.
    dde = "DDE"  # Application based on DDE libraries.  Must also be categorised as Qt.
    gtk = "GTK"  # Application based on GTK+ libraries
    qt = "Qt"  # Application based on Qt libraries
    motif = "Motif"  # Application based on Motif libraries
    java = "Java"  # Application based on Java GUI libraries, such as AWT or Swing
    consoleonly = "ConsoleOnly"  # Application that only works inside a terminal (text-based or command line application)
    screensaver = "Screensaver"  # A screen saver (launching this desktop entry should activate the screen saver)
    trayicon = "TrayIcon"  # An application that is primarily an icon for the "system tray" or "notification area" (apps that open a normal window and just happen to have a tray icon as well should not list this category)
    applet = "Applet"  # An applet that will run inside a panel or another such application, likely desktop specific
    shell = "Shell"  # A shell (an actual specific shell such as bash or tcsh, not a TerminalEmulator)


class PackageApplicationType(StrEnum):
    """
    Type of application a package provides, for their specification and references see entry "Type:" in
    https://github.com/sailfishos-chum/main/blob/main/Metadata.md#table-of-field-descriptions
    """
    generic = enum.auto()
    console_application = "console-application"
    desktop_application = "desktop-application"
    addon = enum.auto()
    codec = enum.auto()
    inputmethod = enum.auto()
    firmware = enum.auto()


CHANGELOG_LINE_REGEX = re.compile(r"^[ \t]*-\s*(?:\[(?P<section>[^]]+)])?\s*(?P<log>\w.*)$")
@dataclass
class ChangelogEntryLine:
    section: str
    text: str

    @staticmethod
    def parse_from_text(text: str) -> List["ChangelogEntryLine"]:

        result: List["ChangelogEntryLine"] = []

        for line in text.splitlines():
            match = CHANGELOG_LINE_REGEX.match(line)
            if match:
                category = match.group("section")
                if category is None:
                    category = ""
                log = match.group("log").strip()

                # Skip empty log lines
                if log == "":
                    continue
                result.append(ChangelogEntryLine(category, log))
            elif len(result) == 0:
                # If the first line fails to parse, it should simply fall back
                return []
            else:
                stripped_line = line.strip()
                if stripped_line != "":
                    result[-1].text += " " + stripped_line

        # Sort entries without a category before the others
        return list([e for e in result if e.section == ""]) + list([e for e in result if e.section != ""])

AUTHOR_VERSION_REGEX = re.compile(r"(?P<author>.*) *<(?P<email>.*)>[ -]*(?P<version>.*)")
@dataclass
class ChangelogEntry:
    timestamp: datetime
    author: str
    email: str
    version: str
    text: str
    lines: List[ChangelogEntryLine]

    @staticmethod
    def from_node(pkg_name: str, dom_element) -> List:
        entries: List["ChangelogEntry"] = []

        for entry in dom_element.getElementsByTagName("changelog"):
            try:
                text: str = entry.firstChild.nodeValue
                author_and_version = entry.getAttribute("author")
                timestamp = datetime.fromtimestamp(int(entry.getAttribute("date")))
                m = AUTHOR_VERSION_REGEX.fullmatch(author_and_version)
                if m:
                    author, email, version = m.group("author", "email", "version")
                else:
                    author = author_and_version
                    email = ""
                    version = ""
                entries.append(ChangelogEntry(timestamp, author, email, version, text,
                                              ChangelogEntryLine.parse_from_text(text)))
            except Exception as e:
                logger.warning(f"Parsing failed for changelog entry from {pkg_name}", exc_info=e)

        # Changelog entries are found from old to new in the XML
        entries.reverse()
        return entries

@dataclass
class PackageVersion:
    epoch: str
    ver: str
    rel: str

    def __init__(self, epoch, ver, rel):
        self.epoch = epoch
        self.ver = ver
        self.rel = rel

    def to_short_str(self) -> str:
        return self.ver.split('+', 2)[0]

    def to_full_str(self) -> str:
        return f"{self.ver}-{self.rel}"


@dataclass
class Package:
    """
    Metadata of an RPM package with associated metadata for SailfishOS:Chum
    """
    name: str
    summary: str | None = None
    description: str | Markup | None = None
    title: str | None = None
    icon: RemoteImage | None = None
    version: PackageVersion | None = None
    developer_name: str | None = None
    packager_name: str | None = None
    type: PackageApplicationType = PackageApplicationType.generic
    categories: Set[PackageApplicationCategory] = field(default_factory=lambda: {PackageApplicationCategory.other})
    screenshots: List[RemoteImage] = field(default_factory=list)
    links: Dict[str, str] = field(default_factory=dict)
    debuginfo_package: Self | None = None
    debugsource_package: Self | None = None
    url: str | None = None
    licence: str | None = None
    markdown_url: str | None = None
    repo_url: str | None = None
    packaging_repo_url: str | None = None
    debug_yaml: str | None = None
    debug_yaml_errors: List[Exception] = field(default_factory=list)
    updated: datetime | None = field(default_factory=lambda: datetime.fromtimestamp(0))

    repos: Set[str] = field(default_factory=set)
    archs: Set[str] = field(default_factory=set)
    download_size: Dict[str, int] = field(default_factory=dict)
    install_size: Dict[str, int] = field(default_factory=dict)
    download_url: Dict[str, str] = field(default_factory=dict)
    checksum_type: Dict[str, str] = field(default_factory=dict)
    checksum_value: Dict[str, str] = field(default_factory=dict)
    changelog_entries: List[ChangelogEntry] = field(default_factory=list)

    @staticmethod
    def from_node(dom_element, repo_arch: str):
        """
        Create an instance of the class `Package` from a `<package>` XML node's `dom_element` as found in
        the `primary.xml` metadata file in RPM repositories.
        """

        def try_get_str(name) -> str | None:
            """Return content of XML tag with `name` or None"""
            return _try_get_str(dom_element, name)

        def try_get_attribute_tags(name, *args: str):
            return _try_get_attribute_tags(dom_element, name, *args)

        def try_get_version():
            """Parse version"""
            epoch, ver, rel = try_get_attribute_tags("version", "epoch", "ver", "rel")
            return PackageVersion(epoch, ver, rel)

        def name_to_title(name: str):
            name_parts: List[str] = name.split("-")
            if name_parts[0] == "harbour" or name_parts[0] == "openrepos":
                name_parts.pop(0)
            if name_parts[0].startswith("lib"):
                name_parts[0] = name_parts[0].removeprefix("lib")
                name_parts.append("(library)")
            if name_parts[-1] == "devel":
                name_parts[-1] = "(development files)"

            return " ".join(map(str.capitalize, name_parts))

        def parse_description(description: str, name: str):
            from yaml import safe_load as yaml_load
            from yaml.parser import ParserError
            from yaml.scanner import ScannerError

            import re
            # Based on
            # https://github.com/sailfishos-chum/sailfishos-chum-gui/blob/0b2882fad79673b762ca184cd242d02334f1d8d1/src/chumpackage.cpp#L152C1-L152C108
            # Metadata in YAML format is put as last paragraph of the application description. Paragraphs are split by two newlines.
            paragraphs = [line for line in re.split(r"(?m)^\s*$", description) if line.strip()]
            if not paragraphs:
                return

            yaml_part = paragraphs.pop()
            p.debug_yaml = yaml_part
            try:
                yaml = yaml_load(yaml_part)
            except (ParserError, ScannerError):
                yaml = None
            # If the description is not valid YAML, it will be parsed as a `str` or generate a `ParserError`.
            # In the latter case, add the source back to the description.
            if type(yaml) in [str, NoneType]:
                paragraphs.append(yaml_part)
            else:
                # Note: Use `Dict.get()` to avoid `IndexError`s; we rather have None values.
                p.title = yaml.get("Title") or yaml.get("PackageName") or name_to_title(name)
                p.type = yaml.get("Type")

                icon_url = yaml.get("PackageIcon") or yaml.get("Icon")
                p.icon = RemoteImage(icon_url) if icon_url else None
                p.screenshots = list(map(lambda s: RemoteImage(s), yaml.get("Screenshots", [])))
                p.developer_name = yaml.get("DeveloperName")
                p.packager_name = yaml.get("PackagedBy")

                if "Custom" in yaml:
                    custom = yaml["Custom"]
                    if type(custom) is list:
                        custom_list = custom
                        custom = {}
                        # Handle cases where the "Custom" value is a list of key-value pairs instead of an object. :(
                        for list_item in custom_list:
                            custom |= {k: v for (k, v) in list_item.items()}

                    p.repo_url = custom.get("Repo")
                    p.packaging_repo_url = custom.get("PackagingRepo")
                    p.markdown_url = custom.get("DescriptionMD")

                try:
                    p.links = {key.lower(): val for key, val in (yaml.get("Links") or yaml.get("Url", {})).items()}
                except AttributeError as e:
                    p.debug_yaml_errors.append(e)

                try:
                    p.categories = set(map(PackageApplicationCategory, yaml["Categories"]))
                except (KeyError, ValueError) as e:
                    p.debug_yaml_errors.append(e)

            p.description = "\n\n".join(map(lambda s: s.replace('\n', ' '), paragraphs))

        arch = try_get_str("arch")

        p = Package(try_get_str("name"))
        p.repos.add(repo_arch)
        p.archs.add(arch)
        p.summary = try_get_str("summary")
        p.version = try_get_version()
        p.url = try_get_str("url")
        p.title = name_to_title(p.name)
        p.licence = try_get_str("rpm:license")
        p.updated = datetime.fromtimestamp(float(try_get_attribute_tags("time", "file")[0]), UTC)

        p.download_size[arch], p.install_size[arch] = try_get_attribute_tags("size", "package", "installed")
        p.download_url[arch] = try_get_attribute_tags("location", "href")[0]
        p.checksum_type[arch] = try_get_attribute_tags("checksum", "type")[0]
        p.checksum_value[arch] = try_get_str("checksum")

        try:
            parse_description(try_get_str("description"), p.name)
        except Exception as e:
            p.description = try_get_str("description")
            p.debug_yaml_errors.append(e)

        if p.name.startswith("lib") and PackageApplicationCategory.library not in p.categories:
            p.categories.add(PackageApplicationCategory.library)

        return p

    def merge_arch(self, other_pkg: Self):
        """
        Add the architecture-specific information from another package to this package.
        """
        for arch in other_pkg.archs:
            self.repos = self.repos.union(other_pkg.repos)
            self.download_size[arch] = other_pkg.download_size[arch]
            self.install_size[arch] = other_pkg.install_size[arch]
            self.download_url[arch] = other_pkg.download_url[arch]
            self.checksum_type[arch] = other_pkg.checksum_type[arch]
            self.checksum_value[arch] = other_pkg.checksum_value[arch]
            self.archs.add(arch)

    def is_app(self) -> bool:
        """
        Heuristic to detect whether this is a graphical application which a user is about to install.
        """
        return self.type == PackageApplicationType.desktop_application \
            or self.name.startswith("harbour-") \
            and not self.is_debug()

    def is_debug(self) -> bool:
        return self.name.endswith("-debuginfo") or self.name.endswith("-debugsource")

    def web_url(self):
        """
        Return URL for use in the web interface.
        """
        if self.is_app():
            return f"apps/{self.name}/"
        else:
            return f"pkgs/{self.name}/"

    def get_download_url(self, arch: str) -> Optional[str]:
        # `noarch` and `src` packages do not have a dedicated repository, use the first available arch I suppose:
        # This might be a "not smart" idea.
        if arch == "noarch" or arch == "src":
            repo = next(self.repos.__iter__())
        else:
            for repo in self.repos:
                repo_arch = repo.split("_")[1]
                if repo_arch == arch:
                    break
            else:
                logger.warning(f"No repo found for architecture {arch} (package: {self.name})")
                #assert False, f"No repo found for architecture {arch} (package: {self.name})"
                return None

        return f"{CONFIG.repo_url_prefix}{repo}/" + self.download_url[arch]


    def caused_requests(self):
        return type(self.markdown_url) == str

    def requested_urls(self):
        return [self.markdown_url]

    def to_search_dict(self):
        return {
            "name": self.name,
            "title": self.title,
            "url": self.web_url(),
            "icon": self.icon.remote_url if self.icon else None,
            "summary": self.summary,
            "description": self.description,
            "version": self.version.to_full_str(),
            "version_short": self.version.to_short_str(),
            "is_app": self.is_app(),
            "is_debug": self.is_debug()
        }
