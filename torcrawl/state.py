"""
State persistence.

Schema:

  onions(
    onion        TEXT PRIMARY KEY,   -- bare address, no scheme
    status       TEXT NOT NULL,       -- alive | dead | unknown
    first_seen   TEXT NOT NULL,       -- ISO8601
    last_seen    TEXT NOT NULL,
    last_status_change TEXT NOT NULL,
    response_time_ms REAL DEFAULT 0,
    fail_count   INTEGER NOT NULL DEFAULT 0,
    in_degree    INTEGER NOT NULL DEFAULT 0,   -- how many other onions link to this one
    notes        TEXT
  )

  edges(
    source_url  TEXT NOT NULL,         -- which seed/index first reported this onion
    target_onion TEXT NOT NULL,         -- bare onion
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    hit_count   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (source_url, target_onion)
  )

  runs(
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    config_json TEXT NOT NULL,
    stats_json  TEXT
  )

WAL mode is enabled so a crash mid-crawl doesn't lose the transaction
log; readers can resume from `runs.finished_at IS NULL`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple


SCHEMA = """
CREATE TABLE IF NOT EXISTS onions (
    onion TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unknown',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_status_change TEXT NOT NULL,
    response_time_ms REAL NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    in_degree INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_onions_status ON onions(status);
CREATE INDEX IF NOT EXISTS idx_onions_last_seen ON onions(last_seen);
CREATE INDEX IF NOT EXISTS idx_onions_in_degree ON onions(in_degree);

CREATE TABLE IF NOT EXISTS edges (
    source_url TEXT NOT NULL,
    target_onion TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (source_url, target_onion)
);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_onion);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_url);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    config_json TEXT NOT NULL,
    stats_json TEXT
);
"""


class State:
    """Thread-safe (single writer, many readers) SQLite state for TORCrawl."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        # check_same_thread=False so we can hand connections to worker
        # threads if we later parallelise. The lock serialises writes.
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        # WAL gives us crash-resilience for free.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.row_factory = sqlite3.Row

    # -- lifecycle -----------------------------------------------------------

    def init(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- core writes ----------------------------------------------------------

    def record_probe(self, *, onion: str, alive: bool, response_time_ms: float) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM onions WHERE onion = ?", (onion,)
            ).fetchone()
            if row is None:
                status = "alive" if alive else "dead"
                self._conn.execute(
                    "INSERT INTO onions (onion, status, first_seen, last_seen, "
                    "last_status_change, response_time_ms, fail_count, in_degree) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                    (onion, status, now, now, now, response_time_ms, 0 if alive else 1),
                )
                return
            new_status = "alive" if alive else "dead"
            if alive:
                self._conn.execute(
                    "UPDATE onions SET status = ?, last_status_change = ?, "
                    "last_seen = ?, response_time_ms = ?, fail_count = 0 "
                    "WHERE onion = ?",
                    (new_status, now, now, response_time_ms, onion),
                )
            else:
                self._conn.execute(
                    "UPDATE onions SET last_seen = ?, fail_count = fail_count + 1, "
                    "response_time_ms = ? WHERE onion = ?",
                    (now, response_time_ms, onion),
                )
            if new_status != row["status"]:
                self._conn.execute(
                    "UPDATE onions SET status = ?, last_status_change = ? "
                    "WHERE onion = ?",
                    (new_status, now, onion),
                )

    def upsert_unknown(self, onion: str, *, source: str = "harvest") -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            cur = self._conn.execute(
                "SELECT status FROM onions WHERE onion = ?", (onion,)
            ).fetchone()
            if cur is None:
                self._conn.execute(
                    "INSERT INTO onions (onion, status, first_seen, last_seen, "
                    "last_status_change, response_time_ms, fail_count, in_degree) "
                    "VALUES (?, 'unknown', ?, ?, ?, 0.0, 0, 0)",
                    (onion, now, now, now),
                )

    def record_edge(self, *, source_url: str, target_onion: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            cur = self._conn.execute(
                "SELECT hit_count FROM edges WHERE source_url = ? AND target_onion = ?",
                (source_url, target_onion),
            ).fetchone()
            if cur is None:
                self._conn.execute(
                    "INSERT INTO edges (source_url, target_onion, first_seen, "
                    "last_seen, hit_count) VALUES (?, ?, ?, ?, 1)",
                    (source_url, target_onion, now, now),
                )
                self._conn.execute(
                    "UPDATE onions SET in_degree = in_degree + 1 WHERE onion = ?",
                    (target_onion,),
                )
            else:
                self._conn.execute(
                    "UPDATE edges SET last_seen = ?, hit_count = hit_count + 1 "
                    "WHERE source_url = ? AND target_onion = ?",
                    (now, source_url, target_onion),
                )

    # -- reads ---------------------------------------------------------------

    def list_candidates(self, *, cutoff_iso: str) -> List[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT onion FROM onions "
                "WHERE status IN ('alive', 'unknown') "
                "OR (status = 'dead' AND last_seen < ?) "
                "ORDER BY in_degree DESC, last_seen ASC",
                (cutoff_iso,),
            )
            return [r["onion"] for r in cur.fetchall()]

    def mark_unseen_as_dead(self, *, currently_alive: Set[str]) -> int:
        """Any onion previously marked alive but NOT in this run's set -> dead."""
        if not currently_alive:
            return 0
        with self._lock:
            placeholders = ",".join("?" for _ in currently_alive)
            cur = self._conn.execute(
                f"UPDATE onions SET status = 'dead', last_status_change = ? "
                f"WHERE status = 'alive' AND onion NOT IN ({placeholders})",
                (datetime.utcnow().isoformat(), *currently_alive),
            )
            return cur.rowcount or 0

    def stats(self) -> Dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS c FROM onions").fetchone()["c"]
            by_status = {
                row["status"]: row["c"]
                for row in self._conn.execute(
                    "SELECT status, COUNT(*) AS c FROM onions GROUP BY status"
                ).fetchall()
            }
            top_in = [
                dict(onion=r["onion"], in_degree=r["in_degree"])
                for r in self._conn.execute(
                    "SELECT onion, in_degree FROM onions ORDER BY in_degree DESC LIMIT 25"
                ).fetchall()
            ]
            edge_total = self._conn.execute("SELECT COUNT(*) AS c FROM edges").fetchone()["c"]
            return {
                "total": total,
                "by_status": by_status,
                "edges": edge_total,
                "top_in_degree": top_in,
            }

    # -- export --------------------------------------------------------------

    def export_graphml(self, path: Path) -> None:
        """Write the onion provenance graph as GraphML (yEd/Gephi compatible)."""
        lines: List[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
            'http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
            '<key id="status" for="node" attr.name="status" attr.type="string"/>',
            '<key id="in_degree" for="node" attr.name="in_degree" attr.type="int"/>',
            '<key id="first_seen" for="node" attr.name="first_seen" attr.type="string"/>',
            '<key id="weight" for="edge" attr.name="weight" attr.type="int"/>',
            '<graph id="torcrawl" edgedefault="directed">',
        ]
        with self._lock:
            for r in self._conn.execute(
                "SELECT onion, status, in_degree, first_seen FROM onions"
            ).fetchall():
                lines.append(
                    f'<node id="{_xml_escape(r["onion"])}">'
                    f'<data key="status">{_xml_escape(r["status"])}</data>'
                    f'<data key="in_degree">{r["in_degree"]}</data>'
                    f'<data key="first_seen">{_xml_escape(r["first_seen"])}</data>'
                    f'</node>'
                )
            for r in self._conn.execute(
                "SELECT source_url, target_onion, hit_count FROM edges"
            ).fetchall():
                lines.append(
                    f'<edge source="{_xml_escape(r["source_url"])}" '
                    f'target="{_xml_escape(r["target_onion"])}">'
                    f'<data key="weight">{r["hit_count"]}</data>'
                    f'</edge>'
                )
        lines.extend(("</graph>", "</graphml>"))
        Path(path).write_text("\n".join(lines), encoding="utf-8")


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )
