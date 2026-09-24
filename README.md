# YJ-64 Base

Stage 2 of the YJ-64 staged architecture.

This repository combines:

- a minimal YJ-64 base application;
- the embedded Internal Diagnostic Agent;
- the development Diagnostic Bridge protocol used by the external YJ-64 monitor.

Startup contract:

1. The base activity starts the internal diagnostic service.
2. The internal service runs self-diagnostics.
3. It sends a `yj64.diagnostic.v1` report to the external monitor when the bridge is available.
4. If the bridge is unavailable, the report is persisted locally as JSONL.
5. The internal service records its own startup report.
6. The service hands control back to the base application.
7. A target-launch report records the result.

The package is intentionally `org.blackmirror.blackmirror`, matching the current external YJ-64 monitor target.

The application is deliberately minimal at this stage. The purpose of Stage 2 is to validate the complete lifecycle before the full YJ-64 architecture is introduced.

## Development transport

The development bridge uses loopback TCP:

- host: `127.0.0.1`
- port: `9333`
- schema: `yj64.diagnostic.v1`
- token: configured in `config/bridge.json`

A real HTTPS reporting endpoint is not configured yet.
