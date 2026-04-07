"""
HEKTO Pattern Engine — Layer 2.

Analyses completed trade chains to discover behavioural patterns that
correlate a trader's speech/voice features with trade outcomes.

The engine runs automatically after 20+ completed chains and produces:
- Pattern records in the ``patterns`` DB table
- Markdown reports in ``data/patterns/``

Pattern types analysed:
1. **Role-outcome** — chunk role presence → outcome (e.g. "doubt → loss 71%")
2. **Voice-outcome** — voice deviations → outcome
3. **Time-outcome** — time-of-day bias
4. **Duration-outcome** — chain duration bias (fast vs slow decisions)
5. **Keyword-outcome** — specific words/phrases → outcome

Each pattern carries:
- ``confidence`` (0.0–1.0) and ``confidence_level`` (Low/Medium/High)
- ``evidence`` list of supporting chain IDs
- ``counter_evidence`` list of contradicting chain IDs
- ``conditions`` JSON describing the trigger
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DB_PATH, PATTERNS_DIR
from src.db_writer import get_connection, insert_pattern, transaction

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

MIN_CHAINS_FOR_PATTERNS: int = 20
MIN_EVIDENCE_FOR_PATTERN: int = 5
CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "high": 0.70,
    "medium": 0.50,
}

CONFIDENCE_LEVEL_LABELS: list[tuple[str, str]] = [
    ("high", "🔴 Высокая уверенность"),
    ("medium", "⚠️ Средняя уверенность"),
    ("low", "ℹ️ Низкая уверенность"),
]

# ── Data loading ──────────────────────────────────────────────────────────


def _load_completed_chains(
    conn,
) -> list[dict[str, Any]]:
    """Load all completed chains with their chunks and events."""
    chains = conn.execute(
        """SELECT * FROM trade_chains
           WHERE status = 'complete' AND outcome IS NOT NULL
           ORDER BY opened_at""",
    ).fetchall()

    result = []
    for ch in chains:
        ch_dict = dict(ch)

        # Load chunks
        chunks = conn.execute(
            """SELECT id, chunk_role, text, system_time, voice_features,
                      baseline_deviation
               FROM speech_chunks
               WHERE chain_id = ?
               ORDER BY chunk_start_ms""",
            (ch["id"],),
        ).fetchall()
        ch_dict["chunks"] = [dict(c) for c in chunks]

        # Parse JSON fields
        for chunk in ch_dict["chunks"]:
            for field in ("voice_features", "baseline_deviation"):
                val = chunk.get(field)
                if val and isinstance(val, str):
                    try:
                        chunk[field] = json.loads(val)
                    except json.JSONDecodeError:
                        chunk[field] = None

        # Load events
        events = conn.execute(
            """SELECT * FROM trade_events
               WHERE chain_id = ?
               ORDER BY timestamp""",
            (ch["id"],),
        ).fetchall()
        ch_dict["events"] = [dict(e) for e in events]

        result.append(ch_dict)

    return result


# ── Analysis helpers ──────────────────────────────────────────────────────


def _is_profitable(chain: dict[str, Any]) -> bool:
    return chain.get("outcome") == "profit"


def _confidence_level(confidence: float) -> str:
    if confidence >= CONFIDENCE_THRESHOLDS["high"]:
        return "high"
    if confidence >= CONFIDENCE_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _compute_confidence(
    evidence_ids: list[int],
    counter_ids: list[int],
) -> float:
    """
    Confidence = evidence / (evidence + counter_evidence).
    Returns 0.0 if no data.
    """
    total = len(evidence_ids) + len(counter_ids)
    if total == 0:
        return 0.0
    return round(len(evidence_ids) / total, 3)


# ── Pattern detectors ────────────────────────────────────────────────────


def _detect_role_outcome_patterns(
    chains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect role-outcome patterns: when a specific chunk role is present
    in a chain, does it correlate with profit or loss?
    """
    role_chains: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {"profit": [], "loss": []}
    )

    for ch in chains:
        roles_seen = set()
        for chunk in ch.get("chunks", []):
            role = chunk.get("chunk_role")
            if role and role != "other":
                roles_seen.add(role)

        for role in roles_seen:
            outcome = ch.get("outcome", "")
            if outcome in ("profit", "loss"):
                role_chains[role][outcome].append(ch["id"])

    patterns = []
    for role, outcomes in role_chains.items():
        profit_ids = outcomes["profit"]
        loss_ids = outcomes["loss"]
        total = len(profit_ids) + len(loss_ids)

        if total < MIN_EVIDENCE_FOR_PATTERN:
            continue

        # Pattern: role → loss
        loss_conf = _compute_confidence(loss_ids, profit_ids)
        if loss_conf >= CONFIDENCE_THRESHOLDS["medium"]:
            loss_pct = round(loss_conf * 100, 1)
            patterns.append({
                "title": f"Роль «{role}» → убыток ({loss_pct}%)",
                "description": (
                    f"В {loss_pct}% случаев, когда в цепочке присутствует "
                    f"роль «{role}», результат — убыток."
                ),
                "conditions": {"type": "role_outcome", "role": role, "predicted_outcome": "loss"},
                "evidence": loss_ids,
                "counter_evidence": profit_ids,
                "evidence_count": len(loss_ids),
                "counter_evidence_count": len(profit_ids),
                "confidence": loss_conf,
                "confidence_level": _confidence_level(loss_conf),
            })

        # Pattern: role → profit
        profit_conf = _compute_confidence(profit_ids, loss_ids)
        if profit_conf >= CONFIDENCE_THRESHOLDS["medium"]:
            profit_pct = round(profit_conf * 100, 1)
            patterns.append({
                "title": f"Роль «{role}» → прибыль ({profit_pct}%)",
                "description": (
                    f"В {profit_pct}% случаев, когда в цепочке присутствует "
                    f"роль «{role}», результат — прибыль."
                ),
                "conditions": {"type": "role_outcome", "role": role, "predicted_outcome": "profit"},
                "evidence": profit_ids,
                "counter_evidence": loss_ids,
                "evidence_count": len(profit_ids),
                "counter_evidence_count": len(loss_ids),
                "confidence": profit_conf,
                "confidence_level": _confidence_level(profit_conf),
            })

    return patterns


def _detect_voice_outcome_patterns(
    chains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect voice deviation patterns: when baseline deviation is elevated
    (any metric above threshold), does it correlate with outcome?
    """
    DEVIATION_THRESHOLD = 15.0  # %
    elevated_profit: list[int] = []
    elevated_loss: list[int] = []
    normal_profit: list[int] = []
    normal_loss: list[int] = []

    for ch in chains:
        # Check if any chunk in chain had elevated voice
        elevated = False
        for chunk in ch.get("chunks", []):
            dev = chunk.get("baseline_deviation")
            if dev and isinstance(dev, dict):
                for key in ("pitch_deviation_pct", "speech_rate_deviation_pct",
                             "energy_deviation_pct"):
                    val = dev.get(key)
                    if val is not None and abs(val) > DEVIATION_THRESHOLD:
                        elevated = True
                        break
            if elevated:
                break

        outcome = ch.get("outcome", "")
        if outcome == "profit":
            (elevated_profit if elevated else normal_profit).append(ch["id"])
        elif outcome == "loss":
            (elevated_loss if elevated else normal_loss).append(ch["id"])

    patterns = []

    # Elevated voice → loss
    total_elevated = len(elevated_profit) + len(elevated_loss)
    if total_elevated >= MIN_EVIDENCE_FOR_PATTERN:
        conf = _compute_confidence(elevated_loss, elevated_profit)
        if conf >= CONFIDENCE_THRESHOLDS["medium"]:
            pct = round(conf * 100, 1)
            patterns.append({
                "title": f"Повышенное отклонение голоса → убыток ({pct}%)",
                "description": (
                    f"В {pct}% случаев, когда голосовые показатели отклоняются "
                    f"от базовой линии более чем на {DEVIATION_THRESHOLD}%, "
                    f"результат — убыток."
                ),
                "conditions": {
                    "type": "voice_outcome",
                    "deviation_threshold_pct": DEVIATION_THRESHOLD,
                    "predicted_outcome": "loss",
                },
                "evidence": elevated_loss,
                "counter_evidence": elevated_profit,
                "evidence_count": len(elevated_loss),
                "counter_evidence_count": len(elevated_profit),
                "confidence": conf,
                "confidence_level": _confidence_level(conf),
            })

    # Normal voice → profit
    total_normal = len(normal_profit) + len(normal_loss)
    if total_normal >= MIN_EVIDENCE_FOR_PATTERN:
        conf = _compute_confidence(normal_profit, normal_loss)
        if conf >= CONFIDENCE_THRESHOLDS["medium"]:
            pct = round(conf * 100, 1)
            patterns.append({
                "title": f"Спокойный голос → прибыль ({pct}%)",
                "description": (
                    f"В {pct}% случаев, когда голос трейдера остаётся в пределах "
                    f"базовой линии, результат — прибыль."
                ),
                "conditions": {
                    "type": "voice_outcome",
                    "deviation_threshold_pct": DEVIATION_THRESHOLD,
                    "predicted_outcome": "profit",
                },
                "evidence": normal_profit,
                "counter_evidence": normal_loss,
                "evidence_count": len(normal_profit),
                "counter_evidence_count": len(normal_loss),
                "confidence": conf,
                "confidence_level": _confidence_level(conf),
            })

    return patterns


def _detect_duration_outcome_patterns(
    chains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect duration-based patterns: fast vs slow decision chains.
    Fast chains = duration below median; slow = above median.
    """
    durations: list[tuple[int, float, str]] = []  # (chain_id, duration_min, outcome)

    for ch in chains:
        if ch.get("opened_at") and ch.get("closed_at") and ch.get("outcome") in ("profit", "loss"):
            try:
                opened = datetime.fromisoformat(ch["opened_at"])
                closed = datetime.fromisoformat(ch["closed_at"])
                dur_min = (closed - opened).total_seconds() / 60.0
                if dur_min > 0:
                    durations.append((ch["id"], dur_min, ch["outcome"]))
            except (ValueError, TypeError):
                continue

    if len(durations) < MIN_EVIDENCE_FOR_PATTERN:
        return []

    # Compute median
    sorted_durs = sorted(d[1] for d in durations)
    mid = len(sorted_durs) // 2
    median_dur = (
        sorted_durs[mid]
        if len(sorted_durs) % 2 != 0
        else (sorted_durs[mid - 1] + sorted_durs[mid]) / 2.0
    )

    fast_profit: list[int] = []
    fast_loss: list[int] = []
    slow_profit: list[int] = []
    slow_loss: list[int] = []

    for chain_id, dur_min, outcome in durations:
        if dur_min <= median_dur:
            (fast_profit if outcome == "profit" else fast_loss).append(chain_id)
        else:
            (slow_profit if outcome == "profit" else slow_loss).append(chain_id)

    patterns = []
    median_str = f"{median_dur:.0f}" if median_dur >= 1 else f"{median_dur:.1f}"

    # Fast chains → outcome
    total_fast = len(fast_profit) + len(fast_loss)
    if total_fast >= MIN_EVIDENCE_FOR_PATTERN:
        for label, evidence, counter, predicted in [
            ("прибыль", fast_profit, fast_loss, "profit"),
            ("убыток", fast_loss, fast_profit, "loss"),
        ]:
            conf = _compute_confidence(evidence, counter)
            if conf >= CONFIDENCE_THRESHOLDS["medium"]:
                pct = round(conf * 100, 1)
                patterns.append({
                    "title": f"Быстрые решения (≤{median_str} мин) → {label} ({pct}%)",
                    "description": (
                        f"В {pct}% случаев, когда цепочка решений длится "
                        f"≤{median_str} минут, результат — {label}."
                    ),
                    "conditions": {
                        "type": "duration_outcome",
                        "duration_threshold_min": round(median_dur, 1),
                        "direction": "fast",
                        "predicted_outcome": predicted,
                    },
                    "evidence": evidence,
                    "counter_evidence": counter,
                    "evidence_count": len(evidence),
                    "counter_evidence_count": len(counter),
                    "confidence": conf,
                    "confidence_level": _confidence_level(conf),
                })

    # Slow chains → outcome
    total_slow = len(slow_profit) + len(slow_loss)
    if total_slow >= MIN_EVIDENCE_FOR_PATTERN:
        for label, evidence, counter, predicted in [
            ("прибыль", slow_profit, slow_loss, "profit"),
            ("убыток", slow_loss, slow_profit, "loss"),
        ]:
            conf = _compute_confidence(evidence, counter)
            if conf >= CONFIDENCE_THRESHOLDS["medium"]:
                pct = round(conf * 100, 1)
                patterns.append({
                    "title": f"Медленные решения (>{median_str} мин) → {label} ({pct}%)",
                    "description": (
                        f"В {pct}% случаев, когда цепочка решений длится "
                        f">{median_str} минут, результат — {label}."
                    ),
                    "conditions": {
                        "type": "duration_outcome",
                        "duration_threshold_min": round(median_dur, 1),
                        "direction": "slow",
                        "predicted_outcome": predicted,
                    },
                    "evidence": evidence,
                    "counter_evidence": counter,
                    "evidence_count": len(evidence),
                    "counter_evidence_count": len(counter),
                    "confidence": conf,
                    "confidence_level": _confidence_level(conf),
                })

    return patterns


def _detect_keyword_outcome_patterns(
    chains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect keyword-outcome patterns: specific Russian words/phrases that
    correlate with outcome.
    """
    # Target keywords (common trader self-talk indicators)
    TARGET_KEYWORDS = [
        "подержу", "ещё чуть-чуть", "потерплю", "не уверен",
        "сомневаюсь", "страшно", "рискованно", "надо было",
        "зря", "стоп", "жду реакции", "вижу сетап",
    ]

    keyword_chains: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {"profit": [], "loss": []}
    )

    for ch in chains:
        outcome = ch.get("outcome", "")
        if outcome not in ("profit", "loss"):
            continue

        all_text = " ".join(
            (c.get("text") or "").lower() for c in ch.get("chunks", [])
        )

        for kw in TARGET_KEYWORDS:
            if kw.lower() in all_text:
                keyword_chains[kw][outcome].append(ch["id"])

    patterns = []
    for kw, outcomes in keyword_chains.items():
        profit_ids = outcomes["profit"]
        loss_ids = outcomes["loss"]
        total = len(profit_ids) + len(loss_ids)

        if total < MIN_EVIDENCE_FOR_PATTERN:
            continue

        # Keyword → loss
        loss_conf = _compute_confidence(loss_ids, profit_ids)
        if loss_conf >= CONFIDENCE_THRESHOLDS["medium"]:
            pct = round(loss_conf * 100, 1)
            patterns.append({
                "title": f"Слово «{kw}» → убыток ({pct}%)",
                "description": (
                    f"В {pct}% случаев, когда трейдер произносит «{kw}», "
                    f"результат цепочки — убыток."
                ),
                "conditions": {"type": "keyword_outcome", "keyword": kw, "predicted_outcome": "loss"},
                "evidence": loss_ids,
                "counter_evidence": profit_ids,
                "evidence_count": len(loss_ids),
                "counter_evidence_count": len(profit_ids),
                "confidence": loss_conf,
                "confidence_level": _confidence_level(loss_conf),
            })

        # Keyword → profit
        profit_conf = _compute_confidence(profit_ids, loss_ids)
        if profit_conf >= CONFIDENCE_THRESHOLDS["medium"]:
            pct = round(profit_conf * 100, 1)
            patterns.append({
                "title": f"Слово «{kw}» → прибыль ({pct}%)",
                "description": (
                    f"В {pct}% случаев, когда трейдер произносит «{kw}», "
                    f"результат цепочки — прибыль."
                ),
                "conditions": {"type": "keyword_outcome", "keyword": kw, "predicted_outcome": "profit"},
                "evidence": profit_ids,
                "counter_evidence": loss_ids,
                "evidence_count": len(profit_ids),
                "counter_evidence_count": len(loss_ids),
                "confidence": profit_conf,
                "confidence_level": _confidence_level(profit_conf),
            })

    return patterns


# ── Main engine ───────────────────────────────────────────────────────────


def run_pattern_analysis(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    Run pattern analysis on all completed chains.

    Requirements:
    - At least MIN_CHAINS_FOR_PATTERNS (20) completed chains.
    - Returns list of new patterns discovered.

    Each call replaces existing candidate patterns and updates confirmed ones.
    """
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        chains = _load_completed_chains(conn)
    finally:
        conn.close()

    if len(chains) < MIN_CHAINS_FOR_PATTERNS:
        logger.info(
            "Pattern Engine: only %d completed chains (need %d). Skipping.",
            len(chains), MIN_CHAINS_FOR_PATTERNS,
        )
        return []

    logger.info("Pattern Engine: analysing %d completed chains", len(chains))

    # Run all detectors
    all_patterns: list[dict[str, Any]] = []
    all_patterns.extend(_detect_role_outcome_patterns(chains))
    all_patterns.extend(_detect_voice_outcome_patterns(chains))
    all_patterns.extend(_detect_duration_outcome_patterns(chains))
    all_patterns.extend(_detect_keyword_outcome_patterns(chains))

    if not all_patterns:
        logger.info("Pattern Engine: no significant patterns found.")
        return []

    # Save to DB (clear old candidates, keep confirmed/rejected)
    with transaction(db) as conn:
        conn.execute(
            "DELETE FROM patterns WHERE status = 'candidate'",
        )
        for p in all_patterns:
            insert_pattern(
                conn,
                title=p["title"],
                description=p["description"],
                conditions=p["conditions"],
                evidence=p["evidence"],
                counter_evidence=p["counter_evidence"],
                evidence_count=p["evidence_count"],
                counter_evidence_count=p["counter_evidence_count"],
                confidence=p["confidence"],
                confidence_level=p["confidence_level"],
                status="candidate",
            )

    logger.info("Pattern Engine: saved %d patterns", len(all_patterns))
    return all_patterns


# ── Pattern-based predictive signal ──────────────────────────────────────


def get_predictive_signal(
    chain_roles: set[str],
    keywords: list[str],
    voice_elevated: bool,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Generate a predictive signal for an active chain based on known patterns.

    Parameters
    ----------
    chain_roles : set of chunk roles seen in the current chain
    keywords : list of keywords/phrases found in current chain text
    voice_elevated : whether voice deviations are elevated

    Returns
    -------
    dict with:
        'has_signal': bool
        'warnings': list[str] — human-readable warnings (Russian)
        'patterns_matched': list[dict] — matching patterns with confidence
    """
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        rows = conn.execute(
            """SELECT * FROM patterns
               WHERE status IN ('candidate', 'confirmed')
                 AND confidence >= ?
               ORDER BY confidence DESC""",
            (CONFIDENCE_THRESHOLDS["medium"],),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"has_signal": False, "warnings": [], "patterns_matched": []}

    warnings: list[str] = []
    matched: list[dict[str, Any]] = []

    for row in rows:
        row_dict = dict(row)
        conditions = row_dict.get("conditions")
        if conditions and isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except json.JSONDecodeError:
                continue
        if not isinstance(conditions, dict):
            continue

        pattern_type = conditions.get("type")
        predicted = conditions.get("predicted_outcome")

        match = False

        if pattern_type == "role_outcome":
            role = conditions.get("role")
            if role and role in chain_roles:
                match = True

        elif pattern_type == "keyword_outcome":
            kw = conditions.get("keyword", "").lower()
            if kw and any(kw in k.lower() for k in keywords):
                match = True

        elif pattern_type == "voice_outcome":
            if conditions.get("predicted_outcome") == "loss" and voice_elevated:
                match = True

        if match and predicted == "loss":
            level = row_dict.get("confidence_level", "low")
            icon = "🔴" if level == "high" else "⚠️"
            conf_pct = round(row_dict.get("confidence", 0) * 100)
            warnings.append(
                f"{icon} Паттерн: {row_dict['title']} (уверенность {conf_pct}%)"
            )
            matched.append({
                "pattern_id": row_dict.get("pattern_id"),
                "title": row_dict["title"],
                "confidence": row_dict.get("confidence"),
                "confidence_level": level,
                "predicted_outcome": predicted,
            })

    return {
        "has_signal": len(warnings) > 0,
        "warnings": warnings,
        "patterns_matched": matched,
    }


# ── Report generation ────────────────────────────────────────────────────


def generate_pattern_report(
    patterns: list[dict[str, Any]],
    *,
    output_dir: Path | None = None,
) -> Path | None:
    """Generate a Markdown report of discovered patterns."""
    if not patterns:
        return None

    dest = output_dir or PATTERNS_DIR
    dest.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now().strftime("%Y-%m-%d")
    lines: list[str] = []
    lines.append(f"# HEKTO Pattern Report — {now_str}\n")
    lines.append(f"Всего паттернов: **{len(patterns)}**\n")

    # Group by confidence level
    for level, label in CONFIDENCE_LEVEL_LABELS:
        level_patterns = [p for p in patterns if p.get("confidence_level") == level]
        if not level_patterns:
            continue

        lines.append(f"\n## {label}\n")
        for p in level_patterns:
            conf_pct = round(p.get("confidence", 0) * 100, 1)
            lines.append(f"### {p['title']}\n")
            lines.append(f"- **Уверенность**: {conf_pct}%")
            lines.append(f"- **Доказательства**: {p.get('evidence_count', 0)} цепочек")
            lines.append(f"- **Контрпримеры**: {p.get('counter_evidence_count', 0)} цепочек")
            if p.get("description"):
                lines.append(f"- {p['description']}")
            lines.append("")

    report_text = "\n".join(lines)
    report_path = dest / f"patterns_{now_str}.md"
    report_path.write_text(report_text, encoding="utf-8")
    logger.info("Pattern report saved → %s", report_path)
    return report_path


# ── CLI ───────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="HEKTO Pattern Engine")
    parser.add_argument("--db", type=Path, default=None, help="Override DB path")
    parser.add_argument("--output-dir", type=Path, default=PATTERNS_DIR, help="Report output directory")
    args = parser.parse_args()

    patterns = run_pattern_analysis(db_path=args.db)
    if patterns:
        report_path = generate_pattern_report(patterns, output_dir=args.output_dir)
        print(f"✅ {len(patterns)} паттернов найдено. Отчёт: {report_path}")
    else:
        print("ℹ️ Паттернов не обнаружено (недостаточно данных или нет значимых корреляций).")


if __name__ == "__main__":
    main()
