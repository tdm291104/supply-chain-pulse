# Supply Chain Pulse — 3-minute demo script

## 00:00–00:25 — Hook
Slide: "$1.5T lost annually to supply chain disruptions. Mid-market manufacturers
have no early warning system."
VO: "Supply Chain Pulse changes that."

## 00:25–00:50 — Data foundation
Show the Pipeline tab.
"Four live data sources syncing through the Fivetran MCP server — orders, inventory,
weather, and news — all unified automatically."
Point at last-sync times and health badges. Click "Sync now" on the orders connection.
[Tool call log: `sync_connection` appears in `logs/tool_calls.jsonl` in real time]

## 00:50–01:30 — The alert
Switch to the Alerts tab. The perfect-storm alert is already there.
"The agent detected three converging signals automatically."
Expand the alert: show the underlying view query and the raw numbers.
"Nine days of stock. A 4.2-day average delay from the primary supplier. A hurricane
forecast on the only corridor that supplier ships through. The agent connected
these dots — no human had to notice the pattern."

## 01:30–02:10 — Human in the loop
Select "Switch to backup supplier (Vertex Fabrics)". Click Approve.
[Live log shows: `create_connection` → `modify_connection`, both attributed to "agent"]
"The agent just reconfigured the pipeline through Fivetran's write APIs in real
time — but only after a human approved it. That approval is enforced in the
backend, not just hidden behind a disabled button."

## 02:10–02:40 — Conversational
Switch to the Chat tab.
Type: "What's my highest-risk SKU?"
Show the agent's answer with specific numbers, and the view it queried.
Type: "Compare SUP-001 vs SUP-002 reliability."

## 02:40–03:00 — Close
"Supply Chain Pulse turns scattered data into decisive action. Any manufacturer
can connect their sources through Fivetran and have this running in under ten
minutes — the data foundation already exists. The agent just needed to listen to it."
