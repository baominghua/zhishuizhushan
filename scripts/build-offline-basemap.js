const fs = require("fs");
const path = require("path");
const { Writable } = require("stream");
const parseOSM = require("osm-pbf-parser");

const input = process.argv[2] || path.join("offline-maps", "fujian-latest.osm.pbf");
const output = process.argv[3] || path.join("offline-maps", "fujian-basemap.geojson");

// Focus the offline layer around the project view instead of shipping all Fujian OSM geometry.
const bbox = {
  minLon: 117.55,
  minLat: 26.05,
  maxLon: 118.85,
  maxLat: 27.2,
};

const wantedWays = new Map();
const wantedRefs = new Set();
const nodes = new Map();

function hasUsefulTags(tags) {
  return Boolean(
    tags.highway ||
      tags.waterway ||
      tags.natural === "water" ||
      tags.landuse ||
      tags.leisure === "park" ||
      tags.building ||
      tags.railway
  );
}

function featureKind(tags) {
  if (tags.highway) return "road";
  if (tags.waterway) return "waterway";
  if (tags.natural === "water") return "water";
  if (tags.landuse === "forest" || tags.natural === "wood") return "forest";
  if (tags.landuse) return "landuse";
  if (tags.building) return "building";
  if (tags.railway) return "railway";
  return "other";
}

function inBbox(coord) {
  return coord[0] >= bbox.minLon && coord[0] <= bbox.maxLon && coord[1] >= bbox.minLat && coord[1] <= bbox.maxLat;
}

function simplify(coords, tolerance) {
  if (coords.length <= 2) return coords;
  const simplified = [coords[0]];
  let last = coords[0];
  for (let i = 1; i < coords.length - 1; i += 1) {
    const point = coords[i];
    if (Math.abs(point[0] - last[0]) >= tolerance || Math.abs(point[1] - last[1]) >= tolerance) {
      simplified.push(point);
      last = point;
    }
  }
  simplified.push(coords[coords.length - 1]);
  return simplified;
}

function parsePass(onItem) {
  return new Promise((resolve, reject) => {
    fs.createReadStream(input)
      .pipe(parseOSM())
      .pipe(
        new Writable({
          objectMode: true,
          write(items, enc, next) {
            for (const item of items) onItem(item);
            next();
          },
        })
      )
      .on("finish", resolve)
      .on("error", reject);
  });
}

async function main() {
  await parsePass((item) => {
    if (item.type !== "way" || !hasUsefulTags(item.tags)) return;
    const kind = featureKind(item.tags);
    if (kind === "building" && !item.tags.name) return;
    wantedWays.set(item.id, {
      id: item.id,
      refs: item.refs,
      tags: item.tags,
      kind,
    });
    for (const ref of item.refs) wantedRefs.add(ref);
  });

  await parsePass((item) => {
    if (item.type !== "node" || !wantedRefs.has(item.id)) return;
    nodes.set(item.id, [Number(item.lon.toFixed(6)), Number(item.lat.toFixed(6))]);
  });

  const features = [];
  for (const way of wantedWays.values()) {
    let coords = way.refs.map((ref) => nodes.get(ref)).filter(Boolean);
    if (coords.length < 2 || !coords.some(inBbox)) continue;

    const isClosed = coords.length > 3 && way.refs[0] === way.refs[way.refs.length - 1];
    const tolerance = way.kind === "road" || way.kind === "waterway" || way.kind === "railway" ? 0.00045 : 0.00075;
    coords = simplify(coords, tolerance);

    if (!coords.some(inBbox)) continue;
    if (way.kind === "building" && features.filter((feature) => feature.properties.kind === "building").length > 900) continue;

    const properties = {
      id: way.id,
      kind: way.kind,
      name: way.tags.name || "",
      class: way.tags.highway || way.tags.waterway || way.tags.landuse || way.tags.natural || way.tags.railway || "",
    };

    if (isClosed && way.kind !== "road" && way.kind !== "waterway" && way.kind !== "railway") {
      if (coords[0][0] !== coords[coords.length - 1][0] || coords[0][1] !== coords[coords.length - 1][1]) {
        coords.push(coords[0]);
      }
      features.push({
        type: "Feature",
        properties,
        geometry: { type: "Polygon", coordinates: [coords] },
      });
    } else {
      features.push({
        type: "Feature",
        properties,
        geometry: { type: "LineString", coordinates: coords },
      });
    }
  }

  features.sort((a, b) => {
    const order = { landuse: 1, forest: 2, water: 3, building: 4, railway: 5, waterway: 6, road: 7 };
    return (order[a.properties.kind] || 9) - (order[b.properties.kind] || 9);
  });

  const geojson = {
    type: "FeatureCollection",
    name: "fujian-offline-basemap",
    bbox: [bbox.minLon, bbox.minLat, bbox.maxLon, bbox.maxLat],
    generatedAt: new Date().toISOString(),
    source: "OpenStreetMap contributors, Geofabrik Fujian extract",
    features,
  };

  fs.writeFileSync(output, JSON.stringify(geojson));
  fs.writeFileSync(`${output}.js`, `window.FUJIAN_BASEMAP_GEOJSON = ${JSON.stringify(geojson)};\n`);
  console.log(`Wrote ${features.length} features to ${output}`);
  console.log(`Wrote browser bundle to ${output}.js`);
  console.log(`${(fs.statSync(output).size / 1024 / 1024).toFixed(2)} MB`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
