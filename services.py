# services.py
from __future__ import annotations

import pandas as pd
from collections import Counter
from datetime import date as _date, timedelta
from typing import Any, Dict, List, Tuple


ENTRY_COLS = ["id", "date", "exercise", "weight", "reps", "sets", "volume", "note", "created_at"]


def rows_to_df(rows: list[Any], columns: list[str] = ENTRY_COLS) -> pd.DataFrame:
    """DBのfetch結果（rows: list[sqlite3.Row] | list[dict]）をDataFrameにする"""
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([dict(r) for r in rows], columns=columns)


def volume_total(df: pd.DataFrame) -> float:
    """合計ボリューム"""
    if df.empty or "volume" not in df.columns:
        return 0.0
    return float(df["volume"].sum())


def _aggregate_volume_by_col(df: pd.DataFrame, col_name: str) -> pd.DataFrame:
    """指定カラムでグループ化してボリューム合計を算出する共通関数"""
    if df.empty:
        return pd.DataFrame(columns=[col_name, "volume"])
    out = (
        df.groupby(col_name, as_index=False)["volume"]
        .sum()
        .sort_values("volume", ascending=False)
        .copy()
    )
    out["volume"] = out["volume"].round(0).astype(int)
    return out

def volume_by_exercise(df: pd.DataFrame) -> pd.DataFrame:
    """種目別の合計ボリューム（降順）"""
    return _aggregate_volume_by_col(df, "exercise")

def daily_volume(df_range: pd.DataFrame, all_days: list[str]) -> pd.DataFrame:
    """日別の合計ボリューム（0埋め）"""
    if df_range.empty:
        return pd.DataFrame({"date": all_days, "volume": [0 for _ in all_days]})

    d = (
        df_range.groupby("date", as_index=False)["volume"]
        .sum()
        .sort_values("date")
        .copy()
    )
    out = pd.DataFrame({"date": all_days}).merge(d, on="date", how="left")
    out["volume"] = out["volume"].fillna(0).round(0).astype(int)
    return out


def today_grouped(df_today: pd.DataFrame) -> list[tuple[str, pd.DataFrame, float]]:
    """本日の記録を種目ごとにまとめて、表示用DataFrameと合計を返す"""
    if df_today.empty:
        return []

    grouped: list[tuple[str, pd.DataFrame, float]] = []
    for ex, g in df_today.groupby("exercise", sort=False):
        g2 = g.copy()
        g2["volume"] = g2["volume"].round(0).astype(int)
        show_df = g2[["id", "weight", "reps", "sets", "volume", "note"]]
        grouped.append((ex, show_df, float(g2["volume"].sum())))
    return grouped


def day_detail(df_range: pd.DataFrame, selected_date: str) -> pd.DataFrame:
    """週/期間タブで選んだ日の詳細（表示用）"""
    if df_range.empty:
        return pd.DataFrame(columns=["id", "exercise", "weight", "reps", "sets", "volume", "note"])

    day_df = df_range[df_range["date"] == selected_date].copy()
    if day_df.empty:
        return pd.DataFrame(columns=["id", "exercise", "weight", "reps", "sets", "volume", "note"])

    day_df["volume"] = day_df["volume"].round(0).astype(int)
    return day_df[["id", "exercise", "weight", "reps", "sets", "volume", "note"]]


def add_body_part(df: pd.DataFrame, exercise_to_body_part: dict[str, str]) -> pd.DataFrame:
    """種目→部位を付与（未知は '未分類'）"""
    out = df.copy()
    if out.empty:
        out["body_part"] = []
        return out
    out["body_part"] = out["exercise"].map(exercise_to_body_part).fillna("未分類")
    return out


def volume_by_body_part(df: pd.DataFrame) -> pd.DataFrame:
    """部位別の合計ボリューム（降順）"""
    return _aggregate_volume_by_col(df, "body_part")

def top_templates(rows, top_k: int = 3) -> list[dict]:
    """
    rows: Row or dict で
      date, weight, reps, sets, note を持つ想定
    """
    if not rows:
        return []

    combos = []
    for r in rows:
        w = r["weight"]
        reps = r["reps"]
        sets = r["sets"]
        combos.append((w, reps, sets))

    counter = Counter(combos)

    return [
        {"weight": w, "reps": reps, "sets": sets, "freq": freq}
        for (w, reps, sets), freq in counter.most_common(top_k)
    ]

def week_range_sunday(d: date) -> Tuple[str, str]:
    """指定日を含む週（日〜土）の start, end を ISOフォーマット文字列で返す"""
    start = d - timedelta(days=(d.weekday() + 1) % 7)
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()
def weekly_volume_by_body_part(rows, exercise_to_body_part: dict[str, str]):
    df = rows_to_df(rows)
    if df.empty:
        return {}

    df = add_body_part(df, exercise_to_body_part)
    out = volume_by_body_part(df)

    return dict(zip(out["body_part"], out["volume"]))

def day_summary(rows: List[Tuple[Any, ...]], exercise_to_body_part: Dict[str, str]) -> Dict[str, Any]:
    """
    rows: DBから取ったエントリ行のリスト（fetch_entries系の戻り値）
    return: { "total_volume": int, "by_body_part": [{body_part, volume}, ...] }
    """
    if not rows:
        return {"total_volume": 0, "by_body_part": []}

    df = rows_to_df(rows)
    df = add_body_part(df, exercise_to_body_part)

    total = volume_total(df)
    by_part_df = volume_by_body_part(df)

    return {
        "total_volume": int(total),
        "by_body_part": by_part_df.to_dict(orient="records"),
    }

def get_date_range_list(start_iso: str, end_iso: str) -> List[str]:
    """開始日〜終了日（ISO文字列）の全日付リストを返す"""
    s = date.fromisoformat(start_iso)
    e = date.fromisoformat(end_iso)
    days = []
    curr = s
    while curr <= e:
        days.append(curr.isoformat())
        curr += timedelta(days=1)
    return days