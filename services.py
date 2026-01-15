# services.py
from __future__ import annotations

import pandas as pd

ENTRY_COLS = ["id", "date", "exercise", "weight", "reps", "sets", "volume", "note", "created_at"]


def rows_to_df(rows: list[tuple], columns: list[str] = ENTRY_COLS) -> pd.DataFrame:
    """DBのfetch結果（rows: list[tuple]）をDataFrameにする"""
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def volume_total(df: pd.DataFrame) -> float:
    """合計ボリューム"""
    if df.empty or "volume" not in df.columns:
        return 0.0
    return float(df["volume"].sum())


def volume_by_exercise(df: pd.DataFrame) -> pd.DataFrame:
    """種目別の合計ボリューム（降順）"""
    if df.empty:
        return pd.DataFrame(columns=["exercise", "volume"])
    out = (
        df.groupby("exercise", as_index=False)["volume"]
        .sum()
        .sort_values("volume", ascending=False)
        .copy()
    )
    out["volume"] = out["volume"].round(0).astype(int)
    return out


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
    if df.empty:
        return pd.DataFrame(columns=["body_part", "volume"])
    out = (
        df.groupby("body_part", as_index=False)["volume"]
        .sum()
        .sort_values("volume", ascending=False)
        .copy()
    )
    out["volume"] = out["volume"].round(0).astype(int)
    return out
