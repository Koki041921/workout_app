# api.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_db  # app.pyでも使ってたやつ
from db import (
    fetch_by_date,
    insert_entry,
    update_entry,
    delete_entry,
    fetch_range,
    fetch_last_for_exercise,
    fetch_last_day_entries_for_exercise,
    fetch_recent_entries_for_exercise,
)
from services import (
    rows_to_df, 
    top_templates,
    weekly_volume_by_body_part,
    week_range_sunday,
    day_summary,
    daily_volume,
    add_body_part,
    volume_by_exercise,
    volume_by_body_part,
    get_date_range_list,
)
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import date as _date, timedelta
from fastapi import HTTPException
import pandas as pd


# app.pyから「定数だけ」持ってくる（UIではなくデータなので）
EXERCISES_DEFAULT = [
    "ベンチプレス",
    "ダンベルプレス",
    "インクラインダンベルプレス",
    "懸垂",
    "ラットプルダウン",
    "ベントオーバーロウ",
    "ショルダープレス",
    "サイドプレス",
]

EXERCISE_TO_BODY_PART = {
    "ベンチプレス": "胸",
    "ダンベルプレス": "胸",
    "インクラインダンベルプレス": "胸",
    "懸垂": "背中",
    "ラットプルダウン": "背中",
    "ベントオーバーロウ": "背中",
    "ショルダープレス": "肩",
    "サイドプレス": "肩",
}

BODY_PARTS = ["胸", "背中", "肩", "脚", "腕", "体幹"]

DUMBBELL_EXERCISES = {
    "ダンベルプレス",
    "ダンベルフライ",
    "ダンベルカール",
    "ダンベルショルダープレス",
    "ワンハンドロー",
    "サイドレイズ",
    "ショルダープレス",
}

BARBELL_EXERCISES = {
    "ベンチプレス",
    "ベントオーバーロウ",
    "スクワット",
    "デッドリフト",
}

app = FastAPI(title="workout-api")
class EntryIn(BaseModel):
    date: str
    exercise: str
    weight: float
    reps: int
    sets: int
    note: Optional[str] = ""
class EntryUpdate(BaseModel):
    weight: float
    reps: int
    sets: int
    note: Optional[str] = ""
class ExercisesResponse(BaseModel):
    exercises: List[str]


class BodyPartsResponse(BaseModel):
    body_parts: List[str]


class ExerciseToBodyPartResponse(BaseModel):
    exercise_to_body_part: Dict[str, str]
class ExerciseTypesResponse(BaseModel):
    dumbbell: List[str]
    barbell: List[str]
class EntryOut(BaseModel):
    id: int
    date: str
    exercise: str
    weight: float
    reps: int
    sets: int
    volume: float
    note: Optional[str] = ""
    created_at: str


class EntriesResponse(BaseModel):
    entries: List[EntryOut]
class LastEntryResponse(BaseModel):
    date: str
    weight: float
    reps: int
    sets: int
    note: Optional[str] = ""
class LastDaySet(BaseModel):
    date: str
    weight: float
    reps: int
    sets: int
    note: Optional[str] = ""


class LastDaySetsResponse(BaseModel):
    sets: List[LastDaySet]
class TemplateItem(BaseModel):
    weight: float
    reps: int
    sets: int
    freq: int


class TemplatesResponse(BaseModel):
    templates: List[TemplateItem]

class WeeklyPart(BaseModel):
    body_part: str
    this: int
    last: int
    diff: int
    ratio: float


class WeeklyProgressResponse(BaseModel):
    week: dict
    parts: list[WeeklyPart]

class InputContextResponse(BaseModel):
    exercise: str
    date: str
    last: Optional[LastEntryResponse] = None
    last_day_sets: LastDaySetsResponse
    templates: TemplatesResponse
    weekly: WeeklyProgressResponse
    day_summary: dict  # day_summaryは既存関数がdict返すので一旦これでOK
class DraftSet(BaseModel):
    exercise: str
    weight: float
    reps: int
    sets: int

class WeeklyPreviewRequest(BaseModel):
    date: Optional[str] = None
    draft_sets: list[DraftSet] = []

class WeeklyPreviewPart(BaseModel):
    body_part: str
    this_base: int
    added: int
    this_projected: int
    last: int
    diff_vs_last: int
    ratio_vs_last: float
    remaining_to_last: int

class WeeklyPreviewResponse(BaseModel):
    week: dict
    parts: list[WeeklyPreviewPart]




# Next.js(3000) → FastAPI(8000) をブラウザから叩けるようにする（CORS）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup() -> None:
    # app.pyの init_db() を「サーバ起動時」に一回だけ実行する形にする
    init_db()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/entries")
def get_entries(date: str):
    rows = fetch_by_date(date)
    df = rows_to_df(rows) if rows else rows_to_df([])
    return df.to_dict(orient="records")

@app.post("/api/entries")
def create_entry(entry: EntryIn):
    insert_entry(
        entry.date,
        entry.exercise,
        entry.weight,
        entry.reps,
        entry.sets,
        entry.note or "",
    )
    return {"ok": True}
@app.put("/api/entries/{entry_id}")
def update_entry_api(entry_id: int, entry: EntryUpdate):
    update_entry(
        entry_id,
        entry.weight,
        entry.reps,
        entry.sets,
        entry.note or "",
    )
    return {"ok": True}
@app.delete("/api/entries/{entry_id}")
def delete_entry_api(entry_id: int):
    delete_entry(entry_id)
    return {"ok": True}

@app.get("/api/meta/exercises", response_model=ExercisesResponse)
def get_exercises():
    return {"exercises": EXERCISES_DEFAULT}


@app.get("/api/meta/body-parts", response_model=BodyPartsResponse)
def get_body_parts():
    return {"body_parts": BODY_PARTS}

@app.get("/api/meta/exercise-to-body-part", response_model=ExerciseToBodyPartResponse)
def get_exercise_to_body_part():
    ordered = dict(sorted(EXERCISE_TO_BODY_PART.items(), key=lambda x: x[0]))
    return {"exercise_to_body_part": ordered}

@app.get("/api/meta/exercise-types", response_model=ExerciseTypesResponse)
def get_exercise_types():
    return {
        "dumbbell": list(DUMBBELL_EXERCISES),
        "barbell": list(BARBELL_EXERCISES),
    }

@app.get("/api/entries/range", response_model=EntriesResponse)
def get_entries_range(start: str, end: str):
    rows = fetch_range(start, end)
    df = rows_to_df(rows)
    # DataFrame -> list[dict] に変換
    entries = df.to_dict(orient="records")
    # noteがNoneなら""に寄せる（フロント側の扱いを簡単にする）
    for e in entries:
        if e.get("note") is None:
            e["note"] = ""
    return {"entries": entries}

@app.get(
    "/api/exercises/{exercise}/last",
    response_model=Optional[LastEntryResponse]
)
def get_last_entry(exercise: str):
    exercise = exercise.strip()
    row = fetch_last_for_exercise(exercise)
    if not row:
        return None

    return {
        "date": row["date"],
        "weight": row["weight"],
        "reps": row["reps"],
        "sets": row["sets"],
        "note": row["note"] or "",
    }


@app.get(
    "/api/exercises/{exercise}/last-day-sets",
    response_model=LastDaySetsResponse
)
def get_last_day_sets(exercise: str):
    rows = fetch_last_day_entries_for_exercise(exercise)
    # rowsは既に List[Dict] 形式で、キーも一致しているためそのまま返す
    return {"sets": rows}

@app.get(
    "/api/exercises/{exercise}/templates",
    response_model=TemplatesResponse
)
def get_templates(
    exercise: str,
    limit: int = 300,
    top: int = 3,
):
    rows = fetch_recent_entries_for_exercise(exercise, limit)
    templates = top_templates(rows, top_k=top)
    return {"templates": templates}

@app.get("/api/exercises/{exercise}/recent")
def get_recent_entries_for_exercise(exercise: str, limit: int = 50):
    exercise = exercise.strip()
    rows = fetch_recent_entries_for_exercise(exercise, limit)

    out = []
    for r in rows:
        out.append({
            "date": r["date"],
            "weight": r["weight"],
            "reps": r["reps"],
            "sets": r["sets"],
            "note": r.get("note", ""),
        })

    return {
        "exercise": exercise,
        "entries": out,
    }



@app.get("/api/progress/weekly", response_model=WeeklyProgressResponse)
def weekly_progress(date: Optional[str] = None):
    base = _date.fromisoformat(date) if date else _date.today()

    this_start, this_end = week_range_sunday(base)
    last_start, last_end = week_range_sunday(base - timedelta(days=7))

    this_rows = fetch_range(this_start, this_end)
    last_rows = fetch_range(last_start, last_end)

    this_map = weekly_volume_by_body_part(this_rows, EXERCISE_TO_BODY_PART)
    last_map = weekly_volume_by_body_part(last_rows, EXERCISE_TO_BODY_PART)

    parts = []
    all_parts = set(this_map) | set(last_map)

    for p in sorted(all_parts):
        t = this_map.get(p, 0)
        l = last_map.get(p, 0)
        diff = t - l
        ratio = round(t / l, 2) if l > 0 else (1.0 if t > 0 else 0.0)

        parts.append({
            "body_part": p,
            "this": t,
            "last": l,
            "diff": diff,
            "ratio": ratio,
        })

    return {
        "week": {"start": this_start, "end": this_end},
        "parts": parts,
    }

@app.get("/api/days/{date}/summary")
def get_day_summary(date: str):
    rows = fetch_by_date(date)
    return day_summary(rows, EXERCISE_TO_BODY_PART)

@app.get("/api/analytics/range/daily")
def analytics_range_daily(
    start: str,
    end: str,
    body_part: Optional[str] = None,
):
    # 1) DBから範囲取得
    rows = fetch_range(start, end)

    # 2) DF化
    df = rows_to_df(rows)

    # 3) 部位で絞りたい場合は、部位列を付けてから絞る
    if body_part:
        df = add_body_part(df, EXERCISE_TO_BODY_PART)
        df = df[df["body_part"] == body_part]

    # 4) 0埋め日付配列を作る（start〜endを全部）
    all_days = get_date_range_list(start, end)

    # 5) 日別ボリューム（0埋め）を作る
    out_df = daily_volume(df, all_days)  # services.pyにある

    return {"daily": out_df.to_dict(orient="records")}

@app.get("/api/analytics/range/summary")
def analytics_range_summary(
    start: str,
    end: str,
    body_part: Optional[str] = None,
):
    rows = fetch_range(start, end)
    df = rows_to_df(rows)

    if body_part:
        df = add_body_part(df, EXERCISE_TO_BODY_PART)
        df = df[df["body_part"] == body_part]

    # dailyと同じ all_days を作る（統一する）
    all_days = get_date_range_list(start, end)

    daily_df = daily_volume(df, all_days)

    total = int(daily_df["volume"].sum())
    avg = float(daily_df["volume"].mean()) if len(daily_df) else 0.0

    max_idx = int(daily_df["volume"].idxmax()) if len(daily_df) else None
    max_day = daily_df.loc[max_idx, "date"] if max_idx is not None else None
    max_vol = int(daily_df.loc[max_idx, "volume"]) if max_idx is not None else 0

    zero_days = int((daily_df["volume"] == 0).sum()) if len(daily_df) else 0

    return {
        "start": start,
        "end": end,
        "body_part": body_part,
        "total_volume": total,
        "avg_daily_volume": avg,
        "max_day": max_day,
        "max_day_volume": max_vol,
        "zero_days": zero_days,
    }

@app.get("/api/analytics/range/exercise/daily")
def analytics_exercise_daily(
    start: str,
    end: str,
    exercise: str,
):
    # 1) DBから範囲取得
    rows = fetch_range(start, end)
    df = rows_to_df(rows)

    # 2) 種目でフィルタ
    df = df[df["exercise"] == exercise]

    # 3) all_days を作る（StepBと同じ型）
    all_days = get_date_range_list(start, end)

    # 4) 日別推移（0埋め）
    out_df = daily_volume(df, all_days)

    return {
        "exercise": exercise,
        "start": start,
        "end": end,
        "daily": out_df.to_dict(orient="records"),
    }
@app.get("/api/analytics/range/exercise/day-detail")
def analytics_exercise_day_detail(
    date: str,
    exercise: str,
):
    rows = fetch_by_date(date)
    df = rows_to_df(rows)

    df = df[df["exercise"] == exercise].copy()

    # 返す列を絞る（フロントが扱いやすい）
    cols = ["id", "date", "exercise", "weight", "reps", "sets", "volume", "note", "created_at"]
    df = df[cols] if all(c in df.columns for c in cols) else df

    return {
        "date": date,
        "exercise": exercise,
        "sets": df.to_dict(orient="records"),
    }




@app.get("/api/analytics/range/rank/exercises")
def analytics_rank_exercises(
    start: str,
    end: str,
    body_part: Optional[str] = None,
    q: Optional[str] = None,
    top_n: int = 20,
):
    # 1) 期間取得
    rows = fetch_range(start, end)
    df = rows_to_df(rows)

    # 2) 部位フィルタ（あれば）
    if body_part:
        df = add_body_part(df, EXERCISE_TO_BODY_PART)
        df = df[df["body_part"] == body_part]

    # 3) 種目別に合計
    rank_df = volume_by_exercise(df)

    # 4) 検索（部分一致）
    if q:
        q = q.strip()
        rank_df = rank_df[rank_df["exercise"].astype(str).str.contains(q)]

    # 5) 上位N
    rank_df = rank_df.head(top_n)

    return {
        "start": start,
        "end": end,
        "body_part": body_part,
        "rank": rank_df.to_dict(orient="records"),
    }
@app.get("/api/analytics/range/rank/body-parts")
def analytics_rank_body_parts(start: str, end: str):
    rows = fetch_range(start, end)
    df = rows_to_df(rows)
    df = add_body_part(df, EXERCISE_TO_BODY_PART)
    rank_df = volume_by_body_part(df)

    return {
        "start": start,
        "end": end,
        "rank": rank_df.to_dict(orient="records"),
    }

@app.get("/api/input/context", response_model=InputContextResponse)
def get_input_context(date: str, exercise: str):
    exercise = exercise.strip()

    # 1) last
    last_row = fetch_last_for_exercise(exercise)
    last = None
    if last_row:
        last = {
            "date": last_row["date"],
            "weight": last_row["weight"],
            "reps": last_row["reps"],
            "sets": last_row["sets"],
            "note": last_row["note"] or "",
        }

    # 2) last-day-sets
    lds_rows = fetch_last_day_entries_for_exercise(exercise)
    lds = {
        "sets": [
            {
                "date": r["date"],
                "weight": r["weight"],
                "reps": r["reps"],
                "sets": r["sets"],
                "note": r["note"] or "",
            }
            for r in lds_rows
        ]
    }

    # 3) templates（recentから算出）
    recent_rows = fetch_recent_entries_for_exercise(exercise, limit=300)
    templates = {"templates": top_templates(recent_rows, top_k=3)}

    # 4) weekly（既存関数を再利用）
    weekly = weekly_progress(date)

    # 5) day summary（その日の全種目→部位集計）
    rows = fetch_by_date(date)
    summary = day_summary(rows, EXERCISE_TO_BODY_PART)

    return {
        "exercise": exercise,
        "date": date,
        "last": last,
        "last_day_sets": lds,
        "templates": templates,
        "weekly": weekly,
        "day_summary": summary,
    }

@app.get("/api/analytics/range/insights")
def analytics_range_insights(start: str, end: str):
    rows_range = fetch_range(start, end)
    df_range = rows_to_df(rows_range)

    if df_range.empty:
        return {"start": start, "end": end, "lines": []}

    # all_days 作成（app.pyと同じ）:contentReference[oaicite:3]{index=3}
    s = _date.fromisoformat(start)
    e = _date.fromisoformat(end)
    all_days = []
    d = s
    while d <= e:
        all_days.append(d.isoformat())
        d += timedelta(days=1)

    # ここから app.py のインサイトロジックを “API用に” 再現
    dfp_all = df_range.copy()
    dfp_all["body_part"] = dfp_all["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")

    lines: list[str] = []

    # 1) 部位の最小 :contentReference[oaicite:4]{index=4}
    part_sum = dfp_all.groupby("body_part", as_index=False)["volume"].sum()
    part_sum["volume"] = part_sum["volume"].fillna(0.0)
    known = part_sum[part_sum["body_part"].isin(BODY_PARTS)].copy()
    target_part_sum = known if not known.empty else part_sum
    if not target_part_sum.empty:
        min_row = target_part_sum.sort_values("volume", ascending=True).iloc[0]
        lines.append(f"この期間、{min_row['body_part']}のボリュームが最小です")

    # 2) 前回同期間比 :contentReference[oaicite:5]{index=5}
    period_days = (e - s).days + 1
    prev_start = s - timedelta(days=period_days)
    prev_end = e - timedelta(days=period_days)

    prev_rows = fetch_range(prev_start.isoformat(), prev_end.isoformat())
    if prev_rows:
        df_prev = rows_to_df(prev_rows)
        if not df_prev.empty:
            df_prev["body_part"] = df_prev["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")

            prev_part = df_prev.groupby("body_part", as_index=False)["volume"].sum()
            cur_part = dfp_all.groupby("body_part", as_index=False)["volume"].sum()

            merged = cur_part.merge(
                prev_part, on="body_part", how="outer", suffixes=("_cur", "_prev")
            ).fillna(0.0)

            merged = merged[merged["volume_prev"] > 0].copy()
            if not merged.empty:
                merged["pct"] = (merged["volume_cur"] - merged["volume_prev"]) / merged["volume_prev"] * 100.0
                best = merged.sort_values("pct", ascending=False).iloc[0]
                sign = "+" if float(best["pct"]) >= 0 else ""
                lines.append(f"前回の同期間より、{best['body_part']}が {sign}{best['pct']:.0f}% 変化しています")

    # 3) 記録ゼロ日（連続優先）:contentReference[oaicite:6]{index=6}
    daily = (
        dfp_all.groupby("date", as_index=False)["volume"]
        .sum()
        .sort_values("date")
        .copy()
    )
    daily_full = pd.DataFrame({"date": all_days}).merge(daily, on="date", how="left")
    daily_full["volume"] = daily_full["volume"].fillna(0).round(0).astype(int)

    vols = daily_full["volume"].astype(float).tolist()
    zero_count = int(sum(1 for v in vols if v == 0))
    max_streak = 0
    cur_streak = 0
    for v in vols:
        if v == 0:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0

    if max_streak >= 2:
        lines.append(f"記録ゼロ日が {max_streak}日 連続しています")
    elif zero_count > 0:
        lines.append(f"記録ゼロ日が {zero_count}日 あります")

    return {"start": start, "end": end, "lines": lines[:3]}
@app.post("/api/progress/weekly/preview", response_model=WeeklyPreviewResponse)
def weekly_progress_preview(req: WeeklyPreviewRequest):
    base_date = _date.fromisoformat(req.date) if req.date else _date.today()

    # 1) 週範囲（既存 weekly_progress と同じ）
    this_start, this_end = week_range_sunday(base_date)
    last_start, last_end = week_range_sunday(base_date - timedelta(days=7))

    # 2) DBから今週/先週の実績
    this_rows = fetch_range(this_start, this_end)
    last_rows = fetch_range(last_start, last_end)

    this_map = weekly_volume_by_body_part(this_rows, EXERCISE_TO_BODY_PART)  # base
    last_map = weekly_volume_by_body_part(last_rows, EXERCISE_TO_BODY_PART)

    # 3) 入力中セット（draft）を部位別に加算
    added_map: dict[str, int] = {}
    for s in req.draft_sets:
        ex = s.exercise.strip()
        bp = EXERCISE_TO_BODY_PART.get(ex, "未分類")
        vol = int(round(float(s.weight) * int(s.reps) * int(s.sets), 0))
        added_map[bp] = added_map.get(bp, 0) + vol

    # 4) 部位一覧（base / last / added の和集合）
    all_parts = set(this_map) | set(last_map) | set(added_map)

    parts: list[dict] = []
    for p in sorted(all_parts):
        this_base = int(this_map.get(p, 0))
        added = int(added_map.get(p, 0))
        this_projected = this_base + added

        last = int(last_map.get(p, 0))
        diff = this_projected - last
        ratio = round(this_projected / last, 2) if last > 0 else (1.0 if this_projected > 0 else 0.0)

        remaining = max(last - this_projected, 0)

        parts.append({
            "body_part": p,
            "this_base": this_base,
            "added": added,
            "this_projected": this_projected,
            "last": last,
            "diff_vs_last": diff,
            "ratio_vs_last": ratio,
            "remaining_to_last": remaining,
        })

    return {
        "week": {"start": this_start, "end": this_end},
        "parts": parts,
    }
