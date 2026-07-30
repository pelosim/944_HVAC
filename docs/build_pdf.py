#!/usr/bin/env python3
"""Build a standalone, printable version of the system map.

The artifact host renders <pre class="mermaid"> for us; a standalone file has
no such help, so the diagram is swapped for hand-authored inline SVG. The
palette is forced to the light tokens — a dark ground is right on screen and
wrong on paper.
"""
import pathlib, re

SRC = pathlib.Path("docs/system-map.html")
OUT = pathlib.Path("docs/944S-system-map-standalone.html")
html = SRC.read_text()

# ── static diagram, replacing the mermaid block ──────────────────────
SVG = r'''<svg viewBox="0 0 940 560" width="100%" role="img"
  aria-labelledby="dgt dgd" style="max-width:940px;height:auto">
<title id="dgt">944S electronics interconnect diagram</title>
<desc id="dgd">The iDrive knob feeds an ESP32 over CAN. That ESP32 drives the head
unit over IR and reports to the HVAC Pi over UART. The Pi drives the HVAC hardware,
the touchscreen and the round auxiliary screen, and a planned USB link reaches the
lighting output board, which is also driven by its own knob over ESP-NOW.</desc>
<defs>
  <marker id="a" markerWidth="9" markerHeight="9" refX="8" refY="3"
    orient="auto" markerUnits="strokeWidth">
    <path d="M0,0 L0,6 L8,3 z" fill="context-stroke"/>
  </marker>
</defs>
<g font-family="ui-monospace,Menlo,monospace" font-size="12">

  <!-- boxes -->
  <g fill="#FFFFFF" stroke="#5A6B68" stroke-width="1.3">
    <rect x="18"  y="38"  width="158" height="52" rx="7"/>
    <rect x="258" y="38"  width="180" height="52" rx="7"/>
    <rect x="530" y="38"  width="170" height="52" rx="7"/>
    <rect x="258" y="196" width="180" height="52" rx="7"/>
    <rect x="530" y="140" width="170" height="42" rx="7"/>
    <rect x="530" y="196" width="170" height="42" rx="7"/>
    <rect x="530" y="252" width="170" height="42" rx="7"/>
    <rect x="18"  y="420" width="158" height="52" rx="7"/>
    <rect x="258" y="420" width="180" height="52" rx="7"/>
    <rect x="530" y="420" width="170" height="52" rx="7"/>
  </g>

  <!-- labels -->
  <g fill="#0E1614" text-anchor="middle">
    <text x="97"  y="60">BMW iDrive</text><text x="97"  y="76" fill="#465754">Preh knob</text>
    <text x="348" y="60">iDrive ESP32-S3</text><text x="348" y="76" fill="#465754">CAN in / IR + UART out</text>
    <text x="615" y="60">CP-71W</text><text x="615" y="76" fill="#465754">head unit</text>
    <text x="348" y="218">HVAC Pi 4</text><text x="348" y="234" fill="#465754">hub · state authority</text>
    <text x="615" y="166">HVAC hardware</text>
    <text x="615" y="222">Touchscreen 1920×720</text>
    <text x="615" y="278">Round aux screen</text>
    <text x="97"  y="442">Lighting knob</text><text x="97" y="458" fill="#465754">CrowPanel</text>
    <text x="348" y="442">Lighting ESP32-S3</text><text x="348" y="458" fill="#465754">strip · dimmer · dome</text>
    <text x="615" y="442">Interior lighting</text><text x="615" y="458" fill="#465754">loads</text>
  </g>

  <!-- links -->
  <g fill="none" marker-end="url(#a)" stroke-width="1.8">
    <path d="M176,64 L252,64"  stroke="#8F5D00"/>
    <path d="M438,64 L524,64"  stroke="#6B7A77" stroke-dasharray="5 3"/>
    <path d="M348,90 L348,190" stroke="#0C7F76"/>
    <path d="M438,212 L524,166" stroke="#5A6B68"/>
    <path d="M438,222 L524,217" stroke="#5A6B68"/>
    <path d="M438,232 L524,268" stroke="#5A6B68"/>
    <path d="M348,248 L348,414" stroke="#175F9E" stroke-dasharray="6 4"/>
    <path d="M176,446 L252,446" stroke="#A81F17"/>
    <path d="M438,446 L524,446" stroke="#5A6B68"/>
  </g>

  <!-- link captions -->
  <g font-size="10.5" fill="#465754">
    <text x="214" y="56"  text-anchor="middle">CAN 500k</text>
    <text x="481" y="56"  text-anchor="middle">IR NEC</text>
    <text x="356" y="146">UART 115200 · NDJSON</text>
    <text x="356" y="338">USB serial · planned</text>
    <text x="214" y="438" text-anchor="middle">ESP-NOW</text>
  </g>
</g>
</svg>'''

html = re.sub(r'<pre class="mermaid">.*?</pre>', SVG, html, flags=re.S)

PRINT_CSS = r'''
<style>
/* Standalone/print build: force the light tokens. A dark ground is correct on
   a screen and wasteful on paper, and the viewer-theme toggle does not exist
   outside the artifact host. */
:root, :root[data-theme="dark"], :root[data-theme="light"]{
  --ground:#FFFFFF; --surface:#FFFFFF; --sunk:#F2F5F4;
  --line:#D6E0DE; --line-2:#B4C4C1;
  --text:#0E1614; --text-2:#3D4E4B; --text-3:#6B7C79;
  --teal:#0C7F76; --amber:#8A5900; --ice:#175F9E; --alarm:#A81F17; --ok:#1E7A46;
  --teal-bg:#0C7F7612; --amber-bg:#8A590012; --ice-bg:#175F9E12; --alarm-bg:#A81F1712;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#FFFFFF; --surface:#FFFFFF; --sunk:#F2F5F4;
  --line:#D6E0DE; --line-2:#B4C4C1;
  --text:#0E1614; --text-2:#3D4E4B; --text-3:#6B7C79;
  --teal:#0C7F76; --amber:#8A5900; --ice:#175F9E; --alarm:#A81F17; --ok:#1E7A46;
}}
@page{ size:Letter portrait; margin:14mm 12mm; }
@media print{
  body{font-size:10.2pt;line-height:1.45}
  .wrap{max-width:none;padding:0}
  header{padding-top:0}
  section{padding-top:20px;break-inside:auto}
  .sechead{break-after:avoid}
  h3{break-after:avoid}
  tr,.mod,.note,ol.steps li,pre.proto{break-inside:avoid}
  .tablewrap{overflow:visible;break-inside:auto}
  table{min-width:0}
  th{background:#F2F5F4}
  .diagram{break-inside:avoid;padding:8px}
  a{text-decoration:none}
}
</style>'''

DOC = ("<!doctype html>\n<html lang=\"en\">\n<head>\n"
       "<meta charset=\"utf-8\">\n"
       "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
       + html.split("</style>", 1)[0] + "</style>\n" + PRINT_CSS
       + "\n</head>\n<body>\n" + html.split("</style>", 1)[1] + "\n</body>\n</html>\n")

OUT.write_text(DOC)
print(f"wrote {OUT} — {OUT.stat().st_size:,} bytes")
print("mermaid removed:", "mermaid" not in DOC)
print("svg present:", "<svg viewBox" in DOC)
