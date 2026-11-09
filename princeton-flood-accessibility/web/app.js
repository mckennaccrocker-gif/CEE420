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
let routing = null;
let routeLayer = null;
let routeActive = false;
let located = null;
let suggestTarget = null;
let picked = { start: null, end: null };
let lastPlaceAt = 0;
let routePickOn = false;

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
function requestRoute(event) {
  if (event) event.preventDefault();
  routeActive = true;
  drawRoute(true);
}
document.getElementById("directions").addEventListener("submit", requestRoute);
document.getElementById("route-go").addEventListener("click", requestRoute);
document.getElementById("route-locate").addEventListener("click", useMyLocation);
document.getElementById("route-pick").addEventListener("click", () => setRoutePick(!routePickOn));
["route-start", "route-end"].forEach((id) => {
  const box = document.getElementById(id);
  box.addEventListener("input", () => {
    picked[id === "route-start" ? "start" : "end"] = null;
    if (id === "route-start") located = null;
    showRouteSuggestions(box);
  });
  box.addEventListener("focus", () => showRouteSuggestions(box));
});

Promise.all([
  fetch("data/summary.json").then((response) => response.json()),
  fetch("data/roads.geojson").then((response) => response.json()),
  fetch("data/boundary.geojson").then((response) => response.json()),
  fetch("data/fema.json").then((response) => response.json()),
  fetch("data/fema-zones.geojson").then((response) => response.json()),
  fetch("data/routing.json").then((response) => response.json()),
]).then(([summaryPayload, roadPayload, boundaryPayload, femaPayload, zonePayload, routingPayload]) => {
  summary = summaryPayload;
  roads = roadPayload;
  fema = femaPayload;
  femaZones = zonePayload;
  prepareRouting(routingPayload);
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
  map = L.map("map", {
    zoomControl: true,
    zoomAnimation: false,
    fadeAnimation: false,
    markerZoomAnimation: false,
  }).setView([40.3562, -74.6693], 13);
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
      layer.on("click", (event) => {
        if (!routePickOn) {
          selectLayer(layer);
          return;
        }
        if (event.originalEvent) event.originalEvent._stopped = true;
        const props = feature.properties || {};
        if (props["status_" + stageKey(stage)] === "assumed_closed") {
          document.getElementById("route-note").textContent = "That road is affected at this rise. Click an open road.";
          return;
        }
        placeClickedRoad(event.latlng.lng, event.latlng.lat, props.name || "");
      });
    },
  }).addTo(map);
  map.on("click", (event) => {
    if (!routePickOn) return;
    placeClickedRoad(event.latlng.lng, event.latlng.lat);
  });
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
  if (routeActive) drawRoute(false);
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

function prepareRouting(payload) {
  routing = {
    stages: payload.stages,
    edges: payload.edges,
    adj: new Map(),
    nodes: new Map(),
    names: [],
    bounds: [180, 90, -180, -90],
  };
  const names = new Set();
  payload.nodes.forEach(([id, lon, lat]) => {
    routing.nodes.set(id, [lon, lat]);
    routing.bounds[0] = Math.min(routing.bounds[0], lon);
    routing.bounds[1] = Math.min(routing.bounds[1], lat);
    routing.bounds[2] = Math.max(routing.bounds[2], lon);
    routing.bounds[3] = Math.max(routing.bounds[3], lat);
  });
  payload.edges.forEach((edge) => {
    if (!routing.adj.has(edge.u)) routing.adj.set(edge.u, []);
    routing.adj.get(edge.u).push(edge);
    if (edge.name) names.add(edge.name);
  });
  routing.names = [...names].sort((left, right) => left.localeCompare(right));
}

function useMyLocation() {
  const note = document.getElementById("route-note");
  if (!navigator.geolocation) {
    note.textContent = "This browser cannot share a location.";
    return;
  }
  note.textContent = "Asking the browser for this location.";
  navigator.geolocation.getCurrentPosition((position) => {
    picked.start = null;
    located = { lon: position.coords.longitude, lat: position.coords.latitude };
    document.getElementById("route-start").value = "Your location";
    note.textContent = "Using this browser's location as the start.";
  }, () => {
    note.textContent = "The browser did not share a location.";
  }, { enableHighAccuracy: true, timeout: 8000 });
}

function showRouteSuggestions(box) {
  suggestTarget = box;
  const list = document.getElementById("route-suggest");
  const needle = box.value.trim().toLowerCase();
  list.replaceChildren();
  if (!routing || needle.length < 2 || needle === "your location") {
    list.hidden = true;
    return;
  }
  const matches = routing.names.filter((name) => name.toLowerCase().includes(needle)).slice(0, 8);
  if (!matches.length) {
    list.hidden = true;
    return;
  }
  matches.forEach((name) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "road-link";
    button.textContent = name;
    button.addEventListener("click", () => {
      box.value = name;
      picked[box.id === "route-start" ? "start" : "end"] = null;
      if (box.id === "route-start") located = null;
      list.hidden = true;
    });
    item.append(button);
    list.append(item);
  });
  list.hidden = false;
}

function matchRoadName(query) {
  const needle = query.trim().toLowerCase();
  const exact = routing.names.find((name) => name.toLowerCase() === needle);
  if (exact) return { name: exact };
  const contains = routing.names.filter((name) => name.toLowerCase().includes(needle));
  if (contains.length === 1) return { name: contains[0] };
  if (contains.length > 1) return { choices: contains.slice(0, 8) };
  return null;
}

function edgeIsClosed(edge, stageIndex) {
  return ((edge.c || 0) & (1 << stageIndex)) !== 0;
}

function openEdgesNamed(name, stageIndex) {
  const wanted = name.toLowerCase();
  return routing.edges.filter((edge) => (edge.name || "").toLowerCase() === wanted && !edgeIsClosed(edge, stageIndex));
}

function nodeOnRoad(name, stageIndex) {
  const open = openEdgesNamed(name, stageIndex);
  if (!open.length) {
    const known = routing.edges.some((edge) => (edge.name || "").toLowerCase() === name.toLowerCase());
    if (known) return { error: name + " is affected at this rise. It is not used for directions." };
    return null;
  }
  const best = open.reduce((left, right) => (right.m > left.m ? right : left));
  const mid = best.g[Math.floor((best.g.length - 1) / 2)];
  const nearer = distanceMeters(mid, routing.nodes.get(best.u)) <= distanceMeters(mid, routing.nodes.get(best.v)) ? best.u : best.v;
  return { node: nearer };
}

function nearestOpenNode(lon, lat, stageIndex, role) {
  let best = null;
  let bestDistance = Infinity;
  routing.nodes.forEach((coord, id) => {
    const outgoing = (routing.adj.get(id) || []).some((edge) => !edgeIsClosed(edge, stageIndex));
    const incoming = routing.edges.some((edge) => edge.v === id && !edgeIsClosed(edge, stageIndex));
    if (role === "start" && !outgoing) return;
    if (role === "end" && !outgoing && !incoming) return;
    const gap = distanceMeters([lon, lat], coord);
    if (gap < bestDistance) {
      bestDistance = gap;
      best = id;
    }
  });
  if (best === null || bestDistance > 200) return { error: "That place is not on an open Princeton road." };
  return { node: best };
}

function distanceMeters(left, right) {
  const radius = 6371000;
  const lat1 = left[1] * Math.PI / 180;
  const lat2 = right[1] * Math.PI / 180;
  const dLat = lat2 - lat1;
  const dLon = (right[0] - left[0]) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(a)));
}

async function geocode(query) {
  const box = routing.bounds;
  const viewbox = [box[0], box[3], box[2], box[1]].join(",");
  const url = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&bounded=1&viewbox="
    + viewbox + "&q=" + encodeURIComponent(query);
  const response = await fetch(url);
  if (!response.ok) return null;
  const rows = await response.json();
  if (!rows.length) return null;
  return { lon: Number(rows[0].lon), lat: Number(rows[0].lat) };
}

function distanceToSegment(point, start, end) {
  const lat = point[1] * Math.PI / 180;
  const kx = 111320 * Math.cos(lat);
  const ky = 110540;
  const ax = (start[0] - point[0]) * kx;
  const ay = (start[1] - point[1]) * ky;
  const bx = (end[0] - point[0]) * kx;
  const by = (end[1] - point[1]) * ky;
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2));
  return Math.hypot(ax + t * dx, ay + t * dy);
}

function distanceToLine(point, line) {
  if (!line || !line.length) return Infinity;
  let best = Infinity;
  for (let index = 1; index < line.length; index += 1) {
    best = Math.min(best, distanceToSegment(point, line[index - 1], line[index]));
  }
  return line.length === 1 ? distanceMeters(point, line[0]) : best;
}

function nearestOpenRoad(lon, lat, stageIndex, role, roadName) {
  const wanted = roadName && String(roadName).trim();
  const point = [lon, lat];
  let best = null;
  let bestDistance = Infinity;
  routing.edges.forEach((edge) => {
    if (edgeIsClosed(edge, stageIndex)) return;
    if (wanted && edge.name !== wanted) return;
    const gap = distanceToLine(point, edge.g);
    if (gap < bestDistance) {
      bestDistance = gap;
      best = edge;
    }
  });
  if (!best || bestDistance > (wanted ? 120 : 200)) {
    if (wanted) return nearestOpenRoad(lon, lat, stageIndex, role);
    return { error: "That place is not on an open Princeton road." };
  }
  const closer = [best.u, best.v].sort((left, right) => {
    return distanceMeters(point, routing.nodes.get(left)) - distanceMeters(point, routing.nodes.get(right));
  });
  const usable = closer.find((id) => {
    const outgoing = (routing.adj.get(id) || []).some((edge) => !edgeIsClosed(edge, stageIndex));
    if (role === "start") return outgoing;
    const incoming = routing.edges.some((edge) => edge.v === id && !edgeIsClosed(edge, stageIndex));
    return outgoing || incoming;
  });
  return {
    node: usable === undefined ? best.u : usable,
    label: best.name || wanted || "Unnamed road",
  };
}

function setRoutePick(on) {
  routePickOn = on;
  const button = document.getElementById("route-pick");
  button.setAttribute("aria-pressed", on ? "true" : "false");
  button.textContent = on ? "Choosing a route on the map" : "Choose a route on the map";
  if (!map) return;
  map.getContainer().style.cursor = on ? "crosshair" : "";
  if (on) map.dragging.disable();
  else map.dragging.enable();
}

function placeClickedRoad(lon, lat, roadName) {
  if (!routePickOn) return;
  const now = Date.now();
  if (now - lastPlaceAt < 40) return;
  lastPlaceAt = now;
  const note = document.getElementById("route-note");
  if (!routing || !map) {
    note.textContent = "The road network is still loading.";
    return;
  }
  const stageIndex = routing.stages.indexOf(stage);
  if (stageIndex < 0) {
    note.textContent = "This rise is not in the saved network.";
    return;
  }
  const startBox = document.getElementById("route-start");
  const endBox = document.getElementById("route-end");
  const choosingStart = !startBox.value.trim() || endBox.value.trim();
  const hit = nearestOpenRoad(lon, lat, stageIndex, choosingStart ? "start" : "end", roadName);
  if (hit.error) {
    note.textContent = hit.error;
    return;
  }
  if (choosingStart) {
    endBox.value = "";
    picked.end = null;
    picked.start = hit;
    located = null;
    startBox.value = hit.label;
    clearRouteLine();
    routeActive = false;
    note.textContent = "Start is " + hit.label + ". Click the map again for a destination.";
    return;
  }
  picked.end = hit;
  endBox.value = hit.label;
  routeActive = true;
  drawRoute(true).then(() => {
    if (routeLayer) setRoutePick(false);
  });
}

async function resolveStop(text, location, stageIndex, role) {
  const chosen = picked[role];
  if (chosen && text === chosen.label) return { node: chosen.node };
  if (location && text.toLowerCase() === "your location") return nearestOpenNode(location.lon, location.lat, stageIndex, role);
  const matched = matchRoadName(text);
  if (matched && matched.name) {
    const node = nodeOnRoad(matched.name, stageIndex);
    return node || { error: "No saved Princeton road has that name." };
  }
  if (matched && matched.choices) return { error: "Several roads match. Choose one from the list." };
  try {
    const point = await geocode(text);
    if (!point) return { error: "No saved road or Princeton address matches that place." };
    return nearestOpenNode(point.lon, point.lat, stageIndex, role);
  } catch (error) {
    return { error: "The address lookup did not answer." };
  }
}

function shortestOpenPath(start, end, stageIndex) {
  const dist = new Map([[start, 0]]);
  const prev = new Map();
  const seen = new Set();
  let current = null;
  while (true) {
    current = null;
    let best = Infinity;
    dist.forEach((value, node) => {
      if (!seen.has(node) && value < best) {
        best = value;
        current = node;
      }
    });
    if (current === null) return null;
    if (current === end) break;
    seen.add(current);
    (routing.adj.get(current) || []).forEach((edge) => {
      if (edgeIsClosed(edge, stageIndex)) return;
      const next = best + edge.m;
      if (next < (dist.has(edge.v) ? dist.get(edge.v) : Infinity)) {
        dist.set(edge.v, next);
        prev.set(edge.v, edge);
      }
    });
  }
  const edges = [];
  let cursor = end;
  let metres = 0;
  while (cursor !== start) {
    const edge = prev.get(cursor);
    if (!edge) return null;
    if (edgeIsClosed(edge, stageIndex)) return null;
    edges.push(edge);
    metres += edge.m;
    cursor = edge.u;
  }
  edges.reverse();
  const line = [];
  edges.forEach((edge) => {
    edge.g.forEach((point) => line.push([point[1], point[0]]));
  });
  return { line, metres, edges };
}

function roadsOnPath(edges) {
  const names = [];
  (edges || []).forEach((edge) => {
    const name = edge.name && String(edge.name).trim();
    if (!name || names[names.length - 1] === name) return;
    names.push(name);
  });
  return names;
}

function turnSentence(names) {
  if (!names.length) return "";
  if (names.length === 1) return "Take " + names[0] + ".";
  return "Take " + names[0] + names.slice(1).map((name) => ", then turn onto " + name).join("") + ".";
}

function showTurns(edges) {
  const list = document.getElementById("route-turns");
  const sentence = turnSentence(roadsOnPath(edges));
  list.hidden = !sentence;
  list.textContent = sentence;
}

function clearTurns() {
  const list = document.getElementById("route-turns");
  if (!list) return;
  list.hidden = true;
  list.textContent = "";
}

function clearRouteLine() {
  if (routeLayer && map) map.removeLayer(routeLayer);
  routeLayer = null;
  clearTurns();
}

function settleMap() {
  if (map && map._animatingZoom && typeof map._onZoomTransitionEnd === "function") {
    map._onZoomTransitionEnd();
  }
}

function paintRoute(latlngs) {
  clearRouteLine();
  settleMap();
  if (!map.getPane("route")) {
    map.createPane("route");
    const pane = map.getPane("route");
    pane.style.zIndex = 650;
    pane.style.pointerEvents = "none";
  }
  routeLayer = L.polyline(latlngs, {
    pane: "route",
    color: "#1a56c4",
    weight: 7,
    opacity: 0.95,
  }).addTo(map);
}

async function drawRoute(fit) {
  const note = document.getElementById("route-note");
  try {
    if (!routing || !map) {
      note.textContent = "The road network is still loading.";
      return;
    }
    const stageIndex = routing.stages.indexOf(stage);
    const startText = document.getElementById("route-start").value.trim();
    const endText = document.getElementById("route-end").value.trim();
    if (stageIndex < 0) {
      note.textContent = "This rise is not in the saved network.";
      clearRouteLine();
      return;
    }
    if (!startText || !endText) {
      note.textContent = "Enter a start and a destination.";
      return;
    }
    note.textContent = "Finding an open path.";
    const start = await resolveStop(startText, located, stageIndex, "start");
    const end = await resolveStop(endText, null, stageIndex, "end");
    if (start.error || end.error) {
      note.textContent = start.error || end.error;
      clearRouteLine();
      return;
    }
    if (start.node === end.node) {
      note.textContent = "Those are the same place on the open network.";
      clearRouteLine();
      return;
    }
    const path = shortestOpenPath(start.node, end.node, stageIndex);
    if (!path) {
      note.textContent = "No open path between those points at this rise.";
      clearRouteLine();
      return;
    }
    paintRoute(path.line);
    showTurns(path.edges);
    note.textContent = groupedMetres(path.metres) + " m on open roads. Affected roads were left out.";
    if (fit && routeLayer) {
      settleMap();
      map.fitBounds(routeLayer.getBounds(), { padding: [36, 36], animate: false });
    }
  } catch (error) {
    note.textContent = "Directions could not be drawn.";
    clearRouteLine();
  }
}
