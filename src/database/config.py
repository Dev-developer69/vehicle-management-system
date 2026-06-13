import streamlit as st
from supabase import Client, create_client

# Regular client — anon key
supabase: Client = create_client(
    st.secrets['SUPABASE_URL'],
    st.secrets['SUPABASE_API_KEY']
)

# Admin client — service role key (user create/delete ke liye)
supabase_admin: Client = create_client(
    st.secrets['SUPABASE_URL'],
    st.secrets['SUPABASE_SERVICE_KEY']
)
