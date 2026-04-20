import os
from supabase import create_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not url.startswith("https://"):
    raise RuntimeError("Invalid SUPABASE_URL")

if not key:
    raise RuntimeError("Missing SUPABASE_KEY")

supabase = create_client(url, key)