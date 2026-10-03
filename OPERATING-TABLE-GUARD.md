# YJ-64 Base — Operating Table Guard

This guard is mandatory before every build of the base application.

## Protected files
- main.py
- services/internal_monitor.py
- buildozer.spec
- config/bridge.json
- .github/workflows/ci.yml

## Required invariants
1. The application creates yj64-reports inside its private app storage.
2. The primary journal is yj64-report.jsonl.
3. The archive path is yj64-diagnostics.zip.
4. The absolute paths are visible in the application and can be copied.
5. The planned-crash report is persisted before SIGABRT.
6. The internal monitor appends signed reports to the primary journal.
7. A persisted crash report is recovered after restart.
8. The planned-crash report contains exactly one event key.
9. The guard must print GUARD_OK before a build is allowed.

## Required order
1. Edit the marked working files.
2. Run: python tools/verify_guard.py
3. Stop if the guard prints GUARD_FAIL.
4. Build only after GUARD_OK.
