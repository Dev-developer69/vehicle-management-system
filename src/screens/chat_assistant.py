"""
💬 Chat Assistant — data-filling only (no Q&A / reporting).

User types a plain-language sentence like:
    "bus 2547 mein aaj 90 litre diesel dala, actual km 420, driver ramesh"
and/or attaches a photo (log sheet, receipt, odometer, purchase/tax invoice,
etc.). The user picks which AI model reads it — Claude (accurate, reads
photos + decides what to save in one step) or Groq (fast; photos are
described in a quick pre-pass, then a Groq text model decides what to save).
Either way the same TOOLS/_run_tool() below do the actual saving via the
existing db.py functions (save_vehicle_records / save_vehicle_expenses /
save_driver_salary / save_driver_rate / save_supplier / save_product) — same
functions the regular forms use, so merge-with-existing-row behaviour,
updated_by tracking, duplicate checks, etc. all stay identical.

Supplier/Product invoices: if a purchase/tax invoice photo is attached, the
assistant extracts the SELLER (supplier) details from the invoice header —
never the "Buyer"/"Bill to"/"Consignee" section — and each line item as a
product, then saves them via add_supplier / add_product.

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

from src.database.auth import get_accessible_vehicles, is_admin_or_manager, get_product_access_flags
from src.database.db import (
    save_vehicle_records,
    save_vehicle_expenses,
    save_driver_salary,
    save_driver_rate,
    save_supplier,
    save_product,
    get_suppliers,
    log_error,
)
from src.screens.products_manager import _compress_image

CLAUDE_MODEL = "claude-sonnet-5"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"   # tool-calling capable
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"        # same model used by the image-extract feature

VEHICLE_TOOL_NAMES = {"save_vehicle_record", "save_expense", "save_driver_salary_payment", "save_driver_rate"}

TOOLS_VEHICLE = [
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

TOOLS_PRODUCTS = [
    {
        "name": "add_supplier",
        "description": (
            "Add a new supplier/vendor to the database. Use this when the user describes a "
            "supplier by hand, OR when a purchase/tax invoice photo is attached — in that case "
            "extract the SELLER's details (company name, phone, address) from the invoice header, "
            "never the 'Buyer'/'Bill to'/'Consignee' section, which is the customer, not the supplier. "
            "If the supplier already exists this is a harmless no-op (duplicate names are skipped)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Company/business name (not a person's name unless no company name is printed)"},
                "phone": {"type": "string", "description": "All phone/mobile numbers, comma-separated if more than one. Required."},
                "address": {"type": "string", "description": "Full postal address"},
                "remark": {"type": "string"},
            },
            "required": ["name", "phone"],
        },
    },
    {
        "name": "add_product",
        "description": (
            "Add or update a purchased product/item — e.g. one line item from a purchase/tax "
            "invoice, or a product the user describes directly. price must be the PER-UNIT rate; "
            "if the source only shows a total amount, divide by quantity yourself before calling this. "
            "If the product name already exists, this updates its price (old price is kept as history) "
            "instead of creating a duplicate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "price": {"type": "number", "description": "Per-unit purchase rate"},
                "mrp": {"type": "number", "description": "Printed MRP, if shown"},
                "quantity": {"type": "string", "description": "e.g. '2 nos', '10 pcs'"},
                "supplier_name": {
                    "type": "string",
                    "description": "Name of the supplier this was purchased from. Call add_supplier first (in the same turn) if this supplier isn't already in the database.",
                },
                "purchased_date": {"type": "string", "description": "YYYY-MM-DD; use the invoice date if visible, else today"},
                "remark": {"type": "string"},
            },
            "required": ["product_name", "price"],
        },
    },
]


def _resolve_supplier_id(supplier_name: str) -> str | None:
    name = (supplier_name or "").strip()
    if not name:
        return None
    df = get_suppliers()
    if df.empty:
        return None
    match = df[df["Name"].str.strip().str.lower() == name.lower()]
    return match.iloc[0]["id"] if not match.empty else None


def _run_tool(name: str, tool_input: dict, accessible: list, updated_by: str) -> dict:
    # ── Vehicle-scoped tools: enforce per-bus access ──
    if name in VEHICLE_TOOL_NAMES:
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

        if name == "add_supplier":
            ok, reason = save_supplier(
                tool_input["name"],
                tool_input.get("phone", ""),
                tool_input.get("address", ""),
                tool_input.get("remark", ""),
            )
            if ok:
                return {"ok": True, "message": f"✅ Supplier '{tool_input['name']}' add ho gaya."}
            if reason == "duplicate":
                return {"ok": True, "message": f"ℹ️ Supplier '{tool_input['name']}' pehle se database mein hai — skip kiya."}
            return {"ok": False, "message": "❌ Supplier add nahi hua — phone number zaroori hai."}

        if name == "add_product":
            supplier_id = _resolve_supplier_id(tool_input.get("supplier_name", ""))
            if tool_input.get("supplier_name") and not supplier_id:
                return {
                    "ok": False,
                    "message": (
                        f"❌ Supplier '{tool_input['supplier_name']}' database mein nahi mila. "
                        f"Pehle add_supplier tool call karo, phir dobara add_product try karo."
                    ),
                }
            save_product(
                tool_input["product_name"],
                float(tool_input.get("price", 0) or 0),
                float(tool_input.get("mrp", 0) or 0),
                supplier_id,
                tool_input.get("purchased_date") or date.today().isoformat(),
                str(tool_input.get("quantity", "") or ""),
                tool_input.get("remark", "") or "",
            )
            return {"ok": True, "message": f"✅ Product '{tool_input['product_name']}' save ho gaya."}

        return {"ok": False, "message": f"Unknown action: {name}"}
    except Exception as e:
        log_error("chat_assistant", str(e), bus_number=tool_input.get("bus_number", ""), extra_data=json.dumps(tool_input))
        return {"ok": False, "message": f"❌ Save fail ho gaya: {e}"}


def _system_prompt(accessible: list, can_manage_products: bool) -> str:
    today = date.today().isoformat()
    products_block = (
        "You can ALSO add suppliers and products using add_supplier / add_product. "
        "When a purchase/tax invoice photo is attached: the SELLER's details (usually printed at "
        "the TOP of the invoice — company name, address, mobile, GSTIN) are the supplier. The "
        "'Buyer', 'Bill to', 'Consignee', or 'Ship to' section is the CUSTOMER — never treat that as "
        "the supplier. Extract every line item as a separate add_product call: price must be the "
        "PER-UNIT rate — if only a line total is printed, divide by quantity yourself. If the "
        "supplier isn't already known, call add_supplier first, then add_product referencing it by "
        "supplier_name, in the same turn."
        if can_manage_products
        else "The current user does NOT have permission to add suppliers or products — if they ask, "
             "reply that they need Products Manager access from an Admin."
    )
    return (
        f"Today's date is {today}. The current user can save vehicle records for these buses: "
        f"{', '.join(accessible) if accessible else '(none)'}. You ONLY fill in data — you never "
        f"answer questions or report existing numbers back. Parse the user's message and call the "
        f"matching tool(s) with the fields you can determine. If multiple rows/items are described, "
        f"call the appropriate tool once per row/item. If a required field is missing or unclear, ask "
        f"ONE short follow-up question instead of guessing — do not call a tool with made-up values. "
        f"If today's date applies, use it. {products_block} Reply in the same language/style the user "
        f"wrote in (Hindi/Hinglish or English), keep replies short."
    )


def _active_tools(can_manage_products: bool) -> list:
    return TOOLS_VEHICLE + TOOLS_PRODUCTS if can_manage_products else TOOLS_VEHICLE


def _run_claude(history_text_messages: list, image_blocks: list, latest_text: str,
                 accessible: list, updated_by: str, can_manage_products: bool) -> str:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    latest_content = (image_blocks + [{"type": "text", "text": latest_text}]) if image_blocks else latest_text
    messages = [{"role": m["role"], "content": m["content"]} for m in history_text_messages]
    messages.append({"role": "user", "content": latest_content})
    tools = _active_tools(can_manage_products)

    for _ in range(6):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1536,
            system=_system_prompt(accessible, can_manage_products),
            tools=tools,
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
            "This could be a vehicle log sheet, an expense receipt, or a purchase/tax invoice. "
            "List every relevant field visible as short plain-text lines. "
            "If it's a vehicle log/receipt: date, bus number, driver/conductor names, scheduled km, "
            "actual km, diesel litres, diesel km, income, gross income, expense category/amount, remark. "
            "If it's a purchase/tax invoice: clearly separate the SELLER (usually at the top — company "
            "name, phone, address) from the 'Buyer'/'Bill to'/'Consignee' (the customer — do not label "
            "this as the supplier). Then list each line item separately: product name, quantity, "
            "per-unit rate, and line total. If it's a table, list every row separately. "
            "Don't guess values that aren't shown."
        ),
    })
    response = client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=2000,
    )
    return (response.choices[0].message.content or "").strip()


def _run_groq(history_text_messages: list, latest_text: str, accessible: list,
              updated_by: str, can_manage_products: bool) -> str:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    tools = _active_tools(can_manage_products)
    tools_oai = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tools
    ]
    convo = [{"role": "system", "content": _system_prompt(accessible, can_manage_products)}]
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
    accessible = get_accessible_vehicles()
    can_manage_products = is_admin_or_manager() or get_product_access_flags().get("products_access", False)

    example = "\"bus 2547 mein aaj 90 litre diesel dala, 420 km chali, driver ramesh\""
    if can_manage_products:
        example += ", ya ek purchase/tax invoice ki photo bhejo — supplier aur products dono save ho jayenge"
    st.caption(f"Plain language mein likho, ya photo attach karo — seedha database mein save ho jayega. Jaise: {example}")

    if not accessible and not can_manage_products:
        st.warning("⚠️ Aapke paas kisi bhi vehicle ya products/suppliers ka access nahi hai.")
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
            "📷 Photo 2 (optional) — chaudi sheet/invoice ho to baaki columns",
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
                            "\n\n(Note: two photos are attached — either the same rows/same order but "
                            "different columns of a wide table split across two photos, merge them "
                            "row-by-row by position; or two separate pages of the same invoice/document.)"
                        )
                    final_text = _run_claude(prior_history, image_blocks, text_for_model, accessible, updated_by, can_manage_products)
                else:
                    text_for_model = user_input
                    if raw_images:
                        image_summary = _groq_describe_images(raw_images)
                        text_for_model += f"\n\n[Extracted from attached photo(s)]:\n{image_summary}"
                    final_text = _run_groq(prior_history, text_for_model, accessible, updated_by, can_manage_products)
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
