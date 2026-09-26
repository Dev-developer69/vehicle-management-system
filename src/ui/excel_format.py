import calendar
import streamlit as st
import pandas as pd
from datetime import date
from fpdf import FPDF

from src.screens.products_manager import _extract_data_from_image
from src.database.db import (
    save_vehicle_records, save_driver_salary, save_vehicle_expenses,
    get_vehicle_records, get_driver_salary, get_vehicle_expenses,
    get_salary_check, get_scheduled_km, get_diesel_summary,
    get_km_combines, save_km_combine, delete_km_combine,
    update_vehicle_expense, delete_vehicle_expense,
    update_driver_salary, delete_driver_salary,delete_vehicle_record,
    get_diesel_rate_payment, save_diesel_rate_payment,
    get_diesel_row_rates, save_diesel_row_rate,
    get_suppliers, save_supplier, delete_supplier, get_supplier_products,
    get_products, save_product, delete_product,
    get_requirements, save_requirement, fulfill_requirement, delete_requirement,
    save_fuel_fill, get_fuel_fills, update_fuel_fill, delete_fuel_fill,
    clear_fuel_fills_for_date, get_existing_fuel_fill_dates, replace_fuel_fill_for_date,
    migrate_diesel_to_fuel_fills, get_unmigrated_diesel_dates,
    get_vehicle_payment_config, save_vehicle_payment_config,
    get_duty_splits, save_duty_split, delete_duty_split,
    get_drivers_for_buses, check_driver_clash,  # ✅ added: driver dropdown + clash check
)

# ──────────────────────────────────────────────
# HELPER: Diesel vs CNG label (AT7389 is CNG)
# ──────────────────────────────────────────────
def fuel_label(bus_number: str) -> str:
    return "CNG" if bus_number == "AT7389" else "Diesel"


# ──────────────────────────────────────────────
# HELPER: Vibrant, eye-catching HTML table — teal→purple gradient header,
# soft glow border, glowing gradient TOTAL row (Driver Report jaisi hi style,
# app-wide consistent look ke liye). st.dataframe ke bajaye yahi use karo.
# ──────────────────────────────────────────────
def _render_html_table(df: pd.DataFrame, total_row: dict = None):
    cols = list(df.columns)
    html = [
        "<div style='overflow-x:auto;border-radius:14px;"
        "border:1px solid rgba(123,140,255,0.35);"
        "box-shadow:0 4px 24px rgba(20,160,133,0.15), 0 0 0 1px rgba(255,255,255,0.03) inset;'>"
        "<table style='width:100%;border-collapse:collapse;color:#f0f0f0;font-size:0.88rem;'>"
    ]
    html.append("<thead><tr>")
    for c in cols:
        html.append(
            f"<th style='padding:12px 10px;text-align:left;white-space:nowrap;"
            f"background:linear-gradient(90deg,#14A085,#7B8CFF);color:#fff;"
            f"font-weight:700;letter-spacing:0.3px;'>{c}</th>"
        )
    html.append("</tr></thead><tbody>")

    for i, r in enumerate(df.to_dict("records")):
        row_bg = "#182838" if i % 2 == 0 else "#1E2B3D"
        html.append("<tr>")
        for c in cols:
            val = r.get(c, "")
            val = "" if pd.isna(val) else val
            html.append(
                f"<td style='border-bottom:1px solid rgba(123,140,255,0.12);padding:10px;"
                f"white-space:nowrap;background:{row_bg};color:#eee;'>{val}</td>"
            )
        html.append("</tr>")

    if total_row:
        html.append("<tr style='background:linear-gradient(90deg,rgba(20,160,133,0.35),rgba(123,140,255,0.35));'>")
        for c in cols:
            val = total_row.get(c, "")
            html.append(
                f"<td style='padding:12px 10px;white-space:nowrap;"
                f"color:#FFD700;font-weight:800;font-size:0.95rem;"
                f"text-shadow:0 0 8px rgba(255,215,0,0.35);'>{val}</td>"
            )
        html.append("</tr>")

    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _render_km_merged_table(display_df: pd.DataFrame, groups: list):
    """Renders display_df as an HTML table where Scheduled KM / Actual KM /
    Income cells for each group of 2+ dates are visually
    merged (rowspan) into a single SUMMED value, Excel-style — every other
    column stays per-row/unchanged. Multiple non-overlapping groups (of any
    size) supported at once.
    Original row order (jaisa display_df me hai, e.g. descending date) ko
    zyada se zyada preserve karta hai — group ke members already adjacent
    hote hain to kuch nahi hilta, warna sirf unhi rows ko ek saath la kar
    minimum movement karta hai.
    Agar kisi purani/duplicate group ki wajah se dates OVERLAP karte hain
    (ek hi date do groups me ho), to baad wali overlapping group ko skip
    kar deta hai — taaki table half-broken na dikhe."""
    MERGE_COLS = ["Scheduled KM", "Actual KM", "Income"]
    rows = display_df.to_dict("records")

    rowspan_at = {}   # idx -> merge info, is row se rowspan shuru hoga
    skip_at    = set()  # baaki group-member rows ke indices (merge cells yaha skip honge)
    claimed_dates = set()  # ab tak jitni dates kisi group me use ho chuki hain
    group_breakdowns = []  # ✅ mobile-friendly breakdown (hover tooltip ki jagah tap se bhi dikhega)

    for group in groups:
        dates = group["dates"] if isinstance(group, dict) else group
        if any(d in claimed_dates for d in dates):
            continue  # overlapping/duplicate group — skip karo, warna table broken dikhegi
        idxs = [i for i, r in enumerate(rows) if r["Date"] in dates]
        if len(idxs) != len(dates) or len(idxs) < 2:
            continue
        idxs.sort()
        insert_at = idxs[0]

        # Group ke saare members ko ek contiguous block me la do (unka aapas
        # ka relative order preserve karte hue), taaki rowspan lag sake.
        extracted = [rows[i] for i in idxs]
        for i in sorted(idxs, reverse=True):
            rows.pop(i)
        rows[insert_at:insert_at] = extracted
        claimed_dates.update(dates)

        date_vals = [r["Date"] for r in extracted]
        col_vals  = {c: [pd.to_numeric(r.get(c), errors="coerce") for r in extracted] for c in MERGE_COLS}
        col_sums  = {c: sum(v for v in col_vals[c] if pd.notna(v)) for c in MERGE_COLS}

        lines = [
            f"{d} — Sch {sch:.0f} / Actual {act:.0f} / Income {inc:,.0f}"
            for d, sch, act, inc in zip(
                date_vals, col_vals["Scheduled KM"], col_vals["Actual KM"], col_vals["Income"]
            )
        ]
        lines.append(
            f"Total — Sch {col_sums['Scheduled KM']:.0f} / Actual {col_sums['Actual KM']:.0f} "
            f"/ Income {col_sums['Income']:,.0f}"
        )
        tooltip = "\n".join(lines)

        rowspan_at[insert_at] = {"sums": col_sums, "span": len(extracted), "tooltip": tooltip}
        group_breakdowns.append({
            "label": " + ".join(date_vals),
            "rows": [
                {"Date": d, "Scheduled KM": sch, "Actual KM": act, "Income": inc}
                for d, sch, act, inc in zip(
                    date_vals, col_vals["Scheduled KM"], col_vals["Actual KM"], col_vals["Income"]
                )
            ],
            "total": {"Date": "TOTAL", **col_sums},
        })
        for i in range(insert_at + 1, insert_at + len(extracted)):
            skip_at.add(i)

    cols = list(display_df.columns)
    html = [
        "<div style='overflow-x:auto;border-radius:14px;"
        "border:1px solid rgba(123,140,255,0.35);"
        "box-shadow:0 4px 24px rgba(20,160,133,0.15), 0 0 0 1px rgba(255,255,255,0.03) inset;'>"
        "<table style='width:100%;border-collapse:collapse;color:#f0f0f0;font-size:0.88rem;'>"
    ]
    html.append("<thead><tr>")
    for c in cols:
        html.append(
            f"<th style='padding:12px 10px;text-align:left;white-space:nowrap;"
            f"background:linear-gradient(90deg,#14A085,#7B8CFF);color:#fff;"
            f"font-weight:700;letter-spacing:0.3px;'>{c}</th>"
        )
    html.append("</tr></thead><tbody>")

    for i, r in enumerate(rows):
        row_bg = "#182838" if i % 2 == 0 else "#1E2B3D"
        html.append("<tr>")
        for c in cols:
            if c in MERGE_COLS and i in rowspan_at:
                info = rowspan_at[i]
                val = info["sums"][c]
                html.append(
                    f"<td rowspan='{info['span']}' title=\"{info['tooltip']}\" style='border-bottom:1px solid rgba(123,140,255,0.12);padding:10px;text-align:center;"
                    f"vertical-align:middle;background:{row_bg};color:#eee;cursor:help;'>{val:,.0f}</td>"
                )
            elif c in MERGE_COLS and i in skip_at:
                continue  # rowspan se cover ho gaya
            else:
                cell_val = r.get(c, "")
                cell_val = "" if pd.isna(cell_val) else cell_val
                html.append(f"<td style='border-bottom:1px solid rgba(123,140,255,0.12);padding:10px;white-space:nowrap;background:{row_bg};color:#eee;'>{cell_val}</td>")
        html.append("</tr>")

    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    groups_text = ", ".join(" + ".join(g["dates"] if isinstance(g, dict) else g) for g in groups)
    st.caption(f"🔗 Combined: {groups_text}")

    # ── ✅ Mobile-friendly breakdown — HTML 'title' hover tooltip phone pe
    # kaam nahi karta (koi hover event nahi hota touch devices pe), isliye
    # yahan ek tap-able expander me wahi breakdown dikhaya hai (desktop pe
    # bhi kaam karega, hover ke alawa). ──
    if group_breakdowns:
        with st.expander("📱 Combined KM/Income breakdown (tap to view)"):
            for gb in group_breakdowns:
                st.markdown(f"**🔗 {gb['label']}**")
                _render_html_table(pd.DataFrame(gb["rows"] + [gb["total"]]))


# ──────────────────────────────────────────────
# HELPER: Editor widget state → DataFrame
# ──────────────────────────────────────────────
def _apply_editor_state(original_df: pd.DataFrame, editor_state: dict) -> pd.DataFrame:
    if not editor_state:
        return original_df.copy()
    df = original_df.copy()
    for row_idx, changes in editor_state.get("edited_rows", {}).items():
        for col, val in changes.items():
            if row_idx < len(df):
                df.at[row_idx, col] = val
    added = editor_state.get("added_rows", [])
    if added:
        new_rows = pd.DataFrame(added)
        for col in df.columns:
            if col not in new_rows.columns:
                new_rows[col] = None
        df = pd.concat([df, new_rows[df.columns]], ignore_index=True)
    deleted = sorted(editor_state.get("deleted_rows", []), reverse=True)
    for row_idx in deleted:
        if row_idx < len(df):
            df = df.drop(index=row_idx).reset_index(drop=True)
    return df


# ──────────────────────────────────────────────
# HELPER: Total row builder
# ──────────────────────────────────────────────
def build_total_row(df: pd.DataFrame, numeric_cols: list, label_col: str = "Driver Name"):
    total = {}
    for col in df.columns:
        if col == label_col:
            total[col] = "TOTAL"
        elif col == "Avg":
            valid = pd.to_numeric(df["Avg"], errors="coerce").dropna()
            total[col] = round(float(valid.mean()), 2) if not valid.empty else 0.0
        elif col in numeric_cols:
            total[col] = round(float(pd.to_numeric(df[col], errors="coerce").sum()), 3)
        else:
            total[col] = ""
    return pd.DataFrame({k: [v] for k, v in total.items()})


# ──────────────────────────────────────────────
# HELPER: Date range filter
# ──────────────────────────────────────────────
def _get_date_range(year, month, period):
    if period == "1-15":
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 15)
    elif period == "16-31":
        last_day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, 16), pd.Timestamp(year, month, last_day)
    else:
        last_day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, last_day)


# ──────────────────────────────────────────────
# HELPER: Year selector — ek hi jagah defined, poore app me (har file me)
# yahi use hota hai. Jab kabhi saal badalne ki range change karni ho
# (abhi: current year se 2 saal peeche tak), sirf yahin change karo.
# ──────────────────────────────────────────────
def year_options() -> list:
    this_year = date.today().year
    return list(range(this_year - 2, this_year + 1))


def year_selectbox(label: str = "Year", key: str = "year"):
    opts = year_options()
    return st.selectbox(label, options=opts, index=opts.index(date.today().year), key=key)


# ──────────────────────────────────────────────
# HELPER: Previous period shift (for Next flag)
# ──────────────────────────────────────────────
def shift_period_back(year, month, period):
    if period == "16-31":
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 15)
    else:
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        last_day   = calendar.monthrange(prev_year, prev_month)[1]
        return pd.Timestamp(prev_year, prev_month, 16), pd.Timestamp(prev_year, prev_month, last_day)


# ──────────────────────────────────────────────
# HELPER: Generate PDF — Vehicle Records
# ──────────────────────────────────────────────
def _safe_pdf_text(val) -> str:
    """FPDF core fonts (Helvetica) sirf Latin-1 support karte hain — unsupported chars replace karo"""
    text = str(val)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _generate_pdf(df, total_row, bus_number, month, half):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Helvetica", "B", 14)
    month_name = date(2000, month, 1).strftime("%B")
    pdf.cell(0, 10, _safe_pdf_text(f"Vehicle Records - {bus_number}  |  {month_name} ({half})"), ln=True, align="C")
    pdf.ln(3)
    cols   = list(df.columns)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w  = page_w / len(cols)
    pdf.set_fill_color(52, 73, 94); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for col in cols:
        pdf.cell(col_w, 8, _safe_pdf_text(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 8)
    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        for col in cols:
            pdf.cell(col_w, 7, _safe_pdf_text(row[col]) if pd.notna(row[col]) else "", border=1, align="C", fill=fill)
        pdf.ln()
    pdf.set_fill_color(230, 240, 255); pdf.set_font("Helvetica", "B", 8)
    for col in cols:
        pdf.cell(col_w, 8, _safe_pdf_text(total_row.iloc[0][col]), border=1, align="C", fill=True)
    pdf.ln()
    return bytes(pdf.output())


def _generate_expenses_pdf(df, bus_number, month, period):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Helvetica", "B", 14)
    month_name = date(2000, month, 1).strftime("%B")
    pdf.cell(0, 10, _safe_pdf_text(f"Vehicle Expenses - {bus_number}  |  {month_name} ({period})"), ln=True, align="C")
    pdf.ln(3)
    cols   = list(df.columns)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w  = page_w / len(cols)
    pdf.set_fill_color(52, 73, 94); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        pdf.cell(col_w, 8, _safe_pdf_text(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 9)
    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        for col in cols:
            pdf.cell(col_w, 7, _safe_pdf_text(row[col]) if pd.notna(row[col]) else "", border=1, align="C", fill=fill)
        pdf.ln()
    total_amount = pd.to_numeric(df["Amount"], errors="coerce").sum()
    pdf.set_fill_color(230, 240, 255); pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        val = "TOTAL" if col == "Category" else (f"{total_amount:,.0f}" if col == "Amount" else "")
        pdf.cell(col_w, 8, _safe_pdf_text(val), border=1, align="C", fill=True)
    pdf.ln()
    return bytes(pdf.output())


# ──────────────────────────────────────────────
# HELPER: Split Duty — ek din, driver/conductor KM ke hisaab se 2 logon me
# baant do (dono role independent — sirf driver split, sirf conductor
# split, ya dono, jo bhi us din chahiye)
# ──────────────────────────────────────────────
def _split_duty_section(bus_number: str, date_options: list):
    st.markdown("#### 👥 Split Duty (ek din, 2 log — KM ke hisaab se)")
    st.caption(
        "Jis din ek driver/conductor ne half aur doosre ne baaki half chalaya "
        "ho, us din ke liye dono logon ka apna-apna KM daalo — duty credit "
        "(salary ke liye) automatically unke KM ke fraction ke hisaab se "
        "baant jayega. Sirf driver split karo, sirf conductor, ya dono — "
        "jo bhi us din laagu ho."
    )

    if not date_options:
        st.caption("Koi date load nahi hui — pehle neeche 'Load' karo.")
        return

    split_date = st.selectbox("Date chuno", options=date_options, key=f"split_date_{bus_number}")
    existing = get_duty_splits(bus_number, [split_date])
    ex_row = existing.iloc[0].to_dict() if not existing.empty else {}

    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("**🧑‍✈️ Driver Split**")
        d1 = st.text_input("Driver 1", value=ex_row.get("Driver 1") or "", key=f"sd_d1_{bus_number}_{split_date}")
        d1km = st.number_input("Driver 1 KM", min_value=0.0, value=float(ex_row.get("Driver 1 KM") or 0), key=f"sd_d1km_{bus_number}_{split_date}")
        d2 = st.text_input("Driver 2", value=ex_row.get("Driver 2") or "", key=f"sd_d2_{bus_number}_{split_date}")
        d2km = st.number_input("Driver 2 KM", min_value=0.0, value=float(ex_row.get("Driver 2 KM") or 0), key=f"sd_d2km_{bus_number}_{split_date}")
    with sc2:
        st.markdown("**🎫 Conductor Split**")
        c1 = st.text_input("Conductor 1", value=ex_row.get("Conductor 1") or "", key=f"sd_c1_{bus_number}_{split_date}")
        c1km = st.number_input("Conductor 1 KM", min_value=0.0, value=float(ex_row.get("Conductor 1 KM") or 0), key=f"sd_c1km_{bus_number}_{split_date}")
        c2 = st.text_input("Conductor 2", value=ex_row.get("Conductor 2") or "", key=f"sd_c2_{bus_number}_{split_date}")
        c2km = st.number_input("Conductor 2 KM", min_value=0.0, value=float(ex_row.get("Conductor 2 KM") or 0), key=f"sd_c2km_{bus_number}_{split_date}")

    if d1.strip() and d2.strip() and (d1km + d2km) > 0:
        total = d1km + d2km
        st.caption(f"➡️ Driver credit: **{d1}** = {d1km/total:.2f} duty, **{d2}** = {d2km/total:.2f} duty")
    if c1.strip() and c2.strip() and (c1km + c2km) > 0:
        total_c = c1km + c2km
        st.caption(f"➡️ Conductor credit: **{c1}** = {c1km/total_c:.2f} duty, **{c2}** = {c2km/total_c:.2f} duty")

    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("💾 Save Split Duty", key=f"sd_save_{bus_number}_{split_date}", width='stretch'):
            save_duty_split(
                bus_number, split_date,
                driver_1=d1, driver_1_km=d1km, driver_2=d2, driver_2_km=d2km,
                conductor_1=c1, conductor_1_km=c1km, conductor_2=c2, conductor_2_km=c2km,
            )
            st.success(f"✅ {split_date} ka split duty saved!")
            st.rerun()
    with bc2:
        if not existing.empty:
            if st.button("🗑️ Remove Split (is date ki)", key=f"sd_del_{bus_number}_{split_date}", width='stretch'):
                delete_duty_split(bus_number, split_date)
                st.success(f"✅ {split_date} ka split duty hata diya — ab normal 1.0 duty (Driver/Conductor Name field wale) apply hoga.")
                st.rerun()

    all_splits = get_duty_splits(bus_number, date_options)
    if not all_splits.empty:
        with st.expander("📋 Is period ke saare split-duty entries"):
            _render_html_table(all_splits.drop(columns=["id"], errors="ignore"))


# ──────────────────────────────────────────────
# 1. VEHICLE RECORDS
# ──────────────────────────────────────────────
def editable_grid(bus_number: str):
    numeric_cols = ["Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Avg", "Income"]
    key          = f"grid_{bus_number}"
    fetch_key    = f"fetched_{bus_number}"
    confirm_key  = f"show_confirm_{bus_number}"
    pending_key  = f"pending_df_{bus_number}"
    sched_km_key = f"sched_km_{bus_number}"

    # ── ✅ Reset counter — ed_key is isse suffix hota hai. Har successful
    # save ke baad iska value +1 hota hai, taaki agli baar ek BILKUL NAYA
    # (kabhi na dekha gaya) widget key mile — Streamlit ko fresh widget
    # banana majboori ho jaata hai, purana typed data kisi bhi internal
    # caching ki wajah se reh nahi sakta. ──
    reset_key = f"grid_reset_{bus_number}"
    if reset_key not in st.session_state:
        st.session_state[reset_key] = 0
    ed_key = f"editor_{bus_number}_{st.session_state[reset_key]}"

    if sched_km_key not in st.session_state:
        st.session_state[sched_km_key] = get_scheduled_km(bus_number)
    scheduled_km = st.session_state[sched_km_key]

    # ── ✅ Driver Name ko "dropdown + writable" banane ke liye — DB me
    # jitne bhi distinct drivers hain (case-insensitive dedup, junk names
    # already filtered) unki list + ek sentinel "Naya Driver" option, jo
    # select hone par neeche ek free-text input khol deta hai. ──
    DRIVER_NEW = "➕ Naya Driver Likho"
    driver_options = get_drivers_for_buses() + [DRIVER_NEW]

    st.markdown(f"### Vehicle Records {bus_number} 🚐")

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":           [date.today()],
            "Status":         ["Present"],
            "Driver Name":    [None],
            "Conductor Name": [None],
            "Scheduled KM":   [scheduled_km],
            "Actual KM":      [scheduled_km],
            "Diesel":         [None],
            "Diesel KM":      [None],
            "Income":         [None],
            "Remark":         [""],
            "Next":           [False],
        })


    # ── Extract Records from Image ──
    FIELD_DEFS = {
        "Diesel":         ("diesel",         "'DSL/CNG' column. POSITIONAL RULE (most reliable — use this over header text): scan each row from RIGHT to LEFT starting at the REMARKS column (which contains 'ON ROUTE'/'LEAVE APPROVED'/'NEXT PERIOD' text). The Diesel/DSL/CNG number is in the column IMMEDIATELY to the left of REMARKS — the very last numeric column in the row, adjacent to REMARKS with nothing numeric between them. Do NOT use the 'LF' (Load Factor) or 'IPKM' columns — those are several columns further left (right after the INCOME column) and contain unrelated calculated decimal ratios that superficially look similar. If a row's REMARKS says 'ON ROUTE' and there's a number just to its left, THAT number is the Diesel/CNG value, not IPKM or LF. If genuinely blank/zero for that row, set 0 or null."),
        "Income":         ("income",         "'Income', 'INCOME', 'Base Fare' (NOT per-km, NOT load factor)"),
        "Remark":         ("remark",         "'Remark', 'REMARK' column — copy the exact text as-is (e.g. 'ON ROUTE', 'LEAVE APPROVED', 'ABSENT', 'NEXT PERIOD'). If empty set null."),
        "Driver Name":    ("driver_name",    "'Driver', 'Driver Name', 'DRIVER' column — copy exact name as-is"),
        "Conductor Name": ("conductor_name", "'Conductor', 'Conductor Name', 'COND' column — copy exact name as-is"),
        "Scheduled KM":   ("scheduled_km",   "'Scheduled KM', 'SCH KM', 'Sch.KM' column (numeric)"),
        "Actual KM":      ("actual_km",      "'Actual KM', 'ACT KM', 'Actual' column (numeric)"),
    }

    with st.expander("📷 Extract Records from Image (optional)"):
        st.caption("Agar sheet chaudi hai aur do photos mein aayi hai, dono upload karo.")

        st.markdown("**Kya extract karna hai?**")
        selected_fields = st.pills(
            "Fields",
            options=list(FIELD_DEFS.keys()),
            selection_mode="multi",
            default=["Income", "Remark"],
            key=f"extract_fields_{bus_number}",
            label_visibility="collapsed",
        )
        if not selected_fields:
            st.caption("⚠️ Kam se kam ek field select karo.")

        ai_choice = st.radio(
            "🤖 AI Model",
            ["🤖 Claude (Accurate — 2 images ek saath)", "⚡ Groq (Fast — 1 image at a time)"],
            index=1,
            horizontal=True,
            key=f"ai_choice_{bus_number}"
        )

        img_file_1 = st.file_uploader("Image 1 (Date wali, ya poori image)",
                                       type=["jpg","jpeg","png","webp"],
                                       key=f"inc_img1_{bus_number}")
        img_file_2 = st.file_uploader("Image 2 (optional — baaki columns wali)",
                                       type=["jpg","jpeg","png","webp"],
                                       key=f"inc_img2_{bus_number}")

        if img_file_1 and selected_fields and st.button("🔍 Extract", key=f"inc_extract_{bus_number}"):
            with st.spinner("Extracting..."):
                from src.screens.products_manager import (
                    _extract_data_from_images, _compress_image
                )

                field_bullets = "\n".join(
                    f"- {FIELD_DEFS[f][0]}: {FIELD_DEFS[f][1]}" for f in selected_fields
                )
                json_keys = ", ".join(["date"] + [FIELD_DEFS[f][0] for f in selected_fields])

                always_ignore = {"IPKM", "LF", "OTH.INC", "load factor", "per-km rates"}
                km_labels = {"Scheduled KM", "Actual KM"}
                ignore_extra = km_labels - set(selected_fields)
                ignore_list = ", ".join(sorted(ignore_extra | always_ignore))

                prompt = (
                    "This is a vehicle log table with varying column names across different sheets. "
                    + ("Two images are provided — they show the SAME rows in the SAME order, "
                       "just different columns of a wide table split across two photos. "
                       "Merge them row-by-row by position. "
                       if img_file_2 else "")
                    + "Extract every row (skip the TOTAL/summary row). "
                    "For each row extract these fields if matching column exists:\n"
                    "- date: Convert to YYYY-MM-DD.\n"
                    f"{field_bullets}\n\n"
                    f"IGNORE: {ignore_list}. "
                    + ("CRITICAL for the diesel field: it sits immediately left of the REMARKS "
                       "column, NOT immediately left of the INCOME column (that position, a few "
                       "columns further left, holds IPKM then LF — both must be ignored for diesel). "
                       "Verify by counting from the right edge of the table (REMARKS is rightmost, "
                       "diesel is one column left of it) rather than from the left. "
                       if "Diesel" in selected_fields else "")
                    + "If field not present set null. "
                    f"Return ONLY JSON array with keys: {json_keys}. "
                    "No explanation, no markdown."
                )

                if "Claude" in ai_choice:
                    import anthropic, base64, json, re
                    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

                    img1_bytes = _compress_image(img_file_1.read())
                    b64_1      = base64.standard_b64encode(img1_bytes).decode("utf-8")

                    content = [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_1}},
                    ]
                    if img_file_2:
                        img2_bytes = _compress_image(img_file_2.read())
                        b64_2      = base64.standard_b64encode(img2_bytes).decode("utf-8")
                        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_2}})

                    content.append({"type": "text", "text": prompt})

                    try:
                        msg = client.messages.create(
                            model="claude-sonnet-4-6",
                            max_tokens=4000,
                            messages=[{"role": "user", "content": content}],
                        )
                        raw   = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
                        match = re.search(r"\[.*\]", raw, re.DOTALL)
                        if match:
                            raw = match.group(0)
                        result = json.loads(raw)
                        if not isinstance(result, list):
                            result = []
                    except Exception as e:
                        st.error(f"❌ Claude extract failed: {e}")
                        result = []

                else:
                    images = [(img_file_1.read(), img_file_1.type)]
                    if img_file_2:
                        images.append((img_file_2.read(), img_file_2.type))
                    result = _extract_data_from_images(images, prompt)

            if result:
                rows = []
                for r in result:
                    remark_text = str(r.get("remark") or "").strip().upper() if "Remark" in selected_fields else ""

                    is_absent_or_leave = ("ABSENT" in remark_text) or ("LEAVE APPROVED" in remark_text) or ("LEAVE" in remark_text and "APPROV" in remark_text)
                    status = "On Leave" if is_absent_or_leave else "Present"
                    is_next = "NEXT" in remark_text and "PERIOD" in remark_text

                    rows.append({
                        "Date":           pd.to_datetime(r.get("date"), errors="coerce"),
                        "Status":         status,
                        "Driver Name":    (r.get("driver_name") or None) if "Driver Name" in selected_fields else None,
                        "Conductor Name": (r.get("conductor_name") or None) if "Conductor Name" in selected_fields else None,
                        "Scheduled KM":   (0 if is_absent_or_leave else (r.get("scheduled_km") if "Scheduled KM" in selected_fields else None)),
                        "Actual KM":      (0 if is_absent_or_leave else (r.get("actual_km") if "Actual KM" in selected_fields else None)),
                        "Diesel":         r.get("diesel") if "Diesel" in selected_fields else None,
                        "Diesel KM":      None,
                        "Income":         r.get("income") if "Income" in selected_fields else None,
                        "Remark":         "",
                        "Next":           is_next,
                    })
                new_df = pd.DataFrame(rows)
                new_df = new_df.dropna(subset=["Date"])
                new_df["Date"] = new_df["Date"].dt.date
                st.session_state[key] = new_df
                st.success(f"✅ {len(new_df)} rows extracted — baaki fields bhar ke Save karo")
                st.rerun()
            else:
                st.warning("⚠️ Extraction failed, fill manually.")
    st.caption(
        f"ℹ️ **{fuel_label(bus_number)}** yahan bharoge to: nayi date pe seedha add ho "
        f"jayega; purani date (jisme pehle se data hai) pe **3 options milenge** — "
        f"Yes Update (purana replace), Add Diesel (naya add), Cancel. **Explicitly '0'** "
        f"bharoge to us date ki saari existing fills clear ho jaayengi."
    )
    st.data_editor(
        st.session_state[key],
        num_rows="dynamic",
        width='stretch',
        hide_index=True,
        key=ed_key,
        column_config={
            "Date":           st.column_config.DateColumn("Date", default=date.today()),
            "Status":         st.column_config.SelectboxColumn("Status", options=["Present", "On Leave"], default="Present"),
            "Driver Name":    st.column_config.SelectboxColumn("Driver Name", options=driver_options),  # ✅ dropdown + "Naya Driver" option
            "Conductor Name": st.column_config.TextColumn("Conductor Name"),
            "Scheduled KM":   st.column_config.NumberColumn("Scheduled KM", min_value=0, default=scheduled_km),
            "Actual KM":      st.column_config.NumberColumn("Actual KM", min_value=0, default=scheduled_km),
            "Diesel":         st.column_config.NumberColumn(f"{fuel_label(bus_number)} (naya fill)", min_value=0.0, step=0.01, format="%.2f"),
            "Diesel KM":      st.column_config.NumberColumn(f"{fuel_label(bus_number)} KM", min_value=0),
            "Income":         st.column_config.NumberColumn("Income", min_value=0),
            "Remark":         st.column_config.TextColumn("Remark"),
            "Next":           st.column_config.CheckboxColumn("Next", default=False),
        },
    )

    editor_state  = st.session_state.get(ed_key, {})
    edited_df     = _apply_editor_state(st.session_state[key], editor_state)
    on_leave_mask = edited_df["Status"] == "On Leave"
    edited_df.loc[on_leave_mask, ["Scheduled KM", "Actual KM", "Income"]] = 0

    # ── ✅ "➕ Naya Driver Likho" select hua to uske liye ek alag free-text
    # input dikhao — typed value seedha edited_df me wapas daal diya jaata
    # hai, taaki save-flow ko pata bhi na chale ki ye dropdown se aaya ya
    # naya typed gaya. ──
    for _drv_idx, _drv_row in edited_df.iterrows():
        if _drv_row.get("Driver Name") == DRIVER_NEW:
            _typed_driver = st.text_input(
                f"Naya driver naam — {_drv_row['Date']}",
                key=f"new_driver_{bus_number}_{_drv_idx}",
            )
            if _typed_driver.strip():
                edited_df.at[_drv_idx, "Driver Name"] = _typed_driver.strip()

    # ── Naye vs purane data ka column-wise compare karo — sirf REAL conflict
    #    (jaha already koi non-empty value ek alag value se overwrite ho rahi
    #    ho) pe hi confirmation mango. Agar sirf khaali field bhari ja rahi
    #    hai (jaise Diesel pehle blank tha), to seedha save ho jaye. ──
    _COMPARE_COLS = ["Status", "Driver Name", "Conductor Name", "Scheduled KM",
                     "Actual KM", "Diesel KM", "Income", "Remark", "Next"]
    _NUMERIC_COMPARE_COLS = {"Scheduled KM", "Actual KM", "Diesel KM", "Income"}

    def _is_empty_val(v) -> bool:
        if v is None:
            return True
        if isinstance(v, float) and pd.isna(v):
            return True
        s = str(v).strip().lower()
        return s in ("", "none", "nan")

    def _values_differ(col: str, old_val, new_val) -> bool:
        """Column-aware comparison. Numeric columns (Scheduled KM, Actual KM,
        Diesel KM, Income) number ki tarah compare hote hain — taaki DB se
        aayi '446.0' (float) aur editor ki '446' (int) SAME maani jayein.
        Pehle plain str() compare hota tha, jisse same value hone par bhi
        false conflict dikhta tha (446.0 != 446 as strings). Baaki (text)
        columns pehle jaisa hi string compare (trimmed) karte hain."""
        if col in _NUMERIC_COMPARE_COLS:
            try:
                return float(old_val) != float(new_val)
            except (TypeError, ValueError):
                pass
        return str(old_val).strip() != str(new_val).strip()

    diesel_confirm_key = f"diesel_confirm_{bus_number}"
    diesel_pending_key = f"diesel_pending_{bus_number}"

    # ── ✅ Diesel-specific 3-button confirmation — sirf tab dikhta hai jab
    # kisi date ka Diesel field bhara ho AUR us date ka fuel_fills me pehle
    # se data ho. Yeh KM/Income wale generic conflict-confirmation (upar)
    # se bilkul alag/independent hai — dono ek saath bhi dikh sakte hain. ──
    if st.session_state.get(diesel_confirm_key):
        pending_diesel = st.session_state.get(diesel_pending_key, [])
        st.warning(
            f"⚠️ Neeche di gayi dates ka {fuel_label(bus_number)} data already maujood "
            f"hai — batao kya karna hai:"
        )
        for item in pending_diesel:
            st.markdown(f"📅 **{item['date']}** — naya entered value: **{item['qty']:.2f} L**")

        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            if st.button("✅ Yes, Update", key=f"diesel_yes_{bus_number}", width='stretch'):
                for item in pending_diesel:
                    rate_data = get_diesel_rate_payment(bus_number, item["month"], item["period"])
                    replace_fuel_fill_for_date(bus_number, item["date"], item["qty"], rate_data["rate"])
                st.session_state.pop(diesel_confirm_key, None)
                st.session_state.pop(diesel_pending_key, None)
                st.success(f"✅ {fuel_label(bus_number)} data update ho gaya (purani saari entries replace ho gayi)!")
                st.rerun()
        with dc2:
            if st.button("➕ Add Diesel", key=f"diesel_add_{bus_number}", width='stretch'):
                for item in pending_diesel:
                    rate_data = get_diesel_rate_payment(bus_number, item["month"], item["period"])
                    save_fuel_fill(bus_number, item["date"], item["qty"], rate_data["rate"])
                st.session_state.pop(diesel_confirm_key, None)
                st.session_state.pop(diesel_pending_key, None)
                st.success(f"✅ Naya {fuel_label(bus_number)} fill add ho gaya (purani entries wahi rahengi)!")
                st.rerun()
        with dc3:
            if st.button("❌ Cancel", key=f"diesel_cancel_{bus_number}", width='stretch'):
                st.session_state.pop(diesel_confirm_key, None)
                st.session_state.pop(diesel_pending_key, None)
                st.info(f"{fuel_label(bus_number)} change cancel ho gaya.")
                st.rerun()

    if st.session_state.get(confirm_key):
        conflict_df = st.session_state.get(pending_key)
        old_lookup  = st.session_state.get(f"{pending_key}_old", {})

        st.warning("⚠️ Neeche di gayi dates ki kuch values already bhari hui hain aur alag value se badal rahi hain — pehle compare kar lo:")
        # ✅ Poore conflict_df me se kaunse fields me actually conflict hai,
        # yeh collect karo — sirf unhi ke buttons dikhenge neeche (jaise sirf
        # KM change hua ho to Driver/Conductor button dikhega hi nahi).
        conflicting_fields = set()
        for _, new_row in conflict_df.iterrows():
            date_str = str(new_row["Date"])
            old_row  = old_lookup.get(date_str, {})
            diff_rows = []
            for col in _COMPARE_COLS:
                old_val = old_row.get(col, "")
                new_val = new_row.get(col, "")
                if not _is_empty_val(old_val) and not _is_empty_val(new_val) and _values_differ(col, old_val, new_val):
                    diff_rows.append({"Field": col, "Old Value": old_val, "New Value": new_val})
                    conflicting_fields.add(col)
            st.markdown(f"**📅 {date_str}**")
            if diff_rows:
                _render_html_table(pd.DataFrame(diff_rows))
            else:
                st.caption("(koi conflicting field nahi mila)")

        show_driver_btn    = "Driver Name" in conflicting_fields
        show_conductor_btn = "Conductor Name" in conflicting_fields
        show_sched_km_btn  = "Scheduled KM" in conflicting_fields
        show_actual_km_btn = "Actual KM" in conflicting_fields
        show_income_btn    = "Income" in conflicting_fields

        btn_specs = []
        if show_driver_btn:
            btn_specs.append(("🧑‍✈️ Sirf Driver", f"upd_driver_{bus_number}", ["driver_name"], "✅ Sirf Driver Name update hua — baaki fields purane hi rahe!"))
        if show_conductor_btn:
            btn_specs.append(("🎫 Sirf Conductor", f"upd_conductor_{bus_number}", ["conductor_name"], "✅ Sirf Conductor Name update hua — baaki fields purane hi rahe!"))
        if show_sched_km_btn:
            btn_specs.append(("📏 Sirf Scheduled KM", f"upd_sched_km_{bus_number}", ["scheduled_km"], "✅ Sirf Scheduled KM update hua — baaki fields purane hi rahe!"))
        if show_actual_km_btn:
            btn_specs.append(("🛣️ Sirf Actual KM", f"upd_actual_km_{bus_number}", ["actual_km"], "✅ Sirf Actual KM update hua — baaki fields purane hi rahe!"))
        if show_income_btn:
            btn_specs.append(("💰 Sirf Income", f"upd_income_{bus_number}", ["income"], "✅ Sirf Income update hua — baaki fields purane hi rahe!"))

        n_btns = len(btn_specs) + 2  # +2 for Sab Update aur Cancel
        cols = st.columns(n_btns)
        for i, (label, btn_key, fields, success_msg) in enumerate(btn_specs):
            with cols[i]:
                if st.button(label, key=btn_key, width='stretch'):
                    save_vehicle_records(bus_number, conflict_df, fields_to_update=fields)
                    st.success(success_msg)
                    st.session_state[reset_key] += 1
                    for k in [key, ed_key, fetch_key, confirm_key, pending_key, f"{pending_key}_old"]:
                        st.session_state.pop(k, None)
                    st.rerun()
        with cols[len(btn_specs)]:
            if st.button("✅ Sab Update", key=f"yes_{bus_number}", width='stretch'):
                save_vehicle_records(bus_number, conflict_df)
                st.success("✅ Saari fields update ho gayi!")
                st.session_state[reset_key] += 1
                for k in [key, ed_key, fetch_key, confirm_key, pending_key, f"{pending_key}_old"]:
                    st.session_state.pop(k, None)
                st.rerun()
        with cols[len(btn_specs) + 1]:
            if st.button("❌ Cancel", key=f"no_{bus_number}", width='stretch'):
                for k in [confirm_key, pending_key, f"{pending_key}_old"]:
                    st.session_state.pop(k, None)
                st.rerun()
    else:
        if st.button("💾 Save Changes", key=f"save_{bus_number}", width='stretch'):
            cleaned_df = edited_df[edited_df["Date"].notna()].copy()
            if cleaned_df.empty:
                st.warning("⚠️ No valid rows to save.")
                return

            # ── ✅ Cross-vehicle driver clash check — agar isi date pe
            # yehi driver naam kisi DUSRI vehicle me bhi 'Present' hai to
            # warning table dikhao. Ye sirf warning hai — save block nahi
            # hota, taaki genuine cases (jaise chota overlap, data-entry
            # correction ke waqt) rukein na. ──
            clashes = []
            for _, crow in cleaned_df.iterrows():
                if crow.get("Status") == "Present" and crow.get("Driver Name"):
                    clash_bus = check_driver_clash(crow["Driver Name"], str(crow["Date"]), bus_number)
                    if clash_bus:
                        clashes.append({
                            "Date": crow["Date"], "Driver": crow["Driver Name"], "Also Present on": clash_bus,
                        })
            if clashes:
                st.warning(
                    "⚠️ Driver clash mila — same date pe ye driver dusri vehicle mein bhi "
                    "'Present' hai (save phir bhi ho gaya, verify kar lo):"
                )
                _render_html_table(pd.DataFrame(clashes))

            # ── ✅ Diesel/CNG yahan bharoge to woh seedha vehicle_records.diesel
            # overwrite NAHI karta. Teen cases:
            # 1. Khaali → kuch nahi hota
            # 2. Positive value, us date ka fuel_fills me PEHLE SE koi data
            #    nahi → seedha naya fill add ho jaata hai (koi confirmation nahi)
            # 3. Positive value, us date ka data PEHLE SE hai → save nahi hota,
            #    3-button confirmation (Yes Update / Add Diesel / Cancel) upar
            #    dikhta hai agli baar page render hone par
            # 4. Explicitly 0 → us date ki saari existing fills clear ho jaati hain
            # save_fuel_fill()/clear_fuel_fills_for_date()/replace_fuel_fill_for_date()
            # internally us date ka vehicle_records.diesel total bhi khud sync
            # kar dete hain. ──
            new_fill_count      = 0
            cleared_date_count  = 0
            diesel_conflict_pending = []

            diesel_rows = [
                (idx, row) for idx, row in cleaned_df.iterrows()
                if row.get("Diesel") is not None and pd.notna(row.get("Diesel"))
            ]
            positive_dates = [
                str(row["Date"]) for _, row in diesel_rows if float(row["Diesel"]) > 0
            ]
            already_filled_dates = get_existing_fuel_fill_dates(bus_number, positive_dates)

            for idx, row in diesel_rows:
                qty = float(row["Diesel"])
                row_date_str = str(row["Date"])
                if qty > 0:
                    row_date   = pd.Timestamp(row["Date"])
                    row_period = "1-15" if row_date.day <= 15 else "16-31"
                    if row_date_str in already_filled_dates:
                        diesel_conflict_pending.append({
                            "date": row_date_str, "qty": qty,
                            "month": row_date.month, "period": row_period,
                        })
                    else:
                        rate_data = get_diesel_rate_payment(bus_number, row_date.month, row_period)
                        save_fuel_fill(bus_number, row_date_str, qty, rate_data["rate"])
                        new_fill_count += 1
                else:
                    # ✅ explicitly 0 — is date ki saari fills clear/reset karo
                    cleared = clear_fuel_fills_for_date(bus_number, row_date_str)
                    if cleared:
                        cleared_date_count += 1
                cleaned_df.at[idx, "Diesel"] = None  # ✅ vehicle_records save-path isko touch na kare

            if diesel_conflict_pending:
                st.session_state[diesel_pending_key] = diesel_conflict_pending
                st.session_state[diesel_confirm_key]  = True

            if fetch_key not in st.session_state:
                st.session_state[fetch_key] = get_vehicle_records(bus_number)
            fetched_df = st.session_state[fetch_key]

            existing_by_date = {}
            if not fetched_df.empty:
                for _, r in fetched_df.iterrows():
                    existing_by_date[str(r["Date"])] = r.to_dict()

            safe_rows, conflict_rows, conflict_old = [], [], {}
            for _, new_row in cleaned_df.iterrows():
                date_str = str(new_row["Date"])
                old_row  = existing_by_date.get(date_str)
                if old_row is None:
                    safe_rows.append(new_row)
                    continue
                has_conflict = False
                for col in _COMPARE_COLS:
                    old_val = old_row.get(col, "")
                    new_val = new_row.get(col, "")
                    if not _is_empty_val(old_val) and not _is_empty_val(new_val) and _values_differ(col, old_val, new_val):
                        has_conflict = True
                        break
                if has_conflict:
                    conflict_rows.append(new_row)
                    conflict_old[date_str] = old_row
                else:
                    safe_rows.append(new_row)  # ✅ sirf khaali fields bhar rahe ho, ya value same hai — direct save

            if safe_rows:
                save_vehicle_records(bus_number, pd.DataFrame(safe_rows))

            if conflict_rows:
                st.session_state[pending_key]              = pd.DataFrame(conflict_rows)
                st.session_state[f"{pending_key}_old"]      = conflict_old
                st.session_state[confirm_key]               = True
                msg_parts = []
                if safe_rows:
                    msg_parts.append(f"{len(safe_rows)} row(s) direct save ho gayi")
                if new_fill_count:
                    msg_parts.append(f"{new_fill_count} naya {fuel_label(bus_number)} fill add hua")
                if cleared_date_count:
                    msg_parts.append(f"{cleared_date_count} date ki {fuel_label(bus_number)} entries clear hui")
                if msg_parts:
                    st.success("✅ " + ", ".join(msg_parts) + ".")
                if diesel_conflict_pending:
                    st.info(f"ℹ️ {len(diesel_conflict_pending)} date(s) ke {fuel_label(bus_number)} data ke liye confirmation chahiye — neeche dekho.")
                st.session_state.pop(fetch_key, None)
                st.rerun()
            else:
                msg_parts = ["✅ Saved!"]
                if new_fill_count:
                    msg_parts.append(f"({new_fill_count} naya {fuel_label(bus_number)} fill bhi add hua)")
                if cleared_date_count:
                    msg_parts.append(f"({cleared_date_count} date ki {fuel_label(bus_number)} entries clear hui)")
                st.success(" ".join(msg_parts))
                if diesel_conflict_pending:
                    st.info(f"ℹ️ {len(diesel_conflict_pending)} date(s) ke {fuel_label(bus_number)} data ke liye confirmation chahiye — neeche dekho.")
                st.session_state[reset_key] += 1
                st.session_state.pop(key, None)
                st.session_state.pop(ed_key, None)
                st.session_state.pop(fetch_key, None)
                st.rerun()

    st.markdown("### Saved Records 📋")

    # ── Delete row by date ──
    with st.expander("🗑️ Delete a record by date"):
        del_date = st.date_input(
            "Select date to delete", value=None, format="DD-MM-YYYY",
            key=f"del_date_{bus_number}",
        )
        if st.button("Delete this record", key=f"del_btn_{bus_number}"):
            if del_date is None:
                st.warning("⚠️ Pehle ek date chuno.")
            else:
                delete_vehicle_record(bus_number, str(del_date))
                st.success(f"✅ Deleted record for {del_date}")
                st.session_state.pop(fetch_key, None)
                st.rerun()

    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_vehicle_records(bus_number)
    fetched_df = st.session_state[fetch_key]

    col_year, col1, col2, col3 = st.columns([1, 2, 2, 1])
    with col_year:
        year = year_selectbox(key=f"year_{bus_number}")
    with col1:
        month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1,
                             format_func=lambda x: date(2000, x, 1).strftime("%B"), key=f"month_{bus_number}")
    with col2:
        default_half = "1-15" if date.today().day <= 15 else "16-31"
        half = st.radio("Period", ["1-15", "16-31"], index=0 if default_half == "1-15" else 1,
                        horizontal=True, key=f"half_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key=f"refresh_{bus_number}", width='stretch'):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if not fetched_df.empty:
        display_df = fetched_df.copy()
        display_df["Date"] = pd.to_datetime(display_df["Date"])
        if "Next" not in display_df.columns:
            display_df["Next"] = False
        start, end           = _get_date_range(year, month, half)
        normal_mask          = (display_df["Date"] >= start) & (display_df["Date"] <= end) & (display_df["Next"] == False)
        prev_start, prev_end = shift_period_back(year, month, half)
        shifted_mask         = (display_df["Date"] >= prev_start) & (display_df["Date"] <= prev_end) & (display_df["Next"] == True)
        display_df           = display_df[normal_mask | shifted_mask]
        display_df["Date"]   = display_df["Date"].dt.strftime("%Y-%m-%d")
        if "Diesel KM" not in display_df.columns:
            display_df["Diesel KM"] = 0
        display_df["Avg"] = (
            pd.to_numeric(display_df["Diesel KM"], errors="coerce") /
            pd.to_numeric(display_df["Diesel"], errors="coerce").replace(0, float("nan"))
        ).round(2)
        for col, default in [("Income", 0), ("Remark", "")]:
            if col not in display_df.columns:
                display_df[col] = default
        display_df = display_df[["Date", "Status", "Driver Name", "Conductor Name",
                                  "Scheduled KM", "Actual KM", "Diesel", "Diesel KM",
                                  "Avg", "Income", "Remark", "Next"]]

        # ── ✅ Split-duty override — jis date ka split-duty entry hai, uska
        # Driver Name / Conductor Name column yahan grid mein khud "Naam1
        # (KM1) / Naam2 (KM2)" format mein dikhega, seedha DB se — manual
        # "A / B" type karne ki zaroorat nahi. ──
        _splits_for_grid = get_duty_splits(bus_number, display_df["Date"].tolist())
        if not _splits_for_grid.empty:
            _split_lookup = {str(r["Date"]): r for _, r in _splits_for_grid.iterrows()}

            def _split_display(date_str, p1_col, p1km_col, p2_col, p2km_col, fallback):
                r = _split_lookup.get(date_str)
                if r is None:
                    return fallback
                p1, p1km = str(r.get(p1_col) or "").strip(), float(r.get(p1km_col) or 0)
                p2, p2km = str(r.get(p2_col) or "").strip(), float(r.get(p2km_col) or 0)
                if p1 and p2 and (p1km + p2km) > 0:
                    return f"{p1} ({p1km:.0f}) / {p2} ({p2km:.0f})"
                return fallback

            display_df["Driver Name"] = display_df.apply(
                lambda r: _split_display(r["Date"], "Driver 1", "Driver 1 KM", "Driver 2", "Driver 2 KM", r["Driver Name"]),
                axis=1,
            )
            display_df["Conductor Name"] = display_df.apply(
                lambda r: _split_display(r["Date"], "Conductor 1", "Conductor 1 KM", "Conductor 2", "Conductor 2 KM", r["Conductor Name"]),
                axis=1,
            )

        # ── ✅ Split Duty section — is loaded period ki dates ke liye ──
        with st.expander("👥 Split Duty (ek din, 2 log KM ke hisaab se)"):
            _split_duty_section(bus_number, display_df["Date"].tolist())

        # ── Kayi din ke KM combine karo (Excel jaisa merge cell) — same period me kayi groups ho sakte hain ──
        date_options = display_df["Date"].tolist()
        combine_key = f"km_combines_{bus_number}"
        if combine_key not in st.session_state:
            st.session_state[combine_key] = get_km_combines(bus_number)
        # sirf wahi groups rakho jinki saari dates is loaded period me maujood hain
        active_groups = [
            g for g in st.session_state[combine_key]
            if all(d in date_options for d in g["dates"])
        ]

        # Overlapping/duplicate groups detect karo (jaise purani testing se stale entries)
        # — inhi ki wajah se table half-broken dikhti thi, ab UI me clearly flag karte hain.
        _claimed = set()
        overlapping_group_ids = set()
        for g in active_groups:
            if any(d in _claimed for d in g["dates"]):
                overlapping_group_ids.add(g["id"])
            else:
                _claimed.update(g["dates"])

        if active_groups:
            _render_km_merged_table(display_df, active_groups)
        else:
            _render_html_table(display_df)

        if overlapping_group_ids:
            st.warning(
                "⚠️ Kuch combined groups ki dates overlap kar rahi hain (purani/duplicate "
                "entries ho sakti hain) — neeche ⚠️ mark ki hui groups ko 'Hatao' se hata do."
            )

        used_dates = {d for g in active_groups for d in g["dates"]}
        available_dates = [d for d in date_options if d not in used_dates]

        if active_groups or len(available_dates) >= 2:
            with st.expander("🔗 Kayi Din Ka KM Combine Karo"):
                if len(available_dates) >= 2:
                    selected_dates = st.multiselect(
                        "Combine karne ke liye dates chuno (2 ya usse zyada)",
                        options=available_dates, key=f"combine_multi_{bus_number}",
                    )
                    if st.button("Combine Karo", key=f"combine_btn_{bus_number}",
                                 disabled=len(selected_dates) < 2):
                        save_km_combine(bus_number, selected_dates)
                        st.session_state[combine_key] = get_km_combines(bus_number)
                        st.rerun()
                    if 0 < len(selected_dates) < 2:
                        st.caption("⚠️ Kam se kam 2 dates chuno.")

                if active_groups:
                    st.caption("Combined groups:")
                    for g in active_groups:
                        dates = g["dates"]
                        rows_g = [display_df[display_df["Date"] == d] for d in dates]
                        sch_vals = [pd.to_numeric(r["Scheduled KM"].iloc[0], errors="coerce") if not r.empty else 0 for r in rows_g]
                        act_vals = [pd.to_numeric(r["Actual KM"].iloc[0], errors="coerce") if not r.empty else 0 for r in rows_g]
                        inc_vals = [pd.to_numeric(r["Income"].iloc[0], errors="coerce") if not r.empty else 0 for r in rows_g]
                        sch_sum = sum(v for v in sch_vals if pd.notna(v))
                        act_sum = sum(v for v in act_vals if pd.notna(v))
                        inc_sum = sum(v for v in inc_vals if pd.notna(v))
                        is_overlap = g["id"] in overlapping_group_ids
                        label = f"{'⚠️ ' if is_overlap else '🔗 '}{' + '.join(dates)}"
                        rc1, rc2, rc3 = st.columns([3, 1, 1])
                        with rc1:
                            st.markdown(
                                f"<span style='{'color:#FFB347;' if is_overlap else ''}'>{label}</span>",
                                unsafe_allow_html=True,
                            )
                        with rc2:
                            # ✅ Mobile-friendly — button tap karke breakdown dikhega,
                            # hover tooltip ki tarah phone pe fail nahi hoga
                            if st.button("🔍 Details", key=f"combine_detail_{bus_number}_{g['id']}"):
                                st.session_state[f"show_detail_{bus_number}_{g['id']}"] = \
                                    not st.session_state.get(f"show_detail_{bus_number}_{g['id']}", False)
                        with rc3:
                            if st.button("❌ Hatao", key=f"uncombine_btn_{bus_number}_{g['id']}"):
                                delete_km_combine(bus_number, g["id"])
                                st.session_state[combine_key] = get_km_combines(bus_number)
                                st.rerun()
                        if st.session_state.get(f"show_detail_{bus_number}_{g['id']}"):
                            detail_rows = [
                                {"Date": d, "Scheduled KM": s, "Actual KM": a, "Income": inc}
                                for d, s, a, inc in zip(dates, sch_vals, act_vals, inc_vals)
                            ]
                            detail_rows.append({
                                "Date": "TOTAL", "Scheduled KM": sch_sum, "Actual KM": act_sum, "Income": inc_sum,
                            })
                            _render_html_table(pd.DataFrame(detail_rows))

        total_row = build_total_row(display_df, numeric_cols, label_col="Driver Name")
        _render_html_table(pd.DataFrame(columns=total_row.columns), total_row=total_row.iloc[0].to_dict())

        # ── 💰 Payment Summary — 2 methods, per-vehicle chosen + saved.
        # Dono methods ke result me se 1% tax + fixed deduction minus hoke
        # Final Payment banta hai. ──
        st.markdown("#### 💰 Payment Summary")
        cfg_key = f"payment_cfg_{bus_number}"
        if cfg_key not in st.session_state:
            st.session_state[cfg_key] = get_vehicle_payment_config(bus_number)
        cfg = st.session_state[cfg_key]

        method_label = st.radio(
            "Payment Method (is vehicle ke liye)",
            ["Standard (Income − KM×Rate − Tax)", "IPKM Slab (kuch vehicles ke liye)"],
            index=0 if cfg["method"] == "standard" else 1,
            key=f"payment_method_{bus_number}", horizontal=True,
        )
        method = "standard" if "Standard" in method_label else "ipkm_slab"

        if method == "standard":
            pc1, pc2 = st.columns([2, 1])
            with pc1:
                payment_rate = st.number_input(
                    "Rate per Actual KM (₹)", min_value=0.0, step=0.5, format="%.2f",
                    value=float(cfg["rate"]), key=f"payment_rate_input_{bus_number}",
                )
            threshold, deduction = cfg["ipkm_threshold"], cfg["ipkm_deduction"]
        else:
            ic1, ic2 = st.columns(2)
            with ic1:
                threshold = st.number_input(
                    "IPKM Threshold (amount1)", min_value=0.0, step=0.1, format="%.2f",
                    value=float(cfg["ipkm_threshold"]), key=f"ipkm_threshold_{bus_number}",
                )
            with ic2:
                deduction = st.number_input(
                    "Deduction (amount2)", min_value=0.0, step=0.1, format="%.2f",
                    value=float(cfg["ipkm_deduction"]), key=f"ipkm_deduction_{bus_number}",
                )
            payment_rate = cfg["rate"]

        # ── Final step — dono methods ke liye common (1% + fixed amount) ──
        fd1, fd2 = st.columns(2)
        with fd1:
            final_deduction = st.number_input(
                "Final Fixed Deduction (₹) — payment banne ke baad minus hoga",
                min_value=0.0, step=50.0, format="%.2f",
                value=float(cfg["final_deduction"]), key=f"final_deduction_{bus_number}",
            )
        with fd2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Save Payment Config", key=f"save_payment_cfg_{bus_number}", width='stretch'):
                save_vehicle_payment_config(bus_number, payment_rate, method, threshold, deduction, final_deduction)
                st.session_state[cfg_key] = get_vehicle_payment_config(bus_number)
                st.success("✅ Saved!")
                st.rerun()

        total_income    = pd.to_numeric(display_df["Income"], errors="coerce").fillna(0).sum()
        total_actual_km = pd.to_numeric(display_df["Actual KM"], errors="coerce").fillna(0).sum()
        PERIOD_TAX      = 11700  # ✅ fixed, har period (chahe 15 din ho ya kam/zyada) ke liye ek hi baar

        if method == "standard":
            km_cost = total_actual_km * payment_rate
            raw_payment = total_income - km_cost - PERIOD_TAX
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Total Income", f"₹{total_income:,.0f}")
            mc2.metric("KM Cost", f"₹{km_cost:,.0f}", help=f"{total_actual_km:,.0f} km × ₹{payment_rate:.2f}")
            mc3.metric("Tax (fixed)", f"₹{PERIOD_TAX:,.0f}")
            mc4.metric("Payment (before final cut)", f"₹{raw_payment:,.0f}")
        else:
            ipkm = (total_income - PERIOD_TAX) / total_actual_km if total_actual_km > 0 else 0
            if ipkm < threshold:
                raw_payment = (ipkm - deduction) * total_actual_km
                slab_used = "Below threshold"
            else:
                # ✅ At/above threshold — High Rate hataya, ab (Threshold − Deduction) × KM
                raw_payment = (threshold - deduction) * total_actual_km
                slab_used = "At/Above threshold"
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Total Income", f"₹{total_income:,.0f}")
            mc2.metric("IPKM", f"₹{ipkm:.2f}", help="(Total Income − Tax) / Total Actual KM")
            mc3.metric("Slab Used", slab_used)
            mc4.metric("Payment (before final cut)", f"₹{raw_payment:,.0f}")

        # ── Final Payment = raw_payment − tax% − final_deduction.
        # Tax % method ke hisaab se alag: IPKM Slab = 2%, Standard = 1% ──
        tax_pct        = 0.02 if method == "ipkm_slab" else 0.01
        tax_amount     = raw_payment * tax_pct
        final_payment  = raw_payment - tax_amount - final_deduction
        fp1, fp2, fp3 = st.columns(3)
        fp1.metric(f"{int(tax_pct*100)}% Tax", f"₹{tax_amount:,.0f}")
        fp2.metric("Final Fixed Deduction", f"₹{final_deduction:,.0f}")
        fp3.metric("💵 Final Payment", f"₹{final_payment:,.0f}")

        pdf_bytes = _generate_pdf(display_df, total_row, bus_number, month, half)
        st.download_button("📥 Download PDF", data=pdf_bytes,
                           file_name=f"vehicle_records_{bus_number}_{date(2000,month,1).strftime('%B')}_{half.replace('-','_')}.pdf",
                           mime="application/pdf", key=f"pdf_{bus_number}")
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 2. DRIVER SALARY
# ──────────────────────────────────────────────
def driver_salary(bus_number: str = ""):
    key       = f"driver_salary_{bus_number}"
    ed_key    = f"editor_salary_{bus_number}"
    fetch_key = f"fetched_salary_{bus_number}"

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":        [date.today()],
            "Driver Name": [None],
            "Salary":      [0],
            "Transaction": [""],
        })

    st.markdown("### Driver Salary 💰")
    st.data_editor(
    st.session_state[key],
    num_rows="dynamic",
    width='stretch',
    hide_index=True,
    key=ed_key,
    column_config={
        "Date":        st.column_config.DateColumn("Date", default=date.today()),
        "Driver Name": st.column_config.TextColumn("Driver Name"),
        "Salary":      st.column_config.NumberColumn("Salary", min_value=0, default=0),
        "Transaction": st.column_config.SelectboxColumn("Transaction", options=["cash", "online"], default="cash"),
    },
)

    editor_state = st.session_state.get(ed_key, {})
    edited_df    = _apply_editor_state(st.session_state[key], editor_state)

    if st.button("💾 Save Changes", key=f"save_salary_{bus_number}"):
        cleaned_df = edited_df[
            edited_df["Driver Name"].notna() &
            (edited_df["Driver Name"].astype(str).str.strip() != "")
        ].copy()
        if cleaned_df.empty:
            st.warning("⚠️ No valid rows to save.")
            return
        save_driver_salary(cleaned_df, bus_number=bus_number)
        st.success("✅ Saved!")
        st.session_state.pop(key, None)
        st.session_state.pop(ed_key, None)  
        st.session_state.pop(fetch_key, None)
        st.rerun()
        
    st.markdown("### Saved Salary Records 📋")
    col_year, col1, col2, col3 = st.columns([1, 2, 2, 1])
    with col_year:
        sal_year = year_selectbox(key=f"sal_year_{bus_number}")
    with col1:
        sal_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1,
                                 format_func=lambda x: date(2000, x, 1).strftime("%B"),
                                 key=f"sal_month_{bus_number}")
    with col2:
        default_half = "1-15" if date.today().day <= 15 else "16-31"
        sal_half = st.radio("Period", ["1-15", "16-31"], index=0 if default_half == "1-15" else 1,
                            horizontal=True, key=f"sal_half_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key=f"ref_sal_{bus_number}", width='stretch'):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_driver_salary(bus_number=bus_number)
    fetched_df = st.session_state[fetch_key]

    if not fetched_df.empty:
        disp = fetched_df.copy()
        disp["Date"] = pd.to_datetime(disp["Date"])
        start, end   = _get_date_range(sal_year, sal_month, sal_half)
        disp         = disp[(disp["Date"] >= start) & (disp["Date"] <= end)].copy()
        disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")

        st.data_editor(
            disp, width='stretch', hide_index=True, num_rows="dynamic",
            key=f"edit_sal_{bus_number}",
            column_config={
                "id":          None,
                "Date":        st.column_config.TextColumn("Date"),
                "Driver Name": st.column_config.TextColumn("Driver Name"),
                "Salary":      st.column_config.NumberColumn("Salary", min_value=0),
                "Transaction": st.column_config.TextColumn("Transaction"),
                "Updated By":  None,
            }
        )

        if st.button("💾 Update Salary", key=f"update_sal_{bus_number}"):
            sal_state = st.session_state.get(f"edit_sal_{bus_number}", {})
            for row_idx, changes in sal_state.get("edited_rows", {}).items():
                update_driver_salary(disp.iloc[row_idx]["id"], changes)
            for row_idx in sorted(sal_state.get("deleted_rows", []), reverse=True):
                delete_driver_salary(disp.iloc[row_idx]["id"])
            st.success("✅ Updated!")
            st.session_state.pop(fetch_key, None)
            st.rerun()

        total_row = build_total_row(disp, ["Salary"], label_col="Driver Name")
        _render_html_table(pd.DataFrame(columns=total_row.columns), total_row=total_row.iloc[0].to_dict())
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 3. VEHICLE EXPENSES
# ──────────────────────────────────────────────
def expenses(bus_number: str = ""):
    key       = f"expenses_{bus_number}"
    ed_key    = f"editor_expenses_{bus_number}"
    fetch_key = f"fetched_expenses_{bus_number}"

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":        [date.today()],
            "Category":    [""],
            "Amount":      [0],
            "Description": [""],
        })

    st.markdown("### Vehicle Expenses 🧾")
    st.data_editor(
        st.session_state[key],
        num_rows="dynamic",
        width='stretch',
        hide_index=True,
        key=ed_key,
        column_config={
            "Date":        st.column_config.DateColumn("Date", default=date.today()),
            "Category":    st.column_config.TextColumn("Category"),
            "Amount":      st.column_config.NumberColumn("Amount", min_value=0, default=0),
            "Description": st.column_config.TextColumn("Description"),
        },
    )

    editor_state = st.session_state.get(ed_key, {})
    edited_df    = _apply_editor_state(st.session_state[key], editor_state)

    if st.button("💾 Save Changes", key=f"save_expenses_{bus_number}"):
        cleaned_df = edited_df[
            edited_df["Category"].notna() &
            (edited_df["Category"].str.strip() != "")
        ].copy()
        if cleaned_df.empty:
            st.warning("⚠️ No valid rows to save.")
            return
        save_vehicle_expenses(bus_number, cleaned_df)
        st.success("✅ Saved!")
        st.session_state.pop(key, None)
        st.session_state.pop(ed_key, None)  
        st.session_state.pop(fetch_key, None)
        st.rerun()

    st.markdown("### Saved Expenses 📋")
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_vehicle_expenses(bus_number)
    fetched_df = st.session_state[fetch_key]

    col_year, col1, col2, col3 = st.columns([1, 2, 2, 1])
    with col_year:
        exp_year = year_selectbox(key=f"exp_year_{bus_number}")
    with col1:
        exp_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1,
                                 format_func=lambda x: date(2000, x, 1).strftime("%B"),
                                 key=f"exp_month_{bus_number}")
    with col2:
        exp_period = st.radio("Period", ["1-15", "16-31", "01-31"], index=2,
                              horizontal=True, key=f"exp_period_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", key=f"ref_exp_{bus_number}", width='stretch'):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if not fetched_df.empty:
        display_exp = fetched_df.copy()
        display_exp["Date"] = pd.to_datetime(display_exp["Date"])
        start, end  = _get_date_range(exp_year, exp_month, exp_period)
        display_exp = display_exp[(display_exp["Date"] >= start) & (display_exp["Date"] <= end)].copy()
        display_exp["Date"] = display_exp["Date"].dt.strftime("%Y-%m-%d")

        st.data_editor(
            display_exp, width='stretch', hide_index=True, num_rows="dynamic",
            key=f"edit_exp_{bus_number}",
            column_config={
                "id":          None,
                "Date":        st.column_config.TextColumn("Date"),
                "Category":    st.column_config.TextColumn("Category"),
                "Amount":      st.column_config.NumberColumn("Amount", min_value=0),
                "Description": st.column_config.TextColumn("Description"),
            }
        )

        if st.button("💾 Update Expenses", key=f"update_exp_{bus_number}"):
            exp_state = st.session_state.get(f"edit_exp_{bus_number}", {})
            for row_idx, changes in exp_state.get("edited_rows", {}).items():
                update_vehicle_expense(display_exp.iloc[row_idx]["id"], changes)
            for row_idx in sorted(exp_state.get("deleted_rows", []), reverse=True):
                delete_vehicle_expense(display_exp.iloc[row_idx]["id"])
            st.success("✅ Updated!")
            st.session_state.pop(fetch_key, None)
            st.rerun()

        total_amount = pd.to_numeric(display_exp["Amount"], errors="coerce").sum()
        st.markdown(f"""
        <div style='background:#2D2D5E;border-radius:8px;padding:12px 20px;margin-top:8px;'>
            <span style='color:#aaa;'>Total: </span>
            <span style='color:#7B8CFF;font-size:1.2rem;font-weight:bold;'>₹{total_amount:,.0f}</span>
        </div>""", unsafe_allow_html=True)

        pdf_data = _generate_expenses_pdf(
            display_exp[["Date", "Category", "Amount", "Description"]],
            bus_number, exp_month, exp_period
        )
        st.download_button("📥 Download PDF", data=pdf_data,
                           file_name=f"expenses_{bus_number}_{date(2000,exp_month,1).strftime('%B')}_{exp_period.replace('-','_')}.pdf",
                           mime="application/pdf", key=f"exp_pdf_{bus_number}")
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 4. DIESEL / CNG VIEW — multiple fills per date allowed
# ──────────────────────────────────────────────
def diesel_view(bus_number: str = ""):
    fuel = fuel_label(bus_number)
    st.markdown(f"### {fuel} View ⛽")

    col_year, col1, col2, col3 = st.columns([1, 2, 2, 1])
    with col_year:
        d_year = year_selectbox(key=f"diesel_year_{bus_number}")
    with col1:
        d_month = st.selectbox("Month", options=list(range(1, 13)),
                               index=date.today().month - 1,
                               format_func=lambda x: date(2000, x, 1).strftime("%B"),
                               key=f"diesel_month_{bus_number}")
    with col2:
        d_period = st.radio("Period", ["1-15", "16-31", "01-31"],
                            index=2, horizontal=True,
                            key=f"diesel_period_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        load = st.button("🔄 Load", key=f"diesel_load_{bus_number}", width='stretch')

    # ✅ DB se rate + payment load karo (bus + month + period wise)
    # ⚠️ NOTE: diesel_details table sirf (bus_number, month, period) se keyed
    # hai — koi 'year' column nahi hai. Matlab neeche wala "Default rate"
    # aur "Payment Status" har saal ke isi month+period ke liye SAME record
    # dikhayega/save karega (fuel_fills ki actual entries neeche year ke
    # hisaab se sahi filter hoti hain, sirf yeh rate/payment config alag hai).
    state_key = f"diesel_state_{bus_number}_{d_month}_{d_period}"
    if state_key not in st.session_state or load:
        st.session_state[state_key] = get_diesel_rate_payment(bus_number, d_month, d_period)

    saved = st.session_state[state_key]

    universal_rate = st.number_input(
        f"⛽ Default rate ({fuel})",
        min_value=0.0, step=0.01, format="%.2f",
        value=saved["rate"],
        key=f"diesel_rate_input_{bus_number}_{d_month}_{d_period}"
    )

    start, end = _get_date_range(d_year, d_month, d_period)

    # ── ✅ Naya fill add karo — ek din mein jitni baar chaho fill kar sakte ho ──
    st.markdown(f"#### ➕ Add {fuel} Fill")
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1])
    with fc1:
        fill_date = st.date_input("Date", value=date.today(), key=f"fill_date_{bus_number}")
    with fc2:
        fill_qty = st.number_input(f"{fuel} (L)", min_value=0.0, step=0.01, format="%.2f",
                                    key=f"fill_qty_{bus_number}")
    with fc3:
        fill_rate = st.number_input("Rate (₹/L)", min_value=0.0, step=0.01, format="%.2f",
                                     value=universal_rate, key=f"fill_rate_{bus_number}")
    with fc4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add", key=f"fill_add_{bus_number}", width='stretch'):
            if fill_qty > 0:
                save_fuel_fill(bus_number, str(fill_date), fill_qty, fill_rate)
                st.session_state.pop(f"fills_df_{bus_number}", None)
                st.success("✅ Entry added!")
                st.rerun()
            else:
                st.warning(f"⚠️ {fuel} quantity 0 se zyada honi chahiye.")

    fetch_key = f"fills_df_{bus_number}"
    if load or fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_fuel_fills(
            bus_number, str(start.date()), str(end.date())
        )
    df = st.session_state.get(fetch_key, pd.DataFrame())

    # ── Migration nudge — sirf df empty hone par nahi, balki JAB BHI
    # kahin bhi (kisi bhi period me) legacy vehicle_records.diesel data
    # ho jo fuel_fills me abhi tak nahi aaya — taaki koi bhi date miss na ho ──
    unmigrated_dates = get_unmigrated_diesel_dates(bus_number)
    if unmigrated_dates:
        st.warning(
            f"⚠️ Vehicle Records tab me {len(unmigrated_dates)} din ka purana "
            f"{fuel.lower()} data bhara hua hai jo abhi yahan nahi aaya."
        )
        with st.expander("🔍 Kaunsi dates flag ho rahi hain (debug)"):
            st.write(sorted(unmigrated_dates))
        if st.button(f"📦 Purana {fuel} data migrate karo ({len(unmigrated_dates)} din)", key=f"migrate_{bus_number}"):
            count = migrate_diesel_to_fuel_fills(bus_number)
            st.session_state.pop(fetch_key, None)
            if count:
                st.success(f"✅ {count} purani entries migrate ho gayi! Refresh ho raha hai...")
            else:
                st.error(
                    "⚠️ Koi entry migrate nahi hui — matlab in dates ka diesel value 0 ya "
                    "khaali hai (sirf date column ka mismatch tha), ya fuel_fills me pehle "
                    "se hi (kisi aur reason se) row maujood hai. Neeche dates check karo."
                )
            st.rerun()

    if df.empty:
        st.info(f"No {fuel.lower()} records found for this period.")
        return

    st.markdown(f"#### 📋 All {fuel} Entries (individual fills)")
    st.caption("✏️ Rate/Qty edit karne ke liye cell pe click karo.")
    ed_key = f"diesel_editor_{bus_number}"
    st.data_editor(
        df, width='stretch', hide_index=True, key=ed_key,
        column_config={
            "id":       None,
            "Date":     st.column_config.TextColumn("Date", disabled=True),
            "Quantity": st.column_config.NumberColumn(f"{fuel} (L)", min_value=0.0, format="%.2f"),
            "Rate":     st.column_config.NumberColumn("Rate (₹/L)", min_value=0.0, format="%.2f"),
            "Amount":   st.column_config.NumberColumn("Amount (₹)", disabled=True, format="%.2f"),
        }
    )
    editor_state = st.session_state.get(ed_key, {})
    if editor_state.get("edited_rows"):
        changed = False
        for row_idx, changes in editor_state["edited_rows"].items():
            if row_idx < len(df):
                update_fuel_fill(bus_number, df.iloc[row_idx]["id"], changes)
                changed = True
        if changed:
            st.session_state.pop(fetch_key, None)
            st.session_state.pop(ed_key, None)
            st.rerun()

    # ── ✅ Explicit Delete section — data_editor ka checkbox-select+Delete-key
    # tarika hide_index ke saath bharosemand nahi hai, isliye ek guaranteed
    # dropdown+button diya hai (Vehicle Records tab ke "Delete by date" jaisa) ──
    with st.expander(f"🗑️ Ek {fuel} entry delete karo"):
        options = {
            f"{row['Date']} — {row['Quantity']:.2f} L @ ₹{row['Rate']:.2f} (₹{row['Amount']:.2f})": row["id"]
            for _, row in df.iterrows()
        }
        if options:
            selected_label = st.selectbox("Entry chuno", options=list(options.keys()), key=f"del_fill_select_{bus_number}")
            if st.button("Delete this entry", key=f"del_fill_btn_{bus_number}"):
                delete_fuel_fill(bus_number, options[selected_label])
                st.success("✅ Entry delete ho gayi!")
                st.session_state.pop(fetch_key, None)
                st.session_state.pop(ed_key, None)
                st.rerun()
        else:
            st.caption("Koi entry nahi hai delete karne ke liye.")

    # ── ✅ Date-wise summary — same date ke multiple fills yahan add hoke dikhenge ──
    st.markdown(f"#### 📊 Date-wise {fuel} Summary")
    summary_df = df.groupby("Date").agg(
        Fills=("id", "count"), Total_Qty=("Quantity", "sum"), Total_Amount=("Amount", "sum")
    ).reset_index()
    summary_df.columns = ["Date", "Fills", f"Total {fuel} (L)", "Total Amount (₹)"]
    _render_html_table(summary_df)

    total_diesel = df["Quantity"].sum()
    total_amount = df["Amount"].sum()

    # ── Summary cards ──
    st.markdown(f"""
    <div style='background:#1e1e3a;border-radius:10px;padding:16px 24px;margin:12px 0;
                display:flex;gap:40px;flex-wrap:wrap;'>
        <div>
            <div style='color:#aaa;font-size:0.85rem;'>Total {fuel}</div>
            <div style='color:#7B8CFF;font-size:1.3rem;font-weight:bold;'>{total_diesel:.2f} L</div>
        </div>
        <div>
            <div style='color:#aaa;font-size:0.85rem;'>Total Amount</div>
            <div style='color:#FFB347;font-size:1.3rem;font-weight:bold;'>₹{total_amount:,.2f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Payment Status (editable + saved per bus+month+period) ──
    st.markdown("#### Payment Status")

    edit_mode_key = f"diesel_pay_edit_{bus_number}_{d_month}_{d_period}"
    if edit_mode_key not in st.session_state:
        st.session_state[edit_mode_key] = False

    is_locked = saved["payment_done"] and not st.session_state[edit_mode_key]

    pay_col1, pay_col2 = st.columns(2)
    with pay_col1:
        paid_amount = st.number_input(
            "Amount Paid (₹)", min_value=0.0, step=0.01, format="%.2f",
            value=saved["paid_amount"],
            disabled=is_locked,
            key=f"diesel_paid_input_{bus_number}_{d_month}_{d_period}"
        )
    with pay_col2:
        payment_done = st.checkbox(
            "✅ Payment Done",
            value=saved["payment_done"],
            disabled=is_locked,
            key=f"diesel_pay_chk_{bus_number}_{d_month}_{d_period}"
        )

    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("💾 Save Rate & Payment", key=f"diesel_save_{bus_number}_{d_month}_{d_period}",
                     width='stretch'):
            save_diesel_rate_payment(bus_number, d_month, d_period,
                                      universal_rate, paid_amount, payment_done)
            st.session_state[state_key] = {
                "rate": universal_rate, "paid_amount": paid_amount, "payment_done": payment_done
            }
            st.session_state[edit_mode_key] = False
            st.success("✅ Saved!")
            st.rerun()
    with btn_col2:
        if saved["payment_done"] and not st.session_state[edit_mode_key]:
            if st.button("✏️ Edit Payment", key=f"diesel_edit_{bus_number}_{d_month}_{d_period}",
                         width='stretch'):
                st.session_state[edit_mode_key] = True
                st.rerun()

    remaining = total_amount - paid_amount
    if payment_done or remaining <= 0:
        st.markdown("""
        <div style='background:#1B5E20;border-radius:10px;padding:14px 24px;margin-top:10px;'>
            <span style='color:#69F0AE;font-size:1.1rem;font-weight:bold;'>✅ Fully Paid</span>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style='background:#4a1010;border-radius:10px;padding:14px 24px;margin-top:10px;
                    display:flex;justify-content:space-between;align-items:center;'>
            <span style='color:#FF5252;font-size:1.1rem;font-weight:bold;'>⚠️ Payment Pending</span>
            <span style='color:#FFB347;font-size:1.2rem;font-weight:bold;'>Remaining: ₹{remaining:,.2f}</span>
        </div>""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 5. SALARY CHECK
# ──────────────────────────────────────────────
def salary_check_view():
    st.markdown("### Salary Check 📊")
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        from_date = st.date_input("From", value=None, key="sc_from", format="YYYY-MM-DD")
    with col2:
        to_date = st.date_input("To", value=None, key="sc_to", format="YYYY-MM-DD")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key="sc_load"):
            st.session_state["salary_check_df"] = get_salary_check(
                from_date=str(from_date) if from_date else None,
                to_date=str(to_date) if to_date else None,
            )
    if "salary_check_df" in st.session_state:
        df = st.session_state["salary_check_df"]
        if not df.empty:
            _render_html_table(df)
        else:
            st.info("No data found.")
