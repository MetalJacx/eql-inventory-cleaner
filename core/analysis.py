"""Core inventory parsing and merge analysis logic shared by desktop and web."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

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
# by the class tests. Matching is name-based because /outputfile inventory
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


def normalized_item_key(name: str) -> str:
    """Normalize EQL punctuation/spacing for reliable static-name matching."""
    return re.sub(r"\s+", " ", name.replace("`", "'").strip().casefold())


SKY_TURNIN_KEYS = {normalized_item_key(name) for name in SKY_TURNIN_NAMES}


def is_sky_turnin_group(items: list[dict]) -> bool:
    if not items:
        return False
    return normalized_item_key(items[0]["base_name"]) in SKY_TURNIN_KEYS


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()

    # EQL exports can be UTF-16. Pasted/saved copies may be UTF-8.
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")

    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-16")


def parse_tier(name: str) -> int:
    match = TIER_RE.search(name.strip())
    if not match:
        return 0

    tier = int(match.group(1))
    return tier if 0 <= tier <= 10 else 0


def base_name(name: str) -> str:
    name = name.strip()
    name = name.replace(" (Exaltation)", "")
    return TIER_RE.sub("", name).strip()


def parse_inventory(text: str) -> list[dict]:
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


def group_duplicates(records: list[dict]) -> dict[int, list[dict]]:
    groups = defaultdict(list)

    for item in records:
        groups[item["id"]].append(item)

    return {
        item_id: items
        for item_id, items in groups.items()
        if len(items) >= 2
    }


def confidence(items: list[dict]) -> str:
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


def project_merge(items: list[dict]) -> dict:
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


def tier_text(tier: int) -> str:
    return f"+{tier}"


def projection_text(plan: dict) -> str:
    target = plan["target"]

    if plan["maxed"]:
        return "Already +10"

    new_tier = plan["new_tier"]

    if plan["progress"] is None:
        return f"{tier_text(target['tier'])} -> +10"

    current, needed = plan["progress"]

    if new_tier > target["tier"]:
        return (
            f"{tier_text(target['tier'])} -> {tier_text(new_tier)} "
            f"({current}/{needed})"
        )

    return f"{tier_text(new_tier)} ({current}/{needed})"


def build_report(filename: str, confirmed_groups: list[list[dict]], possible_groups: list[list[dict]]) -> str:
    bar = "=" * 78
    lines = [
        bar,
        "EQL INVENTORY CLEANER - MERGE FINDER",
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


def analyze_inventory_text(text: str, filename: str = "uploaded-inventory.txt") -> dict:
    """Return structured web-friendly analysis payload for an inventory text blob."""
    records = parse_inventory(text)
    duplicates = group_duplicates(records)

    confirmed_groups = []
    possible_groups = []
    for items in duplicates.values():
        if confidence(items) == "confirmed":
            confirmed_groups.append(items)
        else:
            possible_groups.append(items)

    confirmed_groups.sort(key=lambda group: group[0]["base_name"].casefold())
    possible_groups.sort(key=lambda group: group[0]["base_name"].casefold())

    confirmed_payload = []
    for items in confirmed_groups:
        plan = project_merge(items)
        target = plan["target"]
        confirmed_payload.append({
            "item_name": target["base_name"],
            "item_id": target["id"],
            "keep_tier": target["tier"],
            "keep_location": target["location"],
            "donor_count": len(plan["donors"]),
            "donor_xp": plan["donor_xp"],
            "projection": projection_text(plan),
            "maxed": plan["maxed"],
            "is_sky_turnin": is_sky_turnin_group(items),
            "items": items,
            "plan": plan,
        })

    possible_payload = []
    for items in possible_groups:
        possible_payload.append({
            "item_name": items[0]["base_name"],
            "item_id": items[0]["id"],
            "copy_count": len(items),
            "is_sky_turnin": is_sky_turnin_group(items),
            "items": sorted(items, key=lambda x: x["location"]),
        })

    report_text = build_report(filename, confirmed_groups, possible_groups)
    return {
        "meta": {
            "filename": filename,
            "record_count": len(records),
            "confirmed_count": len(confirmed_groups),
            "possible_count": len(possible_groups),
        },
        "confirmed": confirmed_payload,
        "possible": possible_payload,
        "report_text": report_text,
    }
