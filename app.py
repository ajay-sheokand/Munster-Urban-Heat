from enum import auto
import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

import ee
from google.oauth2 import service_account

st.set_page_config(layout="wide")
st_autorefresh(interval=60000)

st.title("Münster Urban Heat Monitoring Dashboard")
st.markdown("""
This dashboard combines:
- **Real-Time Air temperature** (OpenWeather API)
- **Satellite-Derived Land Surface Temperature** (MODIS LST)
Covering **Münster and North Rhine-Westphalia (NRW), Germany**.
""")

API_KEY = st.secrets["OPENWEATHER_API_KEY"]

# Load Earth Engine credentials
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

# Define Münster/NRW region
#region = ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])
region = ee.Geometry.Rectangle([5.5, 50.8, 8.5, 52.5])


st.subheader("MODIS Satellite-Derived Daily Land Surface Temperature (LST)")

# Fetch MODIS LST
lst = (
    ee.ImageCollection("MODIS/061/MOD11A1")
    .filterDate("2025-12-31", "2026-01-30")
    .select("LST_Day_1km")
    .mean()
)

lst_celsius = lst.multiply(0.02).subtract(273.15)

# Create a plain Folium map
m = folium.Map(location=[51.9607, 7.6261], zoom_start=11)

# Function to add Earth Engine layer to Folium
def add_ee_layer(self, ee_image_object, vis_params, name, opacity=1.0):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=name,
        overlay=True,
        control=True,
        opacity= opacity,
    ).add_to(self)

folium.Map.add_ee_layer = add_ee_layer

# Add MODIS LST layer
vis_params = {
    "min": 25,
    "max": 50,
    "palette": ["blue", "green", "yellow", "orange", "red"],
}

lst = (
    ee.ImageCollection("MODIS/061/MOD11A1")  # Updated collection
    .filterDate("2025-12-31", "2026-01-30")
    .select("LST_Day_1km")
    .mean()
)


if lst.bandNames().size().getInfo() == 0:
    st.error("No MODIS images found for the selected date!")
else:
    lst_celsius = lst.multiply(0.02).subtract(273.15)
    lst_smooth = (
        lst_celsius.resample("bilinear").reproject(crs="EPSG:4326", scale=250)
    )
    m.add_ee_layer(lst_smooth.clip(region), vis_params, "MODIS LST Smooth Heat Map(°C)", opacity=0.5)

# Locations for weather monitoring - Münster districts
locations = [
    ("Altstadt", 51.9626, 7.6255),
    ("Kreuzviertel", 51.9714, 7.5989),
    ("Mauritz", 51.9476, 7.6344),
    ("Gievenbeck", 51.9969, 7.5936),
    ("Kinderhaus", 51.9890, 7.6700),
]

# Function to get live weather
def get_weather(lat, lon):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
    data = requests.get(url).json()
    return {
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "feels_like": data["main"]["feels_like"]
    }

# Function for heat alerts
def heat_alert(temp):
    if temp >= 40:
        return "🔥 Extreme Heat Alert! Stay Hydrated and Avoid Outdoor Activities."
    elif temp >= 35:
        return "⚠️ High Heat Warning! Take Precautions."
    else:
        return "🌤️ Normal Temperature."

# Add weather markers to map
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    alert = heat_alert(w["temperature"])
    popup = f"""
<b>{name}</b><br>
Temperature: {w['temperature']} °C<br>
Feels Like: {w['feels_like']} °C<br>
Humidity: {w['humidity']} %<br>
Status: {alert}
"""
    folium.Marker(
        location=[lat, lon],
        popup=popup,
        icon=folium.Icon(color="red" if w["temperature"] >= 35 else "green"),
    ).add_to(m)

# Render map in Streamlit
st_folium(m, width=1500, height=600)

# Time Series Analysis of MODIS LST
st.subheader("Time Series Analysis - Historical MODIS Land Surface Temperature")

# Date range selector
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=60))
with col2:
    end_date = st.date_input("End Date", datetime.now())

try:
    # Fetch MODIS data for the selected date range
    modis_collection = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .select("LST_Day_1km")
    )
    
    # Extract time series data for the region
    def extract_lst_stats(image):
        date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
        lst_celsius = image.multiply(0.02).subtract(273.15)
        
        # Calculate mean LST for the region
        mean_lst = lst_celsius.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=1000,
            maxPixels=1e9
        ).get('LST_Day_1km')
        
        return ee.Feature(None, {
            'date': date,
            'mean_lst': mean_lst
        })
    
    # Map the function over the collection
    ts_data = modis_collection.map(extract_lst_stats)
    
    # Get the data
    ts_list = ts_data.toList(ts_data.size()).getInfo()
    
    # Create DataFrame
    dates = []
    temps = []
    
    for feature in ts_list:
        if feature and 'properties' in feature:
            props = feature['properties']
            if props.get('mean_lst') is not None:
                dates.append(props['date'])
                temps.append(float(props['mean_lst']))
    
    if dates:
        df_ts = pd.DataFrame({
            'Date': pd.to_datetime(dates),
            'Mean LST (°C)': temps
        })
        df_ts = df_ts.sort_values('Date')
        
        # Create interactive time series plot
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_ts['Date'],
            y=df_ts['Mean LST (°C)'],
            mode='lines+markers',
            name='Mean LST',
            line=dict(color='orangered', width=2),
            marker=dict(size=6)
        ))
        
        fig.update_layout(
            title='MODIS Land Surface Temperature Time Series (Münster Region)',
            xaxis_title='Date',
            yaxis_title='Temperature (°C)',
            hovermode='x unified',
            height=400,
            template='plotly_white'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display statistics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Average LST", f"{df_ts['Mean LST (°C)'].mean():.2f}°C")
        with col2:
            st.metric("Max LST", f"{df_ts['Mean LST (°C)'].max():.2f}°C")
        with col3:
            st.metric("Min LST", f"{df_ts['Mean LST (°C)'].min():.2f}°C")
        with col4:
            st.metric("Data Points", len(df_ts))
    else:
        st.warning("No MODIS data available for the selected date range.")
        
except Exception as e:
    st.error(f"Error fetching time series data: {str(e)}")


st.subheader("Live Heat Alerts for Münster and NRW Region")
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    st.write(f"**{name}**: {w['temperature']} °C, Feels Like: {w['feels_like']} °C, Humidity: {w['humidity']} %")

st.caption("Satellite Data Source: MODIS LST | Weather Data Source: OpenWeather API")
