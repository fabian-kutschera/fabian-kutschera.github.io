#!/usr/bin/env python
# coding: utf-8

import pandas as pd
import geopandas as gpd
import pygmt
import os
import datetime

import json
import requests


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


for i in range(len(gdf)):
    # get id
    id_code = gdf["id"].iloc[i]
    
    # check if reviewed 
    if gdf["status"].iloc[i] == "reviewed":
        print("{} is reviewed.".format(id_code))
    else:
        print("{} not reviewed, skipped.".format(id_code))
        continue

    # check if file exists
    if os.path.isfile("assets/images/seismicity/{}.png".format(id_code)) == True:
        print("File exists, skipped.")
        continue
    else:
        # get detail incl. moment tensor
        url_nodal_plane = gdf["detail"].iloc[i]
        response = requests.get(url_nodal_plane)
        mt_geojson = response.json()

        # failsafe
        try:
            moment_tensor = mt_geojson["properties"]["products"]["moment-tensor"]
            print("Moment Tensor data found.")
        except KeyError:
            print("Key 'moment-tensor' not found. Exiting.")
            break  
        
        # check if nodal-planes can be found 
        for i in range(len(mt_geojson["properties"]["products"]["moment-tensor"])):
            if "nodal-plane-1-dip" in mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]:
                
                # double check status and moment magnitude 
                if mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["review-status"] != "reviewed":
                    continue
                if mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["derived-magnitude-type"] != "Mww":
                    continue
                    
                print("Found {} with status {}."
                      .format(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["eventsourcecode"], 
                              mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["review-status"]))
                
                # get moment tensor information
                nodalplane1dip =  float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["nodal-plane-1-dip"])
                nodalplane1rake = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["nodal-plane-1-rake"])
                nodalplane1strike = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["nodal-plane-1-strike"])
                nodalplane2dip = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["nodal-plane-2-dip"])
                nodalplane2rake = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["nodal-plane-2-rake"])
                nodalplane2strike = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["nodal-plane-2-strike"])
                print(nodalplane1dip, nodalplane1rake, nodalplane1strike, nodalplane2dip, nodalplane2rake, nodalplane2strike)

                lon = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["longitude"])
                lat = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["latitude"])
                depth = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["depth"])
                magnitude = float(mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["derived-magnitude"])
                print(lon, lat, depth, magnitude)
                
                time = mt_geojson["properties"]["products"]["moment-tensor"][i]["properties"]["eventtime"]
                time = datetime.datetime.strptime(time, '%Y-%m-%dT%H:%M:%S.%fZ')
                time_str = time.strftime('%Y-%m-%d %H:%M:%S') + " (UTC)"
                print(time_str)

            else:
                print("No, continue.")
                continue
                
            # check if nodal-plane could be found
            if "nodalplane1dip" in locals():
                print("All good.")
            else:
                print("Continue.")
                continue

            # create figure
            region = [lon-4, lon+4, lat-3, lat+3]
            title = mt_geojson["properties"]["title"]
            prefix, postfix = title.split(' - ')
            title = "Mw {} - ".format(magnitude) + postfix

            faults = "_data/gem_active_faults_harmonized.gmt"
            plates = "_data/pb2002_boundaries.gmt"
            
            topo = pygmt.datasets.load_earth_relief(region=region,resolution="15s")
            
            fig = pygmt.Figure()
            pygmt.config(MAP_FRAME_TYPE="plain")
            
            shadow_grid = pygmt.grdgradient(grid=topo, azimuth=260, normalize=1)
            
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
                map_scale="jBL+w200+o0.75c/0.55c+f+u",
                box="+gwhite@50+r"
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
                compressionfill="red",
                # Fill extensive quadrants with color "cornsilk"
                # [Default is "white"]
                extensionfill="white",
                # Draw a 0.5 points thick dark gray ("gray30") solid outline via
                # the pen parameter [Default is "0.25p,black,solid"]
                pen="0.5p,gray30,solid",
            )
            
            fig.legend(position="JBR+jBR+o0.2c", box="+gwhite+p1p")
            
            fig.text(text=time_str, position="TL", offset="0.2/-0.2c", fill="white@50")
            
            fig.colorbar(frame=["af", "x+lElevation", "y+l[m]"])
            
            bounds = [[region[0],region[2]],
                      [region[0],region[3]],
                      [region[1],region[3]],
                      [region[1],region[2]],
                      [region[0],region[2]]]
            
            # Orthographic
            with fig.inset(position="JTR+w4c+o-1/-3c", margin=0, box=False):
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
            fig.show()

 
            # Add to homepage
            with open("seismicity.md", "r+") as f: #r+ does the work of rw
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if line.startswith("Events are displayed top"):
                        lines[i] = lines[i].strip() + "\n\n![{}](assets/images/seismicity/{}.png)\n".format(id_code,id_code)
                f.seek(0)
                for line in lines:
                    f.write(line)
            print("Next.")

