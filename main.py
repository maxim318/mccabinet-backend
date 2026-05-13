import { useState } from "react";

function getCabinetColor(type) {
  if (type === "wall") return "#ffd37a";
  if (type === "sink_base") return "#9be7ff";
  if (type === "tall") return "#c3a6ff";
  if (type === "filler") return "#ddd";
  if (type === "corner") return "#b6f2a1";
  return "#7db7ff";
}

function CabinetRun({ wall }) {
  const wallLength = wall.length_inches || 120;
  const displayWidth = 700;

  return (
    <div style={{ marginTop: 15, marginBottom: 25 }}>
      <div
        style={{
          display: "flex",
          width: displayWidth,
          height: 70,
          border: "2px solid #333",
          background: "#f3f3f3",
          overflow: "hidden"
        }}
      >
        {(wall.cabinets || []).map((cab, index) => {
          const cabWidth = cab.width || 30;
          const blockWidth = (cabWidth / wallLength) * displayWidth;

          return (
            <div
              key={index}
              style={{
                width: blockWidth,
                minWidth: 45,
                borderRight: "1px solid #fff",
                background: getCabinetColor(cab.type),
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                textAlign: "center"
              }}
            >
              <strong>{cab.width || "?"}"</strong>
              <span>{cab.type}</span>
            </div>
          );
        })}
      </div>

      <div style={{ fontSize: 12, marginTop: 5 }}>
        Wall length: {wall.length_inches || "Needs confirmation"}"
      </div>
    </div>
  );
}

function FloorPlanPreview({ layout }) {
  const walls = layout?.walls || [];
  const appliances = layout?.appliances || [];
  const svgWidth = 900;
  const svgHeight = 600;
  const scale = 2;
  const offsetX = 120;
  const offsetY = 120;

  const allCabinets = walls.flatMap((wall) =>
    (wall.cabinets || []).map((cab) => ({
      ...cab,
      wall_id: wall.id
    }))
  );

  function toSvgX(x) {
    return offsetX + (Number(x) || 0) * scale;
  }

  function toSvgY(y) {
    return offsetY + (Number(y) || 0) * scale;
  }

  function size(value, fallback) {
    return (Number(value) || fallback) * scale;
  }

  function renderCoordinateCabinet(cab, index) {
    const rotation = Number(cab.rotation) || 0;
    const widthPx = size(cab.width, 30);
    const depthPx = size(cab.depth, 24);
    const x = toSvgX(cab.x);
    const y = toSvgY(cab.y);

    const isVertical = rotation === 90 || rotation === 270;
    const rectWidth = isVertical ? depthPx : widthPx;
    const rectHeight = isVertical ? widthPx : depthPx;

    return (
      <g key={`coord-cab-${index}`}>
        <rect
          x={x}
          y={y}
          width={rectWidth}
          height={rectHeight}
          fill={getCabinetColor(cab.type)}
          stroke="#333"
          strokeWidth="1"
        />
        <text
          x={x + rectWidth / 2}
          y={y + rectHeight / 2}
          fontSize="10"
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {cab.width || "?"}"
        </text>
      </g>
    );
  }

  function renderCoordinateWall(wall, index) {
    const hasCoordinates =
      wall.x1 !== undefined &&
      wall.y1 !== undefined &&
      wall.x2 !== undefined &&
      wall.y2 !== undefined;

    if (!hasCoordinates) return null;

    return (
      <g key={`wall-${wall.id || index}`}>
        <line
          x1={toSvgX(wall.x1)}
          y1={toSvgY(wall.y1)}
          x2={toSvgX(wall.x2)}
          y2={toSvgY(wall.y2)}
          stroke="#111"
          strokeWidth="6"
          strokeLinecap="square"
        />
        <text
          x={(toSvgX(wall.x1) + toSvgX(wall.x2)) / 2}
          y={(toSvgY(wall.y1) + toSvgY(wall.y2)) / 2 - 12}
          fontSize="12"
          textAnchor="middle"
        >
          {wall.id} ({wall.length_inches || "?"}")
        </text>
      </g>
    );
  }

  function renderAppliance(appliance, index) {
    const x = toSvgX(appliance.x);
    const y = toSvgY(appliance.y);
    const widthPx = size(appliance.estimated_width || appliance.width, 30);
    const depthPx = size(appliance.depth, 24);
    const rotation = Number(appliance.rotation) || 0;
    const isVertical = rotation === 90 || rotation === 270;

    return (
      <g key={`appliance-${index}`}>
        <rect
          x={x}
          y={y}
          width={isVertical ? depthPx : widthPx}
          height={isVertical ? widthPx : depthPx}
          fill="#ff8c8c"
          stroke="#333"
          strokeWidth="1"
        />
        <text
          x={x + (isVertical ? depthPx : widthPx) / 2}
          y={y + (isVertical ? widthPx : depthPx) / 2}
          fontSize="10"
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {appliance.type}
        </text>
      </g>
    );
  }

  const hasCoordinateCabinets = allCabinets.some(
    (cab) => cab.x !== undefined && cab.y !== undefined
  );

  return (
    <div style={{ marginTop: 40 }}>
      <h2>Basic Floor Plan Preview</h2>
      <p style={{ maxWidth: 760 }}>
        This view uses x/y/depth/rotation data when available. It is still a draft preview.
      </p>

      <svg
        width={svgWidth}
        height={svgHeight}
        style={{
          border: "1px solid #ccc",
          background: "#fafafa"
        }}
      >
        {walls.map((wall, index) => renderCoordinateWall(wall, index))}
        {allCabinets.map((cab, index) => renderCoordinateCabinet(cab, index))}
        {appliances.map((appliance, index) => renderAppliance(appliance, index))}

        {!hasCoordinateCabinets && (
          <text x="40" y="40" fontSize="14" fill="red">
            No cabinet x/y coordinates found yet. Regenerate layout after confirming dimensions.
          </text>
        )}
      </svg>
    </div>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [measurement, setMeasurement] = useState(null);
  const [editableDimensions, setEditableDimensions] = useState([]);
  const [dimensionsConfirmed, setDimensionsConfirmed] = useState(false);
  const [layout, setLayout] = useState(null);
  const [loading, setLoading] = useState(false);
  const [layoutLoading, setLayoutLoading] = useState(false);

  const API = "https://mccabinet-backend-production.up.railway.app";

  function updateDimension(index, field, value) {
    const updated = [...editableDimensions];
    updated[index] = {
      ...updated[index],
      [field]: value
    };
    setEditableDimensions(updated);
    setDimensionsConfirmed(false);
  }

  async function confirmDimensions() {
    if (!measurement) return alert("Analyze a plan first.");

    setLayoutLoading(true);
    setDimensionsConfirmed(false);

    try {
      const response = await fetch(API + "/generate-layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmed_dimensions: editableDimensions,
          detected_appliances: measurement.detected_appliances || [],
          detected_openings: measurement.detected_openings || [],
          layout_type: measurement.layout_type || "",
          notes: "Layout regenerated from user-confirmed dimensions."
        })
      });

      const data = await response.json();
      console.log("GENERATE LAYOUT RESPONSE:", data);

      if (data.status !== "success") {
        alert(data.message || "Layout generation failed.");
        return;
      }

      setLayout(data.cabinet_layout);
      setDimensionsConfirmed(true);
    } catch (err) {
      console.error(err);
      alert(err.message);
    }

    setLayoutLoading(false);
  }

  async function uploadAndAnalyze() {
    if (!file) return alert("Upload a PDF first");

    setLoading(true);
    setMeasurement(null);
    setEditableDimensions([]);
    setDimensionsConfirmed(false);
    setLayout(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const uploadRes = await fetch(API + "/upload", {
        method: "POST",
        body: formData,
      });

      const uploadData = await uploadRes.json();

      const analyzeRes = await fetch(API + "/analyze-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: uploadData.path }),
      });

      const analyzeData = await analyzeRes.json();
      console.log("ANALYZE RESPONSE:", analyzeData);

      const measurementData = analyzeData.measurement_extraction;
      setMeasurement(measurementData);
      setEditableDimensions(measurementData?.detected_dimensions || []);
      setLayout(analyzeData.cabinet_layout);
    } catch (err) {
      console.error(err);
      alert(err.message);
    }

    setLoading(false);
  }

  return (
    <div style={{ padding: 40, fontFamily: "Arial" }}>
      <h1>QuickDesign Kitchen AI</h1>

      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files[0])}
      />

      <br />
      <br />

      <button onClick={uploadAndAnalyze}>
        Analyze Plan
      </button>

      {loading && <p>Analyzing plan...</p>}

      {measurement && (
        <div style={{ marginTop: 40 }}>
          <h2>Measurement Extraction</h2>

          <div
            style={{
              border: "1px solid #ccc",
              padding: 15,
              marginBottom: 20,
              background: "#f8f8f8"
            }}
          >
            <p><strong>Page Used:</strong> {measurement.page_used || "Not detected"}</p>
            <p><strong>Input Type:</strong> {measurement.input_type || "unknown"}</p>
            <p><strong>Scale Detected:</strong> {measurement.scale_detected ? "Yes" : "No"}</p>
            <p><strong>Scale Value:</strong> {measurement.scale_value || "No scale shown / not detected"}</p>
            <p><strong>Can Generate Layout:</strong> {measurement.can_generate_layout ? "Yes" : "No"}</p>
            <p><strong>Reason:</strong> {measurement.layout_generation_reason || "No reason provided"}</p>
            <p><strong>Layout Type:</strong> {measurement.layout_type || "Not detected"}</p>
          </div>

          <h3>Confirm / Edit Dimensions</h3>

          {(editableDimensions || []).length === 0 ? (
            <p>No dimensions detected. Add manual dimensions in the next step.</p>
          ) : (
            <div>
              {(editableDimensions || []).map((item, i) => (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1.5fr 1fr 1.5fr 1fr",
                    gap: 10,
                    marginBottom: 10,
                    alignItems: "center"
                  }}
                >
                  <input
                    value={item.label || ""}
                    onChange={(e) => updateDimension(i, "label", e.target.value)}
                    placeholder="Label"
                  />

                  <input
                    value={item.value || ""}
                    onChange={(e) => updateDimension(i, "value", e.target.value)}
                    placeholder='Value, example 120"'
                  />

                  <input
                    value={item.location || ""}
                    onChange={(e) => updateDimension(i, "location", e.target.value)}
                    placeholder="Location"
                  />

                  <input
                    value={item.confidence || ""}
                    onChange={(e) => updateDimension(i, "confidence", e.target.value)}
                    placeholder="Confidence"
                  />
                </div>
              ))}

              <button onClick={confirmDimensions} disabled={layoutLoading}>
                {layoutLoading ? "Generating Layout..." : "Confirm Dimensions & Regenerate Layout"}
              </button>

              {dimensionsConfirmed && (
                <p style={{ color: "green" }}>
                  Dimensions confirmed. Cabinet layout regenerated from edited dimensions.
                </p>
              )}
            </div>
          )}

          <h3>Detected Appliances</h3>
          <ul>
            {(measurement.detected_appliances || []).map((item, i) => (
              <li key={i}>
                <strong>{item.type}</strong> — {item.location} ({item.confidence})
              </li>
            ))}
          </ul>

          <h3>Detected Openings</h3>
          <ul>
            {(measurement.detected_openings || []).map((item, i) => (
              <li key={i}>
                <strong>{item.type}</strong> — {item.location}
                {item.size ? ` — ${item.size}` : ""} ({item.confidence})
              </li>
            ))}
          </ul>

          <h3>Uncertain Items</h3>
          <ul>
            {(measurement.uncertain_items || []).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>

          <h3>Questions for Client</h3>
          <ul>
            {(measurement.questions_for_client || []).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {layout && (
        <div style={{ marginTop: 40 }}>
          <FloorPlanPreview layout={layout} />

          <h2>Draft Cabinet Layout</h2>

          <p><strong>Status:</strong> {layout.layout_status}</p>
          <p><strong>Kitchen Type:</strong> {layout.kitchen_type}</p>

          <h3>Walls / Cabinet Runs</h3>
          {(layout.walls || []).map((wall, i) => (
            <div key={i} style={{ marginBottom: 25, padding: 15, border: "1px solid #ccc" }}>
              <h4>{wall.id} — {wall.length_inches || "Needs confirmation"}"</h4>
              <p>{wall.description}</p>

              <CabinetRun wall={wall} />

              <ul>
                {(wall.cabinets || []).map((cab, j) => (
                  <li key={j}>
                    <strong>{cab.type}</strong> — {cab.width}" — {cab.position_note}
                    {" "}
                    <span style={{ color: "#555" }}>
                      [x:{cab.x ?? "?"}, y:{cab.y ?? "?"}, d:{cab.depth ?? "?"}, r:{cab.rotation ?? "?"}]
                    </span>
                  </li>
                ))}
              </ul>

              {wall.notes && <p><strong>Notes:</strong> {wall.notes}</p>}
            </div>
          ))}

          <h3>Appliances</h3>
          <ul>
            {(layout.appliances || []).map((item, i) => (
              <li key={i}>
                <strong>{item.type}</strong> — {item.estimated_width}" — {item.wall_id} — {item.location_note}
                {" "}
                <span style={{ color: "#555" }}>
                  [x:{item.x ?? "?"}, y:{item.y ?? "?"}, d:{item.depth ?? "?"}, r:{item.rotation ?? "?"}]
                </span>
              </li>
            ))}
          </ul>

          <h3>Assumptions</h3>
          <ul>
            {(layout.assumptions || []).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>

          <h3>Questions Before Final Layout</h3>
          <ul>
            {(layout.questions_for_client || []).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}