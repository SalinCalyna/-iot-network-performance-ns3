# OpenStreetMap snapshot: PSU Phuket Campus

Data © OpenStreetMap contributors, available under the Open Database License (ODbL 1.0):
https://www.openstreetmap.org/copyright. This folder is a derived extract and is shared under the same licence.

| File | Source | Retrieved | sha256 |
|---|---|---|---|
| `nominatim-campus-20261026.json` | Nominatim search "Prince of Songkla University Phuket Campus" (`format=jsonv2&polygon_geojson=1`) | 2026-10-26 | `aa9dad8d…` |
| `overpass-campus-20261026.json` | Overpass API, OSM data timestamp 2026-10-26T06:28:35Z | 2026-10-26 | `6ddd2802…` |

The campus is OSM way 316508940 (`amenity=university`, name "มหาวิทยาลัยสงขลานครินทร์ วิทยาเขตภูเก็ต", name:en
"Prince of Songkla University, Phuket Campus"), 80 Moo 1, Wichitsongkram Road, Kathu, Phuket 83120.

Overpass query:

```
[out:json][timeout:60];way(316508940);map_to_area->.c;
(way(316508940);way["building"](area.c);way["highway"](area.c);nwr["name"](area.c);
 nwr["natural"="water"](area.c);way["landuse"](area.c););out geom tags;
```

OSM coverage is crowd-sourced. Building footprints and names were not surveyed for this project, and OSM
may be incomplete. The older coordinate in `site/data/phuket-locations.json` (7.8917, 98.3897, marked approximate)
lies about 4 km east of this campus polygon and is not used.
