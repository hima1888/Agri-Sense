# 3D digital twin (Phase 7)

Page: `/twin?farm=<id>` (three.js / React Three Fiber, loaded lazily: the 3D code is downloaded only when this page opens).

## Data, not decoration
`GET /farms/{id}/twin` builds the scene from stored records. Units are metres; x = east, z = south, y = up.

| In the scene | Source |
|---|---|
| Zone shapes | GeoJSON `boundary` (projected to metres) or, without one, rectangles sized from `area_hectares` |
| Crop rows / canopy | Active crop cycle: crop form (grass / bush / tree), row spacing, growth = days since planting ÷ catalogue cycle length |
| Sensors | Sensor records, positioned in their zone; latest reading, simulated flag; live values from the SSE stream |
| Soil-moisture map | Mean of each zone's good-quality soil-moisture readings (sequential blue scale, 10–40 %) |
| Tank level | `water_level` sensors |
| Water flowing, pump running | Irrigation events started in the last hour |
| Sun and sky | Solar elevation and azimuth computed for the farm's coordinates (NOAA approximation) |
| Wind sway, cloud, rain | Latest Open-Meteo observation |

**Schematic** (not stored yet, laid out by rule and labelled "schematic" in the UI): farmhouse, shed, roads, water
channel, pump, pipe routes, gateway, weather-station mast, and the optional solar array.

## Interaction
- Drag to rotate, right-drag to pan, scroll to zoom. Click a zone, sensor or piece of equipment for details.
- Layers: crops, sensors, irrigation, buildings & roads, landscape, labels, soil-moisture map, solar (optional).
- An object list lets you select everything from the keyboard or a screen reader, without using the 3D view.
- Reduced motion: wind sway, water flow, sensor pulses and camera easing are off, and the scene renders only on demand.

## Rendering notes
- Crops: row crops are drawn as instanced row stripes (≤160 rows per zone; thinned uniformly beyond that),
  orchards as individual instanced trees, and the field surface is tinted by canopy cover. Wind sway runs in the
  vertex shader, so it costs nothing on the CPU per plant.
- Labels are canvas-texture sprites (no extra React roots).
- Picking maps `clientX/Y` against the canvas rect rather than `offsetX/Y`, which is wrong under CSS transforms and
  device scaling.
