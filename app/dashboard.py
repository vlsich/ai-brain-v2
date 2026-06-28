from __future__ import annotations


DASHBOARD_HTML = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Brain Knowledge Graph</title>
  <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050816;
      --panel: rgba(9, 16, 36, 0.84);
      --panel-strong: rgba(12, 23, 52, 0.94);
      --line: rgba(91, 214, 255, 0.22);
      --text: #e9f7ff;
      --muted: #8aa7bc;
      --cyan: #34d5ff;
      --green: #35f2a0;
      --pink: #ff4fd8;
      --yellow: #ffd166;
      --red: #ff6b7a;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      overflow: hidden;
      background:
        radial-gradient(circle at 20% 12%, rgba(52, 213, 255, 0.18), transparent 34%),
        radial-gradient(circle at 82% 18%, rgba(255, 79, 216, 0.13), transparent 28%),
        linear-gradient(135deg, #040713 0%, #07111f 46%, #050816 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .shell {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr) 360px;
      grid-template-rows: 78px minmax(0, 1fr);
      height: 100vh;
      gap: 16px;
      padding: 16px;
    }

    header {
      grid-column: 1 / 4;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border: 1px solid var(--line);
      background: linear-gradient(90deg, rgba(9, 16, 36, 0.92), rgba(7, 18, 39, 0.72));
      box-shadow: 0 0 34px rgba(52, 213, 255, 0.12);
      padding: 0 18px;
      border-radius: 8px;
    }

    h1 {
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }

    .subtitle {
      color: var(--muted);
      font-size: 13px;
      margin-top: 4px;
    }

    .toolbar {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    input, button {
      border-radius: 6px;
      border: 1px solid var(--line);
      background: rgba(4, 10, 24, 0.9);
      color: var(--text);
      height: 38px;
      font-size: 14px;
    }

    input {
      width: 260px;
      padding: 0 12px;
      outline: none;
    }

    input:focus {
      border-color: var(--cyan);
      box-shadow: 0 0 0 3px rgba(52, 213, 255, 0.12);
    }

    button {
      padding: 0 13px;
      cursor: pointer;
      font-weight: 650;
    }

    button:hover {
      border-color: var(--green);
      box-shadow: 0 0 18px rgba(53, 242, 160, 0.16);
    }

    aside, .details {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      min-height: 0;
      overflow: auto;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.025);
    }

    aside {
      padding: 16px;
    }

    .details {
      padding: 16px;
    }

    #cy {
      min-width: 0;
      min-height: 0;
      border: 1px solid rgba(52, 213, 255, 0.28);
      border-radius: 8px;
      background:
        linear-gradient(rgba(52, 213, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(52, 213, 255, 0.035) 1px, transparent 1px),
        rgba(3, 7, 18, 0.7);
      background-size: 28px 28px;
      box-shadow: 0 0 42px rgba(52, 213, 255, 0.10);
    }

    .panel-title {
      margin: 0 0 12px;
      color: var(--cyan);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .stat-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 20px;
    }

    .stat {
      border: 1px solid rgba(52, 213, 255, 0.18);
      background: var(--panel-strong);
      padding: 12px;
      border-radius: 8px;
    }

    .stat-value {
      font-size: 28px;
      font-weight: 760;
      color: var(--green);
      line-height: 1;
    }

    .stat-label {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .list {
      display: grid;
      gap: 8px;
      margin-bottom: 20px;
    }

    .item {
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.035);
      padding: 10px;
      border-radius: 8px;
      font-size: 13px;
    }

    .item strong {
      display: block;
      color: var(--text);
      margin-bottom: 4px;
    }

    .muted { color: var(--muted); }
    .tag {
      display: inline-flex;
      align-items: center;
      border: 1px solid rgba(52, 213, 255, 0.24);
      color: var(--cyan);
      background: rgba(52, 213, 255, 0.08);
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      margin: 0 5px 5px 0;
    }

    .detail-title {
      margin: 0 0 6px;
      font-size: 20px;
    }

    .detail-type {
      margin-bottom: 16px;
    }

    .description {
      white-space: pre-wrap;
      line-height: 1.5;
      color: #cbe6f7;
      font-size: 14px;
      margin-bottom: 18px;
    }

    .empty {
      color: var(--muted);
      line-height: 1.5;
      font-size: 14px;
    }

    .status {
      color: var(--muted);
      font-size: 13px;
    }

    @media (max-width: 1080px) {
      body { overflow: auto; }
      .shell {
        height: auto;
        min-height: 100vh;
        grid-template-columns: 1fr;
        grid-template-rows: auto auto 70vh auto;
      }
      header, aside, #cy, .details { grid-column: 1; }
      header {
        align-items: flex-start;
        gap: 12px;
        flex-direction: column;
        padding: 14px;
      }
      .toolbar { width: 100%; flex-wrap: wrap; }
      input { flex: 1; min-width: 180px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>AI Brain Knowledge Graph</h1>
        <div class="subtitle">Second Brain visual dashboard V1</div>
      </div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search nodes, topics, goals..." />
        <button id="searchBtn">Search</button>
        <button id="resetBtn">Reset</button>
        <button id="rebuildBtn">Rebuild</button>
      </div>
    </header>

    <aside>
      <h2 class="panel-title">Graph Stats</h2>
      <section class="stat-grid">
        <div class="stat">
          <div id="totalNodes" class="stat-value">0</div>
          <div class="stat-label">Total nodes</div>
        </div>
        <div class="stat">
          <div id="totalEdges" class="stat-value">0</div>
          <div class="stat-label">Total edges</div>
        </div>
      </section>

      <h2 class="panel-title">Top Node Types</h2>
      <div id="nodeTypes" class="list"></div>

      <h2 class="panel-title">Strongest Connections</h2>
      <div id="strongestConnections" class="list"></div>

      <div id="status" class="status">Loading graph...</div>
    </aside>

    <section id="cy" aria-label="Knowledge graph visualization"></section>

    <section class="details">
      <h2 class="panel-title">Node Details</h2>
      <div id="details" class="empty">Click a node to inspect details and connected nodes.</div>
    </section>
  </main>

  <script>
    let graphData = { nodes: [], edges: [] };
    let cy;

    const typeColors = {
      person: "#34d5ff",
      business: "#35f2a0",
      goal: "#ffd166",
      platform: "#ff4fd8",
      content_pillar: "#a78bfa",
      project: "#5eead4",
      task: "#f97316",
      decision: "#ff6b7a",
      topic: "#93c5fd",
      agent: "#c084fc",
      strategy: "#facc15"
    };

    const $ = (id) => document.getElementById(id);

    async function loadGraph(url = "/graph") {
      setStatus("Loading graph...");
      const response = await fetch(url);
      if (!response.ok) throw new Error("Graph request failed");
      graphData = await response.json();
      renderGraph(graphData);
      renderStats(graphData);
      setStatus("Graph loaded");
    }

    async function rebuildGraph() {
      setStatus("Rebuilding graph...");
      const response = await fetch("/graph/rebuild", { method: "POST" });
      if (!response.ok) throw new Error("Graph rebuild failed");
      await loadGraph();
    }

    async function searchGraph() {
      const query = $("search").value.trim();
      if (!query) return loadGraph();
      await loadGraph(`/graph/search?q=${encodeURIComponent(query)}`);
    }

    function renderGraph(data) {
      const nodes = data.nodes.map((node) => ({
        data: {
          id: String(node.id),
          title: node.title,
          type: node.type,
          label: `${node.title}\\n${node.type}`,
          description: node.description || "",
          importance: node.importance || 3
        }
      }));

      const edges = data.edges.map((edge) => ({
        data: {
          id: `e${edge.id}`,
          source: String(edge.source_node_id),
          target: String(edge.target_node_id),
          relationship: edge.relationship_type,
          strength: edge.strength || 1
        }
      }));

      if (cy) cy.destroy();
      cy = cytoscape({
        container: $("cy"),
        elements: [...nodes, ...edges],
        style: [
          {
            selector: "node",
            style: {
              "background-color": (ele) => typeColors[ele.data("type")] || "#34d5ff",
              "border-color": "#e9f7ff",
              "border-width": 1,
              "color": "#e9f7ff",
              "content": "data(label)",
              "font-size": 10,
              "font-weight": 650,
              "height": (ele) => 26 + (ele.data("importance") * 4),
              "label": "data(label)",
              "min-zoomed-font-size": 6,
              "overlay-opacity": 0,
              "shape": "ellipse",
              "text-halign": "center",
              "text-max-width": 120,
              "text-outline-color": "#050816",
              "text-outline-width": 3,
              "text-valign": "center",
              "text-wrap": "wrap",
              "width": (ele) => 26 + (ele.data("importance") * 4)
            }
          },
          {
            selector: "edge",
            style: {
              "curve-style": "bezier",
              "line-color": "rgba(138, 167, 188, 0.48)",
              "target-arrow-color": "rgba(138, 167, 188, 0.72)",
              "target-arrow-shape": "triangle",
              "width": (ele) => Math.max(1, ele.data("strength")),
              "label": "data(relationship)",
              "font-size": 8,
              "color": "#8aa7bc",
              "text-background-color": "#050816",
              "text-background-opacity": 0.75,
              "text-background-padding": 2
            }
          },
          {
            selector: "node:selected",
            style: {
              "border-color": "#35f2a0",
              "border-width": 3,
              "box-shadow": "0 0 24px #35f2a0"
            }
          },
          {
            selector: ".faded",
            style: {
              "opacity": 0.16,
              "text-opacity": 0.05
            }
          },
          {
            selector: ".highlighted",
            style: {
              "line-color": "#35f2a0",
              "target-arrow-color": "#35f2a0",
              "opacity": 1,
              "z-index": 20
            }
          }
        ],
        layout: {
          name: "cose",
          animate: false,
          nodeRepulsion: 9000,
          idealEdgeLength: 120,
          edgeElasticity: 0.2,
          gravity: 0.25,
          numIter: 1200
        },
        wheelSensitivity: 0.16
      });

      cy.on("tap", "node", (event) => showNodeDetails(event.target));
      cy.on("tap", (event) => {
        if (event.target === cy) {
          cy.elements().removeClass("faded highlighted");
          $("details").innerHTML = "Click a node to inspect details and connected nodes.";
          $("details").className = "empty";
        }
      });
    }

    function showNodeDetails(node) {
      cy.elements().addClass("faded");
      node.removeClass("faded");
      const connectedEdges = node.connectedEdges();
      const connectedNodes = connectedEdges.connectedNodes().difference(node);
      connectedEdges.removeClass("faded").addClass("highlighted");
      connectedNodes.removeClass("faded");

      const connected = connectedNodes.map((item) => {
        const edge = connectedEdges.filter((e) => e.connectedNodes().contains(item))[0];
        return `<div class="item"><strong>${escapeHtml(item.data("title"))}</strong><span class="muted">${escapeHtml(item.data("type"))} via ${escapeHtml(edge?.data("relationship") || "related_to")}</span></div>`;
      }).join("") || `<div class="empty">No connected nodes visible in this graph slice.</div>`;

      $("details").className = "";
      $("details").innerHTML = `
        <h3 class="detail-title">${escapeHtml(node.data("title"))}</h3>
        <div class="detail-type">
          <span class="tag">${escapeHtml(node.data("type"))}</span>
          <span class="tag">importance ${escapeHtml(String(node.data("importance")))}</span>
        </div>
        <div class="description">${escapeHtml(node.data("description") || "No description available.")}</div>
        <h2 class="panel-title">Connected Nodes</h2>
        <div class="list">${connected}</div>
      `;
    }

    function renderStats(data) {
      $("totalNodes").textContent = data.nodes.length;
      $("totalEdges").textContent = data.edges.length;

      const typeCounts = data.nodes.reduce((acc, node) => {
        acc[node.type] = (acc[node.type] || 0) + 1;
        return acc;
      }, {});

      $("nodeTypes").innerHTML = Object.entries(typeCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([type, count]) => `<div class="item"><strong>${escapeHtml(type)}</strong><span class="muted">${count} nodes</span></div>`)
        .join("") || `<div class="empty">No node types yet.</div>`;

      const nodeById = new Map(data.nodes.map((node) => [node.id, node]));
      $("strongestConnections").innerHTML = [...data.edges]
        .sort((a, b) => (b.strength || 0) - (a.strength || 0))
        .slice(0, 8)
        .map((edge) => {
          const source = nodeById.get(edge.source_node_id);
          const target = nodeById.get(edge.target_node_id);
          return `<div class="item"><strong>${escapeHtml(source?.title || "Unknown")} -> ${escapeHtml(target?.title || "Unknown")}</strong><span class="muted">${escapeHtml(edge.relationship_type)} | strength ${edge.strength}</span></div>`;
        })
        .join("") || `<div class="empty">No edges yet.</div>`;
    }

    function setStatus(message) {
      $("status").textContent = message;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    $("searchBtn").addEventListener("click", () => searchGraph().catch(showError));
    $("search").addEventListener("keydown", (event) => {
      if (event.key === "Enter") searchGraph().catch(showError);
    });
    $("resetBtn").addEventListener("click", () => {
      $("search").value = "";
      loadGraph().catch(showError);
    });
    $("rebuildBtn").addEventListener("click", () => rebuildGraph().catch(showError));

    function showError(error) {
      console.error(error);
      setStatus(`Error: ${error.message}`);
    }

    loadGraph().catch(showError);
  </script>
</body>
</html>
"""
