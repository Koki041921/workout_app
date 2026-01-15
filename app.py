# app.py
from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st  # type: ignore

from db import (  # type: ignore
    init_db,
    insert_entry,
    delete_entry,
    update_entry,
    fetch_by_date,
    fetch_range,
    fetch_last_for_exercise,
    fetch_last_day_entries_for_exercise,
)

from services import (  # type: ignore
    rows_to_df,
    volume_total,
    today_grouped,
    add_body_part,
    volume_by_body_part,
)

# ====================
# Settings / Constants
# ====================
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

# 種目 → 部位（まずは主働筋だけに寄せる）
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

BODY_PARTS = ["胸", "背中", "肩", "脚", "腕", "体幹"]  # 将来拡張用

# ====================
# Helpers
# ====================


def ratio_vs_last(actual: int, last_actual: int) -> float | None:
    """先週比率（今週/先週）。先週0は None"""
    if last_actual <= 0:
        return None
    return actual / last_actual


def week_range_monday(d: date) -> tuple[date, date]:
    """今週（月〜日）"""
    start = d - timedelta(days=d.weekday())  # Monday
    end = start + timedelta(days=6)
    return start, end


@st.cache_data(show_spinner=False)
def week_part_volumes(start_iso: str, end_iso: str) -> dict[str, int]:
    """指定期間の部位別ボリュームを dict で返す"""
    rows = fetch_range(start_iso, end_iso)
    df = rows_to_df(rows)
    if df.empty:
        return {}
    dfp = add_body_part(df, EXERCISE_TO_BODY_PART)
    by_part = volume_by_body_part(dfp)
    return {str(r["body_part"]): int(r["volume"]) for _, r in by_part.iterrows()}


def get_part_volume(vol_map: dict[str, int], part: str) -> int:
    return int(vol_map.get(part, 0))


# ====================
# App init
# ====================
init_db()

st.set_page_config(page_title="筋トレボリューム管理", layout="wide")
st.title("筋トレボリューム管理（PC版MVP）")

# ====================
# Sidebar: Visible parts & weekly goals
# ====================
st.sidebar.header("表示する部位")
if "visible_parts" not in st.session_state:
    st.session_state.visible_parts = BODY_PARTS.copy()

visible_parts = st.sidebar.multiselect(
    "ダッシュボードに表示する部位",
    options=BODY_PARTS,
    default=st.session_state.visible_parts,
)
st.session_state.visible_parts = visible_parts

if not visible_parts:
    st.sidebar.warning("最低1つは選択してください（表示が空になります）")

st.sidebar.divider()


# 週レンジ（今週・先週）を一度決める
today_d = date.today()
this_ws, this_we = week_range_monday(today_d)
last_ws, last_we = this_ws - timedelta(days=7), this_we - timedelta(days=7)

this_week_vols = week_part_volumes(this_ws.isoformat(), this_we.isoformat())
last_week_vols = week_part_volumes(last_ws.isoformat(), last_we.isoformat())

tabs = st.tabs(["入力", "本日の記録", "週集計"])

# --------------------
# 入力タブ
# --------------------
with tabs[0]:
    st.subheader("記録（この日のワークアウト）")

    # 1) 日付・種目
    workout_date = st.date_input("日付", value=date.today(), key="input_date")
    exercise = st.selectbox("種目", EXERCISES_DEFAULT, key="input_exercise")

    # ---- 進捗（先週比）：選択中種目の部位
    selected_part = EXERCISE_TO_BODY_PART.get(exercise, "未分類")
    current_actual = get_part_volume(this_week_vols, selected_part)
    current_last = get_part_volume(last_week_vols, selected_part)
    r_now = ratio_vs_last(current_actual, current_last)

    box_l, box_r = st.columns([1.2, 3.8])
    with box_l:
        st.write("#### この種目の部位")
        st.info(selected_part)

    with box_r:
        st.write(f"#### 今週の進捗（先週比）（{this_ws.isoformat()}〜{this_we.isoformat()}）")
        c1, c2, c3 = st.columns([1.4, 1.4, 3.2])
        with c1:
            st.metric("今週", f"{current_actual}")
        with c2:
            st.metric("先週", f"{current_last}")
        with c3:
            if r_now is None:
                st.caption("先週が0なので先週比バーは非表示")
            else:
                st.progress(min(r_now, 1.0))
                st.caption(f"先週比 {r_now*100:.0f}%（先週=100%基準）")

    st.divider()

    # 2) 前回セット（参考・コピー用）
    last_sets = fetch_last_day_entries_for_exercise(exercise)
    last = fetch_last_for_exercise(exercise)

    if last_sets:
        last_date = last_sets[0]["date"]
        with st.expander("前回のセット（参考）", expanded=False):
            lines = [f"{s['weight']}kg×{s['reps']}×{s['sets']}" for s in last_sets]
            st.caption(f"{last_date}： " + " / ".join(lines))

            if st.button("前回セットを追加", key="btn_copy_last"):
                for s in last_sets:
                    insert_entry(
                        workout_date.isoformat(),
                        exercise,
                        s["weight"],
                        s["reps"],
                        s["sets"],
                        s.get("note", ""),
                    )
                st.success("前回セットを追加しました。")
                st.cache_data.clear()
                st.rerun()

    # 3) セット入力（即DB反映）
    base_w = float(last[1]) if last else 60.0
    weight_options = [max(0, base_w + 2.5 * i) for i in [-3, -2, -1, 0, 1, 2, 3]]

    st.write("### セットを追加")
    c1, c2, c3 = st.columns(3)

    with c1:
        weight = st.selectbox("重量(kg)", weight_options, index=3)
        custom_weight = st.text_input("任意重量（空でOK）")

    with c2:
        reps = st.number_input("回数", min_value=1, value=10)

    with c3:
        sets = st.number_input("セット数", min_value=1, value=3)

    note = st.text_input("メモ（任意）")

    # ---- Phase4相当：このセットを入れたら先週比がどう変わるか（予測）
    try:
        w_final_preview = float(custom_weight) if custom_weight.strip() else float(weight)
    except ValueError:
        w_final_preview = float(weight)

    this_volume_preview = int(round(w_final_preview * int(reps) * int(sets), 0))
    predicted_actual = current_actual + this_volume_preview
    r_pred = ratio_vs_last(predicted_actual, current_last)

    if current_last <= 0:
        st.caption(f"このセットの追加ボリューム：+{this_volume_preview}（先週が0のため先週比は計算不可）")
    else:
        st.caption(
            f"このセット（+{this_volume_preview}）を入れると：先週比 {r_pred*100:.0f}%（今週 {predicted_actual} / 先週 {current_last}）"
        )

    if st.button("このセットを記録"):
        insert_entry(
            workout_date.isoformat(),
            exercise,
            float(w_final_preview),
            int(reps),
            int(sets),
            note,
        )
        st.success("記録しました。")
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # 4) この日の記録（DB）を常時表示・編集
    st.subheader("この日の記録（編集・削除）")

    rows_day = fetch_by_date(workout_date.isoformat())
    if not rows_day:
        st.info("この日の記録はまだありません。")
    else:
        df_day = rows_to_df(rows_day)

        for ex2, g in df_day.groupby("exercise", sort=False):
            ex_total = float(g["volume"].sum())
            with st.expander(f"{ex2}（合計 {ex_total:.0f}）", expanded=False):
                for _, r in g.iterrows():
                    entry_id = int(r["id"])
                    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 2.5, 1.2])

                    with c1:
                        new_w = st.number_input(
                            "kg",
                            value=float(r["weight"]),
                            step=2.5,
                            key=f"edit_w_{entry_id}",
                        )
                    with c2:
                        new_reps = st.number_input(
                            "reps",
                            value=int(r["reps"]),
                            step=1,
                            key=f"edit_r_{entry_id}",
                        )
                    with c3:
                        new_sets = st.number_input(
                            "sets",
                            value=int(r["sets"]),
                            step=1,
                            key=f"edit_s_{entry_id}",
                        )
                    with c4:
                        new_note = st.text_input(
                            "note",
                            value=str(r["note"] or ""),
                            key=f"edit_n_{entry_id}",
                        )
                    with c5:
                        if st.button("更新", key=f"btn_up_{entry_id}"):
                            update_entry(entry_id, float(new_w), int(new_reps), int(new_sets), str(new_note))
                            st.success("更新しました。")
                            st.cache_data.clear()
                            st.rerun()

                        if st.button("削除", key=f"btn_del_{entry_id}"):
                            delete_entry(entry_id)
                            st.success("削除しました。")
                            st.cache_data.clear()
                            st.rerun()

# --------------------
# 記録タブ（旧：本日の記録）
# --------------------
with tabs[1]:
    st.subheader("記録")

    # ---- 今週の進捗（部位別）：先週比バー
    st.write(f"### 今週の進捗（先週比）（{this_ws.isoformat()}〜{this_we.isoformat()}）")

    show_parts = visible_parts if visible_parts else BODY_PARTS
    if not show_parts:
        st.info("サイドバーで表示する部位を選択してください。")
    else:
        for p in show_parts:
            actual = get_part_volume(this_week_vols, p)
            last_actual = get_part_volume(last_week_vols, p)
            r = ratio_vs_last(actual, last_actual)

            c1, c2, c3 = st.columns([1.4, 1.4, 3.2])
            with c1:
                st.metric(p, f"{actual}")
            with c2:
                st.metric("先週", f"{last_actual}")
            with c3:
                if r is None:
                    st.caption("先週が0なので先週比バーは非表示")
                else:
                    st.progress(min(r, 1.0))
                    st.caption(f"先週比 {r*100:.0f}%（先週=100%基準）")

        st.divider()

    # ---- 本日の記録（今日）
    st.write("### 本日の記録")

    today_iso = date.today().isoformat()
    rows = fetch_by_date(today_iso)

    if not rows:
        st.info("本日の記録はまだありません。")
    else:
        df_today = rows_to_df(rows)

        # 1) 総ボリューム
        st.metric("本日の総ボリューム", f"{volume_total(df_today):.0f}")

        # 2) 部位別ボリューム（表示部位のみ）
        dfp_today = add_body_part(df_today, EXERCISE_TO_BODY_PART)
        part_today = volume_by_body_part(dfp_today)

        if not part_today.empty:
            # 表示部位でフィルタ（visible_parts未指定ならBODY_PARTS優先）
            filter_parts = show_parts if show_parts else BODY_PARTS
            part_today_view = part_today[part_today["body_part"].isin(filter_parts)].copy()

            if part_today_view.empty:
                st.caption("本日は表示対象部位の記録がありません（未分類のみ等）。")
            else:
                st.write("#### 本日の部位別ボリューム")
                st.dataframe(part_today_view, use_container_width=True)
        else:
            st.caption("本日の部位別ボリュームはありません。")

        st.divider()

        # 3) 種目別（詳細）
        st.write("### 種目別")
        grouped = today_grouped(df_today)
        for ex, show_df, ex_total in grouped:
            with st.expander(f"{ex}（合計 {ex_total:.0f}）", expanded=False):
                st.dataframe(show_df, use_container_width=True)


# --------------------
# 週集計タブ
# --------------------
with tabs[2]:
    st.subheader("週集計（期間ビュー）")

    start_end = st.date_input(
        "期間を選ぶ（開始日〜終了日）",
        value=(this_ws, this_we),
        key="range_pick",
    )

    if not isinstance(start_end, tuple) or len(start_end) != 2:
        st.info("開始日と終了日を選んでください。")
    else:
        start_date, end_date = start_end
        if start_date > end_date:
            st.error("開始日が終了日より後になっています。")
        else:
            rows_range = fetch_range(start_date.isoformat(), end_date.isoformat())
            df_range = rows_to_df(rows_range)

            if df_range.empty:
                st.info("この期間の記録はありません。")
            else:
                all_days = pd.date_range(start_date, end_date, freq="D") \
                    .strftime("%Y-%m-%d").tolist()

                view_tabs = st.tabs(["総（種目）", "部位"])

                # ---- 総（種目） ----
                with view_tabs[0]:
                    st.write("### 日別ボリューム")
                    daily = (
                        df_range.groupby("date", as_index=False)["volume"]
                        .sum()
                        .sort_values("date")
                        .copy()
                    )
                    daily_full = pd.DataFrame({"date": all_days}) \
                        .merge(daily, on="date", how="left")
                    daily_full["volume"] = daily_full["volume"].fillna(0).round(0).astype(int)
                    st.bar_chart(daily_full.set_index("date")[["volume"]])

                    st.write("### 種目別ランキング（期間合計）")
                    by_ex = (
                        df_range.groupby("exercise", as_index=False)["volume"]
                        .sum()
                        .sort_values("volume", ascending=False)
                        .copy()
                    )
                    by_ex["volume"] = by_ex["volume"].round(0).astype(int)
                    st.dataframe(by_ex, use_container_width=True)

                # ---- 部位 ----
                with view_tabs[1]:
                    dfp = add_body_part(df_range, EXERCISE_TO_BODY_PART)

                    is_this_week = (
                        start_date == this_ws and end_date == this_we
                    )

                    st.write("### 目標差（％）")
                    show_parts = visible_parts if visible_parts else BODY_PARTS

                    if show_parts:
                        for p in show_parts:
                            actual = get_part_volume(this_week_vols, p)
                            last_actual = get_part_volume(last_week_vols, p)
                            r = ratio_vs_last(actual, last_actual)

                            c1, c2, c3 = st.columns([1.4, 1.4, 3.2])
                            with c1:
                                st.metric(p, f"{actual}")
                            with c2:
                                st.metric("先週", f"{last_actual}")
                            with c3:
                                if r is None:
                                    st.caption("先週が0なので先週比バーは非表示")
                                else:
                                    st.progress(min(r, 1.0))
                                    st.caption(f"先週比 {r*100:.0f}%（先週=100%基準）")

                    st.divider()

                    st.write("### 部位別ボリューム（期間合計）")
                    part_sum = volume_by_body_part(dfp)
                    st.dataframe(part_sum, use_container_width=True)
