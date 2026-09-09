#!/usr/bin/env python3
"""
EQL Inventory Cleaner - Desktop UI

Cross-platform Tkinter application for EverQuest Legends inventory exports.

Features:
- Browse for an EQL /outputfile inventory text file
- Detect duplicate gear by item ID
- Treat +0/+1/+5/etc. copies as the same item
- Include Equipment KeyRing copies
- Ignore Augmentation/Exaltation records
- Keep uncertain +0 duplicates out of the confirmed list
- Persistently hide Plane of Sky quest turn-in items
- Show KEEP / FEED locations and projected merge XP
- Save or copy a clean text report

No third-party Python packages are required.
"""

import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "EQL Inventory Cleaner"
APP_VERSION = "1.5"

TIER_RE = re.compile(r"\s+\+(\d+)$")

# EQL donor XP by tier.
MERGE_XP = {
    0: 1,
    1: 2,
    2: 4,
    3: 8,
    4: 16,
    5: 32,
    6: 64,
    7: 128,
    8: 256,
    9: 512,
    10: None,  # +10 does not provide donor XP.
}


# Plane of Sky quest turn-in items from the current EverQuest Legends Wiki.
# Rewards are intentionally NOT included: this list is only the items consumed
# by the class tests.  Matching is name-based because /outputfile inventory
# already gives us the canonical EQL item name and ID.
SKY_TURNIN_NAMES = {
    # Bard
    "Light Woolen Mask", "Light Woolen Mantle", "Crude Wooden Flute",
    "Amulet of Woven Hair", "Glowing Diamond", "Efreeti War Horn",
    "Nebulous Diamond", "Efreeti War Spear",

    # Beastlord
    "Spiroc Elder's Totem", "Azarack Skin", "Sphinx Claw", "Mithril Bands",
    "Brass Knuckles", "Leather Cord", "Silken Wrap",

    # Berserker
    "Djinni War Blade", "Efreeti Standard", "Pulsating Ruby",
    "High Quality Raiment", "Feathered Cape", "Azarack Blood",
    "Jester's Mask", "Efreeti Great Staff",

    # Cleric
    "Silver Hoop", "Small Shield", "Shiny Pauldrons",
    "Silvered Spiroc Necklace", "Djinni Aura", "Efreeti Mace",

    # Druid
    "Worn Leather Mask", "Mantle of Woven Grass", "Spiroc Battle Staff",
    "Efreeti Statuette", "Divine Honeycomb", "Ethereal Ruby",
    "Storm Sky Opal", "Efreeti Scimitar",

    # Enchanter
    "Finely Woven Cloth Cord", "Light Cloth Mantle", "Silken Mask",
    "Adamantium Earring", "Glowing Necklace", "Large Sky Sapphire",
    "Efreeti Wind Staff",

    # Magician
    "Feathered Cape", "Ceramic Mask", "Golden Coffer", "Large Diamond",
    "Golden Efreeti Ring", "Hazy Opal", "Efreeti Magi Staff",
    "Djinni Stave",

    # Monk
    "Silken Strands", "Cracked Leather Eyepatch", "Dove Slippers",
    "Silken Wrap", "Nebulous Sapphire", "Brass Knuckles",
    "Tear of Quellious",

    # Necromancer
    "Griffon's Beak", "Black Silk Cape", "Fine Cloth Raiment",
    "Pulsating Ruby", "Ring of Veeshan", "Gorgon Head",
    "Efreeti Great Staff",

    # Paladin
    "Ivory Sky Diamond", "Bixie Sword Blade", "Golden Hilt", "Sphinx Claw",
    "Large Sky Diamond", "Efreeti Zweihander",

    # Ranger
    "Griffon Talon", "Fine Velvet Cloak", "Spiroc Earth Totem",
    "White Gold Earring", "Circlet of Brambles", "Efreeti Long Sword",
    "Shimmering Pearl", "Efreeti War Bow",

    # Rogue
    "Inlaid Choker", "Sphinxian Circlet", "Spiroc Sky Totem",
    "Jester's Mask", "Fine Wool Cloak", "Bixie Stinger",
    "Bloodsky Sapphire",

    # Shadow Knight
    "Finely Crafted Amulet", "Silvery Ring", "Finely Woven Cloth Belt",
    "Rusted Pauldrons", "Efreeti War Shield", "Sphinxian Ring",
    "Fae Pauldrons", "Blood Sky Ruby", "Efreeti War Axe",

    # Shaman
    "Leather Cord", "Ceremonial Belt", "Light Damask Mantle",
    "Corrosive Venom", "Efreeti War Club", "Bixie Essence",
    "Spiritualist`s Ring", "Symbol of Veeshan", "Efreeti War Maul",

    # Warrior
    "Azure Ring", "Stone Amulet", "Spiroc Air Totem", "Wind Tablet",
    "Efreeti Belt", "Djinni War Blade", "Gem of Invigoration",
    "Ethereal Emerald", "Efreeti Battle Axe",

    # Wizard
    "Grey Damask Cloak", "Woven Skull Cap", "High Quality Raiment",
    "Box of Winds", "Efreeti Statuette", "Amethyst Amulet",
    "Large Sky Lapis", "Efreeti War Staff",
}


def normalized_item_key(name):
    """Normalize EQL punctuation/spacing for reliable static-name matching."""
    return re.sub(r"\\s+", " ", name.replace("`", "'").strip().casefold())


SKY_TURNIN_KEYS = {normalized_item_key(name) for name in SKY_TURNIN_NAMES}


def is_sky_turnin_group(items):
    if not items:
        return False
    return normalized_item_key(items[0]["base_name"]) in SKY_TURNIN_KEYS


# ---------------------------------------------------------------------------
# EQL inventory parsing
# ---------------------------------------------------------------------------

def read_text(path):
    raw = Path(path).read_bytes()

    # EQL exports can be UTF-16. Pasted/saved copies may be UTF-8.
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")

    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-16")


def parse_tier(name):
    match = TIER_RE.search(name.strip())
    if not match:
        return 0

    tier = int(match.group(1))
    return tier if 0 <= tier <= 10 else 0


def base_name(name):
    name = name.strip()
    name = name.replace(" (Exaltation)", "")
    return TIER_RE.sub("", name).strip()


def parse_inventory(text):
    lines = text.splitlines()

    if not lines:
        raise ValueError("The selected file is empty.")

    # The EQL export starts with the normal inventory section and can then
    # include a KeyRing section.
    try:
        keyring_index = next(
            i for i, line in enumerate(lines)
            if line.startswith("KeyRing\t")
        )
    except StopIteration:
        keyring_index = len(lines)

    records = []

    # Main inventory / bank / hoard / depot section.
    for line in lines[1:keyring_index]:
        parts = line.split("\t")

        if len(parts) < 5:
            continue

        location, name, item_id, count, slots = parts[:5]

        try:
            item_id = int(item_id)
            count = int(count)
            slots = int(slots)
        except ValueError:
            continue

        if item_id == 0 or name == "Empty":
            continue

        # Exaltations socketed into an item reuse an item ID but are not
        # additional physical copies of the gear.
        if "(Exaltation)" in name:
            continue

        # We only want individual gear copies, not stack quantities.
        if count != 1:
            continue

        records.append({
            "source": "Inventory",
            "location": location,
            "name": name,
            "base_name": base_name(name),
            "id": item_id,
            "tier": parse_tier(name),
            "slots": slots,
        })

    # KeyRing section.
    if keyring_index < len(lines):
        for line in lines[keyring_index + 1:]:
            parts = line.split("\t")

            if len(parts) < 3:
                continue

            keyring_type, name, item_id = parts[:3]

            try:
                item_id = int(item_id)
            except ValueError:
                continue

            # Only Equipment records represent an actual stored gear copy.
            # Augmentation records are Exaltations and must be ignored.
            if keyring_type != "Equipment":
                continue

            if "(Exaltation)" in name:
                continue

            records.append({
                "source": "Equipment KeyRing",
                "location": "Equipment KeyRing",
                "name": name,
                "base_name": base_name(name),
                "id": item_id,
                "tier": parse_tier(name),
                "slots": None,
            })

    if not records:
        raise ValueError(
            "No inventory records were found. Make sure this is an EQL "
            "/outputfile inventory export."
        )

    return records


def group_duplicates(records):
    groups = defaultdict(list)

    for item in records:
        groups[item["id"]].append(item)

    return {
        item_id: items
        for item_id, items in groups.items()
        if len(items) >= 2
    }


def confidence(items):
    """
    Confirmed:
      - at least one copy already has a +tier, OR
      - at least one copy is in the Equipment KeyRing.

    Possible:
      - every copy is +0 and none is in the Equipment KeyRing.

    The export alone cannot prove that every repeated +0 Count=1 item is gear,
    so those records stay separated to avoid false positives.
    """
    if any(item["tier"] > 0 for item in items):
        return "confirmed"

    if any(item["source"] == "Equipment KeyRing" for item in items):
        return "confirmed"

    return "possible"


def project_merge(items):
    # Default target is the highest-tier copy. If tied, favor Equipment KeyRing.
    ordered = sorted(
        items,
        key=lambda item: (
            item["tier"],
            item["source"] == "Equipment KeyRing",
        ),
        reverse=True,
    )

    target = ordered[0]
    donors = ordered[1:]

    donor_xp = 0
    for donor in donors:
        xp = MERGE_XP.get(donor["tier"])
        if xp is not None:
            donor_xp += xp

    if target["tier"] >= 10:
        return {
            "target": target,
            "donors": donors,
            "donor_xp": donor_xp,
            "new_tier": 10,
            "progress": None,
            "maxed": True,
        }

    # XP needed to reach the start of tier N is 2^N - 1.
    target_total_xp = (2 ** target["tier"]) - 1
    projected_total = target_total_xp + donor_xp

    new_tier = min(
        10,
        int(math.floor(math.log2(projected_total + 1))),
    )

    if new_tier >= 10:
        progress = None
    else:
        start_of_tier = (2 ** new_tier) - 1
        progress = (
            projected_total - start_of_tier,
            2 ** new_tier,
        )

    return {
        "target": target,
        "donors": donors,
        "donor_xp": donor_xp,
        "new_tier": new_tier,
        "progress": progress,
        "maxed": False,
    }


def tier_text(tier):
    return f"+{tier}"


def projection_text(plan):
    target = plan["target"]

    if plan["maxed"]:
        return "Already +10"

    new_tier = plan["new_tier"]

    if plan["progress"] is None:
        return f"{tier_text(target['tier'])} → +10"

    current, needed = plan["progress"]

    if new_tier > target["tier"]:
        return (
            f"{tier_text(target['tier'])} → {tier_text(new_tier)} "
            f"({current}/{needed})"
        )

    return f"{tier_text(new_tier)} ({current}/{needed})"


def detail_text(items, confirmed=True):
    if not confirmed:
        item = items[0]
        lines = [
            f"{item['base_name']}  [ID {item['id']}]",
            "",
            "POSSIBLE +0 DUPLICATE",
            "",
            "Every copy is +0 and none is stored in the Equipment KeyRing.",
            "The inventory export alone cannot prove this is mergeable gear.",
            "",
            f"Copies found: {len(items)}",
        ]

        for entry in sorted(items, key=lambda x: x["location"]):
            lines.append(f"  • {entry['location']}")

        return "\n".join(lines)

    plan = project_merge(items)
    target = plan["target"]

    lines = [
        f"{target['base_name']}  [ID {target['id']}]",
        "",
        f"KEEP   {tier_text(target['tier']):>3}   {target['location']}",
        "",
        "FEED",
    ]

    for donor in plan["donors"]:
        xp = MERGE_XP.get(donor["tier"])
        xp_text = "NO XP (+10)" if xp is None else f"{xp} XP"
        lines.append(
            f"  {tier_text(donor['tier']):>3}   "
            f"{donor['location']}   →   {xp_text}"
        )

    lines.extend([
        "",
        f"Donor XP available: {plan['donor_xp']}",
        f"Projection: {projection_text(plan)}",
    ])

    if plan["maxed"]:
        lines.extend([
            "",
            "WARNING: The selected KEEP copy is already +10.",
            "Feeding lower-tier copies into it will not advance it.",
        ])
    else:
        lines.extend([
            "",
            "Projection assumes the KEEP copy has 0 partial item XP",
            "inside its current tier because the export does not show partial XP.",
        ])

    return "\n".join(lines)


def build_report(filename, confirmed_groups, possible_groups):
    bar = "=" * 78
    lines = [
        bar,
        "EQL INVENTORY CLEANER — MERGE FINDER",
        bar,
        f"File: {filename}",
        f"Confirmed merge groups: {len(confirmed_groups)}",
        f"Possible +0 duplicate groups: {len(possible_groups)}",
        "",
        "CONFIRMED MERGE CANDIDATES",
        bar,
    ]

    if not confirmed_groups:
        lines.append("No confirmed merge candidates found.")
    else:
        for items in confirmed_groups:
            plan = project_merge(items)
            target = plan["target"]

            lines.extend([
                "",
                f"{target['base_name']}  [ID {target['id']}]",
                "-" * min(78, len(target["base_name"]) + 16),
                f"KEEP: {tier_text(target['tier']):>3}  {target['location']}",
                "FEED:",
            ])

            for donor in plan["donors"]:
                xp = MERGE_XP.get(donor["tier"])
                xp_text = "NO XP (+10)" if xp is None else f"{xp} XP"
                lines.append(
                    f"  {tier_text(donor['tier']):>3}  "
                    f"{donor['location']:<34} {xp_text}"
                )

            lines.append(f"Donor XP: {plan['donor_xp']}")
            lines.append(f"Projection: {projection_text(plan)}")

            if plan["maxed"]:
                lines.append(
                    "WARNING: KEEP copy is already +10; lower-tier donors "
                    "cannot advance it."
                )

    lines.extend([
        "",
        "",
        "POSSIBLE +0 DUPLICATES",
        bar,
        "These are repeated Count=1 items, but the inventory export alone",
        "does not prove they are mergeable gear.",
    ])

    if not possible_groups:
        lines.append("None.")
    else:
        for items in possible_groups:
            lines.append("")
            lines.append(
                f"{items[0]['base_name']}  "
                f"[ID {items[0]['id']}]  "
                f"({len(items)} copies)"
            )
            for item in sorted(items, key=lambda x: x["location"]):
                lines.append(f"  - {item['location']}")

    lines.extend([
        "",
        "",
        "NOTE",
        bar,
        "Merge projections assume the KEEP copy has 0 partial item XP inside",
        "its current tier because EQL's inventory export does not expose that value.",
        "",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistent settings
# ---------------------------------------------------------------------------

SETTINGS_FILE_NAME = "settings.json"


def settings_path():
    """Return the EQL Inventory Cleaner per-user settings file."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
        folder = base / "EQL Inventory Cleaner"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        folder = base / "eql-inventory-cleaner"

    return folder / SETTINGS_FILE_NAME


def legacy_settings_path():
    """Return the pre-rebrand Merge Finder settings path for migration."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
        folder = base / "EQL Merge Finder"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        folder = base / "eql-merge-finder"

    return folder / SETTINGS_FILE_NAME


def load_settings():
    path = settings_path()
    candidates = [path]

    # One-time compatibility with v1.1-v1.5 builds from before the
    # EQL Inventory Cleaner rebrand. The next save writes the new path.
    if not path.exists():
        candidates.append(legacy_settings_path())

    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            continue

    return {}


def save_settings(data):
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        # Settings are a convenience. Failure should never prevent the app
        # itself from running or closing.
        pass


PALETTES = {
    "dark": {
        "bg": "#0b1220",
        "surface": "#111827",
        "surface2": "#172033",
        "surface3": "#1f2937",
        "border": "#2b384d",
        "text": "#e5edf7",
        "muted": "#93a4b8",
        "accent": "#38bdf8",
        "accent_hover": "#67cff8",
        "accent_text": "#07111d",
        "success": "#34d399",
        "warning": "#fbbf24",
        "danger": "#fb7185",
        "selection": "#155e75",
    },
    "light": {
        "bg": "#eef2f7",
        "surface": "#ffffff",
        "surface2": "#f7f9fc",
        "surface3": "#e8eef6",
        "border": "#d5deea",
        "text": "#182230",
        "muted": "#66758a",
        "accent": "#0284c7",
        "accent_hover": "#0369a1",
        "accent_text": "#ffffff",
        "success": "#059669",
        "warning": "#d97706",
        "danger": "#e11d48",
        "selection": "#bae6fd",
    },
}


# ---------------------------------------------------------------------------
# Desktop UI
# ---------------------------------------------------------------------------

class MergeFinderApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        self.theme_name = self.settings.get("theme", "dark")
        if self.theme_name not in PALETTES:
            self.theme_name = "dark"

        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.minsize(960, 650)

        saved_geometry = self.settings.get("geometry")
        if isinstance(saved_geometry, str) and "x" in saved_geometry:
            try:
                self.geometry(saved_geometry)
            except tk.TclError:
                self.geometry("1220x820")
        else:
            self.geometry("1220x820")

        self.file_path = tk.StringVar(value=self.settings.get("last_file", ""))
        self.search_var = tk.StringVar()
        self.hide_maxed_var = tk.BooleanVar(value=bool(self.settings.get("hide_maxed", False)))
        self.hide_sky_var = tk.BooleanVar(value=bool(self.settings.get("hide_sky_turnins", False)))
        self.status_var = tk.StringVar(value="Choose an EQL inventory export to begin.")
        self.file_name_var = tk.StringVar(value="No file selected")
        self.last_scan_var = tk.StringVar(value="Not scanned yet")

        self.records = []
        self.confirmed_groups = []
        self.possible_groups = []
        self.report = ""

        self._configure_style()
        self._build_ui()
        self._apply_theme_to_tk_widgets()

        # Explicit shutdown is reliable on KDE/Wayland/Bazzite.
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Control-q>", lambda _event: self.on_close())
        self.bind_all("<Control-o>", lambda _event: self.browse_file())
        self.bind_all("<Control-f>", lambda _event: self.search_entry.focus_set())

        self.search_var.trace_add("write", lambda *_: self.refresh_tables())

        # Command-line file always wins over remembered file.
        cli_candidate = None
        if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
            cli_candidate = Path(sys.argv[1])

        if cli_candidate and cli_candidate.exists():
            self.file_path.set(str(cli_candidate))
            self.after(120, self.scan_file)
        else:
            remembered = Path(self.file_path.get()) if self.file_path.get() else None
            if remembered and remembered.exists():
                self.file_name_var.set(remembered.name)
                self.status_var.set(f"Reopening last inventory: {remembered.name}")
                self.after(180, self.scan_file)

    # -------------------------- lifecycle/settings -------------------------

    def current_settings(self):
        path = self.file_path.get().strip()
        last_dir = self.settings.get("last_dir", "")
        if path:
            try:
                last_dir = str(Path(path).expanduser().resolve().parent)
            except OSError:
                last_dir = str(Path(path).expanduser().parent)

        geometry = self.geometry()
        # Do not persist tiny transient geometry during teardown.
        if geometry.startswith("1x1"):
            geometry = self.settings.get("geometry", "1220x820")

        return {
            "last_file": path,
            "last_dir": last_dir,
            "geometry": geometry,
            "theme": self.theme_name,
            "hide_maxed": bool(self.hide_maxed_var.get()),
            "hide_sky_turnins": bool(self.hide_sky_var.get()),
        }

    def persist_settings(self):
        data = self.current_settings()
        self.settings.update(data)
        save_settings(self.settings)

    def on_close(self):
        self.persist_settings()
        try:
            self.quit()
        finally:
            self.destroy()

    # ------------------------------- style --------------------------------

    def _configure_style(self):
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        family = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
        mono = "Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono"
        self.default_font = (family, 10)
        self.small_font = (family, 9)
        self.title_font = (family, 23, "bold")
        self.section_font = (family, 12, "bold")
        self.metric_font = (family, 22, "bold")
        self.mono_font = (mono, 10)
        self.option_add("*Font", self.default_font)
        self.apply_theme()

    def apply_theme(self):
        p = PALETTES[self.theme_name]
        s = self.style

        self.configure(bg=p["bg"])

        s.configure("TFrame", background=p["bg"])
        s.configure("App.TFrame", background=p["bg"])
        s.configure("Card.TFrame", background=p["surface"], relief="flat")
        s.configure("Card2.TFrame", background=p["surface2"], relief="flat")
        s.configure("Toolbar.TFrame", background=p["surface"])

        s.configure("TLabel", background=p["bg"], foreground=p["text"])
        s.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=self.title_font)
        s.configure("Subtitle.TLabel", background=p["bg"], foreground=p["muted"], font=self.small_font)
        s.configure("Card.TLabel", background=p["surface"], foreground=p["text"])
        s.configure("CardMuted.TLabel", background=p["surface"], foreground=p["muted"], font=self.small_font)
        s.configure("Metric.TLabel", background=p["surface"], foreground=p["text"], font=self.metric_font)
        s.configure("SuccessMetric.TLabel", background=p["surface"], foreground=p["success"], font=self.metric_font)
        s.configure("WarningMetric.TLabel", background=p["surface"], foreground=p["warning"], font=self.metric_font)
        s.configure("Section.TLabel", background=p["surface"], foreground=p["text"], font=self.section_font)
        s.configure("Chip.TLabel", background=p["surface3"], foreground=p["muted"], padding=(8, 3), font=self.small_font)
        s.configure("Path.TLabel", background=p["surface"], foreground=p["muted"], font=self.small_font)
        s.configure("Status.TLabel", background=p["surface"], foreground=p["muted"], font=self.small_font)

        s.configure(
            "TButton",
            background=p["surface3"], foreground=p["text"],
            borderwidth=0, focusthickness=0, focuscolor="",
            padding=(12, 8),
        )
        s.map("TButton",
              background=[("active", p["border"]), ("pressed", p["surface2"])],
              foreground=[("disabled", p["muted"])])

        s.configure(
            "Filter.TCheckbutton",
            background=p["surface3"], foreground=p["text"],
            indicatorcolor=p["surface2"], indicatorrelief="flat",
            borderwidth=0, focusthickness=0, focuscolor="",
            padding=(11, 7), font=(self.default_font[0], 9, "bold"),
        )
        s.map(
            "Filter.TCheckbutton",
            background=[("active", p["border"]), ("selected", p["accent"])],
            foreground=[("selected", p["accent_text"])],
            indicatorcolor=[("selected", p["accent_text"]), ("active", p["surface"])],
        )

        s.configure(
            "Primary.TButton",
            background=p["accent"], foreground=p["accent_text"],
            borderwidth=0, focusthickness=0, focuscolor="",
            padding=(14, 9), font=(self.default_font[0], 10, "bold"),
        )
        s.map("Primary.TButton",
              background=[("active", p["accent_hover"]), ("pressed", p["accent"])])

        s.configure(
            "Modern.TEntry",
            fieldbackground=p["surface2"], foreground=p["text"],
            insertcolor=p["text"], bordercolor=p["border"],
            lightcolor=p["border"], darkcolor=p["border"],
            padding=(10, 8),
        )
        s.map("Modern.TEntry",
              bordercolor=[("focus", p["accent"])],
              lightcolor=[("focus", p["accent"])],
              darkcolor=[("focus", p["accent"])])

        s.configure("TNotebook", background=p["bg"], borderwidth=0, tabmargins=(0, 8, 0, 0))
        s.configure(
            "TNotebook.Tab",
            background=p["bg"], foreground=p["muted"],
            borderwidth=0, padding=(16, 9),
        )
        s.map("TNotebook.Tab",
              background=[("selected", p["surface"])],
              foreground=[("selected", p["accent"]), ("active", p["text"])])

        s.configure(
            "Treeview",
            background=p["surface"], fieldbackground=p["surface"],
            foreground=p["text"], borderwidth=0, rowheight=31,
        )
        s.map("Treeview",
              background=[("selected", p["selection"])],
              foreground=[("selected", p["text"])])
        s.configure(
            "Treeview.Heading",
            background=p["surface2"], foreground=p["muted"],
            borderwidth=0, relief="flat",
            padding=(8, 8), font=(self.default_font[0], 9, "bold"),
        )
        s.map("Treeview.Heading", background=[("active", p["surface3"])])

        s.configure("TPanedwindow", background=p["bg"])
        s.configure("Vertical.TScrollbar", background=p["surface3"], troughcolor=p["surface"], borderwidth=0)
        s.configure("Horizontal.TScrollbar", background=p["surface3"], troughcolor=p["surface"], borderwidth=0)

    def _apply_theme_to_tk_widgets(self):
        p = PALETTES[self.theme_name]
        for widget in (getattr(self, "detail_text_widget", None), getattr(self, "report_text_widget", None)):
            if widget:
                widget.configure(
                    bg=p["surface2"], fg=p["text"], insertbackground=p["text"],
                    selectbackground=p["selection"], selectforeground=p["text"],
                    highlightbackground=p["border"], highlightcolor=p["accent"],
                )

        if hasattr(self, "theme_button"):
            self.theme_button.configure(text="Light mode" if self.theme_name == "dark" else "Dark mode")

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.apply_theme()
        self._apply_theme_to_tk_widgets()
        self.persist_settings()

    # ------------------------------- layout --------------------------------

    def _build_ui(self):
        outer = ttk.Frame(self, style="App.TFrame", padding=(20, 18, 20, 14))
        outer.pack(fill="both", expand=True)

        # Header
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 16))
        header.columnconfigure(0, weight=1)

        title_wrap = ttk.Frame(header, style="App.TFrame")
        title_wrap.grid(row=0, column=0, sticky="w")
        ttk.Label(title_wrap, text="EQL Inventory Cleaner", style="Title.TLabel").pack(side="left")
        ttk.Label(title_wrap, text=f"v{APP_VERSION}", style="Chip.TLabel").pack(side="left", padx=(10, 0), pady=(5, 0))

        ttk.Label(
            header,
            text="Clean up your EverQuest Legends inventory. Merge Finder is the first cleanup tool.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.theme_button = ttk.Button(header, command=self.toggle_theme)
        self.theme_button.grid(row=0, column=1, rowspan=2, sticky="e")

        # File card
        file_card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        file_card.pack(fill="x", pady=(0, 14))
        file_card.columnconfigure(0, weight=1)

        ttk.Label(file_card, text="Inventory export", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(file_card, textvariable=self.file_name_var, style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 10))

        path_row = ttk.Frame(file_card, style="Card.TFrame")
        path_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        path_row.columnconfigure(0, weight=1)

        self.path_entry = ttk.Entry(path_row, textvariable=self.file_path, style="Modern.TEntry")
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ttk.Button(path_row, text="Browse…", command=self.browse_file).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(path_row, text="Scan inventory", style="Primary.TButton", command=self.scan_file).grid(row=0, column=2)

        # Summary row
        metrics = ttk.Frame(outer, style="App.TFrame")
        metrics.pack(fill="x", pady=(0, 14))
        for col in range(3):
            metrics.columnconfigure(col, weight=1, uniform="metric")

        confirmed_card = ttk.Frame(metrics, style="Card.TFrame", padding=(16, 12))
        confirmed_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        ttk.Label(confirmed_card, text="CONFIRMED MERGES", style="CardMuted.TLabel").pack(anchor="w")
        self.confirmed_count = ttk.Label(confirmed_card, text="0", style="SuccessMetric.TLabel")
        self.confirmed_count.pack(anchor="w", pady=(2, 0))

        possible_card = ttk.Frame(metrics, style="Card.TFrame", padding=(16, 12))
        possible_card.grid(row=0, column=1, sticky="nsew", padx=7)
        ttk.Label(possible_card, text="POSSIBLE +0", style="CardMuted.TLabel").pack(anchor="w")
        self.possible_count = ttk.Label(possible_card, text="0", style="WarningMetric.TLabel")
        self.possible_count.pack(anchor="w", pady=(2, 0))

        scan_card = ttk.Frame(metrics, style="Card.TFrame", padding=(16, 12))
        scan_card.grid(row=0, column=2, sticky="nsew", padx=(7, 0))
        ttk.Label(scan_card, text="LAST SCAN", style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(scan_card, textvariable=self.last_scan_var, style="Card.TLabel", font=self.section_font).pack(anchor="w", pady=(6, 0))

        # Results toolbar
        toolbar = ttk.Frame(outer, style="Card.TFrame", padding=(12, 8))
        toolbar.pack(fill="x", pady=(0, 2))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="Results", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.hide_maxed_check = ttk.Checkbutton(
            toolbar,
            text="Hide already +10",
            variable=self.hide_maxed_var,
            command=self.on_filter_changed,
            style="Filter.TCheckbutton",
        )
        self.hide_maxed_check.grid(row=0, column=1, sticky="e", padx=(8, 8))
        self.hide_sky_check = ttk.Checkbutton(
            toolbar,
            text="Hide Sky turn-ins",
            variable=self.hide_sky_var,
            command=self.on_filter_changed,
            style="Filter.TCheckbutton",
        )
        self.hide_sky_check.grid(row=0, column=2, sticky="e", padx=(0, 12))
        ttk.Label(toolbar, text="Search", style="CardMuted.TLabel").grid(row=0, column=3, padx=(0, 6))
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=28, style="Modern.TEntry")
        self.search_entry.grid(row=0, column=4, sticky="e")

        # Tabs
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        self.confirmed_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        self.possible_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        self.report_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        self.notebook.add(self.confirmed_tab, text="Confirmed merges")
        self.notebook.add(self.possible_tab, text="Possible +0 duplicates")
        self.notebook.add(self.report_tab, text="Full report")

        self._build_confirmed_tab()
        self._build_possible_tab()
        self._build_report_tab()

        # Footer/status
        footer = ttk.Frame(outer, style="Card.TFrame", padding=(12, 8))
        footer.pack(fill="x", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Copy report", command=self.copy_report).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(footer, text="Save report…", command=self.save_report).grid(row=0, column=2, padx=(8, 0))

        self._apply_theme_to_tk_widgets()

    def _build_confirmed_tab(self):
        paned = ttk.Panedwindow(self.confirmed_tab, orient="vertical")
        paned.pack(fill="both", expand=True)

        table_frame = ttk.Frame(paned, style="Card.TFrame")
        detail_frame = ttk.Frame(paned, style="Card2.TFrame", padding=10)
        paned.add(table_frame, weight=3)
        paned.add(detail_frame, weight=2)

        columns = ("item", "id", "keep", "location", "donors", "xp", "projection")
        headings = {
            "item": "Item", "id": "ID", "keep": "Keep", "location": "Keep location",
            "donors": "Donors", "xp": "Donor XP", "projection": "Projection",
        }
        widths = {"item": 285, "id": 80, "keep": 65, "location": 190, "donors": 70, "xp": 85, "projection": 175}

        self.confirmed_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            self.confirmed_tree.heading(column, text=headings[column], command=lambda c=column: self.sort_tree(self.confirmed_tree, c, False))
            self.confirmed_tree.column(column, width=widths[column], minwidth=55,
                                       anchor="w" if column in ("item", "location", "projection") else "center")

        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=self.confirmed_tree.yview)
        xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.confirmed_tree.xview)
        self.confirmed_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.confirmed_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.confirmed_tree.bind("<<TreeviewSelect>>", self.show_confirmed_detail)

        ttk.Label(detail_frame, text="Selected merge", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        text_wrap = ttk.Frame(detail_frame, style="Card2.TFrame")
        text_wrap.pack(fill="both", expand=True)
        self.detail_text_widget = tk.Text(
            text_wrap, wrap="word", height=12, font=self.mono_font, padx=12, pady=12,
            state="disabled", relief="flat", borderwidth=0, highlightthickness=1,
        )
        detail_scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=self.detail_text_widget.yview)
        self.detail_text_widget.configure(yscrollcommand=detail_scroll.set)
        self.detail_text_widget.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

    def _build_possible_tab(self):
        frame = self.possible_tab
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text="Repeated Count=1 +0 items live here until the export itself proves they are mergeable gear.",
            style="CardMuted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 9))

        columns = ("item", "id", "copies", "locations")
        headings = {"item": "Item", "id": "ID", "copies": "Copies", "locations": "Locations"}
        widths = {"item": 330, "id": 90, "copies": 80, "locations": 590}

        self.possible_tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            self.possible_tree.heading(column, text=headings[column], command=lambda c=column: self.sort_tree(self.possible_tree, c, False))
            self.possible_tree.column(column, width=widths[column], minwidth=60,
                                      anchor="w" if column in ("item", "locations") else "center")

        ybar = ttk.Scrollbar(frame, orient="vertical", command=self.possible_tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=self.possible_tree.xview)
        self.possible_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.possible_tree.grid(row=1, column=0, sticky="nsew")
        ybar.grid(row=1, column=1, sticky="ns")
        xbar.grid(row=2, column=0, sticky="ew")
        self.possible_tree.bind("<Double-1>", self.show_possible_popup)

    def _build_report_tab(self):
        frame = self.report_tab
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.report_text_widget = tk.Text(
            frame, wrap="none", font=self.mono_font, padx=14, pady=14,
            state="disabled", relief="flat", borderwidth=0, highlightthickness=1,
        )
        ybar = ttk.Scrollbar(frame, orient="vertical", command=self.report_text_widget.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=self.report_text_widget.xview)
        self.report_text_widget.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.report_text_widget.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")

    # ---------------------------- file handling ----------------------------

    def browse_file(self):
        current = self.file_path.get().strip()
        remembered_dir = self.settings.get("last_dir", "")

        if current:
            current_path = Path(current).expanduser()
            initial_dir = current_path.parent if current_path.parent.exists() else Path(remembered_dir or Path.home())
            initial_file = current_path.name
        else:
            initial_dir = Path(remembered_dir) if remembered_dir and Path(remembered_dir).exists() else Path.home()
            initial_file = ""

        path = filedialog.askopenfilename(
            title="Choose EQL inventory export",
            initialdir=str(initial_dir),
            initialfile=initial_file,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )

        if path:
            self.file_path.set(path)
            self.file_name_var.set(Path(path).name)
            self.settings["last_file"] = path
            self.settings["last_dir"] = str(Path(path).parent)
            save_settings(self.settings)
            self.scan_file()

    def scan_file(self):
        path = self.file_path.get().strip()
        if not path:
            messagebox.showinfo(APP_TITLE, "Choose an EQL inventory export first.")
            return

        file_path = Path(path).expanduser()
        if not file_path.exists():
            messagebox.showerror(APP_TITLE, "The selected file does not exist.")
            return

        try:
            self.status_var.set(f"Scanning {file_path.name}…")
            self.update_idletasks()

            text = read_text(file_path)
            self.records = parse_inventory(text)
            duplicates = group_duplicates(self.records)
            self.confirmed_groups = []
            self.possible_groups = []

            for items in duplicates.values():
                (self.confirmed_groups if confidence(items) == "confirmed" else self.possible_groups).append(items)

            self.confirmed_groups.sort(key=lambda group: group[0]["base_name"].casefold())
            self.possible_groups.sort(key=lambda group: group[0]["base_name"].casefold())

            self.report = build_report(file_path.name, self.confirmed_groups, self.possible_groups)
            self.confirmed_count.configure(text=str(len(self.confirmed_groups)))
            self.possible_count.configure(text=str(len(self.possible_groups)))
            self.file_name_var.set(file_path.name)
            self.last_scan_var.set(f"{len(self.confirmed_groups)} ready")

            self.refresh_tables()
            self.set_report_text(self.report)

            self.settings["last_file"] = str(file_path)
            self.settings["last_dir"] = str(file_path.parent)
            save_settings(self.settings)

            self.status_var.set(
                f"Scanned {file_path.name}  •  {len(self.confirmed_groups)} confirmed  •  "
                f"{len(self.possible_groups)} possible +0"
            )

            if self.confirmed_tree.get_children():
                first = self.confirmed_tree.get_children()[0]
                self.confirmed_tree.selection_set(first)
                self.confirmed_tree.focus(first)
                self.confirmed_tree.see(first)
                self.show_confirmed_detail()

        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not scan this file:\n\n{exc}")
            self.status_var.set("Scan failed.")
            self.last_scan_var.set("Scan failed")

    # ------------------------------ results --------------------------------

    def on_filter_changed(self):
        self.persist_settings()
        self.refresh_tables()

        if not self.records:
            return

        hidden_maxed = 0
        hidden_sky = 0

        if self.hide_maxed_var.get():
            hidden_maxed = sum(
                1 for items in self.confirmed_groups
                if project_merge(items)["maxed"]
                and not (self.hide_sky_var.get() and is_sky_turnin_group(items))
            )

        if self.hide_sky_var.get():
            hidden_sky = sum(
                1 for items in self.confirmed_groups
                if is_sky_turnin_group(items)
            ) + sum(
                1 for items in self.possible_groups
                if is_sky_turnin_group(items)
            )

        parts = []
        if hidden_sky:
            parts.append(f"{hidden_sky} Sky turn-in group{'s' if hidden_sky != 1 else ''}")
        if hidden_maxed:
            parts.append(f"{hidden_maxed} already +10 group{'s' if hidden_maxed != 1 else ''}")

        if parts:
            self.status_var.set("Hidden " + " and ".join(parts) + ".")
        else:
            self.status_var.set("All merge groups are visible.")

    def refresh_tables(self):
        if not hasattr(self, "confirmed_tree"):
            return

        query = self.search_var.get().strip().casefold()
        for item in self.confirmed_tree.get_children():
            self.confirmed_tree.delete(item)
        for item in self.possible_tree.get_children():
            self.possible_tree.delete(item)

        for index, items in enumerate(self.confirmed_groups):
            plan = project_merge(items)
            if self.hide_maxed_var.get() and plan["maxed"]:
                continue
            if self.hide_sky_var.get() and is_sky_turnin_group(items):
                continue
            target = plan["target"]
            searchable = " ".join([
                target["base_name"], str(target["id"]), target["location"], projection_text(plan),
                " ".join(d["location"] for d in plan["donors"]),
            ]).casefold()
            if query and query not in searchable:
                continue
            self.confirmed_tree.insert("", "end", iid=f"confirmed:{index}", values=(
                target["base_name"], target["id"], tier_text(target["tier"]), target["location"],
                len(plan["donors"]), plan["donor_xp"], projection_text(plan),
            ))

        for index, items in enumerate(self.possible_groups):
            if self.hide_sky_var.get() and is_sky_turnin_group(items):
                continue
            item = items[0]
            locations = ", ".join(entry["location"] for entry in sorted(items, key=lambda x: x["location"]))
            searchable = " ".join([item["base_name"], str(item["id"]), locations]).casefold()
            if query and query not in searchable:
                continue
            self.possible_tree.insert("", "end", iid=f"possible:{index}", values=(
                item["base_name"], item["id"], len(items), locations,
            ))

    def show_confirmed_detail(self, event=None):
        selection = self.confirmed_tree.selection()
        if not selection:
            return
        index = int(selection[0].split(":", 1)[1])
        self.set_detail_text(detail_text(self.confirmed_groups[index], confirmed=True))

    def show_possible_popup(self, event=None):
        selection = self.possible_tree.selection()
        if not selection:
            return
        index = int(selection[0].split(":", 1)[1])
        messagebox.showinfo("Possible +0 Duplicate", detail_text(self.possible_groups[index], confirmed=False))

    def set_detail_text(self, text):
        self.detail_text_widget.configure(state="normal")
        self.detail_text_widget.delete("1.0", "end")
        self.detail_text_widget.insert("1.0", text)
        self.detail_text_widget.configure(state="disabled")

    def set_report_text(self, text):
        self.report_text_widget.configure(state="normal")
        self.report_text_widget.delete("1.0", "end")
        self.report_text_widget.insert("1.0", text)
        self.report_text_widget.configure(state="disabled")

    def copy_report(self):
        if not self.report:
            messagebox.showinfo(APP_TITLE, "Scan an inventory file first.")
            return
        self.clipboard_clear()
        self.clipboard_append(self.report)
        self.update()
        self.status_var.set("Report copied to clipboard.")

    def save_report(self):
        if not self.report:
            messagebox.showinfo(APP_TITLE, "Scan an inventory file first.")
            return

        default_name = "EQL_Merge_Report.txt"
        if self.file_path.get():
            default_name = f"{Path(self.file_path.get()).stem}-Merge-Report.txt"

        initial_dir = self.settings.get("last_report_dir") or self.settings.get("last_dir") or str(Path.home())
        path = filedialog.asksaveasfilename(
            title="Save EQL merge report", defaultextension=".txt", initialfile=default_name,
            initialdir=initial_dir, filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            Path(path).write_text(self.report, encoding="utf-8")
            self.settings["last_report_dir"] = str(Path(path).parent)
            save_settings(self.settings)
            self.status_var.set(f"Saved report: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not save report:\n\n{exc}")

    @staticmethod
    def sort_tree(tree, column, reverse):
        rows = [(tree.set(item, column), item) for item in tree.get_children("")]

        def sort_key(pair):
            value = pair[0]
            try:
                return (0, int(value))
            except ValueError:
                return (1, value.casefold())

        rows.sort(key=sort_key, reverse=reverse)
        for index, (_, item) in enumerate(rows):
            tree.move(item, "", index)
        tree.heading(column, command=lambda: MergeFinderApp.sort_tree(tree, column, not reverse))


def cli_scan(path):
    file_path = Path(path)
    text = read_text(file_path)
    records = parse_inventory(text)
    duplicates = group_duplicates(records)
    confirmed = []
    possible = []
    for items in duplicates.values():
        (confirmed if confidence(items) == "confirmed" else possible).append(items)
    confirmed.sort(key=lambda group: group[0]["base_name"].casefold())
    possible.sort(key=lambda group: group[0]["base_name"].casefold())
    print(build_report(file_path.name, confirmed, possible))
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--cli-scan":
        raise SystemExit(cli_scan(sys.argv[2]))
    app = MergeFinderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
