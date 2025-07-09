from datetime import datetime
import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re
import simplekml
import tempfile

st.set_page_config(page_title="Tejas Surveying - Smart Estimate", layout="centered")
st.title("📍 Property Lookup with Deed, Map & KMZ")

rate = st.number_input("Rate per foot ($)", min_value=0.0, value=1.25)

# Select county
county = st.selectbox("Select County", ["Fort Bend", "Harris"])

# Configuration for each county
county_config = {
    "Fort Bend": {
        "endpoint": "https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCAD_Public_Data/FeatureServer/0/query",
        "crs": "EPSG:2278",
        "fields": {
            "street_num": "situssno",
            "street_name": "situssnm",
            "street_type": "situsstp",
            "owner": "ownername",
            "legal": "legal",
            "deed": "instrunum",
            "parcel_id": "propnumber",
            "quickrefid": "quickrefid",
            "acres": "landsizeac"
        }
    },
    "Harris": {
        "endpoint": "https://services.arcgis.com/su8ic9KbA7PYVxPS/ArcGIS/rest/services/Harris_County_Parcels/FeatureServer/1/query",
        "crs": "EPSG:2278",
        "fields": {
            "street_num": "site_str_num",
            "street_name": "site_str_name",
            "street_type": "site_str_sfx",
            "owner": "owner_name_1",
            "legal": "legal_desc",
            "deed": "deed_ref",
            "parcel_id": "HCAD_NUM",
            "quickrefid": "LOWPARCELID",
            "acres": "Acreage"
        }
    }
}

config = county_config[county]
fields = config["fields"]
endpoint = config["endpoint"]
crs_target = config["crs"]

def parse_address_loose(address):
    pattern = re.compile(r'^(\d+)?\s*([\w\s]+?)(\s+(RD|ST|DR|LN|BLVD|CT|AVE|HWY|WAY|TRAIL|PKWY|CIR))?$', re.IGNORECASE)
    match = pattern.search(address.strip().upper())
    if match:
        number = match.group(1) or ''
        name = match.group(2).strip()
        st_type = match.group(4).strip() if match.group(4) else ''
        return number.strip(), name, st_type
    return None, None, None

def query_parcels(where_clause):
    params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson"
    }
    r = requests.get(endpoint, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("features", [])

def estimate_perimeter_cost(geom, rate):
    project = pyproj.Transformer.from_crs("EPSG:4326", crs_target, always_xy=True).transform
    geom_proj = transform(project, geom)
    perimeter_ft = geom_proj.length
    area_ft2 = geom_proj.area
    area_acres = area_ft2 / 43560
    estimate = perimeter_ft * rate
    return perimeter_ft, area_acres, estimate

# Search UI
search_mode = st.radio("Search by:", ["Address", "Quick Ref ID", "Owner Name"])
query = ""
last = first = ""
matches = []

if search_mode == "Address":
    query = st.text_input("Enter Property Address (e.g. 1810 Main or Main St)")
    if query:
        number, name, st_type = parse_address_loose(query)
        if name:
            clauses = []
            if number and st_type:
                clauses.append(f"{fields['street_num']} = '{number}' AND UPPER({fields['street_name']}) LIKE '%{name.upper()}%' AND UPPER({fields['street_type']}) = '{st_type.upper()}'")
            if number:
                clauses.append(f"{fields['street_num']} = '{number}' AND UPPER({fields['street_name']}) LIKE '%{name.upper()}%'")
            clauses.append(f"UPPER({fields['street_name']}) LIKE '%{name.upper()}%'")
            for clause in clauses:
                matches = query_parcels(clause)
                if matches:
                    break

elif search_mode == "Quick Ref ID":
    query = st.text_input("Enter Quick Ref ID")
    if query:
        where = f"{fields['quickrefid']} = '{query.strip()}'"
        matches = query_parcels(where)

elif search_mode == "Owner Name":
    last = st.text_input("Last Name")
    first = st.text_input("First Name (optional)")
    if last:
        lname = last.strip().upper()
        fname = first.strip().upper()
        if fname:
            where = f"UPPER({fields['owner']}) LIKE '{lname}, {fname}%'"
        else:
            where = f"UPPER({fields['owner']}) LIKE '{lname}%'"
        matches = query_parcels(where)

# Feature selection
feature = None
if matches:
    if len(matches) == 1:
        feature = matches[0]
    else:
        options = {
            f"{f['properties'].get(fields['quickrefid'])} | {f['properties'].get(fields['owner'])} | {f['properties'].get(fields['legal'], '')[:40]}": f
            for f in matches
        }
        option_keys = list(options.keys())
        default_index = 0
        if "selected_option" not in st.session_state:
            st.session_state.selected_option = option_keys[0]
        else:
            try:
                default_index = option_keys.index(st.session_state.selected_option)
            except ValueError:
                default_index = 0
        selected = st.selectbox("Multiple parcels found. Select one:", option_keys, index=default_index, key="parcel_selectbox")
        st.session_state.selected_option = selected
        feature = options[selected]
elif query or last:
    st.warning("No matching parcels found.")

# Display output
if feature:
    props = feature["properties"]
    legal = props.get(fields["legal"], "N/A")
    quickrefid = props.get(fields["quickrefid"], "")
    deed = props.get(fields.get("deed", ""), "").strip()
    subdivision = block = lot = acres = None

    if legal and legal != "N/A":
        subdivision = legal.split(",")[0].title()

    try:
        geom = shape(feature["geometry"])
        perimeter_ft, area_acres, estimate = estimate_perimeter_cost(geom, rate)

        st.success("✅ Parcel found and estimate generated.")
        st.markdown(f"**Owner:** {props.get(fields['owner'], 'N/A')}")
        st.markdown(f"**Quick Ref ID:** {quickrefid}")
        st.markdown(f"**Geo ID:** {props.get(fields['parcel_id'], 'N/A')}")
        st.markdown(f"**Legal Description:** {legal}")
        if subdivision: st.markdown(f"**Subdivision:** {subdivision}")
        if acres: st.markdown(f"**Called Acreage:** {props.get(fields['acres'], 'N/A')}")
        if deed:
            st.markdown(f"**Deed Reference:** {deed} — [Search Site](https://ccweb.co.fort-bend.tx.us/RealEstate/SearchEntry.aspx)")
        else:
            st.markdown("**Deed Reference:** N/A")
        st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
        st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
        st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")

        # Google Maps
        centroid = geom.centroid
        maps_url = f"https://www.google.com/maps/search/?api=1&query={centroid.y},{centroid.x}"
        st.markdown(f"**📍 View on Google Maps:** [Open Map]({maps_url})")

    except Exception as e:
        st.error("❌ Unable to process parcel geometry.")
        st.text(str(e))
