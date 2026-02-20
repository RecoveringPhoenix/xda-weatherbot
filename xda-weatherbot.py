import network
import time
import ntptime
import urequests
from machine import Pin
import dht

# Configuration
WIFI_SSID = ""
WIFI_PASSWORD = ""

OPENWEATHER_API_KEY = ""
CITY = ""

BLUESKY_HANDLE = ".bsky.social"
BLUESKY_PASSWORD = "

POST_HOURS = {7, 12, 17}   # CST local time
UTC_OFFSET = -6
GPIO_PIN = 15

# Hardware setup
sensor = dht.DHT11(Pin(GPIO_PIN))

# WiFi connection
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    while not wlan.isconnected():
        time.sleep(1)

    print("WiFi connected:", wlan.ifconfig())

# Time helpers
def localtime():
    return time.localtime(time.time() + UTC_OFFSET * 3600)
    
def iso_timestamp():
    t = time.gmtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )

def natural_timestamp():
    months = [
        "January","February","March","April","May","June",
        "July","August","September","October","November","December"
    ]

    t = localtime()
    year, month, day, hour, minute = t[0], t[1], t[2], t[3], t[4]

    suffix = "AM"
    if hour >= 12:
        suffix = "PM"
    hour12 = hour % 12
    if hour12 == 0:
        hour12 = 12

    return "{} {}, {} at {}:{:02d} {}".format(
        months[month - 1],
        day,
        year,
        hour12,
        minute,
        suffix
    )

# Collect the data for our post
def collect_data():
    # Inside conditions
    sensor.measure()
    inside_temp_c = sensor.temperature()
    inside_temp_f = (inside_temp_c * 9 / 5) + 32
    humidity = sensor.humidity()
    
    # Outside conditions
    url = (
        "http://api.openweathermap.org/data/2.5/weather?"
        "q={}&appid={}&units=imperial"
        ).format(CITY, OPENWEATHER_API_KEY)
    r = urequests.get(url)
    data = r.json()
    r.close()
    
    outside_temp = data["main"]["temp"]
    weather_desc = data["weather"][0]["description"]

    return {
        "inside_temp_f": inside_temp_f,
        "humidity": humidity,
        "outside_temp": outside_temp,
        "weather_desc": weather_desc,
        "timestamp": natural_timestamp()
    }

# Format the message
def format_post(data):
    return (
        "It's currently {} and here are the weather conditions.\n"
        "In my office, it's {:.1f} F with {}% humidity.\n"
        "Outside, it's {:.1f} F, {}."
        ).format(
            data["timestamp"],
            data["inside_temp_f"],
            data["humidity"],
            data["outside_temp"],
            data["weather_desc"]
            )

# ---- Bluesky publishing ----
def bluesky_login():
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"

    payload = {
        "identifier": BLUESKY_HANDLE,
        "password": BLUESKY_PASSWORD
    }

    r = urequests.post(url, json=payload)
    data = r.json()
    r.close()

    return data["accessJwt"], data["did"]

def publish_post(message):
    token, did = bluesky_login()

    url = "https://bsky.social/xrpc/com.atproto.repo.createRecord"

    headers = {
        "Authorization": "Bearer " + token
    }

    payload = {
        "repo": did,
        "collection": "app.bsky.feed.post",
        "record": {
            "text": message,
            "createdAt": iso_timestamp()
        }
    }

    r = urequests.post(url, headers=headers, json=payload)
    print("Bluesky response:", r.text)
    r.close()

# Bring it all together to publish the post
def report_and_post():
    try:
        data = collect_data()
        message = format_post(data)

        print("\n=== Weather Report ===")
        print(message)

        publish_post(message)
        print("\nPosted to Bluesky.")

    except Exception as e:
        print("Error:", e)

# Startup
connect_wifi()
time.sleep(3)
ntptime.settime()

# Force a post at startup
report_and_post()

last_post_hour = -1
last_post_day = -1
last_sync_day = -1

# Scheduling loop
while True:
    now = localtime()
    hour = now[3]
    minute = now[4]
    day = now[2]

    # Daily time resync at 3:00 AM
    if hour == 3 and minute == 0 and day != last_sync_day:
        ntptime.settime()
        last_sync_day = day

    # Post at the top of the hour only once
    if hour in POST_HOURS and minute == 0:
        if hour != last_post_hour or day != last_post_day:
            report_and_post()
            last_post_hour = hour
            last_post_day = day

    time.sleep(30)
