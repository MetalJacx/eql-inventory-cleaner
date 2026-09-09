# EQL Inventory Cleaner v1.5

The first public GitHub-ready release of EQL Inventory Cleaner, an extensible home for EverQuest Legends inventory-cleanup tools. This release launches with the Merge Finder tool.

## Highlights

- Scan EverQuest Legends `/outputfile inventory` exports in a desktop UI.
- Find duplicate equipment by EQL item ID across inventory, bank, hoard, and the Equipment KeyRing.
- Correctly match different upgrade tiers of the same item (`+0` through `+10`).
- Ignore Exaltation/Augmentation entries so socketed copies are not reported as physical duplicates.
- Show suggested **KEEP** and **FEED** copies, donor XP, and projected merge progress.
- Separate uncertain `+0` duplicates from high-confidence equipment duplicates.
- Remember the last inventory file, browse folder, window size, theme, report folder, and filters.
- Modern light/dark desktop interface with searchable and sortable results.
- Persistent **Hide already +10** filter.
- Persistent **Hide Sky turn-ins** filter based on EverQuest Legends Plane of Sky quest items.
- Save or copy a full text report.
- Read-only: the program never changes the game or inventory file.

## Platform notes

### Windows

Use `EQL-Inventory-Cleaner.exe` from the release assets.

### Linux

Use the `EQL-Inventory-Cleaner` standalone binary from the release assets. Mark it executable if needed:

```bash
chmod +x EQL-Inventory-Cleaner
./EQL-Inventory-Cleaner
```

### Bazzite

The Linux build is intended to avoid modifying Bazzite's immutable base OS. A separately packaged Bazzite portable `.run` build may also be attached to the release when available.

## Known limitation

EQL's inventory export includes an item's current `+tier`, but not partial item XP already accumulated inside that tier. Merge projections therefore assume the target copy starts at 0 partial XP in its current tier.

## Upgrade note

Settings are kept outside the application, so replacing an older build should preserve the remembered inventory path, theme, and filter choices.
