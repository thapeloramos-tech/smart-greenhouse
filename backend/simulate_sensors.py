import random
import time
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
#SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

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

def log_irrigation(zone_id, minutes, mode):
    litres_used = float(minutes) * float(FLOW_RATE_LPM)

    data = {
        "zone_id": zone_id,
        "duration_minutes": float(minutes),
        "litres_used": litres_used,
        "mode": mode
    }

    supabase.table("irrigation_logs").insert(data).execute()
    print(f"💧 Logged irrigation: {litres_used:.1f} litres used")

def run_rule_engine(zone, moisture):
    threshold = float(zone["moisture_threshold"])
    max_minutes = float(zone["max_irrigation_minutes"])
    mode = (zone.get("irrigation_mode") or "rule").lower()

    if mode == "manual":
        print(f"⏸ Zone {zone['name']} is MANUAL (auto disabled)")
        return

    if mode == "smart":
        # For now, smart behaves like rule until Day 6/7 ML
        print(f"🧠 Zone {zone['name']} SMART (using rule logic for now)")

    if moisture < threshold:
        print(f"⚠ Zone {zone['name']} LOW moisture ({moisture:.2f} < {threshold})")
        if not alert_exists_recent(zone["id"], "low_moisture", minutes=60):
            create_alert(zone["id"], "low_moisture", "warning",f"{zone['name']} moisture low: {moisture:.2f}")

        if can_irrigate(zone["id"]):
            print(f"💧 Irrigating for {max_minutes} minutes...")
            log_irrigation(zone["id"], max_minutes, mode)
        else:
            print("⏳ Cooldown active. Skipping irrigation.")
    else:
        print(f"✓ Zone {zone['name']} moisture OK ({moisture:.2f} >= {threshold})")


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

def print_today_water_usage():
    today = datetime.utcnow().date()
    resp = supabase.table("irrigation_logs").select("litres_used, created_at").execute()

    total = 0.0
    for row in resp.data:
        created_date = datetime.fromisoformat(row["created_at"].replace("Z", "")).date()
        if created_date == today and row["litres_used"] is not None:
            total += float(row["litres_used"])

    print(f"📊 Total water used today: {total:.1f} litres")
def fetch_pending_requests():
    resp = supabase.table("irrigation_requests") \
        .select("*") \
        .eq("status", "pending") \
        .order("created_at", desc=False) \
        .execute()
    return resp.data

def mark_request_done(request_id):
    supabase.table("irrigation_requests") \
        .update({"status": "done", "processed_at": datetime.utcnow().isoformat()}) \
        .eq("id", request_id) \
        .execute()

def process_manual_requests():
    requests = fetch_pending_requests()

    for req in requests:
        zone_id = req["zone_id"]
        minutes = float(req["minutes"])

        print(f"🟦 Manual request: zone={zone_id} minutes={minutes}")

        if can_irrigate(zone_id):
            log_irrigation(zone_id, minutes, "manual")
            mark_request_done(req["id"])
        else:
            print("⏳ Cooldown active. Manual request skipped.")

def create_alert(zone_id, alert_type, severity, message):
    data = {
        "zone_id": zone_id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "status": "open"
    }
    supabase.table("alerts").insert(data).execute()

def alert_exists_recent(zone_id, alert_type, minutes=60):
    resp = supabase.table("alerts") \
        .select("created_at") \
        .eq("zone_id", zone_id) \
        .eq("alert_type", alert_type) \
        .eq("status", "open") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if not resp.data:
        return False

    last_time = datetime.fromisoformat(resp.data[0]["created_at"].replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last_time) < timedelta(minutes=minutes)

while True:
    zones = get_zones()
    process_manual_requests()
    print_today_water_usage()

    for zone in zones:
        moisture = random.uniform(20, 60)
        temperature = random.uniform(25, 38)
        humidity = random.uniform(40, 80)

        insert_sensor_readings(zone["id"], moisture, temperature, humidity)
        run_rule_engine(zone, moisture)

    time.sleep(15)