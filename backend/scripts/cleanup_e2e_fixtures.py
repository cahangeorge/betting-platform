"""CLI wrapper for the guarded E2E fixture cleanup service."""

from app.services.e2e_cleanup import main

if __name__ == "__main__":
    raise SystemExit(main())
