from supabase import create_client
from datetime import date
import streamlit as st
import pandas as pd

# Supabase client — apni keys daal
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def editable_grid(bus_number: str):
    numeric_cols = ["Scheduled KM", "Actual KM", "Diesel", "Avg"]

    # ✅ Supabase se fetch — us bus ke records
    response = supabase.table("vehicle_records") \
        .select("*") \
        .eq("bus_number", bus_number) \
        .order("date", desc=False) \
        .execute()

    rows = response.data

    if rows:
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            "date":           "Date",
            "driver_name":    "Driver Name",
            "conductor_name": "Conductor Name",
            "scheduled_km":   "Scheduled KM",
            "actual_km":      "Actual KM",
            "diesel":         "Diesel",
        })
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df = df[["Date", "Driver Name", "Conductor Name", "Scheduled KM", "Actual KM", "Diesel"]]
    else:
        # Pehli baar — empty default
        df = pd.DataFrame({
            "Date":           [date.today()],
            "Driver Name":    [""],
            "Conductor Name": [""],
            "Scheduled KM":   [0],
            "Actual KM":      [0],
            "Diesel":         [0],
        })

    st.markdown("### Vehicle Records 🚐")

    # Session state fix — tab switch pe reset na ho
    key = f"grid_{bus_number}"
    if key not in st.session_state:
        st.session_state[key] = df

    edited_df = st.data_editor(
        st.session_state[key],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"editor_{bus_number}",
        column_config={
            "Date":           st.column_config.DateColumn("Date", default=date.today()),
            "Driver Name":    st.column_config.TextColumn("Driver Name"),
            "Conductor Name": st.column_config.TextColumn("Conductor Name"),
            "Scheduled KM":   st.column_config.NumberColumn("Scheduled KM", min_value=0, default=466),
            "Actual KM":      st.column_config.NumberColumn("Actual KM", min_value=0, default=0),
            "Diesel":         st.column_config.NumberColumn("Diesel", min_value=0, default=0),
        }
    )
    st.session_state[key] = edited_df

    edited_df["Avg"] = (edited_df["Actual KM"] / edited_df["Diesel"].replace(0, 1)).round(2)

    total_row  = build_total_row(edited_df, numeric_cols, label_col="Driver Name")
    display_df = pd.concat([edited_df, total_row], ignore_index=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if st.button("💾 Save Changes", key=f"save_{bus_number}"):
        cleaned_df = edited_df.dropna(subset=["Driver Name"]).copy()
        cleaned_df["Avg"] = (cleaned_df["Actual KM"] / cleaned_df["Diesel"].replace(0, 1)).round(2)

        # ✅ Supabase mein save
        records = []
        for _, row in cleaned_df.iterrows():
            records.append({
                "bus_number":     bus_number,
                "date":           str(row["Date"]),
                "driver_name":    row["Driver Name"],
                "conductor_name": row["Conductor Name"],
                "scheduled_km":   float(row["Scheduled KM"]),
                "actual_km":      float(row["Actual KM"]),
                "diesel":         float(row["Diesel"]),
            })

        # Pehle us bus ke aaj ke records delete karo, phir insert
        supabase.table("vehicle_records") \
            .delete() \
            .eq("bus_number", bus_number) \
            .execute()

        supabase.table("vehicle_records") \
            .insert(records) \
            .execute()

        st.success("✅ Saved to database!")
        st.session_state.pop(key, None)  # cache clear — fresh fetch hoga
        st.rerun()