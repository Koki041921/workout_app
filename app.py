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
    fetch_recent_entries_for_exercise,
)

from services import (  # type: ignore
    rows_to_df,
    volume_total,
    today_grouped,
    add_body_part,
    volume_by_body_part,
    day_detail,
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
DUMBBELL_EXERCISES = {
    "ダンベルプレス",
    "ダンベルフライ",
    "ダンベルカール",
    "ダンベルショルダープレス",
    "ワンハンドロー",
    "サイドレイズ",
    "ショルダープレス"
    # ...
}

BARBELL_EXERCISES = {
    "ベンチプレス",
    "ベントオーバーロウ",
    "スクワット",
    "デッドリフト",
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


def week_range_sunday(d: date) -> tuple[date, date]:
    """今週（日〜土）"""
    start = d - timedelta(days=(d.weekday() + 1) % 7)  # Sunday
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

def week_range_monday(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end

def ratio_vs_last(actual: float, last_actual: float):
    if last_actual <= 0:
        return None
    return float(actual) / float(last_actual)

def dumbbell_weight_options(base_w: float, span_kg: float = 6.0) -> list[float]:
    """
    ダンベル：1-10kgは1kg刻み、10kg超は2kg刻み
    base_w±span_kg の範囲で候補生成
    """
    lo = max(1.0, base_w - span_kg)
    hi = base_w + span_kg

    opts = set()

    # 1〜10（1kg刻み）
    for w in range(1, 11):
        if lo <= w <= hi:
            opts.add(float(w))

    # 12以上（2kg刻み）
    start = max(12, int((lo // 2) * 2))
    end = int(hi) + 2
    for w in range(start, end + 1, 2):
        if w >= 12:
            opts.add(float(w))

    return sorted(opts)


def barbell_weight_options(
    base_w: float,
    span_kg: float = 10.0,
    bar_kg: float = 20.0,
    plates: tuple[float, ...] = (1.25, 2.5, 5, 10, 15, 20),
    max_plates_per_side: int = 8,
) -> list[float]:
    """
    バーベル（フリーウェイト）：
      合計 = bar_kg + 2 * (片側プレート合計)
    plates は片側に載せるプレート種
    base_w±span_kg の範囲で実現可能な合計重量だけ返す
    """
    lo = max(bar_kg, base_w - span_kg)
    hi = base_w + span_kg

    # 片側の最大必要重量
    max_side = (hi - bar_kg) / 2
    if max_side <= 0:
        return [bar_kg]

    # 1.25kg単位でDP（片側）
    unit = 1.25
    max_u = int(round(max_side / unit))

    plate_units = [int(round(p / unit)) for p in plates]
    reachable = [False] * (max_u + 1)
    reachable[0] = True

    # 有限個コインDP（各プレートを最大 max_plates_per_side 枚まで）
    for pu in plate_units:
        for _ in range(max_plates_per_side):
            for s in range(max_u, pu - 1, -1):
                if reachable[s - pu]:
                    reachable[s] = True

    totals = set()
    for s in range(max_u + 1):
        if reachable[s]:
            total = bar_kg + 2 * (s * unit)
            if lo <= total <= hi:
                totals.add(round(total, 2))

    # 範囲内が空なら、近いものを最低限入れる（保険）
    if not totals:
        totals.add(bar_kg)

    return sorted(totals)


def pick_index(options: list[float], base_w: float) -> int:
    """base_w に一番近い候補を選択状態にする"""
    if not options:
        return 0
    best_i = min(range(len(options)), key=lambda i: abs(options[i] - base_w))
    return int(best_i)




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
this_ws, this_we = week_range_sunday(today_d)
last_ws, last_we = this_ws - timedelta(days=7), this_we - timedelta(days=7)

this_week_vols = week_part_volumes(this_ws.isoformat(), this_we.isoformat())
last_week_vols = week_part_volumes(last_ws.isoformat(), last_we.isoformat())

tabs = st.tabs(["入力", "本日の記録", "分析"])

# --------------------
# 入力タブ
# --------------------
# --------------------
# 入力タブ
# --------------------
with tabs[0]:
    st.subheader("入力（この日のワークアウト）")

    # 1) 日付・種目
    workout_date = st.date_input("日付", value=date.today(), key="input_date")
    exercise = st.selectbox("種目", EXERCISES_DEFAULT, key="input_exercise")

    # 2) 部位 + 前回セット（popover的に）
    selected_part = EXERCISE_TO_BODY_PART.get(exercise, "未分類")
    last_sets = fetch_last_day_entries_for_exercise(exercise)  # 直近日の同種目セット一覧
    last = fetch_last_for_exercise(exercise)  # 直近1行（重量候補の基準に使う）

    left, right = st.columns([1.4, 3.6])
    with left:
        st.write("#### この種目の部位")
        st.info(selected_part)

    with right:
        st.write("#### 前回のセット")
        # popover が使える環境なら popover、なければ expander にフォールバック
        popover_fn = getattr(st, "popover", None)
        container = popover_fn("前回セットを見る / 使う") if callable(popover_fn) else st.expander("前回セットを見る / 使う", expanded=False)

        with container:
            if not last_sets:
                st.caption("まだ記録がありません。")
            else:
                last_date = str(last_sets[0]["date"])
                st.caption(f"{last_date} のセット")

                # 直近日の各セットに「使う」(入力欄に反映)
                for i, s in enumerate(last_sets, 1):
                    label = f"{i}. {s['weight']}kg × {s['reps']} × {s['sets']}"
                    c1, c2 = st.columns([4, 1])
                    c1.write(label)
                    if c2.button("使う", key=f"use_lastset_{exercise}_{i}"):
                        st.session_state["input_custom_weight"] = str(s["weight"])
                        st.session_state["input_reps"] = int(s["reps"])
                        st.session_state["input_sets"] = int(s["sets"])
                        st.rerun()

                st.divider()

                # 「もっと行っているセット」= 頻出テンプレ（上位3つ）
                st.caption("もっと行っているセット（頻出）")
                recent = fetch_recent_entries_for_exercise(exercise, limit=300)
                if not recent:
                    st.caption("履歴が少ないので候補を作れません。")
                else:
                    from collections import Counter
                    templates = Counter((float(r[1]), int(r[2]), int(r[3])) for r in recent)  # (w,reps,sets)

                    top_tpl = templates.most_common(3)
                    for j, ((w, reps_, sets_), freq) in enumerate(top_tpl, 1):
                        label = f"{j}. {w:.1f}kg × {reps_} × {sets_}（{freq}回）"
                        c1, c2 = st.columns([4, 1])
                        c1.write(label)
                        if c2.button("使う", key=f"use_freq_{exercise}_{j}"):
                            st.session_state["input_custom_weight"] = str(w)
                            st.session_state["input_reps"] = int(reps_)
                            st.session_state["input_sets"] = int(sets_)
                            st.rerun()

    st.divider()

    # 3) セットを追加（最短導線）
    base_w = float(last[1]) if last else 10.0  # 前回重量ベース。なければ10kg仮

    st.write("### セットを追加")
    c1, c2, c3 = st.columns(3)
    with c1:
        if exercise in DUMBBELL_EXERCISES:
            weight_options = dumbbell_weight_options(base_w, span_kg=6.0)
        elif exercise in BARBELL_EXERCISES:
            weight_options = barbell_weight_options(
                base_w,
                span_kg=10.0,
                bar_kg=20.0,
                plates=(1.25, 2.5, 5, 10, 15, 20),
                max_plates_per_side=8,
            )
        else:
            # 既存（2.5刻みの±レンジ）を残す
            weight_options = [max(0, base_w + 2.5 * i) for i in [-3, -2, -1, 0, 1, 2, 3]]

        # selectbox の index は base_w に近い値を選択状態にする
        idx = pick_index(weight_options, base_w)
        weight = st.selectbox("重量(kg)", weight_options, index=3, key="input_weight")
        custom_weight = st.text_input("任意重量（空でOK）", key="input_custom_weight")
    with c2:
        reps = st.number_input("回数", min_value=1, value=10, key="input_reps")
    with c3:
        sets = st.number_input("セット数", min_value=1, value=3, key="input_sets")

    note = st.text_input("メモ（任意）", key="input_note")

    try:
        w_final = float(custom_weight) if custom_weight.strip() else float(weight)
    except ValueError:
        w_final = float(weight)

    if st.button("このセットを記録"):
        insert_entry(
            workout_date.isoformat(),
            exercise,
            float(w_final),
            int(reps),
            int(sets),
            str(note),
        )
        st.success("記録しました。")
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # 4) 今週の進捗（先週ライン） + ±表示
    today_d = date.today()
    this_ws, this_we = week_range_sunday(today_d)
    last_ws, last_we = this_ws - timedelta(days=7), this_we - timedelta(days=7)

    this_rows = fetch_range(this_ws.isoformat(), this_we.isoformat())
    last_rows = fetch_range(last_ws.isoformat(), last_we.isoformat())
    df_this = rows_to_df(this_rows) if this_rows else pd.DataFrame(columns=rows_to_df([]).columns)
    df_last = rows_to_df(last_rows) if last_rows else pd.DataFrame(columns=rows_to_df([]).columns)

    if not df_this.empty:
        df_this["body_part"] = df_this["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")
    else:
        df_this["body_part"] = []
    if not df_last.empty:
        df_last["body_part"] = df_last["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")
    else:
        df_last["body_part"] = []

    this_part_vol = float(df_this[df_this["body_part"] == selected_part]["volume"].sum()) if not df_this.empty else 0.0
    last_part_vol = float(df_last[df_last["body_part"] == selected_part]["volume"].sum()) if not df_last.empty else 0.0

    st.write(f"### 今週の進捗（先週ライン）（{this_ws.isoformat()}〜{this_we.isoformat()}）")
    c1, c2, c3 = st.columns([1.2, 1.2, 3.6])
    with c1:
        st.metric("今週", f"{this_part_vol:.0f}")
    with c2:
        st.metric("先週", f"{last_part_vol:.0f}")
    with c3:
        if last_part_vol <= 0:
            st.caption("先週が0なので、先週ラインの比較はできません。")
        else:
            ratio = this_part_vol / last_part_vol  # 先週=1.0
            st.progress(min(max(ratio, 0.0), 1.0))

            diff_pct = (ratio - 1.0) * 100.0
            diff_vol = this_part_vol - last_part_vol

            sign_pct = "+" if diff_pct >= 0 else ""
            sign_vol = "+" if diff_vol >= 0 else ""
            st.caption(f"差分: {sign_pct}{diff_pct:.0f}%（{sign_vol}{diff_vol:.0f} volume）")

            # 未達なら「あと」が見えるように
            if diff_vol < 0:
                st.caption(f"先週ラインまであと {-diff_pct:.0f}%（約 {-diff_vol:.0f} volume）")

    # 5) セット換算（残りがある時）
    remaining_vol = max(0.0, last_part_vol - this_part_vol)
    if remaining_vol > 0:
        with st.expander("セット換算（過去の実績から候補）", expanded=False):
            recent = fetch_recent_entries_for_exercise(exercise, limit=300)
            if not recent:
                st.info("まだ候補を作れるほど記録がありません。")
            else:
                from collections import Counter
                import math

                templates = Counter((float(r[1]), int(r[2]), int(r[3])) for r in recent)

                candidates = []
                for (w, reps_, sets_), freq in templates.items():
                    vol = float(w) * float(reps_) * float(sets_)
                    if vol <= 0:
                        continue
                    m = max(1, min(5, int(math.ceil(remaining_vol / vol))))
                    achieved = vol * m
                    overshoot = achieved - remaining_vol
                    candidates.append(
                        {"w": w, "reps": reps_, "sets": sets_, "vol": vol, "m": m,
                         "achieved": achieved, "overshoot": overshoot, "freq": freq}
                    )

                candidates.sort(key=lambda x: (abs(x["overshoot"]), x["m"], -x["freq"]))
                top = candidates[:5]

                st.caption("残り volume に近い順で候補（最大5件）")
                for i, c in enumerate(top, 1):
                    label = (
                        f"{i}. {c['w']:.1f}kg×{c['reps']}×{c['sets']}（{c['vol']:.0f}）"
                        f" ×{c['m']}回 → {c['achieved']:.0f}（超過 {c['overshoot']:.0f}）"
                    )
                    cols = st.columns([4, 1])
                    cols[0].write(label)
                    if cols[1].button("使う", key=f"use_tpl_{exercise}_{i}"):
                        st.session_state["input_custom_weight"] = str(c["w"])
                        st.session_state["input_reps"] = int(c["reps"])
                        st.session_state["input_sets"] = int(c["sets"])
                        st.rerun()

    st.divider()

    # 6) この日の記録（編集・削除）
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
                        new_w = st.number_input("kg", value=float(r["weight"]), step=2.5, key=f"edit_w_{entry_id}")
                    with c2:
                        new_reps = st.number_input("reps", value=int(r["reps"]), step=1, key=f"edit_r_{entry_id}")
                    with c3:
                        new_sets = st.number_input("sets", value=int(r["sets"]), step=1, key=f"edit_s_{entry_id}")
                    with c4:
                        new_note = st.text_input("note", value=str(r["note"] or ""), key=f"edit_n_{entry_id}")
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
# --------------------
# 記録タブ（本日の記録）
# --------------------
with tabs[1]:
    st.subheader("本日の記録")

    # 対象日
    target_date = st.date_input(
        "表示する日付",
        value=date.today(),
        key="record_view_date"
    )

    rows_day = fetch_by_date(target_date.isoformat())

    if not rows_day:
        st.info("この日の記録はありません。")
    else:
        df_day = rows_to_df(rows_day)

        # ---------- この日のサマリー ----------
        total_vol = float(df_day["volume"].sum())
        st.markdown(f"### この日の総ボリューム：**{total_vol:.0f}**")

        part_sum = (
            df_day.assign(
                body_part=df_day["exercise"]
                .map(EXERCISE_TO_BODY_PART)
                .fillna("未分類")
            )
            .groupby("body_part", as_index=False)["volume"]
            .sum()
            .sort_values("volume", ascending=False)
        )

        st.markdown("#### 部位別ボリューム")
        for _, r in part_sum.iterrows():
            st.write(f"- {r['body_part']}: {r['volume']:.0f}")

        st.divider()

        # ---------- 今週の進捗（先週ライン） ----------
        today_d = target_date
        this_ws, this_we = week_range_sunday(today_d)
        last_ws, last_we = this_ws - timedelta(days=7), this_we - timedelta(days=7)

        this_rows = fetch_range(this_ws.isoformat(), this_we.isoformat())
        last_rows = fetch_range(last_ws.isoformat(), last_we.isoformat())

        df_this = rows_to_df(this_rows) if this_rows else pd.DataFrame(columns=df_day.columns)
        df_last = rows_to_df(last_rows) if last_rows else pd.DataFrame(columns=df_day.columns)

        if not df_this.empty:
            df_this["body_part"] = df_this["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")
        if not df_last.empty:
            df_last["body_part"] = df_last["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")

        st.markdown(
            f"### 今週の進捗（先週ライン）"
            f"（{this_ws.isoformat()}〜{this_we.isoformat()}）"
        )

        for part in part_sum["body_part"].tolist():
            this_part_vol = float(
                df_this[df_this["body_part"] == part]["volume"].sum()
            ) if not df_this.empty else 0.0

            last_part_vol = float(
                df_last[df_last["body_part"] == part]["volume"].sum()
            ) if not df_last.empty else 0.0

            st.write(f"**{part}**")

            if last_part_vol <= 0:
                st.caption("先週が0のため、先週ライン比較はできません。")
                continue

            ratio = this_part_vol / last_part_vol
            st.progress(min(max(ratio, 0.0), 1.0))

            diff_pct = (1.0 - ratio) * 100.0
            diff_vol = last_part_vol - this_part_vol

            if diff_vol > 0:
                st.caption(
                    f"先週ラインまであと {diff_pct:.0f}%"
                    f"（約 {diff_vol:.0f} volume）"
                )
            else:
                st.caption(
                    f"先週ラインを {abs(diff_pct):.0f}% 超過"
                    f"（+{abs(diff_vol):.0f} volume）"
                )

            st.divider()

        # ---------- 編集・削除 ----------
        st.subheader("この日の記録（編集・削除）")

        for ex, g in df_day.groupby("exercise", sort=False):
            ex_total = float(g["volume"].sum())
            with st.expander(f"{ex}（合計 {ex_total:.0f}）", expanded=False):
                for _, r in g.iterrows():
                    entry_id = int(r["id"])
                    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 2.5, 1.2])

                    with c1:
                        new_w = st.number_input(
                            "kg",
                            value=float(r["weight"]),
                            step=2.5,
                            key=f"rec_w_{entry_id}",
                        )
                    with c2:
                        new_reps = st.number_input(
                            "reps",
                            value=int(r["reps"]),
                            step=1,
                            key=f"rec_r_{entry_id}",
                        )
                    with c3:
                        new_sets = st.number_input(
                            "sets",
                            value=int(r["sets"]),
                            step=1,
                            key=f"rec_s_{entry_id}",
                        )
                    with c4:
                        new_note = st.text_input(
                            "note",
                            value=str(r["note"] or ""),
                            key=f"rec_n_{entry_id}",
                        )
                    with c5:
                        if st.button("更新", key=f"rec_up_{entry_id}"):
                            update_entry(
                                entry_id,
                                float(new_w),
                                int(new_reps),
                                int(new_sets),
                                str(new_note),
                            )
                            st.success("更新しました。")
                            st.cache_data.clear()
                            st.rerun()

                        if st.button("削除", key=f"rec_del_{entry_id}"):
                            delete_entry(entry_id)
                            st.success("削除しました。")
                            st.cache_data.clear()
                            st.rerun()

# --------------------
# 週集計タブ
# --------------------
with tabs[2]:
    st.subheader("週集計（分析）")

    # 1) 期間セレクタ
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
            # 期間データ取得
            rows_range = fetch_range(start_date.isoformat(), end_date.isoformat())
            df_range = rows_to_df(rows_range)

            if df_range.empty:
                st.info("この期間の記録はありません。")
            else:
                # 2) フィルタ（部位）
                dfp = add_body_part(df_range, EXERCISE_TO_BODY_PART)

                part_options = ["全部位"] + BODY_PARTS + ["未分類"]
                selected_part = st.selectbox("フィルタ：部位", part_options, index=0, key="filter_part")

                if selected_part != "全部位":
                    df_view = dfp[dfp["body_part"] == selected_part].copy()
                else:
                    df_view = dfp.copy()

                if df_view.empty:
                    st.warning("この部位フィルタ条件では記録がありません。")
                else:
                    # 共通：期間内の日付リスト
                    all_days = pd.date_range(start_date, end_date, freq="D").strftime("%Y-%m-%d").tolist()

                    # =========================
                    # 3) サマリー
                    # =========================
                    daily = (
                        df_view.groupby("date", as_index=False)["volume"]
                        .sum()
                        .sort_values("date")
                        .copy()
                    )
                    daily_full = pd.DataFrame({"date": all_days}).merge(daily, on="date", how="left")
                    daily_full["volume"] = daily_full["volume"].fillna(0).round(0).astype(int)
                    
                    # 自動インサイト（最大3行）
                    dfp_all = df_range.copy()
                    dfp_all["body_part"] = dfp_all["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")

                    lines: list[str] = []

                    # 1) 部位の最小
                    part_sum = dfp_all.groupby("body_part", as_index=False)["volume"].sum()
                    part_sum["volume"] = part_sum["volume"].fillna(0.0)
                    known = part_sum[part_sum["body_part"].isin(BODY_PARTS)].copy()
                    target_part_sum = known if not known.empty else part_sum
                    if not target_part_sum.empty:
                        min_row = target_part_sum.sort_values("volume", ascending=True).iloc[0]
                        lines.append(f"この期間、{min_row['body_part']}のボリュームが最小です")

                    # 2) 前回同期間比（期間長ぶん後ろにずらす）
                    period_days = (end_date - start_date).days + 1
                    prev_start = start_date - timedelta(days=period_days)
                    prev_end = end_date - timedelta(days=period_days)
                    prev_rows = fetch_range(prev_start.isoformat(), prev_end.isoformat())
                    if prev_rows:
                        df_prev = rows_to_df(prev_rows)
                        if not df_prev.empty:
                            df_prev["body_part"] = df_prev["exercise"].map(EXERCISE_TO_BODY_PART).fillna("未分類")
                            prev_part = df_prev.groupby("body_part", as_index=False)["volume"].sum()
                            cur_part = dfp_all.groupby("body_part", as_index=False)["volume"].sum()
                            merged = cur_part.merge(prev_part, on="body_part", how="outer", suffixes=("_cur", "_prev")).fillna(0.0)

                            merged = merged[merged["volume_prev"] > 0].copy()
                            if not merged.empty:
                                merged["pct"] = (merged["volume_cur"] - merged["volume_prev"]) / merged["volume_prev"] * 100.0
                                best = merged.sort_values("pct", ascending=False).iloc[0]
                                sign = "+" if float(best["pct"]) >= 0 else ""
                                lines.append(f"前回の同期間より、{best['body_part']}が {sign}{best['pct']:.0f}% 変化しています")

                    # 3) 記録ゼロ日（連続優先）
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

                    lines = lines[:3]
                    if lines:
                        st.markdown("### 🔍 今回の期間の注目ポイント")
                        st.info("\n".join([f"・{t}" for t in lines]))


                    total_vol = int(daily_full["volume"].sum())
                    avg_vol = int(round(daily_full["volume"].mean(), 0))
                    max_idx = int(daily_full["volume"].idxmax())
                    max_vol = int(daily_full.loc[max_idx, "volume"])
                    max_day = str(daily_full.loc[max_idx, "date"])
                    zero_days = int((daily_full["volume"] == 0).sum())

                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.metric("合計ボリューム", f"{total_vol}")
                    with c2:
                        st.metric("1日平均", f"{avg_vol}")
                    with c3:
                        st.metric("最大日", f"{max_vol}", help=f"{max_day}")
                        st.caption(f"日付：{max_day}")
                    with c4:
                        st.metric("記録ゼロ日", f"{zero_days}")

                    st.divider()

                    # =========================
                    # 4) 推移（棒グラフ）
                    # =========================
                    st.write("### 推移（日別ボリューム）")
                    st.bar_chart(daily_full.set_index("date")[["volume"]])

                    st.divider()
                    # =========================
                    # 部位別ランキング（全部位のときのみ）
                    # =========================
                    if selected_part == "全部位":
                        st.divider()
                        st.write("### 部位別ランキング（期間合計）")

                        part_rank = (
                            dfp.groupby("body_part", as_index=False)["volume"]
                            .sum()
                            .sort_values("volume", ascending=False)
                            .copy()
                        )
                        part_rank["volume"] = part_rank["volume"].round(0).astype(int)

                        # 未分類を最後に回したい場合（任意）
                        if "未分類" in part_rank["body_part"].values:
                            part_rank["is_uncat"] = part_rank["body_part"] == "未分類"
                            part_rank = part_rank.sort_values(
                                ["is_uncat", "volume"], ascending=[True, False]
                            ).drop(columns="is_uncat")

                        st.dataframe(part_rank, use_container_width=True)

                    # =========================
                    # 5) 種目別ランキング（期間合計）
                    # =========================
                    st.write("### 種目別ランキング（期間合計）")

                    search = st.text_input("種目検索（任意）", value="", key="ex_search").strip()
                    top_n = st.slider("上位Nを表示", min_value=5, max_value=50, value=15, step=1, key="ex_topn")

                    by_ex = (
                        df_view.groupby("exercise", as_index=False)["volume"]
                        .sum()
                        .sort_values("volume", ascending=False)
                        .copy()
                    )
                    by_ex["volume"] = by_ex["volume"].round(0).astype(int)

                    if search:
                        by_ex_view = by_ex[by_ex["exercise"].str.contains(search, case=False, na=False)].copy()
                    else:
                        by_ex_view = by_ex.copy()

                    st.dataframe(by_ex_view.head(top_n), use_container_width=True)

                    st.divider()

                    # =========================
                    # 6) 種目ドリルダウン
                    # =========================
                    st.write("### 種目ドリルダウン")

                    ex_list = by_ex["exercise"].tolist()
                    if not ex_list:
                        st.info("この条件では種目がありません。")
                    else:
                        picked_ex = st.selectbox("深掘りする種目", ex_list, key="drill_ex")

                        df_ex = df_view[df_view["exercise"] == picked_ex].copy()

                        # この種目の日別推移
                        ex_daily = (
                            df_ex.groupby("date", as_index=False)["volume"]
                            .sum()
                            .sort_values("date")
                            .copy()
                        )
                        ex_daily_full = pd.DataFrame({"date": all_days}).merge(ex_daily, on="date", how="left")
                        ex_daily_full["volume"] = ex_daily_full["volume"].fillna(0).round(0).astype(int)

                        st.write("#### この種目の日別推移")
                        st.bar_chart(ex_daily_full.set_index("date")[["volume"]])

                        # 日別ランキング
                        st.write("#### この種目の日別ランキング")
                        ex_rank = ex_daily_full.sort_values("volume", ascending=False).copy()
                        st.dataframe(ex_rank, use_container_width=True)

                        # その日のセット詳細（任意の日を選択）
                        # volume>0の日だけ選べるようにする
                        available_days = ex_daily_full[ex_daily_full["volume"] > 0]["date"].tolist()
                        if not available_days:
                            st.caption("この種目は期間内に記録がありません。")
                        else:
                            picked_day = st.selectbox("詳細を見る日（この種目）", available_days, key="drill_day")
                            # day_detail が services.py にある前提（無ければ後述）
                            detail = day_detail(df_view, picked_day)
                            # その日の中から該当種目だけに絞る
                            detail_ex = detail[detail["exercise"] == picked_ex].copy() if not detail.empty else detail

                            st.write("#### セット詳細")
                            st.dataframe(detail_ex, use_container_width=True)
