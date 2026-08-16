"""Application configuration.

All values have safe local defaults so the MVP runs with zero setup. In a real
deployment these come from environment variables or a secrets manager.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # Storage
    database_url: str = field(default_factory=lambda: _env("APP_DATABASE_URL", "sqlite:///./fleet.db"))

    # Cryptography. The key-encryption key wraps per-job data keys (envelope
    # encryption). For the MVP a deterministic local key is derived from this
    # secret; production replaces it with a KMS or HSM.
    master_secret: bytes = field(
        default_factory=lambda: _env("APP_MASTER_SECRET", "local-development-master-secret").encode()
    )
    session_secret: bytes = field(
        default_factory=lambda: _env("APP_SESSION_SECRET", "local-development-session-secret").encode()
    )

    # Ledger adapter: "log" (default, transparency log) or "chain".
    ledger: str = field(default_factory=lambda: _env("APP_LEDGER", "log"))
    chain_rpc: str = field(default_factory=lambda: _env("APP_CHAIN_RPC", "http://127.0.0.1:8545"))

    # Randomness beacon: "stub" (deterministic, offline) or "drand".
    beacon: str = field(default_factory=lambda: _env("APP_BEACON", "stub"))
    drand_url: str = field(
        default_factory=lambda: _env("APP_DRAND_URL", "https://api.drand.sh")
    )

    # Verification preview parameters (see Architecture.md section 8).
    sampling_n: int = field(default_factory=lambda: int(_env("APP_SAMPLING_N", "20")))
    bucket_seconds: int = 1

    # Envelopes for phase detection, shared verbatim between simulator and
    # verifier. Freezing one table avoids the classic drift bug.
    # Each phase maps modality -> (low, high).
    envelopes: dict = field(
        default_factory=lambda: {
            "idle": {"power": (40, 60), "thermal": (20, 30), "flow": (0, 0)},
            "heating": {"power": (150, 260), "thermal": (30, 210), "flow": (0, 0)},
            "printing": {"power": (300, 400), "thermal": (200, 218), "flow": (8, 15)},
            "cooling": {"power": (40, 90), "thermal": (25, 210), "flow": (0, 0)},
        }
    )


settings = Settings()
