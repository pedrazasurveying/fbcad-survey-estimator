
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

# County selection
county = st.selectbox("Select County", ["Fort Bend", "Harris"])

# County config
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
            "acres": "landsizeac",
            "market": "totalvalue"
        },
        "deed_url_base": "https://ccweb.co.fort-bend.tx.us/RealEstate/SearchEntry.aspx",
        "fbcad_link_template": "https://esearch.fbcad.org/Property/View?Id={}&year={}"
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
            "acres": "Acreage",
            "market": "MKT_VAL"
        },
        "deed_url_base": "https://www.cclerk.hctx.net/Applications/websearch/RealProperty",
        "fbcad_link_template": None
    }
}

config = county_config[county]
fields = config["fields"]
endpoint = config["endpoint"]
crs_target = config["crs"]

def parse_legal_description(legal):
    subdivision = block = lot = None
    subdivision_match = re.match(r'^(.*?)(BLOCK|LOT|RESERVE|ACRES)', legal, re.IGNORECASE)
    if subdivision_match:
        subdivision = subdivision_match.group(1).strip(", ").title()
    block_match = re.search(r'BLOCK\s+(\w+)', legal, re.IGNORECASE)
    if block_match:
        block = block_match.group(1)
    lot_match = re.search(r'(LOT|RESERVE)\s+["\w]+', legal, re.IGNORECASE)
    if lot_match:
        lot = lot_match.group(0).strip()
    return subdivision, block, lot

def generate_kmz(geom, metadata=None):
    kml = simplekml.Kml()
    poly = None
    if geom.geom_type == "Polygon":
        coords = [(x, y) for x, y in list(geom.exterior.coords)]
        poly = kml.newpolygon(name="Parcel", outerboundaryis=coords)
    elif geom.geom_type == "MultiPolygon":
        for poly_geom in geom.geoms:
            coords = [(x, y) for x, y in list(poly_geom.exterior.coords)]
            poly = kml.newpolygon(name="Parcel Part", outerboundaryis=coords)
    if poly:
        poly.style.polystyle.fill = 0
        poly.style.linestyle.color = simplekml.Color.red
        poly.style.linestyle.width = 5
        if metadata:
            html = ''.join([f"<b>{k}:</b> {v}<br>" for k, v in metadata.items()])
            poly.description = html
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".kmz")
    kml.savekmz(tmp.name)
    return tmp.name

def query_parcels(where_clause):
    params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson"
    }
    try:
        r = requests.get(endpoint, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("features", [])
    except Exception as e:
        st.text(str(e))
        return []

# UI: address entry
search_mode = st.radio("Search by:", ["Address", "Quick Ref ID", "Owner Name"])
query = ""
matches = []

def parse_address_loose(address):
    pattern = re.compile(r'^(\d+)?\s*([\w\s]+?)(\s+(RD|ST|DR|LN|BLVD|CT|AVE|HWY|WAY|TRAIL|PKWY|CIR))?$', re.IGNORECASE)
    match = pattern.search(address.strip().upper())
    if match:
        number = match.group(1) or ''
        name = match.group(2).strip()
        st_type = match.group(4).strip() if match.group(4) else ''
        return number.strip(), name, st_type
    return None, None, None

if search_mode == "Address":
    query = st.text_input("Enter Property Address")
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
        selected = st.selectbox("Multiple parcels found. Select one:", list(options.keys()))
        if selected:
            feature = options[selected]

# Output
if feature:
    props = feature["properties"]
    legal = props.get(fields["legal"], "N/A")
    quickrefid = props.get(fields["quickrefid"], "")
    deed = props.get(fields.get("deed", ""), "").strip()
    owner = props.get(fields["owner"], "N/A")
    market_val = props.get(fields.get("market", ""), "N/A")
    acres = props.get(fields.get("acres", ""), "N/A")

    subdivision = block = lot = None
    if legal and legal != "N/A":
        subdivision, block, lot = parse_legal_description(legal)

    try:
        geom = shape(feature["geometry"])
        project = pyproj.Transformer.from_crs("EPSG:4326", crs_target, always_xy=True).transform
        geom_proj = transform(project, geom)
        perimeter_ft = geom_proj.length
        area_ft2 = geom_proj.area
        area_acres = area_ft2 / 43560

        st.success("✅ Parcel found and estimate generated.")
        st.markdown(f"**Owner:** {owner}")
        st.markdown(f"**Quick Ref ID:** {quickrefid}")
        st.markdown(f"**Geo ID:** {props.get(fields['parcel_id'], 'N/A')}")
        st.markdown(f"**Legal Description:** {legal}")
        if subdivision: st.markdown(f"**Subdivision:** {subdivision}")
        if block: st.markdown(f"**Block:** {block}")
        if lot: st.markdown(f"**Lot/Reserve:** {lot}")
        st.markdown(f"**Called Acreage:** {acres}")
        st.markdown(f"**Market Value:** ${float(market_val):,.2f}" if market_val and str(market_val).replace('.', '').isdigit() else "**Market Value:** N/A")
        st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
        st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
        if deed:
            st.markdown(f"**Deed Reference:** {deed} — [Search Site]({config['deed_url_base']})")
        else:
            st.markdown("**Deed Reference:** N/A")
        if config.get("fbcad_link_template") and quickrefid:
            st.markdown(f"**FBCAD Page:** [View Property]({config['fbcad_link_template'].format(quickrefid, datetime.now().year)})")

        centroid = geom.centroid
        maps_url = f"https://www.google.com/maps/search/?api=1&query={centroid.y},{centroid.x}"
        st.markdown(f"**📍 View on Google Maps:** [Open Map]({maps_url})")

        kmz_data = {
            "Owner": owner,
            "Geo ID": props.get(fields['parcel_id'], "N/A"),
            "Legal": legal,
            "Subdivision": subdivision or "",
            "Block": block or "",
            "Lot/Reserve": lot or "",
            "Deed": deed or "",
            "Area (ac)": f"{area_acres:.2f}",
            "Perimeter (ft)": f"{perimeter_ft:.2f}"
        }

        kmz_path = generate_kmz(geom, metadata=kmz_data)
        with open(kmz_path, "rb") as f:
            st.download_button("📥 Download KMZ (Google Earth)", f, file_name="parcel.kmz")

    except Exception as e:
        st.error("❌ Unable to process parcel geometry.")
        st.text(str(e))
