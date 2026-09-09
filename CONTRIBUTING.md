# Contributing

Thanks for helping improve EQL Inventory Cleaner.

## Good contributions

- Parser fixes for real EverQuest Legends inventory exports.
- UI improvements that remain practical on Windows and Linux/Bazzite.
- Corrections to EQL-specific merge behavior.
- Corrections/additions to the Plane of Sky turn-in filter based on current EQL sources.
- Packaging and release improvements.
- Web API improvements that keep analysis read-only and behavior-aligned with desktop results.

## Before opening a pull request

1. Keep the application read-only. It should never automate gameplay or modify an EQL inventory export.
2. Prefer EverQuest Legends-specific behavior and sources. Do not silently substitute Project 1999 behavior for EQL behavior.
3. Avoid adding runtime dependencies unless the benefit is substantial. The app currently runs on Python's standard library and Tkinter.
4. Test parsing with an actual `/outputfile inventory` export when changing inventory logic.
5. Test both light and dark themes when changing UI styling.
6. When changing shared parser/analysis behavior, keep [core/analysis.py](core/analysis.py) and desktop outputs equivalent.

## Web API local run

```bash
python3 -m pip install -r requirements-web.txt
uvicorn web_api.app:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Running from source

```bash
python3 eql_inventory_cleaner.py
```

On Windows:

```powershell
py eql_inventory_cleaner.py
```

## CLI parser check

The source includes a CLI scan mode that is useful for parser regression checks:

```bash
python3 eql_inventory_cleaner.py --cli-scan path/to/Character-Inventory.txt
```

## Pull requests

Please describe:

- what changed;
- why the change is EQL-correct;
- how you tested it;
- whether it changes filtering, merge calculations, or packaging.
