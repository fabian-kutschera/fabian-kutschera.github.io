#!/usr/bin/env python
# coding: utf-8

import os
import datetime
import requests

# -----------------------------------------------------------------------------
# Configure GMT before PyGMT starts its first GMT session.
# Keep the directory paths supplied by GitHub Actions, but make sure they
# exist and are accessible to GMT.
# -----------------------------------------------------------------------------
gmt_userdir = os.environ.get(
    "GMT_USERDIR", os.path.join(os.path.expanduser("~"), ".gmt")
)
gmt_cachedir = os.environ.get(
    "GMT_CACHEDIR", os.path.join(gmt_userdir, "cache")
)
gmt_sessiondir = os.environ.get(
    "GMT_SESSIONDIR", os.path.join(gmt_userdir, "sessions")
)

for directory in (gmt_userdir, gmt_cachedir, gmt_sessiondir):
    os.makedirs(directory, exist_ok=True)
    if not os.access(directory, os.R_OK | os.W_OK | os.X_OK):
        raise PermissionError(
            f"GMT directory is not readable/writable: {directory}"
        )

# Make sure GMT sees the checked directories before its first session starts.
os.environ["GMT_USERDIR"] = gmt_userdir
os.environ["GMT_CACHEDIR"] = gmt_cachedir
os.environ["GMT_SESSIONDIR"] = gmt_sessiondir

import geopandas as gpd
import pygmt
from pygmt.clib import Session
from pygmt.params import Box, Position

# GMT 6.6 can inherit a setting that disables remote downloads. PyGMT 0.19
# does not expose the deprecated GMT_AUTO_DOWNLOAD setting through
# pygmt.config, so set it directly through GMT's own `set` module.
# GMT still supports this setting for backwards compatibility.
with Session() as lib:
    lib.call_module(
        module="set",
        args=[
            "GMT_AUTO_DOWNLOAD=on",
            "GMT_DATA_UPDATE_INTERVAL=1d",
        ],
    )

print(f"GMT_USERDIR: {gmt_userdir}")
print(f"GMT_CACHEDIR: {gmt_cachedir}")
print(f"GMT_SESSIONDIR: {gmt_sessiondir}")
print("GMT remote data downloads: enabled")


def _safe_product_rank(value):
    """Convert a USGS product ranking/time value to an integer safely."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def select_reviewed_mww_solution(detail_geojson):
    """Return the preferred reviewed Mww moment-tensor product, if present.

    USGS event detail GeoJSON may omit the moment-tensor product entirely.
    If multiple products are available, prefer the largest preferredWeight;
    break ties using the most recent updateTime, following ComCat guidance.
    """
    if not isinstance(detail_geojson, dict):
        return None, "the event-detail response is not a GeoJSON object"

    event_properties = detail_geojson.get("properties")
    if not isinstance(event_properties, dict):
        return None, "the event-detail GeoJSON has no valid properties object"

    products = event_properties.get("products")
    if not isinstance(products, dict):
        return None, "the event-detail GeoJSON has no products object"

    moment_tensor_products = products.get("moment-tensor")
    if not isinstance(moment_tensor_products, list) or not moment_tensor_products:
        return None, "no moment-tensor product is available"

    required_properties = (
        "nodal-plane-1-dip",
        "nodal-plane-1-rake",
        "nodal-plane-1-strike",
        "longitude",
        "latitude",
        "depth",
        "derived-magnitude",
        "eventtime",
    )
    candidates = []

    for product in moment_tensor_products:
        if not isinstance(product, dict):
            continue

        product_properties = product.get("properties")
        if not isinstance(product_properties, dict):
            continue
        if product_properties.get("review-status") != "reviewed":
            continue
        if product_properties.get("derived-magnitude-type") != "Mww":
            continue

        if any(
            product_properties.get(key) in (None, "")
            for key in required_properties
        ):
            continue

        # Validate the values now, so one malformed product does not stop
        # processing of this event or any subsequent event.
        try:
            for key in required_properties[:-1]:
                float(product_properties[key])
            format_utc_event_time(product_properties["eventtime"])
        except (TypeError, ValueError, KeyError):
            continue

        rank = (
            _safe_product_rank(product.get("preferredWeight")),
            _safe_product_rank(product.get("updateTime")),
        )
        candidates.append((rank, product))

    if not candidates:
        return (
            None,
            "no reviewed Mww moment-tensor solution with the required "
            "nodal-plane/source parameters is available",
        )

    return max(candidates, key=lambda item: item[0])[1], None


def format_utc_event_time(value):
    """Format a USGS ISO-8601 event time consistently in UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("USGS eventtime is missing or is not a string")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    else:
        parsed = parsed.astimezone(datetime.timezone.utc)

    return parsed.strftime("%Y-%m-%d %H:%M:%S") + " (UTC)"


# get current time
date = datetime.datetime.today()
print(date)


# USGS GeoJSON
link = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"
gdf = gpd.read_file(link)


# update readme
with open("assets/README.log", 'r+') as f:
    lines = f.readlines()     # lines is list of line, each element '...\n'
    if len(gdf) == 0:
        eqs_found = "No significant earthquakes found on {}, week no. {}.\n".format(date.strftime('%Y-%m-%d'), date.isocalendar().week)
        print(eqs_found)
        lines.insert(0, eqs_found)  # you can use any index if you know the line index
        f.seek(0)                 # file pointer locates at the beginning to write the whole file again
        f.writelines(lines)       # write whole lists again to the same file
        exit()
    else:
        eqs_found = "{} significant earthquake(s) found on {}, week no. {}.\n".format(len(gdf), date.strftime('%Y-%m-%d'), date.isocalendar().week)
        print(eqs_found)
        lines.insert(0, eqs_found)
        f.seek(0)
        f.writelines(lines)


for event_index, event in gdf.iterrows():
    # Get the event ID and review status from the weekly summary feed.
    id_code = event["id"]

    if event.get("status") == "reviewed":
        print("{} is reviewed.".format(id_code))
    else:
        print("{} not reviewed, skipped.".format(id_code))
        continue

    # Preserve the existing image path and filename convention.
    image_path = "assets/images/seismicity/{}.png".format(id_code)
    if os.path.isfile(image_path):
        print("File exists, skipped.")
        continue

    # Retrieve the event-detail GeoJSON. A problem with one event should
    # not prevent subsequent events in the weekly feed from being handled.
    detail_url = event.get("detail")
    if not detail_url:
        print("{} has no detail URL; skipping event.".format(id_code))
        continue

    try:
        response = requests.get(detail_url, timeout=30)
        response.raise_for_status()
        detail_geojson = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(
            "Could not retrieve/parse detail GeoJSON for {}: {}. "
            "Skipping event.".format(id_code, exc)
        )
        continue

    if not isinstance(detail_geojson, dict):
        print("{} returned an unexpected detail-GeoJSON structure; skipping event.".format(id_code))
        continue

    # A reviewed event does not necessarily have a moment-tensor product.
    # Select only a reviewed Mww solution with the parameters needed below.
    moment_tensor_product, skip_reason = select_reviewed_mww_solution(
        detail_geojson
    )
    if moment_tensor_product is None:
        print("{}: {}; skipping this event.".format(id_code, skip_reason))
        continue

    event_properties = detail_geojson.get("properties") or {}
    mt_properties = moment_tensor_product.get("properties") or {}

    source_code = mt_properties.get(
        "eventsourcecode", moment_tensor_product.get("source", "unknown")
    )
    print("Found {} with status {}.".format(
        source_code, mt_properties.get("review-status", "unknown")
    ))
    print("Moment Tensor data found.")

    # Extract the first nodal plane, which is the one used by the existing
    # focal-mechanism plot. The second nodal plane is reported when present.
    nodalplane1dip = float(mt_properties["nodal-plane-1-dip"])
    nodalplane1rake = float(mt_properties["nodal-plane-1-rake"])
    nodalplane1strike = float(mt_properties["nodal-plane-1-strike"])

    nodal_plane_2_keys = (
        "nodal-plane-2-dip",
        "nodal-plane-2-rake",
        "nodal-plane-2-strike",
    )
    if all(mt_properties.get(key) not in (None, "") for key in nodal_plane_2_keys):
        nodalplane2dip, nodalplane2rake, nodalplane2strike = (
            float(mt_properties[key]) for key in nodal_plane_2_keys
        )
        print(
            nodalplane1dip, nodalplane1rake, nodalplane1strike,
            nodalplane2dip, nodalplane2rake, nodalplane2strike,
        )
    else:
        print(
            nodalplane1dip, nodalplane1rake, nodalplane1strike,
            "(second nodal plane unavailable)"
        )

    lon = float(mt_properties["longitude"])
    lat = float(mt_properties["latitude"])
    depth = float(mt_properties["depth"])
    magnitude = float(mt_properties["derived-magnitude"])
    print(lon, lat, depth, magnitude)

    time_str = format_utc_event_time(mt_properties["eventtime"])
    print(time_str)
    print("All good.")

    # create figure
    region = [lon-4, lon+4, lat-3, lat+3]
    event_title = event_properties.get("title") or str(event.get("place", id_code))
    postfix = event_title.split(" - ", 1)[1] if " - " in event_title else event_title
    title = "Mw {} - ".format(magnitude) + postfix

    faults = "_data/gem_active_faults_harmonized.gmt"
    plates = "_data/pb2002_boundaries.gmt"

    topo = pygmt.datasets.load_earth_relief(region=region,resolution="15s")

    fig = pygmt.Figure()
    pygmt.config(MAP_FRAME_TYPE="plain")

    shadow_grid = pygmt.grdgradient(grid=topo, azimuth=260, normalize=True)

    fig.grdimage(
        grid=topo,
        region=region,
        projection="M12c",
        shading=shadow_grid,
        cmap="terra")

    fig.coast(
        region=region,
        projection="M12c",
        resolution="h",
        shorelines="0.01p,grey25",
        area_thresh=3,
        lakes="lightskyblue2",
        borders=["1/1p,black", "2/0.5p,blue"],
    )

    fig.basemap(
        region=region,
        projection="M12c",
        frame=["af", "+t{}".format(title)],
    )

    # Add a 200 km geographic scale bar. Keep GMT's original reference
    # point at the bottom-left map corner (jBL); the offsets affect only
    # where the bar is drawn, not the latitude used for its scale.
    fig.scalebar(
        length=200,
        position=Position(
            "BL", cstype="inside", anchor="BL", offset=("0.75c", "0.55c")
        ),
        scale_loc=False,
        fancy=True,
        unit=True,
        box=Box(fill="white@50", radius="6p"),
    )

    # plot faults from GEM GAF-DB
    fig.plot(data=faults, label="GEM active faults")

    # Store focal mechanism parameters in a dictionary based on the Aki & Richards convention
    focal_mechanism = dict(strike=nodalplane1strike, dip=nodalplane1dip, rake=nodalplane1rake, magnitude=magnitude)
    #focal_mechanism = dict(strike=nodalplane2strike, dip=nodalplane2dip, rake=nodalplane2rake, magnitude=magnitude)

    fig.meca(
        spec=focal_mechanism,
        scale="0.7c",  # in centimeters
        longitude=lon,
        latitude=lat,
        depth=depth,
        # Fill compressive quadrants with color "red"
        # [Default is "black"]
        compression_fill="red",
        # Fill extensive quadrants with color "cornsilk"
        # [Default is "white"]
        extension_fill="white",
        # Draw a 0.5 points thick dark gray ("gray30") solid outline via
        # the pen parameter [Default is "0.25p,black,solid"]
        pen="0.5p,gray30,solid",
    )

    fig.legend(position="JBR+jBR+o0.2c", box="+gwhite+p1p")

    fig.text(
        text=time_str,
        position="TL",
        offset="0.2/-0.2c",
        fill="white@50",
        clearance="0.10c/0.08c+tO",
    )

    fig.colorbar(frame=["af", "x+lElevation", "y+l[m]"])

    bounds = [[region[0],region[2]],
              [region[0],region[3]],
              [region[1],region[3]],
              [region[1],region[2]],
              [region[0],region[2]]]

    # Orthographic
    with fig.inset(position="JTR+w4c+o-1/-3c", clearance=0, box=False):
        fig.coast(projection='G{}/{}/4c'.format(lon,lat),
                  region='g',
                  frame='g',
                  land='grey',
                  shorelines="0.01p,grey25",
                  water="azure",
                  area_thresh=1000)
        fig.plot(data=plates, pen='0.8p,black')
        fig.plot(bounds, pen='1p,red')

    fig.savefig("assets/images/seismicity/{}.png".format(id_code))

    # Add the new map to the homepage using the existing image filename.
    with open("seismicity.md", "r+") as f:
        lines = f.readlines()
        for line_index, line in enumerate(lines):
            if line.startswith("Events are displayed top"):
                lines[line_index] = (
                    lines[line_index].strip()
                    + "\n\n![{}](assets/images/seismicity/{}.png)\n".format(
                        id_code, id_code
                    )
                )
        f.seek(0)
        f.writelines(lines)
    print("Next.")
