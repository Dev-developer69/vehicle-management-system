import streamlit as st
import pandas as pd
from datetime import date
from src.ui.home_base_layout import home_layout
from PIL import Image
import io

from src.database.db import (
    get_suppliers, save_supplier, delete_supplier, get_supplier_products,
    get_products, save_product, delete_product,
    get_requirements, save_requirement, fulfill_requirement, delete_requirement,
)

def _compress_image(image_bytes: bytes, max_dimension: int = 900, quality: int = 55) -> bytes:
    """Image ko resize + compress karo taaki vision model ke token usage kam ho"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")

        w, h = img.size
        scale = max_dimension / max(w, h)
        if scale < 1:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        st.caption(f"🗜️ Compressed: {len(image_bytes)} → {len(compressed)} bytes ({img.size[0]}x{img.size[1]}px)")
        return compressed
    except Exception as e:
        st.warning(f"⚠️ Compression failed, using original: {e}")
        return image_bytes
        
# ──────────────────────────────────────────────
# HELPER: Image → Product data via Claude API
# ──────────────────────────────────────────────
# def _extract_from_image(image_bytes: bytes, mime_type: str) -> list:
#     try:
#         import anthropic, base64, json, re
#         client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
#         b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
#         msg = client.messages.create(
#             model="claude-sonnet-4-6",
#             max_tokens=1000,
#             messages=[{
#                 "role": "user",
#                 "content": [
#                     {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
#                     {"type": "text", "text": (
#                         "Extract ALL products/items from this bill or image. "
#                         "Return ONLY a JSON array of objects, each with keys: "
#                         "name (string), price (number or null), mrp (number or null). "
#                         "price = rate/unit price, not total amount. "
#                         "No explanation, no markdown, just raw JSON array. "
#                         "Example: [{\"name\": \"Item A\", \"price\": 350, \"mrp\": null}]"
#                     )},
#                 ],
#             }],
#         )
#         raw = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
#         parsed = json.loads(raw)
#         if isinstance(parsed, dict):
#             parsed = [parsed]
#         return parsed if isinstance(parsed, list) else []
#     except Exception as e:
#         st.error(f"Image read failed: {e}")
#         return []

# ──────────────────────────────────────────────
# HELPER: Verify/correct Groq's extraction via Claude
# ──────────────────────────────────────────────
def _verify_with_claude(image_bytes: bytes, mime_type: str, groq_result: list) -> list:
    try:
        import anthropic, base64, json, re
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1000,   # verification hai, chhota output expected
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
                    {"type": "text", "text": (
                        "Here is data another model extracted from this bill image:\n\n"
                        f"{json.dumps(groq_result, ensure_ascii=False)}\n\n"
                        "Check this against the image ONLY for errors in: name spelling, "
                        "quantity, price (must be per-unit rate, not total amount), and mrp. "
                        "If a value is correct, keep it unchanged. If wrong, fix it. "
                        "Do not add new items unless one was clearly missed. "
                        "Return ONLY the corrected JSON array in the same format "
                        "(keys: name, quantity, price, mrp). No explanation, no markdown."
                    )},
                ],
            }],
        )
        raw = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed if isinstance(parsed, list) else groq_result
    except Exception as e:
        st.warning(f"⚠️ Verification skipped: {e}")
        return groq_result   # fallback: Groq ka result hi use karo agar Claude fail ho


# ──────────────────────────────────────────────
# HELPER: Image → structured data via Groq Vision
# ──────────────────────────────────────────────
def _extract_data_from_image(image_bytes: bytes, mime_type: str, prompt: str) -> list:
    try:
        import base64, json, re
        from groq import Groq

        image_bytes = _compress_image(image_bytes)  
        mime_type = "image/jpeg"                       
        
        client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        response = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ]
            }],
            max_tokens=4000,   
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            st.error(f"Image read failed: model se khaali response aaya. finish_reason: {response.choices[0].finish_reason}")
            return []
        if not raw:
            st.error("Image read failed: model se khaali response aaya.")
            return []

        raw = re.sub(r"```json|```", "", raw).strip()

    
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            raw = match.group(0)

        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        st.error(f"Image read failed: {e}")
        return []


# ──────────────────────────────────────────────
# HELPER: Multiple images (same rows, split columns) → merged structured data
# Har image alag call mein bhejo (token limit se bachne ke liye), phir row-position se merge karo
# ──────────────────────────────────────────────
def _extract_data_from_images(images: list, prompt: str) -> list:
    all_results = []
    for image_bytes, mime_type in images:
        single_result = _extract_data_from_image(image_bytes, mime_type, prompt)
        all_results.append(single_result or [])

    if not all_results:
        return []

    # Row-position se merge karo — jo bhi non-null field ho wo le lo
    max_len = max(len(r) for r in all_results)
    merged = []
    for i in range(max_len):
        combined = {}
        for result_set in all_results:
            if i < len(result_set) and isinstance(result_set[i], dict):
                for k, v in result_set[i].items():
                    if v is not None:
                        combined[k] = v
        merged.append(combined)
    return merged
# ──────────────────────────────────────────────
# PRODUCTS PAGE — entry point
# ──────────────────────────────────────────────
def products_page():
    home_layout()
    from src.database.config import supabase
    from src.database.auth import get_current_role

    role = get_current_role()
    user = st.session_state.get("user")

    # Admin/Manager — sab access
    if role in ('admin', 'manager'):
        can_products = can_suppliers = can_requirements = True
    else:
        res = supabase.table("user_roles") \
            .select("products_view, suppliers_view, requirements_view") \
            .eq("user_id", user.id).execute()
        flags = res.data[0] if res.data else {}
        can_products     = bool(flags.get("products_view",     False))
        can_suppliers    = bool(flags.get("suppliers_view",    False))
        can_requirements = bool(flags.get("requirements_view", False))

    st.markdown("""
    <div style='display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;'>
        <div style='width:42px;height:42px;background:var(--bg-accent,#e8f0fe);border-radius:10px;
                    display:flex;align-items:center;justify-content:center;font-size:22px;'>📦</div>
        <div>
            <div style='font-size:1.2rem;font-weight:500;'>Products Manager</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state'] = None
            st.rerun()
    
    # ── Allowed tabs ──
    nav_key      = "pm_active_tab"
    allowed_tabs = []
    if can_products:     allowed_tabs.append(("🛒  Product Details",  "products"))
    if can_suppliers:    allowed_tabs.append(("🏭  Supplier Details", "suppliers"))
    if can_requirements: allowed_tabs.append(("📋  Requirements",     "requirements"))

    if not allowed_tabs:
        st.warning("⚠️ Koi tab access nahi hai. Admin se contact karo.")
        return

    if nav_key not in st.session_state or \
       st.session_state[nav_key] not in [t[1] for t in allowed_tabs]:
        st.session_state[nav_key] = allowed_tabs[0][1]

    cols = st.columns(len(allowed_tabs))
    for i, (label, key) in enumerate(allowed_tabs):
        with cols[i]:
            if st.button(
                label,
                use_container_width=True,
                type="primary" if st.session_state[nav_key] == key else "secondary",
                key=f"pm_tab_{key}",
            ):
                st.session_state[nav_key] = key
                st.rerun()

    st.markdown("<hr style='margin:0.75rem 0 1.25rem;opacity:0.15;'>", unsafe_allow_html=True)

    if st.session_state[nav_key] == "products":
        _product_details_tab()
    elif st.session_state[nav_key] == "suppliers":
        _supplier_details_tab()
    elif st.session_state[nav_key] == "requirements":
        _requirements_tab()


def _product_details_tab():
    search = st.text_input("🔍 Search product", key="prod_search", placeholder="type product name...")
    if "products_df" not in st.session_state:
        st.session_state["products_df"] = get_products()
    df = st.session_state["products_df"]
    filtered = df[df["Name"].str.lower().str.contains(search.lower(), na=False)] if search else df

    if not filtered.empty:
        with st.container(border=True):
            st.dataframe(
                filtered[["Name", "MRP", "Latest Price", "Old Price",
                           "Quantity", "Remark", "Supplier", "Purchased Date"]],
                use_container_width=True, hide_index=True,
            )
        with st.expander("🗑️ Delete a product"):
            del_name = st.selectbox("Select a product", filtered["Name"].tolist(), key="del_prod_select")
            if st.button("Delete", key="del_prod_btn", type="primary"):
                pid = filtered[filtered["Name"] == del_name]["id"].values[0]
                delete_product(pid)
                st.success(f"✅ Deleted: {del_name}")
                st.session_state.pop("products_df", None)
                st.rerun()
    else:
        st.info("NO PRODUCT FOUND.")

    st.markdown("---")

    with st.container(border=True):
        st.markdown("#### ➕ Add / Update Product")

        mode = st.radio("Input mode", ["✏️ Manual", "📷 From Image"],
                        horizontal=True, key="prod_input_mode")

        if mode == "📷 From Image":
            img_reset_key = st.session_state.get("img_reset_key", 0)
            uploaded = st.file_uploader("Upload image/Bill",
                                        type=["jpg","jpeg","png","webp"],
                                        key=f"prod_img_{img_reset_key}")
            if uploaded:
                if "img_products_list" not in st.session_state:
                    with st.spinner("Fetching products from image..."):
                        products_list = _extract_data_from_image(
                            uploaded.read(), uploaded.type,
                            "Extract ALL products/items from this bill or image. For each item extract:\n"
                            "- name (string)\n"
                            "- quantity (number - the quantity/pieces purchased; if not clearly mentioned, use 1)\n"
                            "- price (number - the PER PIECE / PER UNIT rate. If the bill shows a TOTAL amount "
                            "instead, CALCULATE price = total_amount / quantity. Never return total as price.)\n"
                            "- mrp (number or null, if printed)\n\n"
                            "Return ONLY a JSON array with keys: name, quantity, price, mrp. "
                            "No explanation, no markdown, just raw JSON array."
                        )

                    if products_list:
                        with st.spinner("Verifying with Claude..."):
                            uploaded.seek(0)
                            products_list = _verify_with_claude(uploaded.read(), uploaded.type, products_list)
                        st.session_state["img_products_list"] = products_list
                    else:
                        st.warning("⚠️ NO PRODUCT FOUND")
            
            if "img_products_list" in st.session_state:
                products_list = st.session_state["img_products_list"]
                st.success(f"✅ {len(products_list)} Product found - edit and save")

                sup_df = get_suppliers()
                sup_options = {"(None)": None}
                sup_options.update({row["Name"]: row["id"] for _, row in sup_df.iterrows()})

                c1, c2 = st.columns(2)
                with c1:
                    p_sup  = st.selectbox("Suppliers", list(sup_options.keys()), key="img_sup")
                with c2:
                    p_date = st.date_input("Purchase Date", value=date.today(), key="img_date")

                edit_df = pd.DataFrame(products_list)
                for col in ["name","price","mrp","quantity"]:
                    if col not in edit_df.columns:
                        edit_df[col] = None
                edit_df = edit_df[["name","price","mrp","quantity"]].copy()
                edit_df.columns = ["Name","Price (₹)","MRP (₹)","Quantity"]
                edit_df["Price (₹)"] = pd.to_numeric(edit_df["Price (₹)"], errors="coerce").fillna(0)
                edit_df["MRP (₹)"]   = pd.to_numeric(edit_df["MRP (₹)"],   errors="coerce").fillna(0)
                edit_df["Quantity"]  = pd.to_numeric(edit_df["Quantity"],  errors="coerce").fillna(0).astype(int).astype(str)
                edit_df["Remark"]    = ""

                edited = st.data_editor(
                    edit_df,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    key="img_editor",
                    column_config={
                        "Name":      st.column_config.TextColumn("Name"),
                        "Price (₹)": st.column_config.NumberColumn("Price (₹)", min_value=0, step=0.01, format="%.2f"),
                        "MRP (₹)":   st.column_config.NumberColumn("MRP (₹)",   min_value=0, step=0.01, format="%.2f"),
                        "Quantity":  st.column_config.TextColumn("Quantity"),
                        "Remark":    st.column_config.TextColumn("Remark"),
                    }
                )

                bc1, bc2 = st.columns([3,1])
                with bc1:
                    if st.button("💾 Save All Products", type="primary",
                                 use_container_width=True, key="save_all_img"):
                        saved, skipped = 0, 0
                        for _, row in edited.iterrows():
                            name = str(row["Name"] or "").strip()
                            if not name:
                                skipped += 1
                                continue
                            save_product(name, float(row["Price (₹)"]), float(row["MRP (₹)"]),
                                         sup_options[p_sup], str(p_date),
                                         str(row.get("Quantity") or ""),
                                         str(row.get("Remark") or ""))
                            saved += 1
                        st.success(f"✅ {saved} products saved!" + (f" ({skipped} skip)" if skipped else ""))
                        st.session_state.pop("img_products_list", None)
                        st.session_state.pop("products_df", None)
                        st.session_state["img_reset_key"] = img_reset_key + 1
                        st.rerun()
                with bc2:
                    if st.button("🗑️ Clear", key="clear_img_list", use_container_width=True):
                        st.session_state.pop("img_products_list", None)
                        st.session_state["img_reset_key"] = img_reset_key + 1
                        st.rerun()

        if mode == "✏️ Manual":
            sup_df = get_suppliers()
            sup_options = {"(None)": None}
            sup_options.update({row["Name"]: row["id"] for _, row in sup_df.iterrows()})

            c1, c2 = st.columns(2)
            with c1:
                p_name = st.text_input("Product Name", key="p_name")
            with c2:
                p_sup  = st.selectbox("Supplier", list(sup_options.keys()), key="p_sup")

            c3, c4, c5 = st.columns(3)
            with c3:
                p_price = st.number_input("Purchased Amount (₹)", min_value=0.0, step=0.01, key="p_price")
            with c4:
                p_mrp   = st.number_input("MRP (₹)", min_value=0.0, step=0.01, key="p_mrp")
            with c5:
                p_date  = st.date_input("Purchase Date", value=date.today(), key="p_date")

            c6, c7 = st.columns(2)
            with c6:
                p_qty    = st.text_input("Quantity", key="p_qty", placeholder="e.g. 10 pcs")
            with c7:
                p_remark = st.text_input("Remark", key="p_remark", placeholder="optional note...")

            bc1, bc2 = st.columns([3,1])
            with bc1:
                if st.button("💾 Save Product", use_container_width=True,
                             key="save_prod_btn", type="primary"):
                    if not p_name.strip():
                        st.warning("⚠️ Product name required.")
                    else:
                        save_product(p_name, p_price, p_mrp, sup_options[p_sup],
                                     str(p_date), p_qty, p_remark)
                        st.success(f"✅ Saved: {p_name}")
                        st.session_state.pop("products_df", None)
                        st.rerun()
            with bc2:
                if st.button("🔄 Refresh", use_container_width=True, key="refresh_prod"):
                    st.session_state.pop("products_df", None)
                    st.rerun()


def _supplier_details_tab():
    if "suppliers_df" not in st.session_state:
        st.session_state["suppliers_df"] = get_suppliers()
    sup_df = st.session_state["suppliers_df"]

    sup_search = st.text_input("🔍 Search supplier", key="sup_search", placeholder="Supplier ka naam...")
    filtered_sup = sup_df[sup_df["Name"].str.lower().str.contains(sup_search.lower(), na=False)] \
        if sup_search else sup_df

    if not filtered_sup.empty:
        with st.container(border=True):
            st.dataframe(filtered_sup[["Name", "Phone", "Address", "Remark"]],
                         use_container_width=True, hide_index=True)

        st.markdown("#### 📦 Supplier's products")
        sel_sup = st.selectbox("Select Supplier", filtered_sup["Name"].tolist(), key="sup_sel_view")
        if sel_sup:
            sid = filtered_sup[filtered_sup["Name"] == sel_sup]["id"].values[0]
            sup_prods = get_supplier_products(sid)
            if not sup_prods.empty:
                with st.container(border=True):
                    st.dataframe(sup_prods, use_container_width=True, hide_index=True)
            else:
                st.info("NO PRODUCTS PURCHASED.")

        with st.expander("🗑️ Delete a supplier"):
            del_sup = st.selectbox("Select karo", filtered_sup["Name"].tolist(), key="del_sup_sel")
            if st.button("Delete Supplier", key="del_sup_btn", type="primary"):
                sid = filtered_sup[filtered_sup["Name"] == del_sup]["id"].values[0]
                delete_supplier(sid)
                st.success(f"✅ Deleted: {del_sup}")
                st.session_state.pop("suppliers_df", None)
                st.rerun()
    else:
        st.info("NO SUPPLIER FOUND.")

    st.markdown("---")

    with st.container(border=True):
        st.markdown("#### ➕ Add Supplier")

        sup_mode = st.radio("Input mode", ["✏️ Manual", "📷 From Card/Image"],
                            horizontal=True, key="sup_input_mode")

        if sup_mode == "📷 From Card/Image":
            sup_img_reset = st.session_state.get("sup_img_reset", 0)
            sup_uploaded = st.file_uploader(
                "Business card ya supplier info ki image upload karo",
                type=["jpg","jpeg","png","webp"],
                key=f"sup_img_{sup_img_reset}"
            )
            if sup_uploaded:
                if "sup_extracted" not in st.session_state:
                    with st.spinner("Image se supplier details read ho rahi hain..."):
                        result = _extract_data_from_image(
                            sup_uploaded.read(), sup_uploaded.type,
                            "Extract supplier/business details from ALL business cards in this image. "
                            "For each card: use COMPANY/BUSINESS name as name (not person's name). "
                            "If no company name, use person's name. "
                            "Save ALL phone numbers from each card as comma-separated string in phone field. "
                            "Return ONLY a JSON array, one object per card with keys: "
                            "name (company name), phone (all numbers comma-separated as string), address (full address). "
                            "If any field not found set it to null. "
                            "No explanation, no markdown, just raw JSON array. "
                            "Example: [{\"name\": \"Rohit Textile Inc\", \"phone\": \"+91 9582297932, +91 9871221331\", \"address\": \"GF 2892/5, Singhara Chowk, Sadar Bazar, Delhi-110006\"}]"
                        )
                        if isinstance(result, dict):  result = [result]
                        if not isinstance(result, list): result = []
                        result = [s for s in result if isinstance(s, dict)]
                        st.session_state["sup_extracted"] = result

            if "sup_extracted" in st.session_state:
                sup_list = st.session_state["sup_extracted"]
                if sup_list:
                    st.success(f"✅ {len(sup_list)} supplier(s) mile — edit karke save karo")
                    sup_edit_df = pd.DataFrame([{
                        "Name":    s.get("name","") or "",
                        "Phone":   str(s.get("phone","") or ""),
                        "Address": s.get("address","") or "",
                        "Remark":  s.get("remark","") or "",
                    } for s in sup_list])

                    edited_sup = st.data_editor(
                        sup_edit_df,
                        use_container_width=True,
                        hide_index=True,
                        num_rows="dynamic",
                        key="sup_editor",
                        column_config={
                            "Name":    st.column_config.TextColumn("Name"),
                            "Phone":   st.column_config.TextColumn("Phone *"),
                            "Address": st.column_config.TextColumn("Address"),
                            "Remark":  st.column_config.TextColumn("Remark"),
                        }
                    )
                    sc1, sc2 = st.columns([3,1])
                    with sc1:
                        if st.button("💾 Save All Suppliers", use_container_width=True,
                                     key="save_sup_img_btn", type="primary"):
                            saved, skipped, duplicate, no_phone = 0, 0, 0, 0
                            for _, row in edited_sup.iterrows():
                                name = str(row["Name"]).strip()
                                if not name:
                                    skipped += 1
                                    continue
                                result, reason = save_supplier(
                                    name, str(row["Phone"]),
                                    str(row["Address"]), str(row.get("Remark",""))
                                )
                                if result:           saved += 1
                                elif reason == "duplicate":  duplicate += 1
                                elif reason == "no_phone":   no_phone += 1
                            msg = f"✅ {saved} saved!"
                            if duplicate: msg += f" | ⚠️ {duplicate} duplicate skip"
                            if no_phone:  msg += f" | ❌ {no_phone} phone nahi tha skip"
                            if skipped:   msg += f" | {skipped} empty rows skip"
                            st.success(msg)
                            st.session_state.pop("sup_extracted", None)
                            st.session_state.pop("suppliers_df", None)
                            st.session_state["sup_img_reset"] = sup_img_reset + 1
                            st.rerun()
                    with sc2:
                        if st.button("🗑️ Clear", use_container_width=True, key="clear_sup_img"):
                            st.session_state.pop("sup_extracted", None)
                            st.session_state["sup_img_reset"] = sup_img_reset + 1
                            st.rerun()
                else:
                    st.warning("⚠️ Image se data nahi mila, manually fill karo.")

        if sup_mode == "✏️ Manual":
            c1, c2 = st.columns(2)
            with c1:
                s_name   = st.text_input("Supplier Name", key="s_name")
            with c2:
                s_phone  = st.text_input("Phone *", key="s_phone")

            c3, c4 = st.columns(2)
            with c3:
                s_address = st.text_input("Address", key="s_address")
            with c4:
                s_remark  = st.text_input("Remark", key="s_remark", placeholder="optional...")

            bc1, bc2 = st.columns([3,1])
            with bc1:
                if st.button("💾 Save Supplier", use_container_width=True,
                             key="save_sup_btn", type="primary"):
                    if not s_name.strip():
                        st.warning("⚠️ Supplier name required.")
                    elif not s_phone.strip():
                        st.warning("⚠️ Phone number required.")
                    else:
                        result, reason = save_supplier(s_name, s_phone, s_address, s_remark)
                        if result:
                            st.success(f"✅ Saved: {s_name}")
                            st.session_state.pop("suppliers_df", None)
                            st.rerun()
                        elif reason == "duplicate":
                            st.warning(f"⚠️ '{s_name}' already exists.")
                        elif reason == "no_phone":
                            st.warning("⚠️ Phone number required.")
            with bc2:
                if st.button("🔄 Refresh", use_container_width=True, key="refresh_sup"):
                    st.session_state.pop("suppliers_df", None)
                    st.rerun()


def _requirements_tab():
    st.caption("✅ Fulfilled requirements Auto delete after 7 days .")

    if "req_df" not in st.session_state:
        st.session_state["req_df"] = get_requirements()
    req_df = st.session_state["req_df"]

    if not req_df.empty:
        for _, row in req_df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1.5, 0.7])
                with c1:
                    status_icon = "✅" if row["Fulfilled"] else "⏳"
                    st.markdown(f"{status_icon} **{row['Product Name']}**")
                    st.caption(f"Qty: {row['Quantity']}  ·  {row['Remark']}  ·  Added: {row['Created']}")
                with c2:
                    if not row["Fulfilled"]:
                        if st.button("✅ Fulfill", key=f"fulfill_{row['id']}", use_container_width=True):
                            st.session_state[f"fmodal_{row['id']}"] = True
                    else:
                        st.success("Fulfilled")
                with c3:
                    if st.button("🗑️", key=f"del_req_{row['id']}", use_container_width=True):
                        delete_requirement(row["id"])
                        st.session_state.pop("req_df", None)
                        st.rerun()

                # Fulfill inline form
                if st.session_state.get(f"fmodal_{row['id']}"):
                    st.markdown("---")
                    st.markdown(f"**Fulfill: {row['Product Name']}**")
                    sup_df = get_suppliers()
                    sup_opts = {"(None)": None}
                    sup_opts.update({r["Name"]: r["id"] for _, r in sup_df.iterrows()})

                    fc1, fc2, fc3 = st.columns(3)
                    with fc1:
                        f_price = st.number_input("Purchased Amount (₹)", min_value=0.0,
                                                   step=0.01, key=f"fp_{row['id']}")
                    with fc2:
                        f_mrp = st.number_input("MRP (₹)", min_value=0.0,
                                                 step=0.01, key=f"fm_{row['id']}")
                    with fc3:
                        f_date = st.date_input("Purchase Date", value=date.today(), key=f"fd_{row['id']}")

                    f_sup = st.selectbox("Supplier", list(sup_opts.keys()), key=f"fs_{row['id']}")

                    ok1, ok2 = st.columns(2)
                    with ok1:
                        if st.button("✅ Confirm", key=f"fc_{row['id']}", type="primary", use_container_width=True):
                            fulfill_requirement(row["id"], row["Product Name"],
                                                f_price, f_mrp, sup_opts[f_sup], str(f_date))
                            st.session_state.pop(f"fmodal_{row['id']}", None)
                            st.session_state.pop("req_df", None)
                            st.session_state.pop("products_df", None)
                            st.success(f"✅ {row['Product Name']} saved!")
                            st.rerun()
                    with ok2:
                        if st.button("❌ Cancel", key=f"fcancel_{row['id']}", use_container_width=True):
                            st.session_state.pop(f"fmodal_{row['id']}", None)
                            st.rerun()
    else:
        st.info("No requirement .")

    st.markdown("---")

    with st.container(border=True):
        st.markdown("#### ➕ Add Requirement")
        r_name = st.text_input("Product Name", key="req_name")
        c1, c2 = st.columns(2)
        with c1:
            r_qty = st.text_input("Quantity", key="req_qty")
        with c2:
            r_rem = st.text_input("Remark", key="req_remark")

        bc1, bc2 = st.columns([3,1])
        with bc1:
            if st.button("💾 Add Requirement", use_container_width=True, key="save_req", type="primary"):
                if not r_name.strip():
                    st.warning("⚠️ Product name required.")
                else:
                    save_requirement(r_name, r_qty, r_rem)
                    st.success(f"✅ Added: {r_name}")
                    st.session_state.pop("req_df", None)
                    st.rerun()
        with bc2:
            if st.button("🔄 Refresh", use_container_width=True, key="refresh_req"):
                st.session_state.pop("req_df", None)
                st.rerun()
