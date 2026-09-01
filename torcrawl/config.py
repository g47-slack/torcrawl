"""
TORCrawl config loader.

Backwards-compatible with the v1 inline constants, but loaded from YAML
so a user can override without editing source. The v1 inline constants
are kept as the defaults in `configs/default.yaml`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class TorConfig:
    socks_host: str = "127.0.0.1"
    socks_port: int = 9052
    control_host: str = "127.0.0.1"
    control_port: int = 9051
    control_password: str = ""  # Set to HashedControlPassword value (plaintext) OR a keyfile path


@dataclass
class NetConfig:
    concurrency: int = 12
    probe_timeout: float = 18.0
    inter_index_delay: float = 3.0
    newnym_interval: int = 20
    dead_rescan_days: int = 30


@dataclass
class Config:
    tor: TorConfig = field(default_factory=TorConfig)
    net: NetConfig = field(default_factory=NetConfig)
    seeds: List[str] = field(default_factory=list)
    scam_list_path: str = "seeds/scam_list.txt"
    db_path: str = "torcrawl_state.db"
    out_dir: str = "./out"


def _coerce_tor(raw: dict) -> TorConfig:
    return TorConfig(
        socks_host=raw.get("socks_host", "127.0.0.1"),
        socks_port=int(raw.get("socks_port", 9052)),
        control_host=raw.get("control_host", "127.0.0.1"),
        control_port=int(raw.get("control_port", 9051)),
        control_password=os.environ.get("TORCRAWL_TOR_PASSWORD", raw.get("control_password", "")),
    )


def _coerce_net(raw: dict) -> NetConfig:
    return NetConfig(
        concurrency=int(raw.get("concurrency", 12)),
        probe_timeout=float(raw.get("probe_timeout", 18.0)),
        inter_index_delay=float(raw.get("inter_index_delay", 3.0)),
        newnym_interval=int(raw.get("newnym_interval", 20)),
        dead_rescan_days=int(raw.get("dead_rescan_days", 30)),
    )


def load_config(path: Path) -> Config:
    """Load YAML config. Missing file -> defaults. Unknown keys -> ignored."""
    if not path.exists():
        return Config()
    data = yaml.safe_load(path.read_text()) or {}
    return Config(
        tor=_coerce_tor(data.get("tor", {})),
        net=_coerce_net(data.get("net", {})),
        seeds=list(data.get("seeds", [])),
        scam_list_path=data.get("scam_list_path", "seeds/scam_list.txt"),
        db_path=data.get("db_path", "torcrawl_state.db"),
        out_dir=data.get("out_dir", "./out"),
    )
