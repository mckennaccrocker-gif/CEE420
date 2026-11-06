const COLORS = {
  accessible_routable: "#1f7a4d",
  at_risk_routable: "#c4920a",
  assumed_closed: "#b42318",
  partial_above_0_30_not_closed: "#e07a2f",
  bridge_deck_unmatched: "#6d4ea8",
  bridge_deck_sampled: "#0e7c86",
  unmatched_no_channel: "#8a8a8a",
  outside_municipality: "#b7b1a6",
};

const LEGEND = [
  ["accessible_routable", "Still open"],
  ["at_risk_routable", "At risk"],
  ["partial_above_0_30_not_closed", "Partly deep but still routed"],
  ["assumed_closed", "Affected / do not use"],
  ["bridge_deck_unmatched", "Unknown bridge deck"],
  ["unmatched_no_channel", "Unmatched (not dry)"],
];

const STATUS_LABEL = {
  accessible_routable: "Still open",
  at_risk_routable: "At risk, still routable",
  partial_above_0_30_not_closed: "Partly at or above 0.30 m, not closed",
  assumed_closed: "Affected / do not use",
  bridge_deck_unmatched: "Bridge deck unmatched",
  bridge_deck_sampled: "Bridge deck sampled",
  unmatched_no_channel: "Unmatched, no channel",
  outside_municipality: "Outside the municipality",
};

const FEMA_STYLE = {
  floodway: { color: "#0b1f33", fillColor: "#16324f", fillOpacity: 0.5, weight: 0.6 },
  ae: { color: "#1d4e89", fillColor: "#8fb8d6", fillOpacity: 0.42, weight: 0.4 },
  a: { color: "#1d4e89", fillColor: "#d5e4f0", fillOpacity: 0.55, weight: 0.5, dashArray: "3 2" },
  moderate: { color: "#6b5b3e", fillColor: "#f4efe2", fillOpacity: 0.55, weight: 0.7, dashArray: "2 2" },
  minimal: { color: "#c5d0d6", fillColor: "#e7eef2", fillOpacity: 0.18, weight: 0 },
  other: { color: "#243040", fillColor: "#d9e2ea", fillOpacity: 0.35, weight: 0.4 },
};

const LONG_LIST = 8;

let summary = null;
let roads = null;
let fema = null;
let femaZones = null;
let stage = "0.25";
let selected = null;
let roadLayer = null;
let femaLayer = null;
let map = null;
let highlighted = [];
let routeMarks = [];
let lastRouteKey = null;
let avoidNames = [];
let openNames = [];

document.getElementById("stage-slider").addEventListener("input", (event) => {
  setStage(nearestStageId(event.target.value));
});
document.getElementById("search").addEventListener("submit", (event) => {
  event.preventDefault();
  findRoad(document.getElementById("road-query").value);
});
document.getElementById("fema-toggle").addEventListener("change", (event) => {
  setFemaVisible(event.target.checked);
});
document.getElementById("avoid-query").addEventListener("input", () => applyNameFilter("avoid"));
document.getElementById("open-query").addEventListener("input", () => applyNameFilter("open"));

Promise.all([
  fetch("data/summary.json").then((response) => response.json()),
  fetch("data/roads.geojson").then((response) => response.json()),
  fetch("data/boundary.geojson").then((response) => response.json()),
  fetch("data/fema.json").then((response) => response.json()),
  fetch("data/fema-zones.geojson").then((response) => response.json()),
]).then(([summaryPayload, roadPayload, boundaryPayload, femaPayload, zonePayload]) => {
  summary = summaryPayload;
  roads = roadPayload;
  fema = femaPayload;
  femaZones = zonePayload;
  document.getElementById("banner").textContent = "Each mark is a chosen rise already computed, not Hurricane Ida and not a forecast.";
  drawLegend();
  drawMap(boundaryPayload);
  setStage("0.25");
}).catch((error) => {
  document.getElementById("banner").textContent = "The dashboard data did not load. " + error;
});

function drawLegend() {
  const root = document.getElementById("legend");
  root.replaceChildren();
  LEGEND.forEach(([key, text]) => {
    const row = document.createElement("div");
    row.className = "legend-row";
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = COLORS[key];
    const label = document.createElement("span");
    label.textContent = text;
    row.append(swatch, label);
    root.append(row);
  });
  const town = document.createElement("div");
  town.className = "legend-row";
  const townSwatch = document.createElement("span");
  townSwatch.className = "swatch town-swatch";
  const townLabel = document.createElement("span");
  townLabel.textContent = "Princeton boundary";
  town.append(townSwatch, townLabel);
  root.append(town);
}

function drawMap(boundary) {
  map = L.map("map", { zoomControl: true }).setView([40.3562, -74.6693], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Boundary: NJGIN Municipal Boundaries of NJ',
  }).addTo(map);
  map.createPane("town");
  map.getPane("town").style.zIndex = 620;
  map.getPane("town").style.pointerEvents = "none";
  L.geoJSON(boundary, {
    pane: "town",
    interactive: false,
    style: { color: "#ffffff", weight: 9, opacity: 0.95, fill: false, fillOpacity: 0 },
  }).addTo(map);
  L.geoJSON(boundary, {
    pane: "town",
    interactive: false,
    style: { color: "#0b1f33", weight: 4.5, opacity: 1, fill: false, fillOpacity: 0 },
  }).addTo(map);
  map.createPane("fema");
  map.getPane("fema").style.zIndex = 350;
  femaLayer = L.featureGroup();
  if (femaZones) {
    L.geoJSON(femaZones, {
      pane: "fema",
      style: (feature) => femaStyle(feature.properties.fill_class),
      onEachFeature: (feature, layer) => {
        layer.on("click", (event) => {
          L.DomEvent.stop(event);
          explainZone(feature.properties || {});
        });
      },
    }).addTo(femaLayer);
  }
  const section = fema && fema.regulatory_water_surface_geometry;
  if (section) {
    L.geoJSON(
      { type: "Feature", geometry: section, properties: {} },
      {
        pane: "fema",
        style: { color: "#102033", weight: 3, opacity: 0.9, dashArray: "6 4" },
      }
    ).on("click", (event) => {
      L.DomEvent.stop(event);
      const water = fema.regulatory_water_surface || {};
      const value = water.value != null ? water.value + " " + (water.units || "") + " " + (water.datum || "") : "saved water surface";
      showBlurb(
        "Stony Brook cross section M",
        "Regulatory base-flood water surface, " + value.trim() + ".",
        ["This is not a road depth."]
      );
    }).addTo(femaLayer);
  }
  roadLayer = L.geoJSON(roads, {
    style: (feature) => styleFor(feature.properties["status_" + stageKey(stage)], feature.properties.deck_status),
    onEachFeature: (feature, layer) => {
      layer.on("click", () => selectLayer(layer));
    },
  }).addTo(map);
  map.fitBounds(roadLayer.getBounds(), { padding: [28, 28] });
  requestAnimationFrame(() => map.invalidateSize());
  window.addEventListener("resize", () => map.invalidateSize());
}

function styleFor(status, deckStatus) {
  const closed = status === "assumed_closed";
  const color = deckStatus === "bridge_deck_sampled" ? COLORS.bridge_deck_sampled : (COLORS[status] || "#444");
  return {
    color: color,
    weight: closed ? 5 : deckStatus === "bridge_deck_sampled" ? 4 : status === "accessible_routable" ? 2.6 : status === "partial_above_0_30_not_closed" ? 3 : 2.2,
    opacity: 0.92,
  };
}

function nearestStageId(raw) {
  if (!summary || !summary.stages || !summary.stages.length) return stage;
  const value = Number(raw);
  let best = summary.stages[0];
  let gap = Infinity;
  summary.stages.forEach((item) => {
    const next = Math.abs(item.stage_above_channel_dem_m - value);
    if (next < gap) {
      gap = next;
      best = item;
    }
  });
  return best.id;
}

function groupedMetres(length) {
  return String(Math.round(length)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function wetCaption(row) {
  return groupedMetres(row.wet_piece_length_m) + " m at or above 0.30 m";
}

function affectedLead(count) {
  if (count === 0) return "No centerline is affected. None is assumed closed.";
  if (count === 1) return "1 centerline is affected. Do not use it.";
  return count + " centerlines are affected. Do not use them.";
}

function openLead(count) {
  if (count === null || count === undefined) return "The still-open count is not saved for this mark.";
  if (count === 1) return "1 centerline is still open. Send traffic there.";
  return count + " centerlines are still open. Send traffic there.";
}

function namesFor(stageId, status) {
  const key = "status_" + stageKey(stageId);
  const counts = new Map();
  ((roads && roads.features) || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props[key] !== status) return;
    const name = props.name || "Unnamed";
    counts.set(name, (counts.get(name) || 0) + 1);
  });
  return [...counts.entries()].sort((left, right) => left[0].localeCompare(right[0]));
}

function listQuery(which) {
  const box = document.getElementById(which + "-query");
  return box ? box.value.trim().toLowerCase() : "";
}

function applyNameFilter(which) {
  const query = listQuery(which);
  const source = which === "avoid" ? avoidNames : openNames;
  const names = source.filter(([name]) => name.toLowerCase().includes(query));
  const status = which === "avoid" ? "assumed_closed" : "accessible_routable";
  fillNameList(document.getElementById(which + "-list"), names, status, query);
  const fold = document.getElementById(which + "-fold");
  if (fold && query) fold.open = true;
}

function fillNameList(list, names, status, query) {
  list.replaceChildren();
  if (!names.length) {
    const item = document.createElement("li");
    item.textContent = query
      ? "No road name matches."
      : (status === "assumed_closed" ? "No road is affected." : "No road is still open.");
    list.append(item);
    return;
  }
  names.forEach(([name, count]) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "road-link";
    button.dataset.road = name;
    button.textContent = count > 1 ? name + ", " + count + " centerlines" : name;
    button.addEventListener("click", () => focusNamedRoad(name, status, button));
    item.append(button);
    list.append(item);
  });
}

function showScenarioSummary(row) {
  const affected = document.getElementById("affected-lead");
  const open = document.getElementById("open-lead");
  if (affected) affected.textContent = affectedLead(row.n_assumed_closed);
  if (open) open.textContent = openLead(row.n_still_open);
  avoidNames = namesFor(row.id, "assumed_closed");
  openNames = namesFor(row.id, "accessible_routable");
  applyNameFilter("avoid");
  applyNameFilter("open");
  showShare(row);
  const avoidFold = document.getElementById("avoid-fold");
  if (avoidFold && !avoidFold.dataset.ready) {
    avoidFold.open = avoidNames.length > 0 && avoidNames.length <= LONG_LIST;
    avoidFold.dataset.ready = "1";
  }
  showFacilityRoutes(row);
}

function showFacilityRoutes(row) {
  const note = document.getElementById("facility-note");
  const list = document.getElementById("facility-routes");
  if (!list) return;
  const meta = (summary && summary.facility_routes) || {};
  if (note) note.textContent = meta.note || "";
  list.replaceChildren();
  const routes = row.facility_routes || [];
  if (!routes.length) {
    const item = document.createElement("li");
    item.textContent = "Not computed for this mark.";
    list.append(item);
    return;
  }
  routes.forEach((route) => {
    const item = document.createElement("li");
    item.className = route.plain === "blocked" ? "captured" : "missed";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "road-link";
    button.dataset.route = route.origin + "→" + route.destination;
    if (button.dataset.route === lastRouteKey) button.setAttribute("aria-pressed", "true");
    const name = document.createElement("span");
    name.className = "road-name";
    name.textContent = route.origin + " to " + route.destination;
    const result = document.createElement("span");
    result.className = "road-result";
    result.textContent = route.scenario_status === "same_node" ? "still open, same corner" : route.plain;
    button.append(name, result);
    button.addEventListener("click", () => focusFacilityRoute(route, button));
    item.append(button);
    list.append(item);
  });
}

function riseText(metres) {
  const quarters = Math.round(Number(metres) * 4) / 4;
  const text = quarters.toFixed(2).replace(/0$/, "").replace(/\.0$/, ".0");
  return "+" + text + " m";
}

function setStage(next) {
  const row = summary && summary.stages.find((item) => item.id === next);
  if (!row) return;
  stage = row.id;
  const slider = document.getElementById("stage-slider");
  if (slider) {
    slider.value = String(row.stage_above_channel_dem_m);
    slider.setAttribute("aria-valuenow", String(row.stage_above_channel_dem_m));
  }
  const readout = document.getElementById("stage-readout");
  if (readout) readout.textContent = riseText(row.stage_above_channel_dem_m);
  const caption = wetCaption(row);
  const captionNode = document.getElementById("stage-caption");
  if (captionNode) captionNode.textContent = caption;
  if (slider) slider.setAttribute("aria-valuetext", riseText(row.stage_above_channel_dem_m) + ". " + caption);
  showScenarioSummary(row);
  if (roadLayer) {
    roadLayer.eachLayer((layer) => {
      const status = layer.feature.properties["status_" + stageKey(stage)];
      layer.setStyle(styleFor(status, layer.feature.properties.deck_status));
      if (status === "assumed_closed" || status === "partial_above_0_30_not_closed" || status === "bridge_deck_unmatched" || layer.feature.properties.deck_status === "bridge_deck_sampled") {
        layer.bringToFront();
      }
    });
  }
  if (highlighted.length) {
    paintHighlight(highlighted);
    blurbForRoads(highlighted);
  }
  if (lastRouteKey) {
    const route = (row.facility_routes || []).find((item) => item.origin + "→" + item.destination === lastRouteKey);
    if (route) showRouteBlurb(route);
  }
}

function clearRoadHighlight() {
  highlighted.forEach((layer) => {
    const status = layer.feature.properties["status_" + stageKey(stage)];
    layer.setStyle(styleFor(status, layer.feature.properties.deck_status));
  });
  highlighted = [];
  document.querySelectorAll(".road-link[aria-pressed='true']").forEach((button) => {
    button.setAttribute("aria-pressed", "false");
  });
}

function clearRouteMarks() {
  routeMarks.forEach((marker) => map.removeLayer(marker));
  routeMarks = [];
  lastRouteKey = null;
}

function paintHighlight(layers) {
  layers.forEach((layer) => {
    layer.setStyle({ color: "#111111", weight: 8, opacity: 1 });
    layer.bringToFront();
  });
}

function focusNamedRoad(name, status, button) {
  if (!map || !roadLayer) return;
  const key = "status_" + stageKey(stage);
  const hits = [];
  roadLayer.eachLayer((layer) => {
    const props = layer.feature.properties || {};
    if ((props.name || "Unnamed") !== name) return;
    if (status && props[key] !== status) return;
    hits.push(layer);
  });
  if (!hits.length) return;
  clearRoadHighlight();
  clearRouteMarks();
  highlighted = hits;
  selected = hits.slice().sort((left, right) => (right.feature.properties.length_m_inside || 0) - (left.feature.properties.length_m_inside || 0))[0];
  paintHighlight(hits);
  if (button) button.setAttribute("aria-pressed", "true");
  blurbForRoads(hits);
  map.fitBounds(L.featureGroup(hits).getBounds(), { padding: [36, 36], maxZoom: 16 });
}

function focusFacilityRoute(route, button) {
  if (!map) return;
  clearRoadHighlight();
  clearRouteMarks();
  lastRouteKey = route.origin + "→" + route.destination;
  if (button) button.setAttribute("aria-pressed", "true");
  const points = [];
  if (typeof route.origin_lat === "number" && typeof route.origin_lon === "number") {
    points.push([route.origin_lat, route.origin_lon]);
  }
  if (typeof route.destination_lat === "number" && typeof route.destination_lon === "number") {
    points.push([route.destination_lat, route.destination_lon]);
  }
  points.forEach((latlng, index) => {
    const marker = L.circleMarker(latlng, {
      radius: 8,
      color: "#0b1f33",
      weight: 3,
      fillColor: "#ffffff",
      fillOpacity: 1,
    }).addTo(map);
    marker.bindTooltip(index === 0 ? route.origin : route.destination, { permanent: false });
    routeMarks.push(marker);
  });
  showRouteBlurb(route);
  if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [48, 48], maxZoom: 15 });
}

function selectLayer(layer) {
  clearRoadHighlight();
  clearRouteMarks();
  highlighted = [layer];
  selected = layer;
  paintHighlight([layer]);
  blurbForRoads([layer]);
}

function carLine(statuses) {
  const closed = statuses.filter((status) => status === "assumed_closed").length;
  const lines = [];
  if (closed) lines.push("Do not drive a passenger car. Half the centerline is at or above 0.30 m.");
  if (closed < statuses.length) lines.push("A passenger car can still pass.");
  return lines.join(" ");
}

function showShare(row) {
  const line = document.getElementById("share-line");
  if (!line) return;
  const affected = row.n_assumed_closed;
  const open = row.n_still_open;
  if (typeof affected !== "number" || typeof open !== "number" || affected + open === 0) {
    line.textContent = "The affected share is not saved for this mark.";
    return;
  }
  const counted = affected + open;
  const percent = (100 * affected) / counted;
  const shown = percent >= 10 ? String(Math.round(percent)) : percent.toFixed(1);
  line.textContent = affected + " of " + counted + " centerlines are affected (" + shown + "% of affected plus still open). Avoid those roads.";
}

function blurbForRoads(layers) {
  const name = layers[0].feature.properties.name || "Unnamed";
  const key = stageKey(stage);
  const statusList = layers.map((layer) => layer.feature.properties["status_" + key]);
  const statuses = [...new Set(statusList)];
  const flood = [];
  flood.push(statuses.length === 1 ? (STATUS_LABEL[statuses[0]] || statuses[0]) : layers.length + " centerlines");
  const depths = layers
    .map((layer) => layer.feature.properties["depth_max_m_" + key])
    .filter((value) => typeof value === "number");
  const wets = layers
    .map((layer) => layer.feature.properties["wet_m_" + key])
    .filter((value) => typeof value === "number");
  if (wets.length) flood.push(groupedMetres(wets.reduce((sum, value) => sum + value, 0)) + " m at or above 0.30 m");
  const deepest = depths.length ? Math.max(...depths) : null;
  if (deepest) flood.push("Saved maximum depth " + deepest.toFixed(3) + " m");
  showBlurb(name, flood.join(". ") + ".", [carLine(statusList)]);
}

function showRouteBlurb(route) {
  const status = route.scenario_status === "same_node" ? "Still open, same corner" : (route.plain === "blocked" ? "Blocked" : "Still open");
  const lines = [];
  if (typeof route.scenario_path_length_m === "number") {
    lines.push("Saved path length " + groupedMetres(route.scenario_path_length_m) + " m");
  }
  lines.push("Saved endpoints.");
  showBlurb(route.origin + " to " + route.destination, status, lines);
}

function showBlurb(title, status, lines) {
  const card = document.getElementById("map-blurb");
  if (!card) return;
  document.getElementById("blurb-name").textContent = title;
  document.getElementById("blurb-status").textContent = status;
  document.getElementById("blurb-detail").textContent = (lines || []).filter(Boolean).join(" ");
  card.hidden = false;
}

function explainZone(props) {
  const label = props.zone_label || props.fld_zone || "Regulatory flood zone";
  const date = props.effective_date ? "Effective " + props.effective_date + "." : "";
  showBlurb(label, ["Regulatory flood zone.", date].filter(Boolean).join(" "), ["This does not change the road depth."]);
}

function findRoad(query) {
  const needle = query.trim().toLowerCase();
  if (!needle || !roadLayer) return;
  const hits = [];
  roadLayer.eachLayer((layer) => {
    const name = (layer.feature.properties.name || "").toLowerCase();
    if (name.includes(needle)) hits.push(layer);
  });
  if (!hits.length) {
    showBlurb(query.trim(), "No saved centerline has that name.", []);
    return;
  }
  clearRoadHighlight();
  clearRouteMarks();
  highlighted = hits;
  paintHighlight(hits);
  blurbForRoads(hits);
  map.fitBounds(L.featureGroup(hits).getBounds(), { padding: [30, 30], maxZoom: 16 });
}

function femaStyle(fillClass) {
  const style = FEMA_STYLE[fillClass] || FEMA_STYLE.other;
  return {
    color: style.color,
    fillColor: style.fillColor,
    fillOpacity: style.fillOpacity,
    weight: style.weight,
    dashArray: style.dashArray || null,
    opacity: 0.9,
  };
}

function setFemaVisible(visible) {
  if (!map || !femaLayer) return;
  if (visible) {
    femaLayer.addTo(map);
    if (roadLayer) roadLayer.bringToFront();
    if (highlighted.length) paintHighlight(highlighted);
  } else if (map.hasLayer(femaLayer)) {
    map.removeLayer(femaLayer);
  }
}

function stageKey(id) {
  return id.replace(".", "_");
}
