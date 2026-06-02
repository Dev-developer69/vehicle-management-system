import streamlit as st
import pandas as pd
from datetime import date


def build_total_row(edited_df, numeric_cols, label_col="Driver Name"):
    total_values = {}
    for col in edited_df.columns:
        if col == label_col:
            total_values[col] = "TOTAL"
        
        elif col == "Avg":
            total_values[col] = round(float(edited_df["Avg"].mean()), 2)
        
        elif col in numeric_cols:
            total_values[col] = round(float(edited_df[col].sum()), 3)
        
        else:
            total_values[col] = ""
    return pd.DataFrame({k: [v] for k, v in total_values.items()})


def editable_grid():

    # ✅ All numeric columns — just add new ones here when needed
    numeric_cols = ["Scheduled KM", "Actual KM", "Diesel", "Avg"]

    try:
        df = pd.read_csv("records.csv")
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
    except FileNotFoundError:
        df = pd.DataFrame({
            "Date":           [date.today()],
            "Driver Name":    ["Ramesh"],
            "Conductor Name": ["Mahesh"],
            "Scheduled KM":   [466],
            "Actual KM":      [466],
            "Diesel":         [90],
        })

    st.markdown("### Vehicle Records 🚐")

    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date":           st.column_config.DateColumn("Date", default=date.today()),
            "Driver Name":    st.column_config.TextColumn("Driver Name"),
            "Conductor Name": st.column_config.TextColumn("Conductor Name"),
            "Scheduled KM":   st.column_config.NumberColumn("Scheduled KM", min_value=0, default=466),
            "Actual KM":      st.column_config.NumberColumn("Actual KM", min_value=0, default=0),
            "Diesel":         st.column_config.NumberColumn("Diesel",  min_value=0, default=0),
        }
    )

    edited_df["Avg"]   = (edited_df["Actual KM"] / edited_df["Diesel"].replace(0, 1)).round(2)


    # ✅ Auto build total row — works for any new column automatically
    total_row  = build_total_row(edited_df, numeric_cols, label_col="Driver Name")
    display_df = pd.concat([edited_df, total_row], ignore_index=True)

    # ✅ Show read-only table with total row at bottom
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if st.button("💾 Save Changes"):
        cleaned_df = edited_df.dropna(how="all")
        cleaned_df["Avg"]   = (cleaned_df["Actual KM"] / cleaned_df["Diesel"].replace(0, 1)).round(2)
        cleaned_df.to_csv("records.csv", index=False)
        st.success("✅ Changes saved!")
        st.rerun()



def driver_salary():
    data= pd.DataFrame({
        'Date':[date.today()],
        'Driver Name': ['Ramesh'],
        'Salary':['2000'],
        'Transaction':['cash/online']

    })
    driver_df = st.data_editor(
        data,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date":           st.column_config.DateColumn("Date", default=date.today()),
            "Driver Name":    st.column_config.TextColumn("Driver Name"),
            "Salary" :        st.column_config.NumberColumn("Salary", min_value=0),
            "Transaction":    st.column_config.TextColumn("Transaction"),
        }
    )
    st.dataframe(driver_df, use_container_width=True, hide_index=True)

    if st.button("💾 Save Changes",width='stretch'):
        cleaned_df = driver_df.dropna(how="all")
        cleaned_df.to_csv("expanse_records.csv", index=False)
        st.success("✅ Changes saved!")





def expenses():
    data= pd.DataFrame({
        'Date':[date.today()],
        'Driver Name': ['Ramesh'],
        'Salary':['2000'],
        'Transaction':['cash/online']

    })
    driver_df = st.data_editor(
        data,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date":           st.column_config.DateColumn("Date", default=date.today()),
            "Driver Name":    st.column_config.TextColumn("Driver Name"),
            "Salary" :        st.column_config.NumberColumn("Salary", min_value=0),
            "Transaction":    st.column_config.TextColumn("Transaction"),
        }
    )