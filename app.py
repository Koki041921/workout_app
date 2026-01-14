# app.py
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st  # type: ignore

DB_PATH = "workout.db"

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


# ====================
# DB
# ====================
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workout_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                exercise TEXT NOT NULL,
                weight REAL NOT NULL,
                reps INTEGER NOT NULL,
                sets INTEGER NOT NULL,
                volume REAL NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def insert_entry(d, exercise, weight, reps, sets, note):
    volume = float(weight) * int(reps) * int(sets)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workout_entries(date, exercise, weight, reps, sets, volume, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (d, exercise, weight, reps, sets, volume, note, now),
        )
        conn.commit()


def delete_entry(entry_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM workout_entries WHERE id = ?", (entry_id,))
        conn.commit()


def fetch_by_date(d):
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, date, exercise, weight, reps, sets, volume, note, created_at
            FROM workout_entries
            WHERE date = ?
            ORDER BY created_at DESC
            """,
            (d,),
        )
        return cur.fetchall()


def fetch_week(start_date, end_date):
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, date, exercise, weight, reps, sets, volume, note, created_at
            FROM workout_entries
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, created_at DESC
            """,
            (start_date, end_date),
        )
        return cur.fetchall()


def fetch_last_for_exercise(exercise: str):
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT date, weight, reps, sets, note
            FROM workout_entries
            WHERE exercise = ?
            ORDER BY date DESC, created_at DESC
            LIMIT 1
            """,
            (exercise,),
        )
        return cur.fetchone()


def fetch_last_day_entries_for_exercise(exercise: str):
    """
    その種目について、直近の「日付」を特定し、
    その日の同種目の全行（= セット構成）を返す
    """
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT date FROM workout_entries WHERE exercise = ? ORDER BY date DESC LIMIT 1",
            (exercise,),
        )
        row = cur.fetchone()
        if not row:
            return []

        last_date = row[0]

        cur2 = conn.execute(
            """
            SELECT weight, reps, sets, note
            FROM workout_entries
            WHERE exercise = ? AND date = ?
            ORDER BY created_at ASC
            """,
            (exercise, last_date),
        )
        rows = cur2.fetchall()

    return [
        {"date": last_date, "weight": r[0], "reps": r[1], "sets": r[2], "note": r[3] or ""}
        for r in rows
    ]


# ====================
# App
# ====================
init_db()

st.set_page_config(page_title="筋トレボリューム管理", layout="wide")
st.title("筋トレボリューム管理（PC版MVP）")

tabs = st.tabs(["入力", "本日の記録", "週集計"])

# --------------------
# 入力タブ
# --------------------
with tabs[0]:
    st.subheader("入力（セットビルダー）")

    # 1) 種目選択
    workout_date = st.date_input("日付", value=date.today(), key="input_date")
    exercise = st.selectbox("種目", EXERCISES_DEFAULT, key="input_exercise")

    # 2) セットビルダーの状態（種目ごとに一時保持）
    draft_key = f"draft_sets::{workout_date.isoformat()}::{exercise}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = []  # list[dict]

    draft_sets = st.session_state[draft_key]

    # 3) 前回セット（小さく表示）＋丸ごとコピー
    last_sets = fetch_last_day_entries_for_exercise(exercise)
    last = fetch_last_for_exercise(exercise)

    if last_sets:
        last_date = last_sets[0]["date"]
        with st.expander("前回セット（参考）", expanded=False):
            lines = [f"{s['weight']}kg×{s['reps']}×{s['sets']}" for s in last_sets]
            st.caption(f"{last_date}： " + " / ".join(lines))

            if st.button("前回セットを全部コピー", key=f"copy_last_{draft_key}"):
                st.session_state[draft_key] = [
                    {
                        "weight": float(s["weight"]),
                        "reps": int(s["reps"]),
                        "sets": int(s["sets"]),
                        "note": s["note"],
                    }
                    for s in last_sets
                ]
                st.success("コピーしました。")
                st.rerun()
    else:
        st.caption("この種目の過去記録がないので、コピーはできません。")

    # 4) 候補（プリセット）
    base_w = float(last[1]) if last else 60.0
    weight_options = [max(0, base_w + 2.5 * i) for i in [-3, -2, -1, 0, 1, 2, 3]]
    reps_options = [5, 6, 8, 10, 12, 15]
    sets_options = [1, 2, 3, 4, 5]

    st.write("### セットを追加（選んでポン）")
    c1, c2, c3 = st.columns(3)

    with c1:
        weight = st.selectbox("重量(kg)", weight_options, index=3, key="sb_weight")
        custom_weight = st.text_input("任意重量（空でOK）", value="", key="sb_custom_weight")

    with c2:
        reps = st.selectbox("回数", reps_options, index=3, key="sb_reps")

    with c3:
        sets = st.selectbox("セット数", sets_options, index=2, key="sb_sets")

    note = st.text_input("メモ（任意）", value="", key="sb_note")

    # 任意重量が入ってたら優先
    try:
        w_final = float(custom_weight) if custom_weight.strip() != "" else float(weight)
    except ValueError:
        w_final = float(weight)

    if st.button("このセット構成を追加"):
        if w_final <= 0 or reps <= 0 or sets <= 0:
            st.error("重量・回数・セット数は1以上で入力してください。")
        else:
            draft_sets.append({"weight": w_final, "reps": int(reps), "sets": int(sets), "note": note})
            st.session_state[draft_key] = draft_sets
            st.success("追加しました。")

    st.divider()

    # 5) 追加済みのセット一覧（この種目）
    st.write("### 追加済みセット（この種目）")
    if not draft_sets:
        st.info("まだ追加されていません。上で追加してください。")
    else:
        df = pd.DataFrame(draft_sets)
        df["volume"] = (df["weight"] * df["reps"] * df["sets"]).round(0).astype(int)

        st.dataframe(df[["weight", "reps", "sets", "volume", "note"]], use_container_width=True)

        ex_total = int(df["volume"].sum())
        st.metric("この種目の合計ボリューム", f"{ex_total}")

        c1, c2, c3 = st.columns([1, 1, 2])

        with c1:
            if st.button("直前の追加を取り消す"):
                if draft_sets:
                    draft_sets.pop()
                    st.session_state[draft_key] = draft_sets
                st.rerun()

        with c2:
            if st.button("この種目の追加を全クリア"):
                st.session_state[draft_key] = []
                st.rerun()

        with c3:
            if st.button("この種目をまとめて保存"):
                for s in draft_sets:
                    insert_entry(
                        workout_date.isoformat(),
                        exercise,
                        s["weight"],
                        s["reps"],
                        s["sets"],
                        s.get("note", ""),
                    )
                st.success("保存しました。")
                st.session_state[draft_key] = []
                st.rerun()

# --------------------
# 本日の記録タブ
# --------------------
with tabs[1]:
    st.subheader("本日の記録")

    today = date.today().isoformat()
    rows = fetch_by_date(today)

    if not rows:
        st.info("本日の記録はまだありません。")
    else:
        df = pd.DataFrame(
            rows,
            columns=["id", "date", "exercise", "weight", "reps", "sets", "volume", "note", "created_at"],
        )

        st.metric("本日の総ボリューム", f"{df['volume'].sum():.0f}")

        st.write("### 種目別")
        for ex, g in df.groupby("exercise", sort=False):
            ex_total = g["volume"].sum()
            with st.expander(f"{ex}（合計 {ex_total:.0f}）", expanded=True):
                show = g[["id", "weight", "reps", "sets", "volume", "note"]].copy()
                show["volume"] = show["volume"].round(0).astype(int)
                st.dataframe(show, use_container_width=True)

        st.write("### 削除")
        delete_id = st.number_input("削除したいID", min_value=0, value=0, step=1, key="today_delete_id")
        if st.button("このIDを削除（本日の記録から）"):
            if delete_id <= 0:
                st.error("IDを正しく入力してください。")
            else:
                delete_entry(int(delete_id))
                st.success("削除しました。")
                st.rerun()

# --------------------
# 週集計タブ
# --------------------
with tabs[2]:
    st.subheader("週集計（期間ビュー）")

    start_end = st.date_input(
        "期間を選ぶ（開始日〜終了日）",
        value=(date.today() - timedelta(days=6), date.today()),
        key="range_weekly",
    )

    if isinstance(start_end, tuple) and len(start_end) == 2:
        start_date, end_date = start_end
    else:
        start_date, end_date = start_end, start_end

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    start = start_date.isoformat()
    end = end_date.isoformat()

    rows = fetch_week(start, end)

    if not rows:
        st.info(f"{start} 〜 {end} の記録はありません。")
    else:
        df = pd.DataFrame(
            rows,
            columns=["id", "date", "exercise", "weight", "reps", "sets", "volume", "note", "created_at"],
        )

        daily = df.groupby("date", as_index=False)["volume"].sum().sort_values("date")
        all_days = pd.date_range(start=start, end=end, freq="D").strftime("%Y-%m-%d")
        daily_full = (
            pd.DataFrame({"date": all_days})
            .merge(daily, on="date", how="left")
            .fillna({"volume": 0})
        )

        st.metric("期間合計ボリューム", f"{daily_full['volume'].sum():.0f}")

        st.write("### 日別ボリューム（棒グラフ）")
        st.bar_chart(daily_full.set_index("date")[["volume"]])

        st.write("### 種目別ランキング（期間合計）")
        by_ex = (
            df.groupby("exercise", as_index=False)["volume"]
            .sum()
            .sort_values("volume", ascending=False)
        )
        by_ex["volume"] = by_ex["volume"].round(0).astype(int)
        st.dataframe(by_ex, use_container_width=True)

        st.write("### 日別の詳細（選んだ日だけ）")
        selected_date = st.selectbox("日付", daily_full["date"].tolist(), key="weekly_pick_date")
        day_df = df[df["date"] == selected_date].copy()
        day_df["volume"] = day_df["volume"].round(0).astype(int)
        st.dataframe(day_df[["id", "exercise", "weight", "reps", "sets", "volume", "note"]], use_container_width=True)
