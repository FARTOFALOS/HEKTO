"""
HEKTO daily reporter — chain-centric.

Reads the day's data from SQLite and produces a structured Markdown report
saved to ``data/patterns/``.  The report now centres on trade chains as the
primary unit, with baseline deviations and role breakdowns.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config import DB_PATH, PATTERNS_DIR
from src.db_writer import get_connection

logger = logging.getLogger(__name__)

# ── Data fetching ─────────────────────────────────────────────────────────

def _fetch_day_chunks(conn, day: str) -> list[dict[str, Any]]:
    """Return all speech chunks whose audio_file was recorded on *day*."""
    rows = conn.execute(
        """SELECT sc.*, af.filename, af.silence_threshold_db, af.mean_db
           FROM speech_chunks sc
           JOIN audio_files af ON sc.audio_file_id = af.id
           WHERE af.recorded_at LIKE ?
           ORDER BY sc.chunk_start_ms""",
        (f"{day}%",),
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_daily_state(conn, day: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM daily_state WHERE date = ?", (day,)).fetchone()
    return dict(row) if row else None


def _fetch_day_chains(conn, day: str) -> list[dict[str, Any]]:
    """Return all trade chains that were opened or active on *day*."""
    rows = conn.execute(
        """SELECT * FROM trade_chains
           WHERE opened_at LIKE ? OR (status = 'incomplete' AND opened_at < ?)
           ORDER BY opened_at""",
        (f"{day}T%", f"{day}T00:00:00"),
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_baseline(conn, day: str) -> dict[str, Any] | None:
    """Return baseline for the day if it exists."""
    row = conn.execute(
        "SELECT * FROM voice_baseline WHERE date <= ? ORDER BY date DESC LIMIT 1",
        (day,),
    ).fetchone()
    return dict(row) if row else None


# ── Stats ─────────────────────────────────────────────────────────────────

def _compute_stats(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate voice statistics for the day."""
    if not chunks:
        return {}

    features_list: list[dict] = []
    for c in chunks:
        vf = c.get("voice_features")
        if vf:
            if isinstance(vf, str):
                vf = json.loads(vf)
            features_list.append(vf)

    if not features_list:
        return {"chunk_count": len(chunks)}

    def _mean(key: str) -> float:
        vals = [f[key] for f in features_list if key in f and f[key] is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    # Role breakdown
    role_counts: dict[str, int] = {}
    for c in chunks:
        role = c.get("chunk_role", "other")
        role_counts[role] = role_counts.get(role, 0) + 1

    return {
        "chunk_count": len(chunks),
        "avg_speech_rate": _mean("speech_rate_proxy"),
        "avg_pitch_hz": _mean("pitch_mean_hz"),
        "avg_pitch_std": _mean("pitch_std_hz"),
        "avg_energy_db": _mean("energy_mean_db"),
        "avg_pause_ratio": _mean("pause_ratio"),
        "self_catch_count": sum(1 for c in chunks if c.get("self_catch_flag")),
        "total_duration_sec": round(sum(
            (c["chunk_end_ms"] - c["chunk_start_ms"]) / 1000.0 for c in chunks
        ), 1),
        "role_breakdown": role_counts,
    }

# ── Report generation ─────────────────────────────────────────────────────

def generate_daily_report(
    day: str | date | None = None,
    db_path: Path | str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """
    Generate a Markdown daily report for *day* (defaults to today).

    Returns the path to the saved report file.
    """
    if day is None:
        day = date.today().isoformat()
    day_str = str(day)

    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        chunks = _fetch_day_chunks(conn, day_str)
        daily_state = _fetch_daily_state(conn, day_str)
        chains = _fetch_day_chains(conn, day_str)
        baseline = _fetch_baseline(conn, day_str)
    finally:
        conn.close()

    stats = _compute_stats(chunks)

    # ── Build report ──────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"# HEKTO Daily Report — {day_str}\n")

    # Daily state
    if daily_state:
        lines.append("## Состояние дня\n")
        lines.append(f"- Сон: {daily_state.get('sleep_hours', '?')} ч")
        lines.append(f"- Стресс: {daily_state.get('stress_level', '?')} / 10")
        lines.append(f"- Физическое состояние: {daily_state.get('physical_state', '—')}")
        if daily_state.get("notes"):
            lines.append(f"- Заметки: {daily_state['notes']}")
        lines.append("")

    # Baseline status
    lines.append("## Базовая линия (Baseline)\n")
    if baseline:
        lines.append(f"- Дата базовой линии: {baseline.get('date', '—')}")
        lines.append(f"- Количество чанков: {baseline.get('chunk_count', 0)}")
        if baseline.get("pitch_mean"):
            lines.append(f"- Средний тон: {baseline['pitch_mean']:.1f} Гц")
        if baseline.get("speech_rate_mean"):
            lines.append(f"- Средний темп: {baseline['speech_rate_mean']:.2f}")
    else:
        lines.append("_Базовая линия ещё не сформирована (нужно ≥5 чанков)._")
    lines.append("")

    # Stats
    lines.append("## Статистика\n")
    if stats:
        lines.append(f"- Фрагментов речи: {stats.get('chunk_count', 0)}")
        lines.append(f"- Общая длительность речи: {stats.get('total_duration_sec', 0)} с")
        lines.append(f"- Средний темп речи: {stats.get('avg_speech_rate', 0)}")
        lines.append(f"- Средний тон: {stats.get('avg_pitch_hz', 0)} Гц")
        lines.append(f"- Вариативность тона: {stats.get('avg_pitch_std', 0)} Гц")
        lines.append(f"- Средняя энергия: {stats.get('avg_energy_db', 0)} дБ")
        lines.append(f"- Доля пауз: {stats.get('avg_pause_ratio', 0)}")
        lines.append(f"- SELF_CATCH: {stats.get('self_catch_count', 0)}")

        # Role breakdown
        roles = stats.get("role_breakdown", {})
        if roles:
            lines.append("")
            lines.append("### Типы высказываний")
            for role, count in sorted(roles.items(), key=lambda x: -x[1]):
                lines.append(f"- {role}: {count}")
    else:
        lines.append("_Нет данных за этот день._")
    lines.append("")

    # Trade chains
    lines.append("## Цепочки решений (Trade Chains)\n")
    if chains:
        for ch in chains:
            status_icon = "✅" if ch.get("status") == "complete" else "⏳"
            outcome = ch.get("outcome") or "—"
            pnl = ch.get("pnl")
            pnl_str = f"  P&L: {pnl}" if pnl is not None else ""
            lines.append(
                f"- {status_icon} Chain #{ch['id']}: {ch.get('symbol', '—')} "
                f"{ch.get('direction', '—')}  → {outcome}{pnl_str}"
            )

            # Show chunks for this chain
            chain_chunks = [c for c in chunks if c.get("chain_id") == ch["id"]]
            for c in chain_chunks:
                time_label = c.get("spoken_time") or c.get("system_time") or "—"
                role = c.get("chunk_role", "other")
                text = c.get("text") or ""
                lines.append(f"  - **[{time_label}]** `{role}` {text}")
        lines.append("")
    else:
        lines.append("_Нет цепочек за этот день._\n")

    # Unlinked chunks
    unlinked = [c for c in chunks if not c.get("chain_id")]
    if unlinked:
        lines.append("## Свободные фрагменты (unlinked)\n")
        for c in unlinked:
            time_label = c.get("spoken_time") or c.get("system_time") or "—"
            role = c.get("chunk_role", "other")
            text = c.get("text") or ""
            lines.append(f"- **[{time_label}]** `{role}` {text}")
        lines.append("")

    # Transcript excerpts (full)
    if chunks:
        lines.append("## Расшифровка (фрагменты)\n")
        for c in chunks:
            time_label = c.get("spoken_time") or c.get("system_time") or "—"
            text = c.get("text") or ""
            lines.append(f"- **[{time_label}]** {text}")
        lines.append("")

    # Observations placeholder
    lines.append("## Наблюдения\n")
    if stats and stats.get("chunk_count", 0) > 0:
        lines.append("Наблюдение: данные собраны, анализ паттернов будет доступен по мере накопления цепочек.")
        lines.append("Связь: —")
        lines.append("Контекст: —")
        lines.append("Сигнал опережения: —")
    else:
        lines.append("_Нет данных для анализа._")
    lines.append("")

    report_text = "\n".join(lines)

    # Save
    dest = output_dir or PATTERNS_DIR
    report_path = dest / f"report_{day_str}.md"
    report_path.write_text(report_text, encoding="utf-8")
    logger.info("Report saved → %s", report_path)
    return report_path


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="HEKTO daily report generator")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    path = generate_daily_report(day=args.date, db_path=args.db)
    print(f"✅  Report: {path}")


if __name__ == "__main__":
    main()
