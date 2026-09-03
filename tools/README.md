# CLI tools

Root `tools/` is the stable command-line surface shared by every harness. These files are thin compatibility launchers; implementations live under the corresponding `agents/<package>/tools/` directory.

Primary entry point:

```bash
python tools/astock.py --help
```

Maintenance:

```bash
python tools/sync_harness.py
python tools/sync_harness.py --check
python tools/validate_artifact.py --run-id <run_id> --artifact <name>
```
