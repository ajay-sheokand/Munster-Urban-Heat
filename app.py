import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh


import ee 
import geemap

st_autorefresh(interval=60000)

st.title("Delhi-NCR Urban Heat Monitoring Dashboard")
st.markdown("""
This dashboard combines;
            -**Real-Time Air temperature**(OpenWeather API)
            -**Satellite-Derived Land Surface Temperature** (MODIS LST)

Covering **Delhi + NCR Region**.
            """)

API_KEY = st.secrets["OPENWEATHER_API_KEY"]


import json
from google.oauth2 import service_account

# Load credentials from Streamlit secrets
service_account_info = {
    "type": "service_account",
    "client_email": st.secrets["GEE_SERVICE_ACCOUNT"],
    "private_key": st.secrets["GEE_PRIVATE_KEY"],
    "token_uri": "https://oauth2.googleapis.com/token",
}

credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/earthengine"]
)

ee.Initialize(credentials)


region = ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])


st.subheader("MODIS Satellite-Derived Daily Land Surface Temperature (LST)")

lst = (
    ee.ImageCollection("MODIS/006/MOD11A1")
    .filterDate("2024-05-01", "2024-05-02")  # latest day
    .select("LST_Day_1km")
    .mean()
)


lst_celsius = lst.multiply(0.02).subtract(273.15)

Map = geemap.Map(center=[28.6139, 77.209], zoom=8)

Map.addLayer(
    lst_celsius.clip(region),
    {
        "Min":25,
        "Max":50,
        "palette":["blue", "green", "yellow", "orange", "red"],
    },
    "MODIS Land Surface Temperature (Degree Celsius)",
)

locations = [
    ("Delhi", 28.6139, 77.2090),
    ("Gurgaon", 28.4595, 77.0266),
    ("Noida", 28.5355, 77.3910),
    ("Faridabad", 28.4089, 77.3178),
    ("Ghaziabad", 28.6692, 77.4538),  
]

def get_weather(lat, lon):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
    data = requests.get(url).json()
    return{
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "feels like": data["main"]["feels_like"],

    }


def heat_alert(temp):
    if temp >= 40:
        return "🔥 Extreme Heat Alert! Stay Hydrated and Avoid Outdoor Activities."
    elif temp >= 35:
        return "⚠️ High Heat Warning! Take Precautions."
    else:
        return "🌤️ Normal Temperature."
    

for name, lat, lon in locations:
    w = get_weather(lat,lon)
    alert = heat_alert(w["temperature"])

    popup = f"""
<b>{name}</b><br>
Temperature: {w['temperature']} °C<br>
Feels Like: {w['feels like']} °C<br>
Humidity: {w['humidity']} %<br>
Status: {alert}
    """
    folium.Marker(
        location=[lat, lon],
        popup=popup,
        icon=folium.Icon(color="red" if w["temperature"] >=35 else "green"),
    ).add_to(Map)


st_folium(Map, width=800, height=500)
st.subheader("Live Heat Alerts for Delhi-NCR Region")


for name, lat, lon in locations:
    w = get_weather(lat, lon)
    st.write(f"**{name}**: {w['temperature']} °C, Feels Like: {w['feels like']} °C, Humidity: {w['humidity']} %")

st.caption("Satellite Data Source: MODIS LST | Weather Data Source: OpenWeather API")