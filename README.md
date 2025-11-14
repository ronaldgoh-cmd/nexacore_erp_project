# NexaCore Digital Solutions — Modular ERP Base Framework

## Getting Started

The package exposes a CLI entry point so you can either launch the desktop
application or run helper utilities:

```bash
python -m nexacore_erp            # Launch the main Qt application
python -m nexacore_erp --diag-db  # Print lightweight database diagnostics
```

The diagnostics helper mirrors the behaviour of `diag_db.py` but is available
directly through the module entry point, which is convenient when the project is
installed as a package.

## Documentation

* [Beginner Guide to Going Online](docs/getting_online_beginner_guide.md)
