const COLORS = {
  accessible_routable: "#1f7a4d",
  at_risk_routable: "#c4920a",
  assumed_closed: "#c0392b",
  partial_above_0_30_not_closed: "#e07a2f",
  bridge_deck_unmatched: "#6d4ea8",
  bridge_deck_sampled: "#0e7c86",
  unmatched_no_channel: "#8a8a8a",
  outside_municipality: "#b7b1a6",
};

const LEGEND = [
  ["accessible_routable", "Accessible. Scenario depth stays below 0.10 m."],
  ["at_risk_routable", "At risk. Some length is 0.10–0.30 m. Still routable."],
  ["partial_above_0_30_not_closed", "Partly at or above 0.30 m, but under half the inside length. Still routable."],
  ["assumed_closed", "Assumed closed. At least half the inside length is at or above 0.30 m. A preliminary rule, not a closure standard."],
  ["bridge_deck_unmatched", "Purple is an unknown bridge deck. No published elevation was joined. Not a flood depth."],
  ["bridge_deck_sampled", "Teal is a sampled deck. Depth is max(0, scenario water surface − a published deck elevation)."],
  ["unmatched_no_channel", "Gray is unmatched, not dry. No channel was found within 500 m. Not called closed."],
  ["outside_municipality", "Outside the municipality. Not a depth."],
];

const STATUS_LABEL = {
  accessible_routable: "Accessible",
  at_risk_routable: "At risk, still routable",
  partial_above_0_30_not_closed: "Partly at or above 0.30 m, not closed",
  assumed_closed: "Assumed closed",
  bridge_deck_unmatched: "Bridge deck unmatched",
  bridge_deck_sampled: "Bridge deck sampled",
  unmatched_no_channel: "Unmatched, no channel",
  outside_municipality: "Outside the municipality",
};

let summary = null;
let roads = null;
let fema = null;
let femaZones = null;
let stage = "1.00";
let selected = null;
let roadLayer = null;
let femaLayer = null;
let map = null;

const FEMA_STYLE = {
  floodway: { color: "#0b1f33", fillColor: "#16324f", fillOpacity: 0.5, weight: 0.6 },
  ae: { color: "#1d4e89", fillColor: "#8fb8d6", fillOpacity: 0.42, weight: 0.4 },
  a: { color: "#1d4e89", fillColor: "#d5e4f0", fillOpacity: 0.55, weight: 0.5, dashArray: "3 2" },
  moderate: { color: "#6b5b3e", fillColor: "#f4efe2", fillOpacity: 0.55, weight: 0.7, dashArray: "2 2" },
  minimal: { color: "#c5d0d6", fillColor: "#e7eef2", fillOpacity: 0.18, weight: 0 },
  other: { color: "#243040", fillColor: "#d9e2ea", fillOpacity: 0.35, weight: 0.4 },
};

const FEMA_LEGEND = [
  ["floodway", "Floodway. Special flood hazard area."],
  ["ae", "Zone AE. Special flood hazard area, base flood elevation from the study."],
  ["a", "Zone A. Special flood hazard area, no published base flood elevation on the polygon."],
  ["moderate", "Zone X, 0.2% annual chance. Not the special flood hazard area."],
  ["minimal", "Zone X, minimal hazard. Not a scenario depth."],
];

document.getElementById("stage-1").addEventListener("click", () => setStage("1.00"));
document.getElementById("stage-2").addEventListener("click", () => setStage("2.00"));
document.getElementById("search").addEventListener("submit", (event) => {
  event.preventDefault();
  findRoad(document.getElementById("road-query").value);
});

document.getElementById("fema-toggle").addEventListener("change", (event) => {
  setFemaVisible(event.target.checked);
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
]).then(([summaryPayload, roadPayload, boundaryPayload, ensoPayload, idaPayload, deckPayload, femaPayload, zonePayload]) => {
  summary = summaryPayload;
  roads = roadPayload;
  fema = femaPayload;
  femaZones = zonePayload;
  document.getElementById("banner").textContent = summary.banner;
  const stamp = (summary.computed_at_utc || "").replace("T", " ").replace("Z", " UTC");
  document.getElementById("product-line").textContent =
    "Hypothetical 3DEP scenario. Not Hurricane Ida. " + stamp;
  document.getElementById("component-note").textContent = summary.component_note;
  drawLegend();
  drawMap(boundaryPayload);
  drawChart();
  renderEnso(ensoPayload);
  renderIda(idaPayload);
  renderDecks(deckPayload);
  renderFema(femaPayload);
  setStage("1.00");
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
  if (!fema) return;
  const heading = document.createElement("p");
  heading.className = "legend-heading";
  heading.textContent = "Regulatory. Effective " + (fema.effective_date_label || "date not loaded") + ".";
  root.append(heading);
  FEMA_LEGEND.forEach(([key, text]) => {
    const row = document.createElement("div");
    row.className = "legend-row";
    const swatch = document.createElement("span");
    swatch.className = "swatch area";
    swatch.style.background = FEMA_STYLE[key].fillColor;
    const label = document.createElement("span");
    label.textContent = text;
    row.append(swatch, label);
    root.append(row);
  });
  const surface = document.createElement("p");
  surface.className = "hint";
  const water = fema.regulatory_water_surface;
  surface.textContent = water
    ? "Stony Brook cross section M: " + water.value + " " + water.units + " " + water.datum + " regulatory water surface. Not a deck elevation."
    : "No regulatory water-surface attribute is loaded.";
  root.append(surface);
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
  roadLayer = L.geoJSON(roads, {
    style: (feature) => styleFor(feature.properties["status_" + stageKey(stage)], feature.properties.deck_status),
    onEachFeature: (feature, layer) => {
      layer.on("click", () => selectLayer(layer));
    },
  }).addTo(map);
  map.fitBounds(roadLayer.getBounds(), { padding: [20, 20] });
}

function styleFor(status, deckStatus) {
  const closed = status === "assumed_closed";
  const color = deckStatus === "bridge_deck_sampled" ? COLORS.bridge_deck_sampled : (COLORS[status] || "#444");
  return {
    color: color,
    weight: closed || deckStatus === "bridge_deck_sampled" ? 4 : status === "partial_above_0_30_not_closed" ? 3 : 2.2,
    opacity: 0.92,
  };
}

function setStage(next) {
  stage = next;
  document.getElementById("stage-1").setAttribute("aria-pressed", next === "1.00" ? "true" : "false");
  document.getElementById("stage-2").setAttribute("aria-pressed", next === "2.00" ? "true" : "false");
  if (roadLayer) {
    roadLayer.eachLayer((layer) => {
      const status = layer.feature.properties["status_" + stageKey(stage)];
      layer.setStyle(styleFor(status, layer.feature.properties.deck_status));
      if (status === "assumed_closed" || status === "partial_above_0_30_not_closed" || status === "bridge_deck_unmatched" || layer.feature.properties.deck_status === "bridge_deck_sampled") {
        layer.bringToFront();
      }
    });
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
  const showing = row.hospital_disconnected ? "disconnected from the high school, fire station, police, and municipal building" : "still connected to those destinations";
  const only = summary.hospital.disconnects_only_at_2_00
    ? "The hospital routes disconnect only at the +2.0 m assumption. "
    : "";
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
    name.textContent = "+" + item.stage_above_channel_dem_m.toFixed(1) + " m";
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

function setFemaVisible(visible) {
  if (!map || !femaLayer) return;
  if (visible) {
    femaLayer.addTo(map);
    if (roadLayer) roadLayer.bringToFront();
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
  root.replaceChildren();
  if (!record.ok) {
    const fail = document.createElement("p");
    fail.textContent = record.fetch_error || "ENSO observations are unavailable.";
    root.append(fail);
    return;
  }
  if (record.using_saved_observation) {
    const saved = document.createElement("p");
    saved.textContent = "NOAA could not be reached. Showing the last successful observation, retrieved " + record.fetched_at_utc + ".";
    root.append(saved);
  }
  const weekly = record.weekly;
  const oni = record.oni;
  addLine(root, "Weekly Niño-3.4 anomaly", signed(weekly.nino34_anomaly_c) + " °C");
  addLine(root, "Week centered", weekly.week_centered);
  addLine(root, "Weekly Niño-3.4 SST", weekly.nino34_sst_c.toFixed(1) + " °C");
  addLine(root, "ONI", oni.season + " " + oni.year + " (" + oni.season_label + "), anomaly " + signed(oni.anomaly_c) + " °C");
  addLine(root, "Retrieved", record.fetched_at_utc);
  const phase = document.createElement("p");
  if (record.official_phase) {
    phase.textContent = "Official phase: " + record.official_phase.status + ", issued " + (record.official_phase.issued || "date not parsed") + ". " + record.official_phase.note;
  } else {
    phase.textContent = record.official_phase_note || "No official phase is shown.";
  }
  root.append(phase);
  const context = document.createElement("p");
  context.className = "hint";
  context.textContent = record.context;
  root.append(context);
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

function signed(value) {
  const tenths = Math.abs(value * 10 - Math.round(value * 10)) < 1e-6;
  const text = value.toFixed(tenths ? 1 : 2);
  return (value > 0 ? "+" : "") + text;
}

function stageKey(id) {
  return id.replace(".", "_");
}
