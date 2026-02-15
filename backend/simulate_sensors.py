import random
import time
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

COOLDOWN_MINUTES = 30 # Minutes before the same zone can be irrigated again
FLOW_RATE_LPM = 20  # litres per minute

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_zones():
    response = supabase.table("zones").select("*").execute()
    return response.data

def insert_sensor_readings(zone_id, moisture, temperature, humidity):
    data = {
        "zone_id": zone_id,
        "moisture": moisture,
        "temperature": temperature,
        "humidity": humidity
    }
    supabase.table("sensor_readings").insert(data).execute()

def log_irrigation(zone_id, duration, mode):
    data = {
        "zone_id": zone_id,
        "duration_minutes": duration,
        "mode": mode
    }
    supabase.table("irrigation_logs").insert(data).execute()

def run_rule_engine(zone, moisture):
    threshold = zone["moisture_threshold"]
    max_minutes = zone["max_irrigation_minutes"]

    if moisture < threshold:
        print(f"⚠ Zone {zone['name']} LOW moisture ({moisture:.2f})")

        if can_irrigate(zone["id"]):
            print(f"💧 Irrigating for {max_minutes} minutes...")
            log_irrigation(zone["id"], max_minutes, "rule")
        else:
            print("⏳ Cooldown active. Skipping irrigation.")
    else:
        print(f"✓ Zone {zone['name']} moisture OK ({moisture:.2f})")

def can_irrigate(zone_id):
    response = supabase.table("irrigation_logs") \
        .select("*") \
        .eq("zone_id", zone_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if len(response.data) == 0:
        return True  # Never irrigated before

    last_irrigation = response.data[0]["created_at"]
    # Parse as aware datetime (UTC)
    last_time = datetime.fromisoformat(last_irrigation.replace("Z", "+00:00"))

    # Use UTC-aware datetime for comparison
    if datetime.now(timezone.utc) - last_time > timedelta(minutes=COOLDOWN_MINUTES):
        return True

    return False

while True:
    zones = get_zones()

    for zone in zones:
        moisture = random.uniform(20, 60)
        temperature = random.uniform(25, 38)
        humidity = random.uniform(40, 80)

        insert_sensor_readings(zone["id"], moisture, temperature, humidity)
        run_rule_engine(zone, moisture)

    time.sleep(15)