"""
💬 Chat Assistant — data-filling only (no Q&A / reporting).

User types a plain-language sentence like:
    "bus 2547 mein aaj 90 litre diesel dala, actual km 420, driver ramesh"
and Claude parses it into structured fields, then calls one of the existing
db.py save functions (save_vehicle_records / save_vehicle_expenses /
save_driver_salary) — same functions the regular forms use, so merge-with-
existing-row behaviour, updated_by tracking, etc. all stay identical.

The assistant NEVER reads data back to the user — it only fills it in. If a
required field is missing or ambiguous, it asks a short follow-up question
instead of guessing.
"""

import json
from datetime import date

import pandas as pd
import streamlit as st
import anthropic

from src.database.auth import get_accessible_vehicles, get_current_role
from src.database.db import (
    save_vehicle_records,
    save_vehicle_expenses,
    save_driver_salary,
    save_driver_rate,
    get_scheduled_km,
    log_error,
)

TOOLS = [
    {
        "name": "save_vehicle_record",
        "description": (
            "Save/update a single day's vehicle record — KM, diesel, income. "
            "Only include fields the user actually mentioned; omit the rest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bus_number": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "status": {"type": "string", "enum": ["Present", "On Leave"]},
                "driver_name": {"type": "string"},
                "conductor_name": {"type": "string"},
                "scheduled_km": {"type": "number"},
                "actual_km": {"type": "number"},
                "diesel": {"type": "number", "description": "litres"},
                "diesel_km": {"type": "number"},
                "income": {"type": "number"},
                "gross_income": {"type": "number"},
                "remark": {"type": "string"},
            },
            "required": ["bus_number", "date"],
        },
    },
    {
        "name": "save_expense",
        "description": "Save a vehicle expense entry (maintenance, toll, fine, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "bus_number": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "category": {"type": "string"},
                "amount": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["bus_number", "date", "category", "amount"],
        },
    },
    {
        "name": "save_driver_salary_payment",
        "description": "Save an amount actually paid to a driver.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bus_number": {"type": "string"},
                "driver_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "salary": {"type": "number"},
                "transaction": {"type": "string", "enum": ["cash", "online"]},
            },
            "required": ["bus_number", "driver_name", "date", "salary"],
        },
    },
    {
        "name": "save_driver_rate",
        "description": "Set a driver's per-duty pay rate (used later to calculate salary due).",
        "input_schema": {
            "type": "object",
            "properties": {
                "bus_number": {"type": "string"},
                "driver_name": {"type": "string"},
                "rate_per_duty": {"type": "number"},
            },
            "required": ["bus_number", "driver_name", "rate_per_duty"],
        },
    },
]


def _run_tool(name: str, tool_input: dict, accessible: list, updated_by: str) -> dict:
    bus = str(tool_input.get("bus_number", "")).strip()
    if bus not in accessible:
        return {"ok": False, "message": f"❌ Bus {bus} tumhare access mein nahi hai."}

    try:
        if name == "save_vehicle_record":
            on_leave = tool_input.get("status") == "On Leave"
            row = {
                "Date": tool_input["date"],
                "Status": "On Leave" if on_leave else "Present",
                "Driver Name": tool_input.get("driver_name", "none"),
                "Conductor Name": tool_input.get("conductor_name", "none"),
                "Scheduled KM": tool_input.get("scheduled_km", get_scheduled_km(bus)),
                "Actual KM": tool_input.get("actual_km"),
                "Diesel": tool_input.get("diesel"),
                "Diesel KM": tool_input.get("diesel_km"),
                "Income": tool_input.get("income"),
                "Gross Income": tool_input.get("gross_income"),
                "Remark": tool_input.get("remark", ""),
                "Next": False,
            }
            save_vehicle_records(bus, pd.DataFrame([row]))
            return {"ok": True, "message": f"✅ Bus {bus} ka {tool_input['date']} ka record save ho gaya."}

        if name == "save_expense":
            row = {
                "Date": tool_input["date"],
                "Category": tool_input["category"],
                "Amount": tool_input["amount"],
                "Description": tool_input.get("description", ""),
            }
            save_vehicle_expenses(bus, pd.DataFrame([row]))
            return {"ok": True, "message": f"✅ Bus {bus} ka expense (₹{tool_input['amount']} — {tool_input['category']}) save ho gaya."}

        if name == "save_driver_salary_payment":
            row = {
                "Driver Name": tool_input["driver_name"],
                "Date": tool_input["date"],
                "Salary": tool_input["salary"],
                "Transaction": tool_input.get("transaction", "cash"),
            }
            save_driver_salary(pd.DataFrame([row]), bus_number=bus)
            return {"ok": True, "message": f"✅ {tool_input['driver_name']} ko ₹{tool_input['salary']} salary payment save ho gaya."}

        if name == "save_driver_rate":
            save_driver_rate(bus, tool_input["driver_name"], tool_input["rate_per_duty"], updated_by)
            return {"ok": True, "message": f"✅ {tool_input['driver_name']} ka rate ₹{tool_input['rate_per_duty']}/duty set ho gaya."}

        return {"ok": False, "message": f"Unknown action: {name}"}
    except Exception as e:
        log_error("chat_assistant", str(e), bus_number=bus, extra_data=json.dumps(tool_input))
        return {"ok": False, "message": f"❌ Save fail ho gaya: {e}"}


def chat_assistant_page():
    st.header("💬 Data Assistant")
    st.caption("Plain language mein likho, seedha database mein save ho jayega — jaise: \"bus 2547 mein aaj 90 litre diesel dala, 420 km chali, driver ramesh\"")

    if st.button("🏠 Home page", type="primary", icon=":material/home:"):
        st.session_state["login_state"] = None
        st.rerun()

    accessible = get_accessible_vehicles()
    if not accessible:
        st.warning("⚠️ Aapke paas kisi bhi vehicle ka access nahi hai.")
        return

    if "ANTHROPIC_API_KEY" not in st.secrets:
        st.error("❌ ANTHROPIC_API_KEY set nahi hai secrets mein.")
        return

    if "chat_assistant_history" not in st.session_state:
        st.session_state["chat_assistant_history"] = []

    for msg in st.session_state["chat_assistant_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Apni entry likho...")
    if not user_input:
        return

    st.session_state["chat_assistant_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    user = st.session_state.get("user")
    updated_by = user.email if user else "unknown"

    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    today = date.today().isoformat()
    system = (
        f"Today's date is {today}. The current user can save records for these buses: "
        f"{', '.join(accessible)}. You ONLY fill in data — you never answer questions or "
        f"report existing numbers back. Parse the user's message and call the matching tool "
        f"with the fields they mentioned. If the bus number, date, or another required field "
        f"is missing or unclear, ask ONE short follow-up question instead of guessing — do not "
        f"call a tool with made-up values. If today's date applies, use it. Reply in the same "
        f"language/style the user wrote in (Hindi/Hinglish or English), keep replies short."
    )

    messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state["chat_assistant_history"]]

    with st.chat_message("assistant"):
        with st.spinner("Samajh raha hoon..."):
            try:
                final_text = ""
                for _ in range(4):
                    response = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1024,
                        system=system,
                        tools=TOOLS,
                        messages=messages,
                    )

                    if response.stop_reason != "tool_use":
                        final_text = "".join(b.text for b in response.content if b.type == "text")
                        break

                    messages.append({"role": "assistant", "content": response.content})
                    tool_results = []
                    for block in response.content:
                        if block.type != "tool_use":
                            continue
                        result = _run_tool(block.name, block.input, accessible, updated_by)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                    messages.append({"role": "user", "content": tool_results})

                final_text = final_text or "Ho gaya."
            except Exception as e:
                log_error("chat_assistant", str(e))
                final_text = f"❌ Kuch gadbad ho gayi: {e}"

        st.markdown(final_text)

    st.session_state["chat_assistant_history"].append({"role": "assistant", "content": final_text})
