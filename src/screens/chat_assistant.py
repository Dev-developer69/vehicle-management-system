"""
💬 Chat Assistant — data-filling only (no Q&A / reporting).

User types a plain-language sentence like:
    "bus 2547 mein aaj 90 litre diesel dala, actual km 420, driver ramesh"
and/or attaches a photo (log sheet, receipt, odometer, etc.). The user picks
which AI model reads it — Claude (accurate, reads photos + decides what to
save in one step) or Groq (fast; photos are described in a quick pre-pass,
then a Groq text model decides what to save). Either way the same TOOLS/
_run_tool() below do the actual saving via the existing db.py functions
(save_vehicle_records / save_vehicle_expenses / save_driver_salary /
save_driver_rate) — same functions the regular forms use, so merge-with-
existing-row behaviour, updated_by tracking, etc. all stay identical.

The assistant NEVER reads data back to the user — it only fills it in. If a
required field is missing or ambiguous, it asks a short follow-up question
instead of guessing.
"""

import base64
import json
from datetime import date

import pandas as pd
import streamlit as st
import anthropic
from groq import Groq

from src.database.auth import get_accessible_vehicles
from src.database.db import (
    save_vehicle_records,
    save_vehicle_expenses,
    save_driver_salary,
    save_driver_rate,
    log_error,
)
from src.screens.products_manager import _compress_image

CLAUDE_MODEL = "claude-sonnet-4-6"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"   # tool-calling capable
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"        # same model used by the image-extract feature

TOOLS = [
    {
        "name": "save_vehicle_record",
        "description": (
            "Save/update a single day's vehicle record — KM, diesel, income. "
            "Only include fields the user actually mentioned or that are visible in a photo; omit the rest."
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
                "Scheduled KM": tool_input.get("scheduled_km"),
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


def _system_prompt(accessible: list) -> str:
    today = date.today().isoformat()
    return (
        f"Today's date is {today}. The current user can save records for these buses: "
        f"{', '.join(accessible)}. You ONLY fill in data — you never answer questions or "
        f"report existing numbers back. Parse the user's message and call the matching tool "
        f"with the fields you can determine. If multiple rows are described, call the "
        f"appropriate tool once per row. If the bus number, date, or another required field "
        f"is missing or unclear, ask ONE short follow-up question instead of guessing — do not "
        f"call a tool with made-up values. If today's date applies, use it. Reply in the same "
        f"language/style the user wrote in (Hindi/Hinglish or English), keep replies short."
    )


def _run_claude(history_text_messages: list, image_blocks: list, latest_text: str, accessible: list, updated_by: str) -> str:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    latest_content = (image_blocks + [{"type": "text", "text": latest_text}]) if image_blocks else latest_text
    messages = [{"role": m["role"], "content": m["content"]} for m in history_text_messages]
    messages.append({"role": "user", "content": latest_content})

    for _ in range(6):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1536,
            system=_system_prompt(accessible),
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text") or "Ho gaya."

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _run_tool(block.name, block.input, accessible, updated_by)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
        messages.append({"role": "user", "content": tool_results})

    return "Sorry, ye query thodi complex ho gayi — dobara simple karke poochho."


def _groq_describe_images(raw_images: list) -> str:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    content = []
    for raw in raw_images:
        compressed = _compress_image(raw)
        b64 = base64.standard_b64encode(compressed).decode("utf-8")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    content.append({
        "type": "text",
        "text": (
            "List every relevant field visible in this image as short plain-text lines — date, "
            "bus number, driver/conductor names, scheduled km, actual km, diesel litres, diesel km, "
            "income, gross income, expense category/amount, remark — whatever is actually visible. "
            "If it's a table, list every row separately. Don't guess values that aren't shown."
        ),
    })
    response = client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=2000,
    )
    return (response.choices[0].message.content or "").strip()


def _run_groq(history_text_messages: list, latest_text: str, accessible: list, updated_by: str) -> str:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    tools_oai = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in TOOLS
    ]
    convo = [{"role": "system", "content": _system_prompt(accessible)}]
    convo += [{"role": m["role"], "content": m["content"]} for m in history_text_messages]
    convo.append({"role": "user", "content": latest_text})

    for _ in range(6):
        response = client.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=convo,
            tools=tools_oai,
            max_tokens=1536,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or "Ho gaya."

        convo.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = _run_tool(tc.function.name, args, accessible, updated_by)
            convo.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

    return "Sorry, ye query thodi complex ho gayi — dobara simple karke poochho."


def _render_chat_body():
    st.caption(
        "Plain language mein likho, ya photo attach karo — seedha database mein save ho jayega. "
        "Jaise: \"bus 2547 mein aaj 90 litre diesel dala, 420 km chali, driver ramesh\""
    )

    accessible = get_accessible_vehicles()
    if not accessible:
        st.warning("⚠️ Aapke paas kisi bhi vehicle ka access nahi hai.")
        return

    has_claude = "ANTHROPIC_API_KEY" in st.secrets
    has_groq = "GROQ_API_KEY" in st.secrets
    if not has_claude and not has_groq:
        st.error("❌ Na ANTHROPIC_API_KEY na GROQ_API_KEY set hai secrets mein.")
        return

    ai_options = []
    if has_claude:
        ai_options.append("🤖 Claude (Accurate)")
    if has_groq:
        ai_options.append("⚡ Groq (Fast)")
    ai_choice = st.radio("AI Model", ai_options, horizontal=True, key="chat_ai_choice") if len(ai_options) > 1 else ai_options[0]
    using_claude = ai_choice.startswith("🤖")

    if "chat_assistant_history" not in st.session_state:
        st.session_state["chat_assistant_history"] = []
    if "chat_img_reset" not in st.session_state:
        st.session_state["chat_img_reset"] = 0

    for msg in st.session_state["chat_assistant_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["display"])

    uploader_key = f"chat_img_{st.session_state['chat_img_reset']}"
    img_col1, img_col2 = st.columns(2)
    with img_col1:
        uploaded1 = st.file_uploader("📷 Photo 1 (optional)", type=["jpg", "jpeg", "png", "webp"], key=f"{uploader_key}_1")
    with img_col2:
        uploaded2 = st.file_uploader(
            "📷 Photo 2 (optional) — chaudi sheet ho to baaki columns",
            type=["jpg", "jpeg", "png", "webp"], key=f"{uploader_key}_2",
        )
    if uploaded2 and not uploaded1:
        st.caption("⚠️ Photo 2 se pehle Photo 1 bhi lagao.")

    user_input = st.chat_input("Apni entry likho...")
    if not user_input:
        return

    raw_images = []
    if uploaded1 is not None:
        for f in [uploaded1, uploaded2] if uploaded2 is not None else [uploaded1]:
            raw_images.append(f.read())

    display_text = user_input
    if raw_images:
        display_text = f"{user_input}\n\n📷 _({len(raw_images)} photo{'s' if len(raw_images) > 1 else ''} attached)_"
        st.session_state["chat_img_reset"] += 1  # fresh uploaders next render

    # History only ever stores plain text — this keeps it valid input for
    # EITHER model, even if the user switches AI choice mid-conversation.
    st.session_state["chat_assistant_history"].append({"role": "user", "content": user_input, "display": display_text})
    with st.chat_message("user"):
        st.markdown(display_text)
        for raw in raw_images:
            st.image(raw, width=200)

    user = st.session_state.get("user")
    updated_by = user.email if user else "unknown"
    prior_history = st.session_state["chat_assistant_history"][:-1]  # everything except the message just added

    with st.chat_message("assistant"):
        with st.spinner("Samajh raha hoon..."):
            try:
                if using_claude:
                    image_blocks = []
                    for raw in raw_images:
                        compressed = _compress_image(raw)
                        b64 = base64.standard_b64encode(compressed).decode("utf-8")
                        image_blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
                    text_for_model = user_input
                    if len(raw_images) == 2:
                        text_for_model += (
                            "\n\n(Note: two photos are attached — same rows, same order, just "
                            "different columns of a wide table split across two photos. Merge "
                            "them row-by-row by position before saving.)"
                        )
                    final_text = _run_claude(prior_history, image_blocks, text_for_model, accessible, updated_by)
                else:
                    text_for_model = user_input
                    if raw_images:
                        image_summary = _groq_describe_images(raw_images)
                        text_for_model += f"\n\n[Extracted from attached photo(s)]:\n{image_summary}"
                    final_text = _run_groq(prior_history, text_for_model, accessible, updated_by)
            except Exception as e:
                log_error("chat_assistant", str(e))
                final_text = f"❌ Kuch gadbad ho gayi: {e}"

        st.markdown(final_text)

    st.session_state["chat_assistant_history"].append({"role": "assistant", "content": final_text, "display": final_text})


@st.dialog("💬 Data Assistant", width="large")
def chat_assistant_dialog():
    """Opens as a proper modal (not full-screen) that overlays whatever page
    the user is currently on. Calling this function IS what opens it —
    Streamlit manages showing/closing it internally, no session_state routing
    or page navigation required."""
    _render_chat_body()
