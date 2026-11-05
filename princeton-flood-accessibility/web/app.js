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

let summary = null;
let roads = null;
let fema = null;
let femaZones = null;
let stage = "0.25";
let selected = null;
let roadLayer = null;
let femaLayer = null;
let reportsLayer = null;
let reportFocus = null;
let observedReports = null;
let nameCheck = null;
let map = null;

const REPORT_STYLE = {
  color: "#111111",
  weight: 4,
  opacity: 0.95,
  dashArray: "2 8",
  lineCap: "butt",
};

const FEMA_STYLE = {
  floodway: { color: "#0b1f33", fillColor: "#16324f", fillOpacity: 0.5, weight: 0.6 },
  ae: { color: "#1d4e89", fillColor: "#8fb8d6", fillOpacity: 0.42, weight: 0.4 },
  a: { color: "#1d4e89", fillColor: "#d5e4f0", fillOpacity: 0.55, weight: 0.5, dashArray: "3 2" },
  moderate: { color: "#6b5b3e", fillColor: "#f4efe2", fillOpacity: 0.55, weight: 0.7, dashArray: "2 2" },
  minimal: { color: "#c5d0d6", fillColor: "#e7eef2", fillOpacity: 0.18, weight: 0 },
  other: { color: "#243040", fillColor: "#d9e2ea", fillOpacity: 0.35, weight: 0.4 },
};

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
document.getElementById("reports-toggle").addEventListener("change", (event) => {
  setReportsVisible(event.target.checked);
});

Promise.all([
  fetch("/api/summary").then((response) => response.json()),
  fetch("/api/roads.geojson").then((response) => response.json()),
  fetch("/api/boundary.geojson").then((response) => response.json()),
  fetch("/api/enso").then((response) => response.json()),
  fetch("/api/ida").then((response) => response.json()),
  fetch("/api/bridge-decks").then((response) => response.json()),
  fetch("/api/fema").then((response) => response.json()),
  fetch("/api/fema-zones.geojson").then((response) => response.json()),
  fetch("/api/observed-reports.geojson").then((response) => response.json()),
  fetch("/api/name-check").then((response) => response.json()),
]).then(([summaryPayload, roadPayload, boundaryPayload, ensoPayload, idaPayload, deckPayload, femaPayload, zonePayload, reportPayload, nameCheckPayload]) => {
  summary = summaryPayload;
  roads = roadPayload;
  fema = femaPayload;
  femaZones = zonePayload;
  observedReports = reportPayload;
  document.getElementById("banner").textContent = "Not Hurricane Ida. Each mark is a chosen rise, not a forecast.";
  const scenarioNote = document.getElementById("scenario-note");
  if (scenarioNote) scenarioNote.textContent = summary.banner;
  const stamp = (summary.computed_at_utc || "").replace("T", " ").replace("Z", " UTC");
  document.getElementById("product-line").textContent =
    "Road accessibility. Hypothetical 3DEP scenario. Not Hurricane Ida. " + stamp;
  document.getElementById("component-note").textContent = summary.component_note;
  drawLegend();
  drawMap(boundaryPayload);
  drawChart();
  renderEnso(ensoPayload);
  renderIda(idaPayload);
  renderNameCheck(nameCheckPayload);
  renderDecks(deckPayload);
  renderFema(femaPayload);
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
}

function drawMap(boundary) {
  map = L.map("map", { zoomControl: true }).setView([40.3562, -74.6693], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  L.geoJSON(boundary, {
    style: { color: "#16324f", weight: 1.5, fill: false, dashArray: "4 4" },
  }).addTo(map);
  map.createPane("fema");
  map.getPane("fema").style.zIndex = 350;
  femaLayer = L.featureGroup();
  if (femaZones) {
    L.geoJSON(femaZones, {
      pane: "fema",
      style: (feature) => femaStyle(feature.properties.fill_class),
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
    ).bindTooltip(
      "Regulatory base-flood water surface, Stony Brook cross section M: 65.5 ft NAVD 88. Not a deck elevation and not a scenario depth.",
      { sticky: true }
    ).addTo(femaLayer);
  }
  femaLayer.addTo(map);
  map.createPane("reports");
  map.getPane("reports").style.zIndex = 640;
  const reportData = observedReports || { type: "FeatureCollection", features: [] };
  const reportHits = L.geoJSON(reportData, {
    pane: "reports",
    style: () => ({ color: "#111111", weight: 18, opacity: 0 }),
    onEachFeature: (feature, layer) => {
      layer.bindPopup(reportPopup(feature.properties));
      layer.on("add", () => {
        if (layer._path) layer._path.setAttribute("pointer-events", "stroke");
      });
      layer.on("click", (event) => {
        L.DomEvent.stop(event);
        layer.openPopup(event.latlng);
      });
    },
  });
  const reportInk = L.geoJSON(reportData, {
    pane: "reports",
    interactive: false,
    style: () => REPORT_STYLE,
  });
  reportsLayer = L.featureGroup([reportHits, reportInk]);
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
  return "chosen rise, not a forecast. " + groupedMetres(row.wet_piece_length_m) + " m at or above 0.30 m";
}

function scenarioSummaryLines(row) {
  const roads = (nameCheck && nameCheck.rows || []).map((road) => {
    const step = (road.steps || []).find((item) => item.id === row.id);
    const captured = Boolean(step && step.result === "captured");
    let result = "still open";
    if (captured) result = step.captured_of ? "affected / do not use, " + step.captured_of : "affected / do not use";
    return { road: road.road, result: result, captured: captured };
  });
  return { roads: roads };
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

function affectedRoadNames(stageId) {
  const key = "status_" + stageKey(stageId);
  const counts = new Map();
  ((roads && roads.features) || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props[key] !== "assumed_closed") return;
    const name = props.name || "Unnamed centerline";
    counts.set(name, (counts.get(name) || 0) + 1);
  });
  return [...counts.entries()].sort((left, right) => left[0].localeCompare(right[0]));
}

function showAvoidList(stageId, affectedCount) {
  const lead = document.getElementById("avoid-lead");
  const list = document.getElementById("avoid-list");
  if (!list) return;
  const names = affectedRoadNames(stageId);
  list.replaceChildren();
  if (!names.length) {
    if (lead) lead.textContent = affectedCount ? "The affected names are not in the saved centerlines." : "No road is assumed closed. There is nowhere new to avoid.";
    return;
  }
  if (lead) lead.textContent = "Do not send traffic onto these roads.";
  names.forEach(([name, count]) => {
    const item = document.createElement("li");
    item.textContent = count > 1 ? name + ", " + count + " centerlines" : name;
    list.append(item);
  });
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
    item.className = "missed";
    const name = document.createElement("span");
    name.className = "road-name";
    name.textContent = "Not computed for this mark.";
    item.append(name);
    list.append(item);
    return;
  }
  routes.forEach((route) => {
    const item = document.createElement("li");
    item.className = route.plain === "blocked" ? "captured" : "missed";
    const name = document.createElement("span");
    name.className = "road-name";
    name.textContent = route.origin + " to " + route.destination;
    const result = document.createElement("span");
    result.className = "road-result";
    result.textContent = route.scenario_status === "same_node" ? "still open, same corner" : route.plain;
    item.append(name, result);
    list.append(item);
  });
}

function showScenarioSummary(row) {
  const node = document.getElementById("scenario-summary");
  const roadNode = document.getElementById("summary-roads");
  const affected = document.getElementById("affected-lead");
  const open = document.getElementById("open-lead");
  if (affected) affected.textContent = affectedLead(row.n_assumed_closed);
  if (open) open.textContent = openLead(row.n_still_open);
  showAvoidList(row.id, row.n_assumed_closed);
  showFacilityRoutes(row);
  if (!node || !nameCheck) return;
  const lines = scenarioSummaryLines(row);
  if (!roadNode) return;
  roadNode.replaceChildren();
  lines.roads.forEach((item) => {
    const line = document.createElement("li");
    line.className = item.captured ? "captured" : "missed";
    const name = document.createElement("span");
    name.className = "road-name";
    name.textContent = item.road;
    const result = document.createElement("span");
    result.className = "road-result";
    result.textContent = item.result;
    line.append(name, result);
    roadNode.append(line);
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
  showNameCheck(stage);
  if (roadLayer) {
    roadLayer.eachLayer((layer) => {
      const status = layer.feature.properties["status_" + stageKey(stage)];
      layer.setStyle(styleFor(status, layer.feature.properties.deck_status));
      if (status === "assumed_closed" || status === "partial_above_0_30_not_closed" || status === "bridge_deck_unmatched" || layer.feature.properties.deck_status === "bridge_deck_sampled") {
        layer.bringToFront();
      }
    });
  }
  if (reportsLayer && map && map.hasLayer(reportsLayer)) {
    reportsLayer.bringToFront();
  }
  renderStats();
  drawChart();
  if (selected) {
    selected.setStyle({ weight: 7, color: "#111" });
    selected.bringToFront();
    showDetail(selected.feature.properties);
  }
}

function renderStats() {
  const row = summary.stages.find((item) => item.id === stage);
  const stats = document.getElementById("stats");
  stats.replaceChildren();
  addStat(stats, "Wet piece length at or above 0.30 m", metres(row.wet_piece_length_m) + " (" + row.wet_piece_percent_of_network.toFixed(2) + "% of the network)");
  addStat(stats, "Assumed closed", row.n_assumed_closed + " centerlines, " + metres(row.assumed_closed_length_m));
  addStat(stats, "Weak components", String(row.n_weak_components));
  addStat(stats, "Largest component", metres(row.largest_component_length_m) + " (" + row.largest_component_n_nodes + " nodes)");
  const hospital = document.getElementById("hospital");
  const showing = row.hospital_disconnected ? "blocked from the high school, fire station, police, and municipal building" : "still open to those destinations";
  let only = "";
  if (summary.hospital.disconnects_only_at_2_00) {
    only = "The hospital routes disconnect only at the +2.0 m rise. ";
  } else if (summary.hospital.disconnected_rises_m && summary.hospital.disconnected_rises_m.length) {
    only = "The hospital routes are disconnected at " + summary.hospital.disconnected_rises_m.map(riseText).join(", ") + ". ";
  }
  hospital.textContent = only + "Showing " + row.label + ": Princeton House Behavioral Health is " + showing + ".";
  const aadt = document.getElementById("aadt");
  aadt.textContent = "AADT: " + row.aadt_nearest_edge_assumed_closed + " of " + row.aadt_records + " station-records have a nearest edge assumed closed. " + summary.aadt_note;
}

function drawChart() {
  const root = document.getElementById("chart");
  if (!summary) return;
  root.replaceChildren();
  const wetMax = Math.max(...summary.stages.map((item) => item.wet_piece_length_m));
  const closedMax = Math.max(...summary.stages.map((item) => item.n_assumed_closed));
  root.append(metric("Wet piece length", summary.stages, (item) => item.wet_piece_length_m, wetMax, (item) => (item.wet_piece_length_m / 1000).toFixed(1) + " km"));
  root.append(metric("Assumed-closed centerlines", summary.stages, (item) => item.n_assumed_closed, closedMax, (item) => String(item.n_assumed_closed)));
}

function metric(title, stages, value, max, label) {
  const block = document.createElement("div");
  const heading = document.createElement("p");
  heading.className = "metric";
  heading.textContent = title;
  const bars = document.createElement("div");
  bars.className = "bars";
  stages.forEach((item) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const name = document.createElement("span");
    name.textContent = riseText(item.stage_above_channel_dem_m);
    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("div");
    fill.className = "fill" + (item.id === stage ? " on" : "");
    fill.style.width = Math.max(2, (100 * value(item)) / max) + "%";
    track.append(fill);
    const number = document.createElement("span");
    number.className = "bar-value";
    number.textContent = label(item);
    row.append(name, track, number);
    bars.append(row);
  });
  block.append(heading, bars);
  return block;
}

function selectLayer(layer) {
  if (selected) {
    selected.setStyle(styleFor(selected.feature.properties["status_" + stageKey(stage)], selected.feature.properties.deck_status));
  }
  selected = layer;
  layer.setStyle({ weight: 7, color: "#111" });
  layer.bringToFront();
  const fold = document.getElementById("selected-road");
  if (fold) fold.open = true;
  showDetail(layer.feature.properties);
}

function showDetail(props) {
  const key = stageKey(stage);
  const status = props["status_" + key];
  const depth = props["depth_max_m_" + key];
  const wet = props["wet_m_" + key];
  const root = document.getElementById("road-detail");
  root.replaceChildren();
  addLine(root, "Name", props.name || "Unnamed");
  addLine(root, "Class", props.road_class || "unknown");
  addLine(root, "Status", STATUS_LABEL[status] || status);
  addLine(root, "Max depth", depth === null || depth === undefined ? "not sampled" : depth.toFixed(3) + " m");
  addLine(root, "Wet piece length", wet === null || wet === undefined ? "not sampled" : wet.toFixed(1) + " m at or above 0.30 m");
  addLine(root, "Inside length", props.length_m_inside === null ? "none" : props.length_m_inside.toFixed(1) + " m");
  addLine(root, "Bridge flag", props.is_bridge ? "yes" : "no");
  const zones = props.fema_zones || [];
  addLine(root, "Regulatory zone", zones.length ? zones.map((zone) => zone.zone + " (" + zone.length_m + " m)").join("; ") : "none");
  addLine(root, "Zone depth", "not assigned");
  if (props.deck_status === "bridge_deck_sampled") {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "Teal means this depth is the scenario water surface minus a published deck elevation.";
    root.append(note);
  } else if (status === "bridge_deck_unmatched" || props.deck_status === "bridge_deck_unmatched") {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = props.deck_note || "Purple means the deck elevation is unknown. It is not a flood depth.";
    root.append(note);
  }
  (props.deck_structures || []).forEach((label) => addLine(root, "Inventory", label));
  if (status === "unmatched_no_channel") {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "Gray means unmatched, not dry.";
    root.append(note);
  }
}

function findRoad(query) {
  const needle = query.trim().toLowerCase();
  if (!needle || !roadLayer) return;
  const hits = [];
  roadLayer.eachLayer((layer) => {
    const name = (layer.feature.properties.name || "").toLowerCase();
    if (name.includes(needle)) hits.push(layer);
  });
  hits.sort((a, b) => (b.feature.properties.length_m_inside || 0) - (a.feature.properties.length_m_inside || 0));
  if (!hits.length) {
    const root = document.getElementById("road-detail");
    root.replaceChildren();
    const note = document.createElement("p");
    note.className = "empty";
    note.textContent = "No centerline name contains “" + query.trim() + "”.";
    root.append(note);
    const fold = document.getElementById("selected-road");
    if (fold) fold.open = true;
    return;
  }
  const group = L.featureGroup(hits);
  map.fitBounds(group.getBounds(), { padding: [30, 30], maxZoom: 16 });
  selectLayer(hits[0]);
}

function renderFema(record) {
  const root = document.getElementById("fema");
  const date = document.getElementById("fema-date");
  root.replaceChildren();
  date.textContent = record.effective_date_label
    ? "Regulatory. Effective " + record.effective_date_label + ". Not Hurricane Ida. Not a scenario depth."
    : "Regulatory layer is not loaded.";
  (record.zones || []).forEach((zone) => {
    addLine(root, zone.zone, zone.length_m + " m, " + zone.n_centerlines + " centerlines");
  });
  const water = record.regulatory_water_surface;
  if (water) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = water.stream + " cross section " + water.cross_section
      + " regulatory water surface: " + water.value + " " + water.units + " " + water.datum
      + ". Not a deck elevation. It is not subtracted from the +1.0 m or +2.0 m scenario.";
    root.append(note);
  }
  if (record.neighbor_firm_note) {
    const extra = document.createElement("p");
    extra.className = "hint";
    extra.textContent = record.neighbor_firm_note;
    root.append(extra);
  }
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

function setReportsVisible(visible) {
  if (!map || !reportsLayer) return;
  if (visible) {
    reportsLayer.addTo(map);
    reportsLayer.bringToFront();
  } else if (map.hasLayer(reportsLayer)) {
    map.removeLayer(reportsLayer);
  }
}

function reportPopup(props) {
  const root = document.createElement("div");
  root.className = "report-popup";
  const title = document.createElement("strong");
  title.textContent = props.title || props.name || "News report";
  const news = document.createElement("p");
  news.textContent = "News date: " + (props.news_date || "not recorded") + ". " + (props.news_note || "");
  const scenario = document.createElement("p");
  scenario.textContent = props.scenario_note || "The scenario result for this road is not loaded.";
  const mark = document.createElement("p");
  mark.textContent = "This mark is a news report. It is not a model depth.";
  root.append(title, news, scenario, mark);
  return root;
}

function setFemaVisible(visible) {
  if (!map || !femaLayer) return;
  if (visible) {
    femaLayer.addTo(map);
    if (roadLayer) roadLayer.bringToFront();
    if (reportsLayer && map.hasLayer(reportsLayer)) reportsLayer.bringToFront();
  } else if (map.hasLayer(femaLayer)) {
    map.removeLayer(femaLayer);
  }
}

function renderDecks(record) {
  const root = document.getElementById("decks");
  root.replaceChildren();
  const count = document.createElement("p");
  const sampled = record.n_sampled;
  const total = record.n_bridge_centerlines;
  const withElevation = record.n_with_deck_elevation;
  count.textContent = sampled === null || sampled === undefined
    ? "Bridge-deck join has not been run."
    : "Published deck elevations joined: " + withElevation + " of " + total + ". Sampled decks: " + sampled + ".";
  root.append(count);
  const unknown = document.createElement("p");
  unknown.className = "hint";
  unknown.textContent = "Purple is an unknown deck. Teal would be a sampled deck, and it is a different color. A 3DEP elevation under the span is not a deck.";
  root.append(unknown);
  const quakers = (record.centerlines || []).filter((item) => item.name === "Quaker Road");
  quakers.forEach((item) => {
    const line = document.createElement("p");
    line.className = "hint";
    const structures = (item.accepted_structures || []).map((structure) => structure.structure_number).join(", ");
    line.textContent = "Quaker Road, " + item.length_m_inside + " m inside: " + item.exposure_status
      + (structures ? ". Structures " + structures + "." : ". No accepted structure.")
      + (item.deck_elevation_m == null ? " Deck elevation: not published." : " Deck elevation: " + item.deck_elevation_m + " m.");
    root.append(line);
  });
}

function renderEnso(record) {
  const root = document.getElementById("enso");
  if (!root) return;
  root.replaceChildren();
  if (!record.ok) {
    const fail = document.createElement("p");
    fail.textContent = record.fetch_error || "No saved ENSO observation.";
    root.append(fail);
    return;
  }
  const saved = document.createElement("p");
  saved.className = "hint";
  const retrieved = formatStamp(record.fetched_at_utc);
  saved.textContent = record.using_saved_observation
    ? "Showing the last saved observation, retrieved " + retrieved + "."
    : "Saved observation, retrieved " + retrieved + ".";
  root.append(saved);
  const weekly = record.weekly || {};
  const oni = record.oni || {};
  if (weekly.nino34_anomaly_c != null) {
    const week = document.createElement("p");
    week.textContent = "Weekly Niño-3.4 " + signed(weekly.nino34_anomaly_c) + " °C (week centered " + formatIsoDate(weekly.week_centered) + ")";
    root.append(week);
  }
  if (oni.anomaly_c != null) {
    const index = document.createElement("p");
    index.textContent = "ONI " + signed(oni.anomaly_c) + " °C for " + (oni.season || "") + " " + (oni.year || "");
    root.append(index);
  }
  const phase = document.createElement("p");
  if (record.official_phase && record.official_phase.status) {
    phase.textContent = record.official_phase.status + " from the " + (record.official_phase.issued || "undated") + " discussion.";
  } else {
    phase.textContent = record.official_phase_note || "No official phase is shown. The weekly anomaly is not a phase.";
  }
  root.append(phase);
  const rule = document.createElement("p");
  rule.className = "hint";
  rule.textContent = "The phase is NOAA’s sentence, not a threshold on the weekly anomaly. ENSO does not set Princeton road depths.";
  root.append(rule);
}

function renderNameCheck(record) {
  nameCheck = record;
  const root = document.getElementById("name-check");
  if (!root) return;
  root.replaceChildren();
  const hint = root.previousElementSibling;
  if (hint && record.label) hint.textContent = record.label;
  const list = document.createElement("ul");
  list.className = "name-check";
  list.setAttribute("aria-label", "Name check, not a validation");
  (record.rows || []).forEach((row) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "name-check-road";
    button.textContent = row.road;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => focusReportedRoad(row));
    const detail = document.createElement("p");
    detail.className = "hint name-check-detail";
    detail.hidden = true;
    detail.textContent = row.detail || "";
    const marks = document.createElement("div");
    marks.className = "name-check-marks";
    const mark = document.createElement("span");
    mark.dataset.road = row.road;
    marks.append(mark);
    item.append(button, marks, detail);
    list.append(item);
  });
  root.append(list);
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "The five rows follow the selected rise. Affected / do not use means at least one centerline of that name is assumed closed at that mark. Still open means none are. Click a name to turn on the news dashes and zoom to those centerlines.";
  root.append(note);
  showNameCheck(stage);
}

function nameCheckLine(step) {
  const label = riseText(step.stage_m);
  if (step.result === "captured" && step.captured_of) {
    return label + " Affected / do not use, " + step.captured_of;
  }
  if (step.result === "captured") return label + " Affected / do not use";
  return label + " Still open";
}

function showNameCheck(stageId) {
  if (!nameCheck) return;
  const byRoad = {};
  (nameCheck.rows || []).forEach((row) => {
    byRoad[row.road] = row;
  });
  document.querySelectorAll(".name-check-marks span").forEach((mark) => {
    const row = byRoad[mark.dataset.road];
    const step = row && (row.steps || []).find((item) => item.id === stageId);
    if (!step) return;
    mark.className = step.result === "captured" ? "result" : "missed";
    mark.textContent = nameCheckLine(step);
  });
  const summaryNode = document.getElementById("name-check-summary");
  const sample = (nameCheck.rows || [])[0];
  const sampleStep = sample && (sample.steps || []).find((item) => item.id === stageId);
  if (summaryNode && sampleStep) {
    summaryNode.textContent = "Name check, " + riseText(sampleStep.stage_m);
  }
}

function focusReportedRoad(row) {
  const root = document.getElementById("name-check");
  if (root) {
    root.querySelectorAll(".name-check-road").forEach((button) => {
      const on = button.textContent === row.road;
      button.setAttribute("aria-pressed", on ? "true" : "false");
      const item = button.parentElement;
      if (!item) return;
      item.classList.toggle("selected", on);
      const detail = item.querySelector(".name-check-detail");
      if (detail) detail.hidden = !on;
    });
  }
  const toggle = document.getElementById("reports-toggle");
  if (toggle) toggle.checked = true;
  setReportsVisible(true);
  if (!map || !reportsLayer || !observedReports) return;
  if (reportFocus) {
    reportsLayer.removeLayer(reportFocus);
    reportFocus = null;
  }
  const features = (observedReports.features || []).filter(
    (feature) => feature.properties && feature.properties.title === row.road
  );
  if (!features.length) return;
  reportFocus = L.geoJSON(
    { type: "FeatureCollection", features: features },
    {
      pane: "reports",
      interactive: false,
      style: () => ({
        color: "#111111",
        weight: 7,
        opacity: 0.95,
        dashArray: "8 5",
        lineCap: "butt",
      }),
    }
  );
  reportsLayer.addLayer(reportFocus);
  reportsLayer.bringToFront();
  const bounds = reportFocus.getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [48, 48], maxZoom: 16 });
  }
}

function renderIda(record) {
  const root = document.getElementById("ida");
  root.replaceChildren();
  const lead = document.createElement("p");
  lead.textContent = record.note || "";
  root.append(lead);
  (record.places || []).forEach((place) => {
    const block = document.createElement("div");
    block.className = "place";
    const title = document.createElement("p");
    const tag = document.createElement("span");
    tag.className = "tag " + place.verification;
    tag.textContent = place.verification === "partial" ? "partially documented" : place.verification;
    title.append(tag, document.createTextNode(" " + place.title));
    block.append(title);
    const qualitative = document.createElement("p");
    qualitative.textContent = place.qualitative;
    block.append(qualitative);
    (place.claims || []).forEach((claim) => {
      const line = document.createElement("p");
      const link = document.createElement("a");
      link.href = claim.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = claim.source + ", " + claim.published;
      line.append(link, document.createTextNode(" — " + claim.statement));
      block.append(line);
    });
    if (place.unverified_note) {
      const extra = document.createElement("p");
      extra.className = "hint";
      extra.textContent = place.unverified_note;
      block.append(extra);
    }
    root.append(block);
  });
  const footer = document.createElement("p");
  footer.className = "hint";
  footer.textContent = "Not a validation. No precision or recall is computed.";
  root.append(footer);
}

function addStat(list, label, value) {
  const row = document.createElement("div");
  row.className = "stat";
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value;
  row.append(dt, dd);
  list.append(row);
}

function addLine(root, label, value) {
  const line = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = label + ": ";
  line.append(strong, document.createTextNode(value));
  root.append(line);
}

function metres(value) {
  if (value >= 1000) return (value / 1000).toFixed(1) + " km";
  return Math.round(value) + " m";
}

function formatStamp(iso) {
  if (!iso) return "date not recorded";
  const date = formatIsoDate(iso.slice(0, 10));
  const time = iso.length >= 16 ? iso.slice(11, 16) : "";
  return time ? date + ", " + time + " UTC" : date;
}

function formatIsoDate(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return iso || "date not recorded";
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const parts = iso.slice(0, 10).split("-");
  return Number(parts[2]) + " " + months[Number(parts[1]) - 1] + " " + parts[0];
}

function signed(value) {
  const tenths = Math.abs(value * 10 - Math.round(value * 10)) < 1e-6;
  const text = value.toFixed(tenths ? 1 : 2);
  return (value > 0 ? "+" : "") + text;
}

function stageKey(id) {
  return id.replace(".", "_");
}
