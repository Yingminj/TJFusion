            const GROUP_ORDER = ["vision", "inference", "action", "ungrouped"];
            let selectedDocker = null;
            let selectedBridge = null;
            let launcherConfigDirty = false;
            let dockerConnectionDirty = false;
            let bridgeConfigDirty = false;
            let dockerServiceConfigDirty = false;
            let lastStatusPayload = null;
            let activeWindow = "docker";
            let statusRefreshInFlight = false;
            let dockerLogsRefreshInFlight = false;
            let bridgeLogsRefreshInFlight = false;
            let bridgeGraphState = null;
            let bridgeGraphRenderQueued = false;
            let bridgeGraphEventsReady = false;

            function escapeHtml(value) {
              return String(value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
            }

            function formatTime(value) {
              const date = new Date(value);
              if (Number.isNaN(date.getTime())) {
                return value;
              }
              return date.toLocaleString();
            }

            // Auth token (only needed when the dashboard is exposed on a
            // non-loopback host). Read once from the URL query string and reused
            // for every request via the X-Auth-Token header.
            const AUTH_TOKEN = new URLSearchParams(window.location.search).get("token") || "";

            function authHeaders(extra) {
              const headers = Object.assign({}, extra || {});
              if (AUTH_TOKEN) {
                headers["X-Auth-Token"] = AUTH_TOKEN;
              }
              return headers;
            }

            async function fetchJson(url) {
              const response = await fetch(url, { cache: "no-store", headers: authHeaders() });
              const payload = await response.json();
              if (!response.ok) {
                throw new Error(payload.error || "Request failed");
              }
              return payload;
            }

            async function postJson(url, payload) {
              const response = await fetch(url, {
                method: "POST",
                headers: authHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify(payload),
              });
              const body = await response.json();
              if (!response.ok) {
                const requestError = new Error(body.error || body.message || "Request failed");
                requestError.payload = body;
                throw requestError;
              }
              return body;
            }

            function prettyJson(value) {
              if (value === null || value === undefined) {
                return "";
              }
              if (typeof value === "string") {
                return value;
              }
              try {
                return JSON.stringify(value, null, 2);
              } catch (error) {
                return String(value);
              }
            }

            function stripYamlComment(value) {
              let inSingle = false;
              let inDouble = false;
              for (let i = 0; i < value.length; i += 1) {
                const char = value[i];
                if (char === "'" && !inDouble) {
                  inSingle = !inSingle;
                } else if (char === '"' && !inSingle) {
                  inDouble = !inDouble;
                } else if (char === "#" && !inSingle && !inDouble) {
                  return value.slice(0, i);
                }
              }
              return value;
            }

            function cleanYamlValue(value) {
              const trimmed = String(value || "").trim();
              if (!trimmed) {
                return "";
              }
              if (
                (trimmed.startsWith("'") && trimmed.endsWith("'"))
                || (trimmed.startsWith('"') && trimmed.endsWith('"'))
              ) {
                return trimmed.slice(1, -1);
              }
              return trimmed;
            }

            function parseInlineList(value) {
              if (value === null || value === undefined) {
                return null;
              }
              const trimmed = String(value).trim();
              if (!trimmed) {
                return null;
              }
              if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
                const inner = trimmed.slice(1, -1).trim();
                if (!inner) {
                  return [];
                }
                return inner
                  .split(",")
                  .map((item) => cleanYamlValue(item))
                  .filter(Boolean);
              }
              return [cleanYamlValue(trimmed)];
            }

            function uniqueList(values) {
              return Array.from(
                new Set(
                  (values || [])
                    .map((item) => String(item || "").trim())
                    .filter(Boolean),
                ),
              );
            }

            function parsePipelineSteps(yamlText) {
              const steps = [];
              const warnings = [];
              if (!yamlText || typeof yamlText !== "string") {
                return { steps, warnings };
              }

              const lines = yamlText.split(/\r?\n/);
              let inPipeline = false;
              let pipelineIndent = 0;
              let current = null;
              let listIndent = 0;
              let expectName = false;
              let activeList = null;
              let activeListIndent = 0;
              let inResponseMap = false;
              let responseMapIndent = 0;

              const pushCurrent = () => {
                if (current) {
                  current.inputs = uniqueList(current.inputs);
                  current.outputs = uniqueList(current.outputs);
                  current.dependsOn = uniqueList(current.dependsOn);
                  steps.push(current);
                }
              };

              for (const rawLine of lines) {
                const lineNoComment = stripYamlComment(rawLine);
                if (!lineNoComment.trim()) {
                  continue;
                }
                const indentMatch = lineNoComment.match(/^\s*/);
                const indent = indentMatch ? indentMatch[0].length : 0;
                const trimmed = lineNoComment.trim();

                if (!inPipeline) {
                  if (/^pipeline\s*:/.test(trimmed)) {
                    inPipeline = true;
                    pipelineIndent = indent;
                  }
                  continue;
                }

                if (indent <= pipelineIndent && !trimmed.startsWith("-")) {
                  inPipeline = false;
                  continue;
                }

                const nameInlineMatch = trimmed.match(/^-\s*name\s*:\s*(.+)$/);
                if (nameInlineMatch) {
                  pushCurrent();
                  current = {
                    name: cleanYamlValue(nameInlineMatch[1]),
                    inputs: [],
                    outputs: [],
                    dependsOn: [],
                  };
                  listIndent = indent;
                  expectName = false;
                  activeList = null;
                  inResponseMap = false;
                  continue;
                }

                if (trimmed === "-") {
                  pushCurrent();
                  current = {
                    name: "",
                    inputs: [],
                    outputs: [],
                    dependsOn: [],
                  };
                  listIndent = indent;
                  expectName = true;
                  activeList = null;
                  inResponseMap = false;
                  continue;
                }

                if (!current) {
                  continue;
                }

                if (expectName && indent > listIndent) {
                  const nameMatch = trimmed.match(/^name\s*:\s*(.+)$/);
                  if (nameMatch) {
                    current.name = cleanYamlValue(nameMatch[1]);
                    expectName = false;
                    continue;
                  }
                }

                if (activeList && indent <= activeListIndent) {
                  activeList = null;
                }
                if (inResponseMap && indent <= responseMapIndent) {
                  inResponseMap = false;
                }

                if (!activeList && !inResponseMap) {
                  const listMatch = trimmed.match(/^(depends_on|inputs|outputs)\s*:\s*(.*)$/);
                  if (listMatch) {
                    const listName = listMatch[1];
                    const listValue = listMatch[2] || "";
                    const inlineItems = parseInlineList(listValue);
                    if (inlineItems !== null) {
                      if (listName === "depends_on") {
                        current.dependsOn.push(...inlineItems);
                      } else if (listName === "inputs") {
                        current.inputs.push(...inlineItems);
                      } else if (listName === "outputs") {
                        current.outputs.push(...inlineItems);
                      }
                    } else {
                      activeList = listName;
                      activeListIndent = indent;
                    }
                    continue;
                  }

                  if (trimmed.startsWith("response_map:")) {
                    inResponseMap = true;
                    responseMapIndent = indent;
                    continue;
                  }
                }

                if (activeList) {
                  const itemMatch = trimmed.match(/^-+\s*(.+)$/);
                  if (itemMatch) {
                    const value = cleanYamlValue(itemMatch[1]);
                    if (activeList === "depends_on") {
                      current.dependsOn.push(value);
                    } else if (activeList === "inputs") {
                      current.inputs.push(value);
                    } else if (activeList === "outputs") {
                      current.outputs.push(value);
                    }
                  }
                  continue;
                }

                if (inResponseMap) {
                  const keyMatch = trimmed.match(/^([A-Za-z0-9_.-]+)\s*:/);
                  if (keyMatch) {
                    current.outputs.push(cleanYamlValue(keyMatch[1]));
                  }
                }
              }

              if (current) {
                pushCurrent();
              }

              if (!steps.length) {
                warnings.push("pipeline not found");
              }

              return { steps, warnings };
            }

            function buildBridgePipelineGraph(yamlText) {
              const parsed = parsePipelineSteps(yamlText);
              const nodes = [];
              const edges = [];
              const warnings = [...parsed.warnings];
              const nameCounts = new Map();
              const baseToId = new Map();

              parsed.steps.forEach((step, index) => {
                const baseName = step.name || `step-${index + 1}`;
                const count = (nameCounts.get(baseName) || 0) + 1;
                nameCounts.set(baseName, count);
                const id = count === 1 ? baseName : `${baseName}-${count}`;
                if (count > 1) {
                  warnings.push(`duplicate name ${baseName}`);
                }
                if (!baseToId.has(baseName)) {
                  baseToId.set(baseName, id);
                }
                nodes.push({
                  id,
                  baseName,
                  displayName: id,
                  inputs: uniqueList(step.inputs),
                  outputs: uniqueList(step.outputs),
                  dependsOn: uniqueList(step.dependsOn),
                  dependsOnIds: [],
                  missingDeps: [],
                });
              });

              const nodeById = new Map(nodes.map((node) => [node.id, node]));
              for (const node of nodes) {
                for (const depName of node.dependsOn) {
                  const depId = baseToId.get(depName);
                  if (depId && nodeById.has(depId)) {
                    node.dependsOnIds.push(depId);
                    edges.push({ from: depId, to: node.id });
                  } else if (depName) {
                    node.missingDeps.push(depName);
                  }
                }
              }

              if (nodes.some((node) => node.missingDeps.length)) {
                warnings.push("missing depends_on");
              }

              const depth = new Map();
              const visiting = new Set();
              const cycleNodes = new Set();

              function visit(node) {
                if (depth.has(node.id)) {
                  return depth.get(node.id);
                }
                if (visiting.has(node.id)) {
                  cycleNodes.add(node.id);
                  return 0;
                }
                visiting.add(node.id);
                let maxDepth = -1;
                for (const depId of node.dependsOnIds) {
                  const depNode = nodeById.get(depId);
                  if (depNode) {
                    maxDepth = Math.max(maxDepth, visit(depNode));
                  }
                }
                visiting.delete(node.id);
                const nodeDepth = maxDepth + 1;
                depth.set(node.id, nodeDepth);
                return nodeDepth;
              }

              for (const node of nodes) {
                visit(node);
              }

              if (cycleNodes.size) {
                warnings.push("cycle detected");
              }

              const maxDepth = nodes.length
                ? Math.max(...Array.from(depth.values()))
                : 0;
              const layers = Array.from({ length: maxDepth + 1 }, () => []);
              for (const node of nodes) {
                const layerIndex = depth.get(node.id) || 0;
                layers[layerIndex].push(node);
              }
              for (const layer of layers) {
                layer.sort((a, b) => a.displayName.localeCompare(b.displayName));
              }

              return { nodes, edges, warnings, layers };
            }

            function setBridgeGraphStatus(message) {
              const statusNode = document.getElementById("bridge-graph-status");
              if (statusNode) {
                statusNode.textContent = message;
              }
            }

            function clearBridgePipelineGraph(message) {
              const nodesRoot = document.getElementById("bridge-graph-nodes");
              const lines = document.getElementById("bridge-graph-lines");
              if (nodesRoot) {
                nodesRoot.innerHTML = `<div class="graph-empty">${escapeHtml(message)}</div>`;
              }
              if (lines) {
                lines.innerHTML = "";
              }
              bridgeGraphState = null;
              setBridgeGraphStatus(message);
            }

            function renderBridgePipelineGraph(yamlText) {
              const nodesRoot = document.getElementById("bridge-graph-nodes");
              const lines = document.getElementById("bridge-graph-lines");
              const body = document.getElementById("bridge-graph-body");
              if (!nodesRoot || !lines || !body) {
                return;
              }
              if (!yamlText) {
                clearBridgePipelineGraph("No config loaded.");
                return;
              }

              const model = buildBridgePipelineGraph(yamlText);
              if (!model.nodes.length) {
                clearBridgePipelineGraph("No pipeline found.");
                return;
              }

              const columnCount = model.layers.length || 1;
              nodesRoot.style.gridTemplateColumns = `repeat(${columnCount}, minmax(220px, 1fr))`;
              nodesRoot.innerHTML = "";

              for (const layer of model.layers) {
                const column = document.createElement("div");
                column.className = "graph-column";
                for (const node of layer) {
                  const card = document.createElement("div");
                  card.className = "graph-node";
                  card.dataset.nodeId = node.id;
                  const inputsLabel = node.inputs.length ? node.inputs.join(", ") : "none";
                  const outputsLabel = node.outputs.length ? node.outputs.join(", ") : "none";
                  const missingDeps = node.missingDeps.length
                    ? `missing: ${node.missingDeps.join(", ")}`
                    : "";
                  card.innerHTML = `
                    <div class="graph-node-title">${escapeHtml(node.displayName)}</div>
                    <div class="graph-node-meta">
                      <span>inputs: ${escapeHtml(inputsLabel)}</span>
                      <span>outputs: ${escapeHtml(outputsLabel)}</span>
                      ${missingDeps ? `<span class="graph-node-warning">${escapeHtml(missingDeps)}</span>` : ""}
                    </div>
                  `;
                  column.appendChild(card);
                }
                nodesRoot.appendChild(column);
              }

              const summary = `nodes: ${model.nodes.length} | edges: ${model.edges.length}`;
              const statusMessage = model.warnings.length
                ? `${summary} | ${model.warnings[0]}`
                : summary;
              setBridgeGraphStatus(statusMessage);

              bridgeGraphState = model;
              scheduleBridgeGraphRedraw();
            }

            function drawBridgePipelineEdges() {
              if (!bridgeGraphState || !bridgeGraphState.edges) {
                return;
              }
              const body = document.getElementById("bridge-graph-body");
              const svg = document.getElementById("bridge-graph-lines");
              if (!body || !svg) {
                return;
              }

              const bodyRect = body.getBoundingClientRect();
              const scrollLeft = body.scrollLeft;
              const scrollTop = body.scrollTop;
              const width = Math.max(body.scrollWidth, body.clientWidth);
              const height = Math.max(body.scrollHeight, body.clientHeight);

              svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
              svg.setAttribute("width", `${width}`);
              svg.setAttribute("height", `${height}`);
              svg.innerHTML = "";

              for (const edge of bridgeGraphState.edges) {
                const fromNode = document.querySelector(`[data-node-id="${edge.from}"]`);
                const toNode = document.querySelector(`[data-node-id="${edge.to}"]`);
                if (!fromNode || !toNode) {
                  continue;
                }

                const fromRect = fromNode.getBoundingClientRect();
                const toRect = toNode.getBoundingClientRect();
                const startX = fromRect.right - bodyRect.left + scrollLeft;
                const startY = fromRect.top + fromRect.height / 2 - bodyRect.top + scrollTop;
                const endX = toRect.left - bodyRect.left + scrollLeft;
                const endY = toRect.top + toRect.height / 2 - bodyRect.top + scrollTop;
                const offset = Math.max(40, (endX - startX) * 0.35);

                const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                path.setAttribute(
                  "d",
                  `M ${startX} ${startY} C ${startX + offset} ${startY}, ${endX - offset} ${endY}, ${endX} ${endY}`,
                );
                svg.appendChild(path);
              }
            }

            function scheduleBridgeGraphRedraw() {
              if (bridgeGraphRenderQueued) {
                return;
              }
              bridgeGraphRenderQueued = true;
              requestAnimationFrame(() => {
                bridgeGraphRenderQueued = false;
                drawBridgePipelineEdges();
              });
            }

            function initBridgeGraphEvents() {
              if (bridgeGraphEventsReady) {
                return;
              }
              const body = document.getElementById("bridge-graph-body");
              if (body) {
                body.addEventListener("scroll", () => scheduleBridgeGraphRedraw());
              }
              window.addEventListener("resize", () => scheduleBridgeGraphRedraw());
              bridgeGraphEventsReady = true;
            }

            function groupDockers(dockers) {
              const groups = new Map();
              for (const groupName of GROUP_ORDER) {
                groups.set(groupName, []);
              }
              for (const docker of dockers) {
                const groupName = docker.group || "ungrouped";
                if (!groups.has(groupName)) {
                  groups.set(groupName, []);
                }
                groups.get(groupName).push(docker);
              }
              return groups;
            }

            function statusClass(status) {
              if (status === "running") {
                return "status-running";
              }
              if (status === "error") {
                return "status-error";
              }
              if (status === "ended" || status === "stopped") {
                return "status-ended";
              }
              return "status-unknown";
            }

            function findDocker(name) {
              if (!lastStatusPayload || !lastStatusPayload.dockers) {
                return null;
              }
              return lastStatusPayload.dockers.find((item) => item.name === name) || null;
            }

            function findBridge(name) {
              if (!lastStatusPayload || !lastStatusPayload.bridges) {
                return null;
              }
              return lastStatusPayload.bridges.find((item) => item.name === name) || null;
            }

            function updateMetrics(summary) {
              document.getElementById("metric-total").textContent = String(summary.total || 0);
              document.getElementById("metric-running").textContent = String(summary.running || 0);
              document.getElementById("metric-error").textContent = String(summary.error || 0);
              document.getElementById("metric-ended").textContent = String(summary.ended || 0);
            }

            function setLauncherConfigDirty(isDirty) {
              launcherConfigDirty = Boolean(isDirty);
              document.getElementById("launcher-config-editor").classList.toggle("dirty", launcherConfigDirty);
              const cards = document.getElementById("launcher-cards");
              if (cards) {
                cards.classList.toggle("dirty", launcherConfigDirty);
              }
            }

            function markLauncherConfigDirty() {
              setLauncherConfigDirty(true);
              document.getElementById("launcher-config-status").textContent =
                "Unsaved launcher changes. Save Config to write docker_launch.yaml, or Reload to discard.";
            }

            function updateLauncherConfigControls(enabled) {
              for (const nodeId of [
                "launcher-config-editor",
                "launcher-config-reload",
                "launcher-config-restart",
                "launcher-config-save",
                "launcher-config-save-restart",
                "launcher-advanced-save",
                "launcher-advanced-save-restart",
                "lc-docker-root",
                "lc-tmux",
                "lc-monitor",
                "lc-replace",
                "lc-poll",
                "lc-add-target-select",
                "lc-add-bridge",
              ]) {
                const node = document.getElementById(nodeId);
                if (node) {
                  node.disabled = !enabled;
                }
              }
            }

            function buildTargetRow(target) {
              const row = document.createElement("div");
              row.className = "lc-target-row";
              row.dataset.name = target.name;
              // Location defaults to local; remote details are managed in the
              // Docker Connection panel, so we only round-trip the value here.
              row.dataset.location = target.location === "remote" ? "remote" : "local";

              const check = document.createElement("input");
              check.type = "checkbox";
              check.className = "lc-target-enabled";
              check.checked = target.enabled !== false;
              check.title = "Enable (launch) this docker";
              check.addEventListener("change", markLauncherConfigDirty);

              const nameLabel = document.createElement("label");
              nameLabel.className = "lc-target-name";
              nameLabel.appendChild(check);
              const nameText = document.createElement("span");
              nameText.textContent = target.name;
              nameLabel.appendChild(nameText);
              if (row.dataset.location === "remote") {
                const badge = document.createElement("span");
                badge.className = "lc-remote-badge";
                badge.textContent = "remote";
                badge.title = "Runs remotely — edit host details in the Docker Connection panel";
                nameLabel.appendChild(badge);
              }

              const group = document.createElement("input");
              group.type = "text";
              group.className = "lc-target-group";
              group.value = target.group || "ungrouped";
              group.title = "Group";
              group.addEventListener("input", markLauncherConfigDirty);

              const remove = document.createElement("button");
              remove.type = "button";
              remove.className = "lc-row-remove";
              remove.textContent = "✕";
              remove.title = "Remove from catalog";
              remove.addEventListener("click", () => {
                row.remove();
                addTargetSelectOption(target.name);
                markLauncherConfigDirty();
              });

              row.appendChild(nameLabel);
              row.appendChild(group);
              row.appendChild(remove);
              return row;
            }

            function addTargetSelectOption(name) {
              const select = document.getElementById("lc-add-target-select");
              if (!select || !name) {
                return;
              }
              const exists = Array.from(select.options).some((opt) => opt.value === name);
              if (!exists) {
                const option = document.createElement("option");
                option.value = name;
                option.textContent = name;
                select.appendChild(option);
              }
            }

            function buildBridgeRow(bridge) {
              const row = document.createElement("div");
              row.className = "lc-bridge-row";

              const nameField = document.createElement("input");
              nameField.type = "text";
              nameField.className = "lc-bridge-name";
              nameField.value = bridge.name || "";
              nameField.placeholder = "Bridge name";
              nameField.addEventListener("input", markLauncherConfigDirty);

              const enabledLabel = document.createElement("label");
              enabledLabel.className = "lc-check";
              const enabled = document.createElement("input");
              enabled.type = "checkbox";
              enabled.className = "lc-bridge-enabled";
              enabled.checked = bridge.enabled !== false;
              enabled.addEventListener("change", markLauncherConfigDirty);
              enabledLabel.appendChild(enabled);
              const enabledText = document.createElement("span");
              enabledText.textContent = "Enabled";
              enabledLabel.appendChild(enabledText);

              const configField = document.createElement("input");
              configField.type = "text";
              configField.className = "lc-bridge-config";
              configField.value = bridge.config || "";
              configField.placeholder = "configs/bridge.example.yaml";
              configField.addEventListener("input", markLauncherConfigDirty);

              const remove = document.createElement("button");
              remove.type = "button";
              remove.className = "lc-row-remove";
              remove.textContent = "✕";
              remove.title = "Remove bridge";
              remove.addEventListener("click", () => {
                row.remove();
                markLauncherConfigDirty();
              });

              row.appendChild(nameField);
              row.appendChild(enabledLabel);
              row.appendChild(configField);
              row.appendChild(remove);
              return row;
            }

            function renderLauncherStructured(structured) {
              const rootInput = document.getElementById("lc-docker-root");
              const targetList = document.getElementById("lc-target-list");
              const bridgeList = document.getElementById("lc-bridge-list");
              const addSelect = document.getElementById("lc-add-target-select");
              const countNode = document.getElementById("lc-targets-count");

              if (!structured || !structured.available) {
                rootInput.value = "";
                document.getElementById("lc-tmux").checked = true;
                document.getElementById("lc-monitor").checked = true;
                document.getElementById("lc-replace").checked = false;
                document.getElementById("lc-poll").value = "0.5";
                targetList.innerHTML = '<div class="lc-empty">No launcher config yet. Save to create one.</div>';
                bridgeList.innerHTML = "";
                addSelect.innerHTML = '<option value="">+ Add Docker Target…</option>';
                countNode.textContent = "";
                return;
              }

              rootInput.value = structured.docker_model_root || "";
              document.getElementById("lc-tmux").checked = structured.tmux !== false;
              document.getElementById("lc-monitor").checked = structured.monitor !== false;
              document.getElementById("lc-replace").checked = Boolean(structured.replace_session);
              document.getElementById("lc-poll").value =
                structured.poll_interval != null ? structured.poll_interval : 0.5;

              const targets = Array.isArray(structured.docker_targets) ? structured.docker_targets : [];
              targetList.innerHTML = "";
              if (targets.length === 0) {
                targetList.innerHTML = '<div class="lc-empty">No docker targets defined yet.</div>';
              } else {
                for (const target of targets) {
                  targetList.appendChild(buildTargetRow(target));
                }
              }
              const enabledCount = targets.filter((t) => t.enabled !== false).length;
              countNode.textContent = `${enabledCount}/${targets.length} active`;

              const bridges = Array.isArray(structured.bridges) ? structured.bridges : [];
              bridgeList.innerHTML = "";
              for (const bridge of bridges) {
                bridgeList.appendChild(buildBridgeRow(bridge));
              }

              addSelect.innerHTML = '<option value="">+ Add Docker Target…</option>';
              const available = Array.isArray(structured.available_dockers)
                ? structured.available_dockers
                : [];
              for (const name of available) {
                addTargetSelectOption(name);
              }
            }

            function collectLauncherStructured() {
              const pollRaw = document.getElementById("lc-poll").value;
              const pollValue = Number.parseFloat(pollRaw);
              const targets = [];
              for (const row of document.querySelectorAll("#lc-target-list .lc-target-row")) {
                targets.push({
                  name: row.dataset.name,
                  group: (row.querySelector(".lc-target-group").value || "ungrouped").trim() || "ungrouped",
                  location: row.dataset.location || "local",
                  enabled: row.querySelector(".lc-target-enabled").checked,
                });
              }
              const bridges = [];
              for (const row of document.querySelectorAll("#lc-bridge-list .lc-bridge-row")) {
                bridges.push({
                  name: (row.querySelector(".lc-bridge-name").value || "").trim(),
                  enabled: row.querySelector(".lc-bridge-enabled").checked,
                  config: (row.querySelector(".lc-bridge-config").value || "").trim(),
                });
              }
              return {
                docker_model_root: document.getElementById("lc-docker-root").value.trim(),
                tmux: document.getElementById("lc-tmux").checked,
                monitor: document.getElementById("lc-monitor").checked,
                replace_session: document.getElementById("lc-replace").checked,
                poll_interval: Number.isFinite(pollValue) ? pollValue : 0.5,
                docker_targets: targets,
                bridges,
              };
            }

            function setDockerConnectionDirty(isDirty) {
              dockerConnectionDirty = Boolean(isDirty);
            }

            function updateDockerConnectionControls(enabled) {
              for (const nodeId of [
                "docker-conn-location",
                "docker-conn-root",
                "docker-conn-remote-host",
                "docker-conn-remote-user",
                "docker-conn-remote-root",
                "docker-conn-remote-port",
                "docker-conn-remote-password",
                "docker-connection-reload",
                "docker-connection-save",
              ]) {
                const node = document.getElementById(nodeId);
                if (node) {
                  node.disabled = !enabled;
                }
              }
            }

            function updateDockerConnectionVisibility() {
              const location = document.getElementById("docker-conn-location").value || "local";
              const isRemote = location === "remote";
              const controlsEnabled = !document.getElementById("docker-conn-location").disabled;
              for (const nodeId of [
                "docker-conn-remote-host-wrap",
                "docker-conn-remote-user-wrap",
                "docker-conn-remote-root-wrap",
                "docker-conn-remote-port-wrap",
                "docker-conn-remote-password-wrap",
              ]) {
                document.getElementById(nodeId).classList.toggle("hidden", !isRemote);
              }
              document.getElementById("docker-conn-root").disabled = !controlsEnabled || isRemote;
            }

            function renderDockerConnection(docker, force = false) {
              const statusNode = document.getElementById("docker-connection-status");
              const locationNode = document.getElementById("docker-conn-location");
              const rootNode = document.getElementById("docker-conn-root");
              const remoteHostNode = document.getElementById("docker-conn-remote-host");
              const remoteUserNode = document.getElementById("docker-conn-remote-user");
              const remoteRootNode = document.getElementById("docker-conn-remote-root");
              const remotePortNode = document.getElementById("docker-conn-remote-port");
              const remotePasswordNode = document.getElementById("docker-conn-remote-password");

              if (!docker) {
                locationNode.value = "local";
                rootNode.value = "";
                remoteHostNode.value = "";
                remoteUserNode.value = "";
                remoteRootNode.value = "";
                remotePortNode.value = "22";
                remotePasswordNode.value = "";
                remotePasswordNode.placeholder = "Leave blank to keep saved password";
                locationNode.dataset.loadedName = "";
                statusNode.textContent = "Select a docker to edit localhost/remote launch mapping.";
                setDockerConnectionDirty(false);
                updateDockerConnectionControls(false);
                updateDockerConnectionVisibility();
                return;
              }

              const loadedName = locationNode.dataset.loadedName || "";
              const switchedDocker = loadedName !== docker.name;
              if (force || switchedDocker || !dockerConnectionDirty) {
                locationNode.value = docker.location || "local";
                rootNode.value = docker.docker_model_root || "";
                remoteHostNode.value = docker.remote_host || "";
                remoteUserNode.value = docker.remote_user || "";
                remoteRootNode.value = docker.remote_docker_model_root || "";
                remotePortNode.value = String(docker.remote_ssh_port || 22);
                remotePasswordNode.value = "";
                remotePasswordNode.placeholder = docker.remote_password_set
                  ? "Saved (leave blank to keep current password)"
                  : "Optional: enter SSH password";
                locationNode.dataset.loadedName = docker.name;
                setDockerConnectionDirty(false);
              }

              updateDockerConnectionControls(true);
              updateDockerConnectionVisibility();

              if (dockerConnectionDirty && !force && !switchedDocker) {
                statusNode.textContent = `Unsaved connection changes for ${docker.name}. Save to apply local/remote mapping.`;
                return;
              }

              const locationLabel = locationNode.value === "remote" ? "REMOTE" : "LOCALHOST";
              let passwordState = "";
              if (locationNode.value === "remote") {
                passwordState = docker.remote_password_set ? " | ssh-password=saved" : " | ssh-password=empty";
              }
              statusNode.textContent = `${docker.name} | ${locationLabel} | group=${docker.group}${passwordState}`;
            }

            function setDockerServiceConfigDirty(isDirty) {
              dockerServiceConfigDirty = Boolean(isDirty);
            }

            function updateDockerServiceConfigControls(enabled) {
              for (const nodeId of [
                "docker-service-container-name",
                "docker-service-host",
                "docker-service-port",
                "docker-service-config-reload",
                "docker-service-config-save",
                "docker-service-config-save-restart",
              ]) {
                const node = document.getElementById(nodeId);
                if (node) {
                  node.disabled = !enabled;
                }
              }
            }

            function renderDockerServiceConfig(payload, resetDraft = false) {
              const statusNode = document.getElementById("docker-service-config-status");
              const pathNode = document.getElementById("docker-service-config-path");
              const containerNode = document.getElementById("docker-service-container-name");
              const hostNode = document.getElementById("docker-service-host");
              const portNode = document.getElementById("docker-service-port");

              if (!payload) {
                pathNode.value = "";
                containerNode.value = "";
                hostNode.value = "";
                portNode.value = "";
                pathNode.dataset.loadedName = "";
                setDockerServiceConfigDirty(false);
                updateDockerServiceConfigControls(false);
                statusNode.textContent = "Select docker to load docker/server yaml config.";
                return;
              }

              const loadedName = pathNode.dataset.loadedName || "";
              const switchedDocker = loadedName !== payload.name;
              if (resetDraft || switchedDocker || !dockerServiceConfigDirty) {
                pathNode.value = payload.config_path || "";
                containerNode.value = payload.container_name || "";
                hostNode.value = payload.host || "192.168.1.61";
                portNode.value = payload.port !== null && payload.port !== undefined ? String(payload.port) : "";
                pathNode.dataset.loadedName = payload.name || "";
                setDockerServiceConfigDirty(false);
              }

              updateDockerServiceConfigControls(true);
              if (dockerServiceConfigDirty && !resetDraft && !switchedDocker) {
                statusNode.textContent = `Unsaved service config changes for ${payload.name}. Save to write YAML updates.`;
                return;
              }

              const updatedLabel = payload.updated_at ? formatTime(payload.updated_at) : "just now";
              statusNode.textContent = `${payload.name} | ${payload.location} | loaded ${updatedLabel}`;
              statusNode.title = payload.config_path || "";
            }

            async function refreshDockerServiceConfig(resetDraft = false) {
              if (!selectedDocker) {
                renderDockerServiceConfig(null, true);
                return;
              }
              try {
                const payload = await fetchJson(`/api/docker/service-config?name=${encodeURIComponent(selectedDocker)}`);
                renderDockerServiceConfig(payload, resetDraft);
              } catch (error) {
                renderDockerServiceConfig(null, true);
                document.getElementById("docker-service-config-status").textContent = error.message;
              }
            }

            async function saveDockerServiceConfig(restart = false) {
              if (!selectedDocker) {
                showActionBanner("Please select a docker first.", true);
                return;
              }

              const containerName = document.getElementById("docker-service-container-name").value.trim();
              const host = document.getElementById("docker-service-host").value.trim();
              const portText = document.getElementById("docker-service-port").value.trim();
              const port = Number(portText);

              if (!host) {
                showActionBanner("Service host cannot be empty.", true);
                return;
              }
              if (!Number.isInteger(port) || port <= 0 || port > 65535) {
                showActionBanner("Service port must be between 1 and 65535.", true);
                return;
              }

              try {
                const response = await postJson("/api/docker/service-config", {
                  name: selectedDocker,
                  container_name: containerName || null,
                  host,
                  port,
                  restart,
                });
                showActionBanner(response.message || "Service config saved.");
                setDockerServiceConfigDirty(false);
                renderDockerServiceConfig(response.config || null, true);
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                if (selectedDocker) {
                  await refreshLogs(true);
                  await refreshDockerServiceConfig(false);
                }
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            function reloadDockerServiceConfig() {
              refreshDockerServiceConfig(true);
            }

            function renderLauncherConfig(payload, resetDraft = false) {
              const editor = document.getElementById("launcher-config-editor");
              const statusNode = document.getElementById("launcher-config-status");

              if (!payload) {
                editor.value = "";
                renderLauncherStructured(null);
                setLauncherConfigDirty(false);
                updateLauncherConfigControls(false);
                statusNode.textContent = "Launcher config is unavailable.";
                return;
              }

              // A single dirty flag governs both editors (form + Advanced YAML);
              // skip clobbering either when the user has unsaved edits.
              if (resetDraft || !launcherConfigDirty) {
                editor.value = payload.content || "";
                renderLauncherStructured(payload.structured || null);
                setLauncherConfigDirty(false);
              }

              updateLauncherConfigControls(true);
              if (launcherConfigDirty && !resetDraft) {
                statusNode.textContent =
                  "Unsaved launcher changes. Save Config to write docker_launch.yaml, or Reload to discard.";
                return;
              }

              const configPath = payload.config_path || "config path will be created on first save";
              const updatedLabel = payload.updated_at ? formatTime(payload.updated_at) : "just now";
              const dockerRoot = payload.docker_model_root || "inherit current DockerModel root";
              const dockerCount = Number(payload.docker_count || 0);
              const bridgeCount = Number(payload.bridge_count || 0);
              statusNode.textContent =
                `${String(payload.status || "unknown").toUpperCase()} | ${dockerCount} docker(s) | ${bridgeCount} bridge(s) | loaded ${updatedLabel}`;
              statusNode.title =
                `${configPath}
root=${dockerRoot}
${payload.message || "Launcher config is ready."}`;
            }

            function updateBridgeButtons(bridge) {
              const startButtons = [document.getElementById("bridge-start-main")];
              const restartButtons = [document.getElementById("bridge-restart-main")];
              const stopButtons = [document.getElementById("bridge-stop-main")];
              const status = bridge && bridge.status ? bridge.status : "disabled";
              const enabled = Boolean(bridge && bridge.enabled);

              for (const button of startButtons) {
                button.disabled = !enabled || status === "running" || status === "unavailable";
              }
              for (const button of restartButtons) {
                button.disabled = !enabled || status === "unavailable";
              }
              for (const button of stopButtons) {
                button.disabled = !enabled || ["disabled", "stopped", "unavailable"].includes(status);
              }
            }

            function setBridgeConfigDirty(isDirty) {
              bridgeConfigDirty = Boolean(isDirty);
              document.getElementById("bridge-config-editor").classList.toggle("dirty", bridgeConfigDirty);
            }

            function updateBridgeConfigControls(enabled) {
              for (const nodeId of [
                "bridge-config-editor",
                "bridge-config-reload",
                "bridge-config-save",
                "bridge-config-save-restart",
              ]) {
                document.getElementById(nodeId).disabled = !enabled;
              }
            }

            function renderBridgeConfig(payload, resetDraft = false) {
              const editor = document.getElementById("bridge-config-editor");
              const statusNode = document.getElementById("bridge-config-status");

              if (!payload) {
                editor.value = "";
                editor.dataset.bridgeName = "";
                statusNode.textContent = "Select a bridge to load and edit its YAML config.";
                setBridgeConfigDirty(false);
                updateBridgeConfigControls(false);
                clearBridgePipelineGraph("Select a bridge to view pipeline.");
                return;
              }

              const loadedName = editor.dataset.bridgeName || "";
              const switchedBridge = loadedName !== (payload.name || "");
              if (resetDraft || switchedBridge || !bridgeConfigDirty) {
                editor.value = payload.content || "";
                editor.dataset.bridgeName = payload.name || "";
                setBridgeConfigDirty(false);
              }

              updateBridgeConfigControls(true);
              if (bridgeConfigDirty && !resetDraft && !switchedBridge) {
                statusNode.textContent = `Unsaved changes for ${payload.name}. Save to write the YAML or reload to discard your draft.`;
                setBridgeGraphStatus("Draft changed. Reload or save to update graph.");
                return;
              }

              const configPath = payload.config_path || "config path will be created on first save";
              const updatedLabel = payload.updated_at ? formatTime(payload.updated_at) : "just now";
              const bridgeStatus = payload.status || "unknown";
              const runtimeMessage = payload.message || "Bridge config is ready to edit.";
              statusNode.textContent = `${bridgeStatus.toUpperCase()} | loaded ${updatedLabel}`;
              statusNode.title = `${configPath}
${runtimeMessage}`;
              renderBridgePipelineGraph(editor.value);
            }

            function applyTruncateText(nodeId, value, fallback = "-") {
              const node = document.getElementById(nodeId);
              const text = value && String(value).trim() ? String(value) : fallback;
              node.textContent = text;
              node.title = text;
            }

            function renderBridge(bridge) {
              const payload = bridge || {
                name: "Bridge Service",
                enabled: false,
                status: "disabled",
                endpoint: "unconfigured",
                config_path: "",
                log_path: "",
                message: "Bridge control is not configured.",
              };

              document.getElementById("bridge-view-name").textContent = payload.name || "Bridge Console";
              document.getElementById("bridge-view-status-chip").className = `status-chip ${statusClass(payload.status)}`;
              document.getElementById("bridge-view-status-chip").textContent = payload.status;
              applyTruncateText("bridge-view-endpoint", payload.endpoint || "unconfigured", "unconfigured");
              applyTruncateText("bridge-view-config", payload.config_path || "not loaded", "not loaded");
              applyTruncateText("bridge-view-log-path", payload.log_path || "not available", "not available");
              applyTruncateText("bridge-view-runtime", payload.message || "Bridge status unavailable.", "Bridge status unavailable.");
              document.getElementById("bridge-view-subtitle").textContent = payload.enabled
                ? "Bridge runtime status and recent log output."
                : "Bridge control is disabled in launch config.";
              updateBridgeButtons(payload);
              if (!bridge) {
                renderBridgeConfig(null, true);
              }
            }

            function renderBridgeList(bridges) {
              const root = document.getElementById("bridge-switcher");
              root.innerHTML = "";

              if (!bridges.length) {
                selectedBridge = null;
                root.innerHTML = '<div class="bridge-empty">No bridge configuration was found.</div>';
                renderBridge(null);
                return;
              }

              if (!selectedBridge || !bridges.some((item) => item.name === selectedBridge)) {
                const preferred = bridges.find((item) => item.status === "running") || bridges[0];
                selectedBridge = preferred.name;
              }

              for (const bridge of bridges) {
                const button = document.createElement("button");
                button.className = "bridge-selector";
                button.type = "button";
                if (bridge.name === selectedBridge) {
                  button.classList.add("active");
                }
                button.innerHTML = `
                  <div class="bridge-selector-row">
                    <strong>${escapeHtml(bridge.name)}</strong>
                    <span class="status-chip ${statusClass(bridge.status)}">${escapeHtml(bridge.status)}</span>
                  </div>
                  <div class="bridge-selector-meta">${escapeHtml(bridge.endpoint || "unconfigured")}</div>
                `;
                button.addEventListener("click", async () => {
                  selectedBridge = bridge.name;
                  renderBridgeList(bridges);
                  renderBridge(bridge);
                  if (activeWindow === "bridge") {
                    await refreshBridgeConfig(true);
                    await refreshBridgeLogs(true);
                  }
                });
                root.appendChild(button);
              }

              const activeBridge = findBridge(selectedBridge) || bridges[0];
              renderBridge(activeBridge);
            }

            function showActionBanner(message, isError = false) {
              const banner = document.getElementById("action-banner");
              banner.textContent = message;
              banner.className = `action-banner global-banner visible${isError ? " error" : ""}`;
            }

            function clearActionBanner() {
              const banner = document.getElementById("action-banner");
              banner.textContent = "";
              banner.className = "action-banner global-banner";
            }

            function switchWindow(windowName) {
              activeWindow = windowName === "bridge" ? "bridge" : "docker";
              const isBridge = activeWindow === "bridge";
              const isDocker = activeWindow === "docker";

              document.getElementById("docker-window").classList.toggle("hidden", !isDocker);
              document.getElementById("bridge-window").classList.toggle("hidden", !isBridge);

              for (const tabButton of document.querySelectorAll(".view-tab")) {
                const selected = tabButton.dataset.window === activeWindow;
                tabButton.classList.toggle("active", selected);
                tabButton.setAttribute("aria-selected", selected ? "true" : "false");
              }

              if (isBridge) {
                refreshBridgeConfig(false);
                refreshBridgeLogs(false);
              } else {
                refreshLauncherConfig(false);
                if (selectedDocker) {
                  refreshLogs(false);
                }
              }
            }

            function switchDockerSubview(subview) {
              const target = subview === "config" ? "config" : "logs";
              document.getElementById("docker-subview-logs").classList.toggle("hidden", target !== "logs");
              document.getElementById("docker-subview-config").classList.toggle("hidden", target !== "config");
              for (const subtabButton of document.querySelectorAll(".subtab")) {
                const selected = subtabButton.dataset.subtab === target;
                subtabButton.classList.toggle("active", selected);
                subtabButton.setAttribute("aria-selected", selected ? "true" : "false");
              }
            }

            function renderStatusOnly(docker, updatedAtText) {
              const output = document.getElementById("log-output");
              document.getElementById("viewer-name").textContent = docker.name;
              document.getElementById("viewer-subtitle").textContent = "";
              document.getElementById("viewer-status-chip").className = `status-chip ${statusClass(docker.status)}`;
              document.getElementById("viewer-status-chip").textContent = docker.status;
              document.getElementById("detail-group").textContent = docker.group;
              document.getElementById("detail-runtime").textContent = `${docker.status} / session ${docker.session_state}`;
              document.getElementById("detail-image").textContent = docker.image || "untracked";
              document.getElementById("detail-container").textContent = docker.container_summary;
              document.getElementById("detail-ports").textContent = docker.ports || "untracked";
              document.getElementById("log-source").textContent = "source: status";
              document.getElementById("log-updated").textContent = updatedAtText || "status snapshot";
              document.getElementById("log-session").textContent = docker.session_name
                ? `tmux: ${docker.session_name}`
                : "tmux: not available";
              output.classList.remove("placeholder");
              output.classList.add("error-state");
              output.innerHTML = escapeHtml(docker.status_message || `Startup status: ${docker.status}.`);
            }

            function renderStatus(payload) {
              lastStatusPayload = payload;
              const dockers = payload.dockers || [];
              const bridges = payload.bridges || [];
              const summary = payload.summary || {};
              const root = document.getElementById("docker-groups");
              root.innerHTML = "";
              updateMetrics(summary);
              renderBridgeList(bridges);
              if (activeWindow === "bridge" && bridges.length) {
                refreshBridgeConfig(false);
              }

              const grouped = groupDockers(dockers);
              for (const [groupName, entries] of grouped.entries()) {
                if (!entries.length) {
                  continue;
                }

                const block = document.createElement("section");
                block.className = "group-block";

                const title = document.createElement("div");
                title.className = "group-title";
                title.innerHTML = `<strong>${escapeHtml(groupName)}</strong><span>${entries.length} docker(s)</span>`;
                block.appendChild(title);

                for (const docker of entries) {
                  const card = document.createElement("div");
                  card.className = "docker-card";
                  if (docker.name === selectedDocker) {
                    card.classList.add("active");
                  }
                  card.addEventListener("click", () => selectDocker(docker.name));
                  card.innerHTML = `
                    <div class="card-top">
                      <strong>${escapeHtml(docker.name)}</strong>
                      <span class="status-chip ${statusClass(docker.status)}">${escapeHtml(docker.status)}</span>
                    </div>
                    <div class="card-bottom">
                      <div class="card-actions">
                        <button class="mini-control" data-action="start" data-name="${escapeHtml(docker.name)}" type="button">Start</button>
                        <button class="mini-control mini-restart" data-action="restart" data-name="${escapeHtml(docker.name)}" type="button">Restart</button>
                        <button class="mini-control mini-stop" data-action="stop" data-name="${escapeHtml(docker.name)}" type="button">Stop</button>
                        <button class="mini-control" data-action="terminal" data-name="${escapeHtml(docker.name)}" type="button">Terminal</button>
                      </div>
                    </div>
                  `;
                  for (const actionButton of card.querySelectorAll("[data-action]")) {
                    actionButton.addEventListener("click", (event) => {
                      event.stopPropagation();
                      const { action, name } = event.currentTarget.dataset;
                      triggerDockerAction(action, name);
                    });
                  }
                  block.appendChild(card);
                }

                root.appendChild(block);
              }

              const selectedState = selectedDocker ? findDocker(selectedDocker) : null;
              if (selectedDocker && !selectedState) {
                selectedDocker = null;
              }
              renderDockerConnection(selectedState || null, false);
              if (!selectedState) {
                renderDockerServiceConfig(null, true);
              }

              if (!selectedDocker && dockers.length) {
                const preferred = dockers.find((item) => item.status === "running") || dockers[0];
                selectDocker(preferred.name);
              }
            }

            async function refreshLauncherConfig(resetDraft = false) {
              try {
                const payload = await fetchJson("/api/launcher/config");
                renderLauncherConfig(payload, resetDraft);
              } catch (error) {
                updateLauncherConfigControls(false);
                if (resetDraft || !launcherConfigDirty) {
                  document.getElementById("launcher-config-editor").value = "";
                  setLauncherConfigDirty(false);
                }
                document.getElementById("launcher-config-status").textContent = error.message;
              }
            }

            async function saveLauncherConfig(restart = false) {
              const editor = document.getElementById("launcher-config-editor");
              try {
                const response = await postJson("/api/launcher/config", {
                  content: editor.value,
                  restart,
                });
                showActionBanner(response.message || "Launcher config saved.");
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                renderLauncherConfig(response.config || null, true);
                if (selectedDocker) {
                  await refreshLogs(false);
                }
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            async function saveLauncherStructured(restart = false) {
              const structured = collectLauncherStructured();
              try {
                const response = await postJson("/api/launcher/structured", {
                  structured,
                  restart,
                });
                showActionBanner(response.message || "Launcher configuration saved.");
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                renderLauncherConfig(response.config || null, true);
                if (selectedDocker) {
                  await refreshLogs(false);
                }
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            function setLauncherConfigCollapsed(collapsed) {
              const root = document.getElementById("launcher-config");
              const toggle = document.getElementById("launcher-config-toggle");
              root.classList.toggle("collapsed", collapsed);
              toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
            }

            function toggleLauncherAdvanced(force) {
              const advanced = document.getElementById("launcher-advanced");
              const toggle = document.getElementById("launcher-advanced-toggle");
              const show = typeof force === "boolean" ? force : advanced.classList.contains("hidden");
              if (show) {
                // The Advanced YAML editor lives inside the collapsible body, so
                // make sure the config form is expanded when it is revealed.
                setLauncherConfigCollapsed(false);
              }
              advanced.classList.toggle("hidden", !show);
              toggle.setAttribute("aria-expanded", show ? "true" : "false");
              toggle.classList.toggle("active", show);
            }

            async function restartLauncherConfig() {
              try {
                const response = await postJson("/api/launcher/reload", {});
                showActionBanner(response.message || "Launcher config reloaded.");
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                renderLauncherConfig(response.config || null, true);
                if (selectedDocker) {
                  await refreshLogs(false);
                }
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            async function refreshStatus() {
              if (statusRefreshInFlight) {
                return;
              }
              statusRefreshInFlight = true;
              try {
                const payload = await fetchJson("/api/status");
                renderStatus(payload);
              } catch (error) {
                showActionBanner(error.message, true);
              } finally {
                statusRefreshInFlight = false;
              }
            }

            async function selectDocker(name) {
              selectedDocker = name;
              clearActionBanner();
              if (lastStatusPayload) {
                renderStatus(lastStatusPayload);
              }
              await refreshDockerServiceConfig(true);
              await refreshLogs(true);
            }

            async function openDockerTerminal() {
              if (!selectedDocker) {
                showActionBanner("Please select a docker first.", true);
                return;
              }
              try {
                const response = await postJson("/api/docker/open-terminal", { name: selectedDocker });
                showActionBanner(response.message || `Opened terminal for ${selectedDocker}.`);
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            async function triggerDockerAction(action, name) {
              const dockerName = name || selectedDocker;
              if (!dockerName) {
                showActionBanner("Please select a docker first.", true);
                return;
              }

              if (action === "terminal") {
                if (selectedDocker !== dockerName) {
                  await selectDocker(dockerName);
                }
                await openDockerTerminal();
                return;
              }

              if (
                (action === "start" || action === "restart") &&
                dockerName === selectedDocker &&
                dockerConnectionDirty
              ) {
                showActionBanner(
                  `Connection changes for ${dockerName} are not saved. Click Save Connection first.`,
                  true,
                );
                return;
              }
              if (
                (action === "start" || action === "restart") &&
                dockerName === selectedDocker &&
                dockerServiceConfigDirty
              ) {
                showActionBanner(
                  `Service config changes for ${dockerName} are not saved. Click Save Service Config first.`,
                  true,
                );
                return;
              }

              let endpoint = "/api/start";
              if (action === "stop") {
                endpoint = "/api/stop";
              } else if (action === "restart") {
                endpoint = "/api/restart";
              }
              try {
                const response = await postJson(endpoint, { name: dockerName });
                showActionBanner(response.message || `${action} completed.`);
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                if (selectedDocker === dockerName) {
                  await refreshLogs(true);
                }
                setTimeout(() => { refreshStatus(); }, 400);
                setTimeout(() => { refreshStatus(); }, 1400);
              } catch (error) {
                if (error.payload && error.payload.status) {
                  renderStatus(error.payload.status);
                } else {
                  await refreshStatus();
                }
                if (selectedDocker === dockerName) {
                  await refreshLogs(true);
                }
                showActionBanner(error.message, true);
              }
            }

            async function saveDockerConnection() {
              const dockerName = selectedDocker;
              if (!dockerName) {
                showActionBanner("Please select a docker first.", true);
                return;
              }

              const location = document.getElementById("docker-conn-location").value || "local";
              const dockerModelRoot = document.getElementById("docker-conn-root").value.trim();
              const remoteHost = document.getElementById("docker-conn-remote-host").value.trim();
              const remoteUser = document.getElementById("docker-conn-remote-user").value.trim();
              const remoteRoot = document.getElementById("docker-conn-remote-root").value.trim();
              const remotePortText = document.getElementById("docker-conn-remote-port").value.trim();
              const remotePassword = document.getElementById("docker-conn-remote-password").value;
              const remotePort = remotePortText ? Number(remotePortText) : 22;

              if (location === "remote") {
                if (!remoteHost || !remoteUser || !remoteRoot) {
                  showActionBanner(
                    "Remote mode requires host, user, and remote DockerModel root.",
                    true,
                  );
                  return;
                }
                if (!Number.isInteger(remotePort) || remotePort <= 0 || remotePort > 65535) {
                  showActionBanner("Remote SSH port must be between 1 and 65535.", true);
                  return;
                }
              }

              try {
                const response = await postJson("/api/docker/connection", {
                  name: dockerName,
                  location,
                  docker_model_root: dockerModelRoot || null,
                  remote_host: remoteHost || null,
                  remote_user: remoteUser || null,
                  remote_docker_model_root: remoteRoot || null,
                  remote_ssh_port: location === "remote" ? remotePort : null,
                  remote_password: location === "remote" && remotePassword.trim() ? remotePassword : null,
                });
                showActionBanner(response.message || `Connection saved for ${dockerName}.`);
                setDockerConnectionDirty(false);
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                await refreshLauncherConfig(false);
                if (selectedDocker) {
                  await refreshLogs(true);
                  await refreshDockerServiceConfig(true);
                }
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            function reloadDockerConnection() {
              const selectedState = selectedDocker ? findDocker(selectedDocker) : null;
              renderDockerConnection(selectedState, true);
            }

            async function triggerBridgeAction(action) {
              const bridgeName = selectedBridge;
              if (!bridgeName) {
                showActionBanner("Please select a bridge first.", true);
                return;
              }
              let endpoint = "/api/bridge/start";
              if (action === "stop") {
                endpoint = "/api/bridge/stop";
              } else if (action === "restart") {
                endpoint = "/api/bridge/restart";
              }

              try {
                const response = await postJson(endpoint, { name: bridgeName });
                showActionBanner(`${bridgeName}: ${response.message || `${action} completed.`}`);
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                await refreshBridgeConfig(false);
                await refreshBridgeLogs(true);
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            async function refreshBridgeConfig(resetDraft = false) {
              const editor = document.getElementById("bridge-config-editor");
              if (!selectedBridge) {
                renderBridgeConfig(null, true);
                return;
              }

              try {
                const payload = await fetchJson(`/api/bridge/config?name=${encodeURIComponent(selectedBridge)}`);
                renderBridgeConfig(payload, resetDraft);
              } catch (error) {
                updateBridgeConfigControls(false);
                if (resetDraft || !bridgeConfigDirty) {
                  editor.value = "";
                  setBridgeConfigDirty(false);
                }
                document.getElementById("bridge-config-status").textContent = error.message;
              }
            }

            async function saveBridgeConfig(restart = false) {
              if (!selectedBridge) {
                showActionBanner("Please select a bridge first.", true);
                return;
              }

              const editor = document.getElementById("bridge-config-editor");
              try {
                const response = await postJson("/api/bridge/config", {
                  name: selectedBridge,
                  content: editor.value,
                  restart,
                });
                showActionBanner(`${selectedBridge}: ${response.message || "Bridge config saved."}`);
                if (response.status) {
                  renderStatus(response.status);
                } else {
                  await refreshStatus();
                }
                renderBridgeConfig(response.config || null, true);
                if (restart) {
                  await refreshBridgeLogs(true);
                }
              } catch (error) {
                showActionBanner(error.message, true);
              }
            }

            async function refreshBridgeLogs(scrollToBottom = false) {
              const output = document.getElementById("bridge-log-output");
              if (!selectedBridge) {
                output.classList.add("placeholder");
                output.classList.remove("error-state");
                output.textContent = "No bridge selected.";
                return;
              }
              if (bridgeLogsRefreshInFlight) {
                return;
              }
              bridgeLogsRefreshInFlight = true;
              const bridgeName = selectedBridge;
              try {
                const payload = await fetchJson(`/api/bridge/logs?name=${encodeURIComponent(bridgeName)}`);
                if (selectedBridge !== bridgeName) {
                  return;
                }
                document.getElementById("bridge-log-source").textContent = `source: ${payload.source}`;
                document.getElementById("bridge-log-updated").textContent = `updated: ${formatTime(payload.updated_at)}`;
                applyTruncateText(
                  "bridge-log-session",
                  payload.log_path ? `log: ${payload.log_path}` : "log: unavailable",
                  "log: unavailable",
                );
                output.classList.remove("placeholder");
                output.classList.toggle("error-state", Boolean(payload.is_error));
                output.innerHTML = payload.html || escapeHtml(payload.content || "No bridge log content.");
                if (scrollToBottom) {
                  output.scrollTop = output.scrollHeight;
                }
              } catch (error) {
                output.classList.add("placeholder");
                output.classList.remove("error-state");
                output.textContent = error.message;
              } finally {
                bridgeLogsRefreshInFlight = false;
              }
            }

            async function refreshLogs(scrollToBottom = false) {
              const output = document.getElementById("log-output");
              if (!selectedDocker) {
                return;
              }
              if (dockerLogsRefreshInFlight) {
                return;
              }
              dockerLogsRefreshInFlight = true;
              const dockerName = selectedDocker;

              const selectedState = findDocker(dockerName);

              try {
                const payload = await fetchJson(`/api/logs?name=${encodeURIComponent(dockerName)}`);
                if (selectedDocker !== dockerName) {
                  return;
                }
                document.getElementById("viewer-name").textContent = payload.name;
                document.getElementById("viewer-subtitle").textContent = "";
                document.getElementById("viewer-status-chip").className = `status-chip ${statusClass(selectedState ? selectedState.status : "unknown")}`;
                document.getElementById("viewer-status-chip").textContent = selectedState ? selectedState.status : "unknown";
                document.getElementById("detail-group").textContent = selectedState ? selectedState.group : payload.group;
                document.getElementById("detail-runtime").textContent = selectedState
                  ? `${selectedState.status} / session ${selectedState.session_state}`
                  : "unknown";
                document.getElementById("detail-image").textContent = selectedState
                  ? (selectedState.image || "untracked")
                  : "-";
                document.getElementById("detail-container").textContent = selectedState
                  ? selectedState.container_summary
                  : "-";
                document.getElementById("detail-ports").textContent = selectedState
                  ? (selectedState.ports || "untracked")
                  : "-";
                document.getElementById("log-source").textContent = `source: ${payload.source}`;
                document.getElementById("log-updated").textContent = `updated: ${formatTime(payload.updated_at)}`;
                document.getElementById("log-session").textContent = payload.session_name
                  ? `tmux: ${payload.session_name}`
                  : "tmux: not available";
                output.classList.remove("placeholder");
                output.classList.toggle("error-state", Boolean(payload.is_error));
                output.innerHTML = payload.html || escapeHtml(payload.content || "No log content.");
                if (scrollToBottom) {
                  output.scrollTop = output.scrollHeight;
                }
              } catch (error) {
                output.classList.add("placeholder");
                output.classList.remove("error-state");
                output.textContent = error.message;
              } finally {
                dockerLogsRefreshInFlight = false;
              }
            }

            document.getElementById("refresh-logs").addEventListener("click", () => refreshLogs(false));
            document.getElementById("launcher-config-reload").addEventListener("click", () => refreshLauncherConfig(true));
            document.getElementById("launcher-config-restart").addEventListener("click", () => restartLauncherConfig());
            document.getElementById("launcher-config-save").addEventListener("click", () => saveLauncherStructured(false));
            document.getElementById("launcher-config-save-restart").addEventListener("click", () => saveLauncherStructured(true));
            document.getElementById("launcher-advanced-save").addEventListener("click", () => saveLauncherConfig(false));
            document.getElementById("launcher-advanced-save-restart").addEventListener("click", () => saveLauncherConfig(true));
            document.getElementById("launcher-advanced-toggle").addEventListener("click", () => toggleLauncherAdvanced());
            document.getElementById("launcher-config-toggle").addEventListener("click", () => {
              const collapsed = document.getElementById("launcher-config").classList.contains("collapsed");
              setLauncherConfigCollapsed(!collapsed);
            });
            document.getElementById("launcher-config-editor").addEventListener("input", () => {
              setLauncherConfigDirty(true);
              document.getElementById("launcher-config-status").textContent =
                "Unsaved YAML changes. Save YAML to write docker_launch.yaml, or reload to discard your draft.";
            });
            for (const nodeId of ["lc-docker-root", "lc-poll"]) {
              document.getElementById(nodeId).addEventListener("input", markLauncherConfigDirty);
            }
            for (const nodeId of ["lc-tmux", "lc-monitor", "lc-replace"]) {
              document.getElementById(nodeId).addEventListener("change", markLauncherConfigDirty);
            }
            document.getElementById("lc-add-bridge").addEventListener("click", () => {
              const list = document.getElementById("lc-bridge-list");
              list.appendChild(buildBridgeRow({ name: "", enabled: true, config: "" }));
              markLauncherConfigDirty();
            });
            document.getElementById("lc-add-target-select").addEventListener("change", (event) => {
              const name = event.target.value;
              if (!name) {
                return;
              }
              const list = document.getElementById("lc-target-list");
              const empty = list.querySelector(".lc-empty");
              if (empty) {
                empty.remove();
              }
              list.appendChild(buildTargetRow({ name, group: "ungrouped", location: "local", enabled: true }));
              const option = Array.from(event.target.options).find((opt) => opt.value === name);
              if (option) {
                option.remove();
              }
              event.target.value = "";
              markLauncherConfigDirty();
            });
            (function wireTargetsCollapse() {
              const toggle = document.getElementById("lc-targets-toggle");
              const card = document.getElementById("lc-targets-card");
              const apply = () => {
                const collapsed = card.classList.toggle("collapsed");
                toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
              };
              toggle.addEventListener("click", apply);
              toggle.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  apply();
                }
              });
            })();
            document.getElementById("start-docker").addEventListener("click", () => triggerDockerAction("start"));
            document.getElementById("restart-docker").addEventListener("click", () => triggerDockerAction("restart"));
            document.getElementById("stop-docker").addEventListener("click", () => triggerDockerAction("stop"));
            document.getElementById("open-docker-terminal").addEventListener("click", () => openDockerTerminal());
            document.getElementById("docker-connection-reload").addEventListener("click", () => reloadDockerConnection());
            document.getElementById("docker-connection-save").addEventListener("click", () => saveDockerConnection());
            document.getElementById("docker-service-config-reload").addEventListener("click", () => reloadDockerServiceConfig());
            document.getElementById("docker-service-config-save").addEventListener("click", () => saveDockerServiceConfig(false));
            document.getElementById("docker-service-config-save-restart").addEventListener("click", () => saveDockerServiceConfig(true));
            for (const nodeId of [
              "docker-service-container-name",
              "docker-service-host",
              "docker-service-port",
            ]) {
              document.getElementById(nodeId).addEventListener("input", () => {
                setDockerServiceConfigDirty(true);
                document.getElementById("docker-service-config-status").textContent =
                  `Unsaved service config changes for ${selectedDocker || "docker"}. Save to write YAML updates.`;
              });
            }
            for (const nodeId of [
              "docker-conn-location",
              "docker-conn-root",
              "docker-conn-remote-host",
              "docker-conn-remote-user",
              "docker-conn-remote-root",
              "docker-conn-remote-port",
              "docker-conn-remote-password",
            ]) {
              document.getElementById(nodeId).addEventListener("input", () => {
                setDockerConnectionDirty(true);
                if (nodeId === "docker-conn-location") {
                  updateDockerConnectionVisibility();
                }
                document.getElementById("docker-connection-status").textContent =
                  `Unsaved connection changes for ${selectedDocker || "docker"}. Save to apply local/remote mapping.`;
              });
              if (nodeId === "docker-conn-location") {
                document.getElementById(nodeId).addEventListener("change", () => {
                  setDockerConnectionDirty(true);
                  updateDockerConnectionVisibility();
                });
              }
            }
            document.getElementById("bridge-start-main").addEventListener("click", () => triggerBridgeAction("start"));
            document.getElementById("bridge-restart-main").addEventListener("click", () => triggerBridgeAction("restart"));
            document.getElementById("bridge-stop-main").addEventListener("click", () => triggerBridgeAction("stop"));
            document.getElementById("bridge-refresh-logs").addEventListener("click", () => refreshBridgeLogs(false));
            document.getElementById("bridge-config-reload").addEventListener("click", () => refreshBridgeConfig(true));
            document.getElementById("bridge-config-save").addEventListener("click", () => saveBridgeConfig(false));
            document.getElementById("bridge-config-save-restart").addEventListener("click", () => saveBridgeConfig(true));
            document.getElementById("bridge-config-editor").addEventListener("input", () => {
              setBridgeConfigDirty(true);
              document.getElementById("bridge-config-status").textContent =
                `Unsaved changes for ${selectedBridge || "bridge"}. Save to write the YAML or reload to discard your draft.`;
              setBridgeGraphStatus("Draft changed. Reload or save to update graph.");
            });
            for (const tabButton of document.querySelectorAll(".view-tab")) {
              tabButton.addEventListener("click", () => switchWindow(tabButton.dataset.window || "docker"));
            }
            for (const subtabButton of document.querySelectorAll(".subtab")) {
              subtabButton.addEventListener("click", () => switchDockerSubview(subtabButton.dataset.subtab || "logs"));
            }

            window.addEventListener("load", async () => {
              updateDockerConnectionControls(false);
              updateDockerServiceConfigControls(false);
              updateDockerConnectionVisibility();
              initBridgeGraphEvents();
              await refreshStatus();
              await refreshLauncherConfig(true);
              switchWindow(activeWindow);
              setInterval(refreshStatus, 4500);
              setInterval(() => {
                if (activeWindow === "bridge") {
                  refreshBridgeLogs(false);
                } else if (activeWindow === "docker" && selectedDocker) {
                  refreshLogs(false);
                }
              }, 3000);
            });
