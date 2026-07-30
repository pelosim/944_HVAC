#!/usr/bin/env python3
"""Generate docs/system-map.html for the 944S electronics bench reference."""
import pathlib

ORB = pathlib.Path("/tmp/orb.b64").read_text().strip()

HTML = r"""<title>944S Electronics — System Map &amp; Bench Reference</title>
<style>
@font-face{font-family:'Orbitron';font-style:normal;font-weight:500 900;font-display:swap;
  src:url(data:font/woff2;base64,__ORB__) format('woff2')}

:root{
  --ground:#F5F8F7; --surface:#FFFFFF; --sunk:#EDF2F1;
  --line:#D6E0DE; --line-2:#BFCECB;
  --text:#0E1614; --text-2:#465754; --text-3:#788A87;
  --teal:#0C7F76; --amber:#8F5D00; --ice:#175F9E; --alarm:#A81F17; --ok:#1E7A46;
  --teal-bg:#0C7F7614; --amber-bg:#8F5D0014; --ice-bg:#175F9E14; --alarm-bg:#A81F1714;
  --radius:10px;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#0A0E0F; --surface:#111819; --sunk:#0D1415;
  --line:#212D2E; --line-2:#2F3E3F;
  --text:#E9F3F1; --text-2:#9DB2AE; --text-3:#6A7E7B;
  --teal:#2CE8D8; --amber:#FFB000; --ice:#5CB8FF; --alarm:#FF6B60; --ok:#3AFF8C;
  --teal-bg:#2CE8D81A; --amber-bg:#FFB0001A; --ice-bg:#5CB8FF1A; --alarm-bg:#FF6B601A;
}}
:root[data-theme="dark"]{
  --ground:#0A0E0F; --surface:#111819; --sunk:#0D1415;
  --line:#212D2E; --line-2:#2F3E3F;
  --text:#E9F3F1; --text-2:#9DB2AE; --text-3:#6A7E7B;
  --teal:#2CE8D8; --amber:#FFB000; --ice:#5CB8FF; --alarm:#FF6B60; --ok:#3AFF8C;
  --teal-bg:#2CE8D81A; --amber-bg:#FFB0001A; --ice-bg:#5CB8FF1A; --alarm-bg:#FF6B601A;
}
:root[data-theme="light"]{
  --ground:#F5F8F7; --surface:#FFFFFF; --sunk:#EDF2F1;
  --line:#D6E0DE; --line-2:#BFCECB;
  --text:#0E1614; --text-2:#465754; --text-3:#788A87;
  --teal:#0C7F76; --amber:#8F5D00; --ice:#175F9E; --alarm:#A81F17; --ok:#1E7A46;
  --teal-bg:#0C7F7614; --amber-bg:#8F5D0014; --ice-bg:#175F9E14; --alarm-bg:#A81F1714;
}

*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--text);
  font-family:var(--sans);font-size:16px;line-height:1.6;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px 96px}

h1,h2,h3,.eyebrow,.mod-name{font-family:'Orbitron',var(--sans)}
h1{font-size:clamp(28px,5vw,44px);font-weight:800;letter-spacing:-.01em;
  line-height:1.1;margin:0 0 10px;text-wrap:balance}
h2{font-size:clamp(19px,2.6vw,25px);font-weight:700;letter-spacing:.01em;
  margin:0;text-wrap:balance}
h3{font-size:15px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--text-2);margin:28px 0 10px}
p{margin:0 0 14px;max-width:68ch;color:var(--text-2)}
a{color:var(--teal)}
code,.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}

header{padding:52px 0 30px;border-bottom:1px solid var(--line)}
.eyebrow{font-size:12px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--teal);margin:0 0 14px;font-weight:700}
.lede{font-size:17px;color:var(--text-2);max-width:66ch;margin:0}
.stamp{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}
.stamp span{font-family:var(--mono);font-size:12px;padding:4px 10px;
  border:1px solid var(--line-2);border-radius:99px;color:var(--text-2)}

section{padding-top:44px;scroll-margin-top:20px}
.sechead{display:flex;align-items:baseline;gap:14px;
  padding-bottom:12px;margin-bottom:20px;border-bottom:1px solid var(--line)}
.sechead .n{font-family:var(--mono);font-size:13px;color:var(--text-3);
  font-variant-numeric:tabular-nums}

/* transport legend + chips: colour encodes what instrument probes it */
.legend{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.chip{font-family:var(--mono);font-size:12px;font-weight:600;
  padding:3px 9px;border-radius:5px;white-space:nowrap;
  border:1px solid currentColor}
.t-can{color:var(--amber);background:var(--amber-bg)}
.t-uart{color:var(--teal);background:var(--teal-bg)}
.t-usb{color:var(--ice);background:var(--ice-bg)}
.t-radio{color:var(--alarm);background:var(--alarm-bg)}
.t-ir{color:var(--text-2);background:var(--sunk)}

.diagram{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:22px 18px;overflow-x:auto;margin-bottom:8px}
.diagram pre.mermaid{margin:0;min-width:520px}

.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(290px,1fr))}
.mod{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:18px;border-top:3px solid var(--teal)}
.mod.pi{border-top-color:var(--alarm)}
.mod.light{border-top-color:var(--amber)}
.mod.future{border-top-color:var(--line-2);opacity:.82}
.mod-name{font-size:16px;font-weight:700;margin:0 0 3px}
.mod-role{font-size:13px;color:var(--text-3);margin:0 0 13px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:13.5px}
.kv dt{color:var(--text-3);white-space:nowrap}
.kv dd{margin:0;font-family:var(--mono);color:var(--text-2);word-break:break-word}

.tablewrap{overflow-x:auto;border:1px solid var(--line);
  border-radius:var(--radius);background:var(--surface)}
table{border-collapse:collapse;width:100%;min-width:600px;font-size:14px}
th{font-family:var(--mono);font-size:11.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--text-3);text-align:left;font-weight:600;
  padding:11px 14px;border-bottom:1px solid var(--line-2);white-space:nowrap}
td{padding:10px 14px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
td.pin{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-weight:600;white-space:nowrap;color:var(--text)}
td.mono{font-family:var(--mono);font-size:13px;color:var(--text-2)}
.lvl{font-family:var(--mono);font-size:11.5px;padding:2px 7px;border-radius:4px;
  white-space:nowrap;border:1px solid currentColor}
.lo{color:var(--alarm);background:var(--alarm-bg)}
.hi{color:var(--ok);background:var(--ok)0F}
.an{color:var(--ice);background:var(--ice-bg)}

.note{border-left:3px solid var(--amber);background:var(--amber-bg);
  padding:13px 16px;border-radius:0 6px 6px 0;margin:18px 0;font-size:14.5px}
.note strong{color:var(--amber)}
.note.stop{border-left-color:var(--alarm);background:var(--alarm-bg)}
.note.stop strong{color:var(--alarm)}
.note p{margin:0;color:var(--text-2);max-width:none}
.note p+p{margin-top:8px}

pre.proto{background:var(--sunk);border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;overflow-x:auto;font-family:var(--mono);font-size:13px;
  line-height:1.55;margin:0 0 14px;color:var(--text-2)}
pre.proto b{color:var(--teal);font-weight:600}

ol.steps{counter-reset:s;list-style:none;padding:0;margin:0;
  display:flex;flex-direction:column;gap:10px}
ol.steps li{counter-increment:s;position:relative;padding:14px 16px 14px 52px;
  background:var(--surface);border:1px solid var(--line);border-radius:var(--radius)}
ol.steps li::before{content:counter(s);position:absolute;left:15px;top:13px;
  font-family:var(--mono);font-size:12px;font-weight:700;color:var(--teal);
  width:22px;height:22px;border:1px solid var(--teal);border-radius:5px;
  display:grid;place-items:center}
ol.steps b{display:block;font-size:14.5px;margin-bottom:3px;color:var(--text)}
ol.steps span{font-size:13.5px;color:var(--text-2)}
ol.steps .expect{display:block;margin-top:7px;font-family:var(--mono);font-size:12.5px;
  color:var(--text-3);padding-top:7px;border-top:1px dashed var(--line-2)}

footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);
  font-size:13px;color:var(--text-3)}
@media (max-width:640px){
  .kv{grid-template-columns:1fr;gap:2px}
  .kv dt{margin-top:7px}
  body{font-size:15px}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>

<div class="wrap">

<header>
  <p class="eyebrow">1987 Porsche 944S · Restomod Electronics</p>
  <h1>System Map &amp; Bench Reference</h1>
  <p class="lede">Every module, every interconnect, and the complete I/O map for the
  HVAC Pi. Pin assignments here are read from source, not from documentation —
  <code>hvac_backend.py</code>, <code>idrive_controller.ino</code>, and
  <code>pwm_controller.ino</code>.</p>
  <div class="stamp">
    <span>5 modules on the bench</span>
    <span>3 boards on the Pi USB hub</span>
    <span>generated 2026-07-30</span>
  </div>
</header>

<section id="map">
  <div class="sechead"><span class="n">01</span><h2>System map</h2></div>
  <p>Link colour is the transport, which is also what you probe it with — a scope on CAN,
  a terminal on serial, nothing at all on the radio link.</p>
  <div class="legend">
    <span class="chip t-can">CAN 500 kbps</span>
    <span class="chip t-uart">UART 115200</span>
    <span class="chip t-usb">USB serial</span>
    <span class="chip t-radio">ESP-NOW</span>
    <span class="chip t-ir">IR 38 kHz</span>
  </div>
  <div class="diagram">
<pre class="mermaid">
graph LR
  KNOB["BMW iDrive<br/>Preh 6582 6829079-03"]
  IDR["iDrive Controller<br/>ESP32-S3"]
  RADIO["Power Acoustik<br/>CP-71W"]
  PI["HVAC Pi 4<br/>944HVACPi"]
  HVAC["HVAC Hardware<br/>relays · flaps · sensors"]
  PANEL["Touchscreen<br/>1920x720"]
  AUX["Round Aux Screen<br/>clock / G-meter"]
  LOUT["Lighting Output<br/>ESP32-S3"]
  LKNOB["Lighting Knob<br/>CrowPanel 1.28in"]
  LEDS["Strip · Dimmer · Dome"]

  KNOB -- "CAN 0x25B" --> IDR
  IDR -- "IR NEC" --> RADIO
  IDR -- "UART NDJSON" --> PI
  IDR -. "USB power + flash" .- PI
  PI --> HVAC
  PI --> PANEL
  PI --> AUX
  PI -. "USB planned" .-> LOUT
  LKNOB -- "ESP-NOW" --> LOUT
  LOUT --> LEDS

  classDef esp fill:#2CE8D81A,stroke:#2CE8D8,color:#0E1614
  classDef pi fill:#FF6B601A,stroke:#A81F17,color:#0E1614
  classDef hw fill:#FFB0001A,stroke:#8F5D00,color:#0E1614
  class IDR,LOUT,LKNOB esp
  class PI pi
  class HVAC,LEDS,RADIO,KNOB,PANEL,AUX hw
</pre>
  </div>
  <div class="note">
    <p><strong>Not in this bench setup.</strong> The two T-Display-S3-Long aux gauge
    panels and the ACC/IGN ignition display are separate projects with no link to
    this system yet. The iDrive's <code>GAUGE</code> mode is reserved for the gauge
    panels but currently emits actions nothing consumes.</p>
  </div>
</section>

<section id="modules">
  <div class="sechead"><span class="n">02</span><h2>Module inventory</h2></div>
  <div class="grid">

    <div class="mod pi">
      <p class="mod-name">HVAC Pi 4</p>
      <p class="mod-role">Hub · climate control · state authority</p>
      <dl class="kv">
        <dt>Host</dt><dd>944HVACPi · user mark</dd>
        <dt>Path</dt><dd>/home/mark/hvac/</dd>
        <dt>Net</dt><dd>eth0 192.168.1.142</dd>
        <dt>Runtime</dt><dd>Python 3.11 · FastAPI · 10 Hz loop</dd>
        <dt>Serves</dt><dd>:8000 dashboard + /ws</dd>
        <dt>Repo</dt><dd>pelosim/944_HVAC</dd>
      </dl>
    </div>

    <div class="mod">
      <p class="mod-name">iDrive Controller</p>
      <p class="mod-role">Input surface · IR transmitter</p>
      <dl class="kv">
        <dt>Board</dt><dd>Lonely Binary ESP32-S3 N16R8</dd>
        <dt>MAC</dt><dd>D0:CF:13:24:DB:B8</dd>
        <dt>Core</dt><dd>esp32 3.3.10 (~/.arduino-cli-esp32v3)</dd>
        <dt>Flash</dt><dd>tools/flash-via-pi.sh</dd>
        <dt>Version</dt><dd>v1.6.0</dd>
        <dt>Repo</dt><dd>pelosim/idrive-controller</dd>
      </dl>
    </div>

    <div class="mod light">
      <p class="mod-name">Lighting Output</p>
      <p class="mod-role">Strip · dimmer · dome relay</p>
      <dl class="kv">
        <dt>Board</dt><dd>Lonely Binary ESP32-S3 N16R8</dd>
        <dt>MAC</dt><dd>3C:DC:75:40:0B:F0</dd>
        <dt>Core</dt><dd>esp32 2.0.14 (~/.arduino-cli-esp32v2)</dd>
        <dt>Partition</dt><dd>Huge APP (3 MB, no OTA)</dd>
        <dt>Repo</dt><dd>pelosim/Automotive-Lighting-Controller</dd>
      </dl>
    </div>

    <div class="mod light">
      <p class="mod-name">Lighting Knob</p>
      <p class="mod-role">Rotary UI · ESP-NOW only</p>
      <dl class="kv">
        <dt>Board</dt><dd>ELECROW CrowPanel 1.28" round</dd>
        <dt>MCU</dt><dd>ESP32-S3R8 · 240x240 GC9A01</dd>
        <dt>Encoder</dt><dd>CLK 45 · DT 42 · BTN 41</dd>
        <dt>LCD power</dt><dd>GPIO 1 + 2 HIGH before tft.begin()</dd>
        <dt>Stack</dt><dd>LVGL 9.x · TFT_eSPI</dd>
      </dl>
    </div>

  </div>
</section>

<section id="links">
  <div class="sechead"><span class="n">03</span><h2>Interconnects</h2></div>
  <div class="tablewrap">
    <table>
      <thead><tr>
        <th>Link</th><th>Transport</th><th>Physical</th><th>Carries</th><th>Status</th>
      </tr></thead>
      <tbody>
        <tr>
          <td>iDrive knob &rarr; ESP32</td>
          <td><span class="chip t-can">CAN 500k</span></td>
          <td class="mono">Green=CANH, Green/Org=CANL<br/>SN65HVD230 &middot; 120&Omega; term</td>
          <td class="mono">ID 0x25B, all 14 inputs</td>
          <td>Working</td>
        </tr>
        <tr>
          <td>ESP32 &rarr; head unit</td>
          <td><span class="chip t-ir">IR NEC</span></td>
          <td class="mono">GPIO17 &rarr; 220&Omega; &rarr; LED</td>
          <td class="mono">5 codes, addr 0x00</td>
          <td>Loopback 15/15</td>
        </tr>
        <tr>
          <td>ESP32 &rarr; Pi</td>
          <td><span class="chip t-uart">UART</span></td>
          <td class="mono">ESP 43&rarr;Pi 15 &middot; ESP 44&larr;Pi 14<br/>common GND</td>
          <td class="mono">NDJSON actions</td>
          <td>Working</td>
        </tr>
        <tr>
          <td>ESP32 &harr; Pi</td>
          <td><span class="chip t-usb">USB</span></td>
          <td class="mono">/dev/idrive &rarr; ttyACM0</td>
          <td class="mono">console + remote flashing</td>
          <td>Working</td>
        </tr>
        <tr>
          <td>Pi &rarr; lighting board</td>
          <td><span class="chip t-usb">USB</span></td>
          <td class="mono">/dev/lighting</td>
          <td class="mono">L SET / L ADJ / L GET</td>
          <td>Working</td>
        </tr>
        <tr>
          <td>Knob &harr; lighting board</td>
          <td><span class="chip t-radio">ESP-NOW</span></td>
          <td class="mono">no wires, shared GND</td>
          <td class="mono">4-byte packets</td>
          <td>Working</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="note">
    <p><strong>Why the iDrive keeps both links.</strong> UART carries the data because
    <code>/dev/serial0</code> is stable and survives resets on either end. USB carries
    power and flashing because <code>ttyACM</code> re-enumerates every time the ESP
    reboots. Moving data onto USB would mean writing reconnect logic for no gain.</p>
  </div>
</section>

<section id="pio">
  <div class="sechead"><span class="n">04</span><h2>HVAC Pi — GPIO map</h2></div>
  <p>BCM numbering. Relays and solenoids are <strong>active-LOW</strong> — the pin is
  driven low to energise, so a floating or un-initialised pin leaves them off.</p>
  <div class="tablewrap">
    <table>
      <thead><tr>
        <th>BCM</th><th>Function</th><th>Direction</th><th>Active</th><th>Drives</th>
      </tr></thead>
      <tbody>
        <tr><td class="pin">4</td><td>DS18B20 1-Wire bus</td><td>bidir</td>
            <td><span class="lvl an">1-Wire</span></td><td>3&times; temp sensors</td></tr>
        <tr><td class="pin">5</td><td>Blower HI</td><td>out</td>
            <td><span class="lvl lo">LOW = on</span></td><td>relay</td></tr>
        <tr><td class="pin">6</td><td>Blower LOW</td><td>out</td>
            <td><span class="lvl lo">LOW = on</span></td><td>relay</td></tr>
        <tr><td class="pin">12</td><td>Footwell flap IN1</td><td>out</td>
            <td><span class="lvl hi">HIGH</span></td><td>H-bridge</td></tr>
        <tr><td class="pin">13</td><td>Seat heat — driver</td><td>out PWM</td>
            <td><span class="lvl an">2 Hz</span></td><td>MOSFET</td></tr>
        <tr><td class="pin">14</td><td>UART TXD &rarr; iDrive RX</td><td>out</td>
            <td><span class="lvl an">serial</span></td><td>ESP GPIO44</td></tr>
        <tr><td class="pin">15</td><td>UART RXD &larr; iDrive TX</td><td>in</td>
            <td><span class="lvl an">serial</span></td><td>ESP GPIO43</td></tr>
        <tr><td class="pin">16</td><td>Defrost flap IN1</td><td>out</td>
            <td><span class="lvl hi">HIGH</span></td><td>H-bridge</td></tr>
        <tr><td class="pin">18</td><td>A/C clutch &rarr; MS3</td><td>out</td>
            <td><span class="lvl lo">LOW = on</span></td><td>relay RLY1</td></tr>
        <tr><td class="pin">19</td><td>Heat valve solenoid</td><td>out</td>
            <td><span class="lvl lo">LOW = on</span></td><td>relay RLY2</td></tr>
        <tr><td class="pin">20</td><td>Defrost flap IN2</td><td>out</td>
            <td><span class="lvl hi">HIGH</span></td><td>H-bridge</td></tr>
        <tr><td class="pin">21</td><td>Footwell flap IN2</td><td>out</td>
            <td><span class="lvl hi">HIGH</span></td><td>H-bridge</td></tr>
        <tr><td class="pin">23</td><td>Blend flap &rarr; COLD</td><td>out</td>
            <td><span class="lvl hi">HIGH</span></td><td>H-bridge</td></tr>
        <tr><td class="pin">24</td><td>Blend flap &rarr; HOT</td><td>out</td>
            <td><span class="lvl hi">HIGH</span></td><td>H-bridge</td></tr>
        <tr><td class="pin">25</td><td>Seat heat — passenger</td><td>out PWM</td>
            <td><span class="lvl an">2 Hz</span></td><td>MOSFET</td></tr>
        <tr><td class="pin">26</td><td>Fresh-air solenoid</td><td>out</td>
            <td><span class="lvl lo">LOW = on</span></td><td>relay RLY3</td></tr>
        <tr><td class="pin">2 / 3</td><td>I&sup2;C SDA / SCL</td><td>bidir</td>
            <td><span class="lvl an">I&sup2;C</span></td><td>ADS1115 @ 0x48</td></tr>
      </tbody>
    </table>
  </div>

  <h3>Analog feedback — ADS1115 @ 0x48</h3>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Ch</th><th>Measures</th><th>0%</th><th>100%</th><th>Watchdog</th></tr></thead>
      <tbody>
        <tr><td class="pin">A0</td><td>Blend flap position</td><td class="mono">225 mV</td>
            <td class="mono">4090 mV</td><td class="mono">cut after 8.0 s &lt;1.5% travel</td></tr>
        <tr><td class="pin">A1</td><td>Defrost flap position</td><td class="mono">225 mV</td>
            <td class="mono">4090 mV</td><td class="mono">as above</td></tr>
        <tr><td class="pin">A2</td><td>Footwell flap position</td><td class="mono">225 mV</td>
            <td class="mono">4090 mV</td><td class="mono">as above</td></tr>
        <tr><td class="pin">A3</td><td>spare</td><td class="mono">—</td>
            <td class="mono">—</td><td class="mono">—</td></tr>
      </tbody>
    </table>
  </div>

  <h3>Temperature — DS18B20 on GPIO 4</h3>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Sensor</th><th>ROM ID</th><th>Range shown</th></tr></thead>
      <tbody>
        <tr><td>Mixing chamber (duct)</td><td class="mono">000000bd3d51</td><td class="mono">32–180 °F</td></tr>
        <tr><td>Exterior</td><td class="mono">000000be5d11</td><td class="mono">−20–120 °F</td></tr>
        <tr><td>Interior / cabin</td><td class="mono">000000bbdd26</td><td class="mono">20–140 °F</td></tr>
      </tbody>
    </table>
  </div>
  <div class="note stop">
    <p><strong>IDs carry no <code>28-</code> prefix.</strong> The w1thermsensor library
    strips it. Adding it back gives three sensors that all read zero and a dashboard
    that looks alive but is lying.</p>
  </div>

  <h3>Serial ports</h3>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Device</th><th>Resolves to</th><th>Peer</th><th>Baud</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td class="mono">/dev/serial0</td><td class="mono">ttyAMA0</td><td>iDrive UART</td>
            <td class="mono">115200</td><td>needs <code>dtoverlay=disable-bt</code></td></tr>
        <tr><td class="mono">/dev/idrive</td><td class="mono">ttyACM1</td><td>iDrive USB</td>
            <td class="mono">—</td><td>udev by MAC D0:CF:13:24:DB:B8</td></tr>
        <tr><td class="mono">/dev/lighting</td><td class="mono">ttyACM0</td><td>Lighting board</td>
            <td class="mono">115200</td><td>udev by MAC 3C:DC:75:40:0B:F0</td></tr>
        <tr><td class="mono">/dev/gauges</td><td class="mono">ttyACM2</td><td>Gauge panel (primary)</td>
            <td class="mono">—</td><td>console + flashing only; no protocol yet</td></tr>
      </tbody>
    </table>
  </div>
  <div class="note stop">
    <p><strong>Two boot-config settings are load-bearing.</strong>
    <code>dtoverlay=disable-bt</code> moves <code>/dev/serial0</code> onto the real PL011.
    Without it you get the mini-UART, whose baud tracks the VPU core clock and corrupts
    under load — which the 10 Hz control loop guarantees.</p>
    <p>And <code>console=serial0,115200</code> must stay <em>out</em> of
    <code>cmdline.txt</code>, or the kernel console fights the backend for the same port.
    Backups sit beside both files as <code>.bak</code>.</p>
  </div>
</section>

<section id="esp-io">
  <div class="sechead"><span class="n">05</span><h2>ESP32 I/O</h2></div>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Board</th><th>GPIO</th><th>Function</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td rowspan="6">iDrive<br/>Controller</td><td class="pin">4</td><td>CAN TX (CTX)</td><td class="mono">SN65HVD230 — never MCP2551</td></tr>
        <tr><td class="pin">8</td><td>CAN RX (CRX)</td><td class="mono">120&Omega; across CANH/CANL</td></tr>
        <tr><td class="pin">17</td><td>IR LED</td><td class="mono">220&Omega; series</td></tr>
        <tr><td class="pin">18</td><td>IR receiver</td><td class="mono">bench loopback only</td></tr>
        <tr><td class="pin">43 / 44</td><td>UART to Pi</td><td class="mono">TX / RX</td></tr>
        <tr><td class="pin">48</td><td>NeoPixel</td><td class="mono">mode colour feedback</td></tr>

        <tr><td rowspan="4">Lighting<br/>Output</td><td class="pin">4</td><td>Illumination sense</td><td class="mono">INPUT_PULLUP, LOW = night</td></tr>
        <tr><td class="pin">5</td><td>NeoPixel data (CH1)</td><td class="mono">330&Omega; · 4&times; Flora V2</td></tr>
        <tr><td class="pin">6</td><td>MOSFET PWM (CH2)</td><td class="mono">IRLZ44N · 5 kHz · 8-bit</td></tr>
        <tr><td class="pin">7</td><td>Dome relay</td><td class="mono">active HIGH</td></tr>
      </tbody>
    </table>
  </div>
  <div class="note">
    <p><strong>GPIO 5, 6, 7, 15, 16 on the iDrive board are free.</strong> They hold the
    unused SWC resistor ladder (<code>OUT_SWC 0</code>), kept as a fallback in case the
    radio's fixed ladder is ever worth chasing.</p>
  </div>
</section>

<section id="proto">
  <div class="sechead"><span class="n">06</span><h2>Wire protocols</h2></div>

  <h3>iDrive &rarr; Pi · newline-delimited JSON</h3>
  <pre class="proto"><b>{"mode":"HVAC","action":"TEMP_UP","count":2}</b>
mode    RADIO | HVAC | ILLUM | GAUGE
action  TEMP_UP TEMP_DOWN FAN_UP FAN_DOWN HVAC_TOGGLE
        HVAC_MODE_NEXT HVAC_MODE_PREV AUX_SWAP
        LIGHT_BRIGHTER LIGHT_DIMMER LIGHT_TOGGLE
        LIGHT_SCENE_NEXT LIGHT_SCENE_PREV  MODE_ENTER
        VOL_UP VOL_DOWN MUTE NEXT PREV   (mirror only — IR does the work)
count   detents in this frame, clamped 1..12</pre>

  <h3>Pi &harr; lighting board · text out, JSON back</h3>
  <pre class="proto"><b>L SET</b> &lt;ch&gt; &lt;val&gt;     absolute
<b>L ADJ</b> &lt;ch&gt; &lt;delta&gt;   relative — what the Pi actually sends
<b>L GET</b>                 request a state report

ch  1 = strip brightness   2 = MOSFET dimmer
    3 = dome relay         5 = palette index 0–9

<b>{"src":"illum","ch1":200,"ch2":128,"color":3,"relay":1,"night":0}</b></pre>

  <h3>Lighting knob &harr; output board · ESP-NOW, 4 bytes</h3>
  <pre class="proto">[ header ][ channel ][ value ][ channel XOR value ]

<b>0xAA</b>  knob &rarr; output   0x01 ch1 · 0x02 ch2 · 0x03 relay · 0x05 colour
<b>0xBB</b>  output &rarr; knob   0x04 day/night</pre>

  <div class="note">
    <p><strong>Lighting commands are relative, never absolute.</strong> The Pi cannot know
    current brightness — the round knob may change it at any moment — so it sends
    <code>L ADJ 1 +24</code> and the output board decides what that means, then reports
    the truth back. The board was already the owner of those values; this keeps it that
    way, and is the only thing stopping the two controllers from drifting apart.</p>
  </div>
</section>

<section id="bench">
  <div class="sechead"><span class="n">07</span><h2>Bench bring-up</h2></div>
  <p>Ordered so each step depends only on ones already passed. If a step fails, stop —
  later results will be misleading.</p>
  <ol class="steps">
    <li><b>Power the Pi alone</b>
      <span>No ESP boards, no loads. Confirm the backend comes up and the dashboard serves.</span>
      <span class="expect">systemctl is-active hvac-backend → active · http://944hvacpi.local:8000 renders</span></li>
    <li><b>Verify sensors before any actuator</b>
      <span>All three DS18B20s should read plausible room temperature, and the ADS1115 should answer.</span>
      <span class="expect">/api/state → onewire_ok true, ads_ok true, three distinct temps</span></li>
    <li><b>Flap travel, one at a time</b>
      <span>Drive each flap end to end and watch its feedback percentage track. The 8-second
      no-progress watchdog should cut the motor if a flap is disconnected.</span>
      <span class="expect">position sweeps 0→100 · disconnected flap sets *_fault true and stops</span></li>
    <li><b>Relays and solenoids</b>
      <span>Blower HI/LOW, A/C clutch, heat valve, fresh-air. All active-LOW — listen for the click.</span>
      <span class="expect">each energises on command, none energised at rest</span></li>
    <li><b>Seat heaters</b>
      <span>2 Hz PWM to the MOSFETs. Check duty at LOW/MED/HIGH (33/66/100%).</span>
      <span class="expect">visible slow pulsing, no buzz from the MOSFET board</span></li>
    <li><b>iDrive on CAN, bench-powered</b>
      <span>120&Omega; termination fitted, grounds common. It needs one physical button press
      to wake on the bench.</span>
      <span class="expect">serial shows PRESS lines for all 14 inputs</span></li>
    <li><b>iDrive UART into the Pi</b>
      <span>Turn the knob in HVAC mode and watch the setpoint follow on screen.</span>
      <span class="expect">idrive_last_s non-zero · clockwise raises setpoint</span></li>
    <li><b>IR at the head unit</b>
      <span>Aim the LED at the CP-71W's IR window from close range first.</span>
      <span class="expect">volume moves · if it works close but not from the dash, that is drive
      current — put the LED behind a 2N3904, do not touch the firmware</span></li>
    <li><b>Lighting board on USB</b>
      <span>Flash it with the core 2.0.14 toolchain, plug into the Pi, capture its USB serial,
      then enable the udev line.</span>
      <span class="expect">/dev/lighting appears · backend logs "lighting link up"</span></li>
  </ol>
</section>

<section id="traps">
  <div class="sechead"><span class="n">08</span><h2>Known traps</h2></div>
  <p>Each of these cost real debugging time. They share a shape: the symptom points
  somewhere other than the cause.</p>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Symptom</th><th>Actual cause</th></tr></thead>
      <tbody>
        <tr><td>LED lags, drops encoder events, looks like flaky hardware — then works
            perfectly the moment a terminal is opened</td>
            <td>USB CDC blocks on write with no host draining it, up to ~2 s per printf.
            Fix is <code>Serial.setTxTimeoutMs(0)</code>. Present on both ESP32 boards.</td></tr>
        <tr><td>Encoder dies after ~20 s of turning, buttons keep working</td>
            <td>Byte 2 of <code>0x25B</code> is not a two-state flag — it latches at 0x81
            during sustained rotation. Never gate rotation on it.</td></tr>
        <tr><td>Setpoint numerals shove the layout as the value changes</td>
            <td>Orbitron has no tabular figures — "1" is 0.391 em against 0.834 em for
            "0". <code>tabular-nums</code> is silently ignored; fixed cells are the fix.</td></tr>
        <tr><td>Serial link works, then reports "multiple access on port"</td>
            <td><code>console=serial0</code> left in cmdline.txt — the kernel console
            holds the same port.</td></tr>
        <tr><td>Flashing an ESP over the Pi works sometimes, fails others</td>
            <td>ModemManager probes new ttyACM devices with AT commands. udev rule
            ignores VID 303a.</td></tr>
        <tr><td>Flashing a board over the Pi dies partway with "No more data to
            read from the serial port"</td>
            <td>The backend holds that port. It grabs <code>/dev/lighting</code> the
            instant udev creates the symlink, then fights esptool for the device and
            leaves a half-written app partition. <code>flash-via-pi.sh</code> now stops
            and restarts the backend around the write.</td></tr>
        <tr><td>Dashboard "still looks old" after a rebuild</td>
            <td>Browser cache. Hard-refresh, or restart the kiosk.</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section id="harness">
  <div class="sechead"><span class="n">09</span><h2>Harness mapping — factory sheet 5</h2></div>
  <p>Read from <em>Wiring Diagram Type 944 / 944 turbo / 944 S, Model 87, Sheet 5</em>.
  The Pi substitutes for the <strong>Heating and A/C control switch</strong>, so almost
  everything below lands on that unit's <code>A</code> and <code>B</code> connectors.</p>

  <h3>German colour abbreviations</h3>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Abbr</th><th>German</th><th>Colour</th><th>Abbr</th><th>German</th><th>Colour</th></tr></thead>
      <tbody>
        <tr><td class="pin">SW</td><td class="mono">schwarz</td><td>black</td>
            <td class="pin">BR</td><td class="mono">braun</td><td>brown (ground)</td></tr>
        <tr><td class="pin">WS</td><td class="mono">weiß</td><td>white</td>
            <td class="pin">GR</td><td class="mono">grau</td><td>grey</td></tr>
        <tr><td class="pin">RT</td><td class="mono">rot</td><td>red</td>
            <td class="pin">BL</td><td class="mono">blau</td><td>blue</td></tr>
        <tr><td class="pin">GN</td><td class="mono">grün</td><td>green</td>
            <td class="pin">GE</td><td class="mono">gelb</td><td>yellow</td></tr>
        <tr><td class="pin">LI</td><td class="mono">lila</td><td>lilac / violet</td>
            <td class="pin">RS</td><td class="mono">rosa</td><td>pink</td></tr>
      </tbody>
    </table>
  </div>
  <p><code>1,0 SW/RT</code> reads as 1.0 mm² black with a red tracer — base colour first,
  stripe after the slash, cross-section in front.</p>

  <h3>Flap actuators — the bulk of the work</h3>
  <p>Each flap is one DC motor plus one feedback potentiometer in a single 5-pin
  connector. <strong>Pins 4 and 5 are the motor; 1, 2 and 3 are the pot, with pin 3 as
  the wiper.</strong> Handily, the wiper is the only un-striped wire in each family.</p>
  <div class="tablewrap">
    <table>
      <thead><tr>
        <th>Flap / Pi pins</th><th>Pin</th><th>Role</th><th>Wire</th><th>Terminal</th>
      </tr></thead>
      <tbody>
        <tr><td rowspan="5"><b>Defrost</b><br/><span class="mono">GPIO 16 / 20<br/>ADS A1</span></td>
            <td class="pin">4</td><td>motor</td><td class="mono">1,0 GN/SW</td><td class="mono">B11</td></tr>
        <tr><td class="pin">5</td><td>motor</td><td class="mono">1,0 WS/SW</td><td class="mono">B12</td></tr>
        <tr><td class="pin">2</td><td>pot end</td><td class="mono">0,5 SW/BL</td><td class="mono">B5</td></tr>
        <tr><td class="pin">3</td><td><b>wiper</b></td><td class="mono">0,5 SW</td><td class="mono">B7</td></tr>
        <tr><td class="pin">1</td><td>pot end</td><td class="mono">0,5 SW/RT</td><td class="mono">A6</td></tr>

        <tr><td rowspan="5"><b>Footwell</b><br/><span class="mono">GPIO 12 / 21<br/>ADS A2</span></td>
            <td class="pin">4</td><td>motor</td><td class="mono">1,0 GN/LI</td><td class="mono">B9</td></tr>
        <tr><td class="pin">5</td><td>motor</td><td class="mono">1,0 GN/WS</td><td class="mono">B10</td></tr>
        <tr><td class="pin">2</td><td>pot end</td><td class="mono">0,5 GN/BL</td><td class="mono">B3</td></tr>
        <tr><td class="pin">3</td><td><b>wiper</b></td><td class="mono">0,5 GN</td><td class="mono">B8</td></tr>
        <tr><td class="pin">1</td><td>pot end</td><td class="mono">0,5 GN/RT</td><td class="mono">A5</td></tr>

        <tr><td rowspan="5"><b>Blend / temp mix</b><br/><span class="mono">GPIO 23 / 24<br/>ADS A0</span></td>
            <td class="pin">4</td><td>motor</td><td class="mono">1,0 GR/SW</td><td class="mono">A10</td></tr>
        <tr><td class="pin">5</td><td>motor</td><td class="mono">1,0 GR/GN</td><td class="mono">A11</td></tr>
        <tr><td class="pin">2</td><td>pot end</td><td class="mono">0,5 GR/RT</td><td class="mono">A7</td></tr>
        <tr><td class="pin">3</td><td><b>wiper</b></td><td class="mono">0,5 GR</td><td class="mono">A12</td></tr>
        <tr><td class="pin">1</td><td>pot end</td><td class="mono">0,5 GR/BL</td><td class="mono">B6</td></tr>
      </tbody>
    </table>
  </div>
  <div class="note">
    <p><strong>Pot excitation is now your job.</strong> The factory control head fed
    these dividers; the Pi must. Your scaling constants — 225 mV at 0%, 4090 mV at 100% —
    imply roughly 5 V across the element, so the ADS1115 needs to be on 5 V too. On 3.3 V
    the top of travel clips and every reading above ~80% is wrong.</p>
    <p>On the blend flap the <code>/RT</code> and <code>/BL</code> ends read swapped
    relative to the other two. That may be deliberate (flap sense) or my reading of the
    scan — ohm it out before trusting the direction.</p>
  </div>

  <h3>Solenoids and A/C</h3>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Function</th><th>Pi</th><th>Wire</th><th>Terminal</th></tr></thead>
      <tbody>
        <tr><td>Heat valve solenoid</td><td class="mono">GPIO 19</td>
            <td class="mono">1,0 SW</td><td class="mono">A4</td></tr>
        <tr><td>Recirc / fresh-air solenoid</td><td class="mono">GPIO 26</td>
            <td class="mono">1,0 SW/GN</td><td class="mono">A3</td></tr>
        <tr><td>Solenoid common ground</td><td class="mono">—</td>
            <td class="mono">0,5 BR</td><td class="mono">chassis</td></tr>
        <tr><td>A/C clutch request &rarr; MS3</td><td class="mono">GPIO 18</td>
            <td class="mono">via A/C relay G17</td><td class="mono">sheet col. A–B</td></tr>
      </tbody>
    </table>
  </div>

  <h3>Blower — read this before wiring relays</h3>
  <p>The factory blower is <strong>four speeds</strong>, not two. A resistor pack
  (0.25 / 0.4 / 1.0 / 2.5 Ω in series) is tapped by the fresh-air blower switch:</p>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Switch pos.</th><th>Tap</th><th>Wire</th><th>Terminal</th><th>Result</th></tr></thead>
      <tbody>
        <tr><td class="pin">1</td><td>4</td><td class="mono">1,5 BR/WS</td><td class="mono">C1</td><td>slowest — full resistance</td></tr>
        <tr><td class="pin">2</td><td>3</td><td class="mono">1,5 WS/GE</td><td class="mono">C6</td><td>—</td></tr>
        <tr><td class="pin">3</td><td>2</td><td class="mono">2,5 WS</td><td class="mono">C3</td><td>—</td></tr>
        <tr><td class="pin">4</td><td>1</td><td class="mono">2,5 BR/SW</td><td class="mono">C5</td><td>fastest — least resistance</td></tr>
        <tr><td class="pin">—</td><td>motor</td><td class="mono">2,5 BR</td><td class="mono">ground</td><td>blower return</td></tr>
      </tbody>
    </table>
  </div>
  <div class="note stop">
    <p><strong>Your software models two speeds, the car has four.</strong>
    <code>fan_speed</code> is OFF / LOW / HI driving <code>GPIO 5</code> and
    <code>GPIO 6</code>, but the harness offers four taps. Pick two and accept the
    coarser control, or add two more relays and widen <code>fan_speed</code> — either
    is fine, but decide before wiring rather than discovering it at the bench.</p>
    <p>These are the fat wires on the sheet — 2.5 mm² carrying blower current. Size the
    relay contacts for the motor's stall draw, not its running draw.</p>
  </div>

  <h3>What you do <em>not</em> need to connect</h3>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Factory item</th><th>Why it is redundant</th></tr></thead>
      <tbody>
        <tr><td>Inside / outside / mixed-chamber temp sensors</td>
            <td>Replaced by your three DS18B20s on GPIO 4</td></tr>
        <tr><td>Heating and A/C control switch</td>
            <td>The Pi <em>is</em> this unit now — you are wiring into its connectors</td></tr>
        <tr><td>Fresh air blower switch</td>
            <td>Replaced by relays under Pi control</td></tr>
        <tr><td>Seat heater time relay and 4-way switches</td>
            <td>Bypassed — the Pi drives the elements through MOSFETs on GPIO 13 / 25</td></tr>
        <tr><td>Evaporator icing protection</td>
            <td>Series safety in the A/C circuit — leave it in place, do not bypass</td></tr>
      </tbody>
    </table>
  </div>

  <div class="note stop">
    <p><strong>Before applying power on the bench.</strong> Ohm every pot end-to-end
    (expect a few kΩ) and wiper-to-end (should sweep smoothly as the flap moves by hand).
    A pot wired where a motor belongs will be destroyed the instant an H-bridge drives it.</p>
    <p>Colours here are transcribed from a scan. Buzz each one out at the connector
    before you commit — the sheet is the map, the meter is the territory.</p>
  </div>
</section>

<footer>
  944S restomod electronics · pin data read from hvac_backend.py,
  idrive_controller.ino v1.6.0, pwm_controller.ino ·
  source at <code>docs/system-map.html</code> in pelosim/944_HVAC
</footer>

</div>
"""

out = pathlib.Path("docs/system-map.html")
out.write_text(HTML.replace("__ORB__", ORB))
print(f"wrote {out} — {out.stat().st_size:,} bytes")
