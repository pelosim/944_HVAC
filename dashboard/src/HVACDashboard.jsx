import { useState, useEffect, useCallback, useRef } from "react";

// ═══════════════════════════════════════════════════════════════
// 944S ELECTRONIC CLIMATE CONTROL — Horizontal Console
// Clean-sheet design for 1920×720. One continuous fascia:
//   BAND 1 (70px):  header rail — ID, annunciator, clock
//   BAND 2 (fills): instrument band — temps | setpoint | blower
//   BAND 3 (240px): control rail — modes, functions, seats
// Every band stretches edge-to-edge. No dead space.
// ═══════════════════════════════════════════════════════════════

// The physical panel. Everything is laid out at exactly this size and then
// scaled to fit — never reflowed. See the stage wrapper in the render.
const DESIGN_W = 1920;
const DESIGN_H = 720;

const C = {
  bg: "#04070a",
  fascia: "#0a0e13",
  fasciaHi: "#11161d",
  line: "#1c232c",
  lineHi: "#2a333e",
  vfd: "#2ce8d8",
  vfdHi: "#8ffff2",
  vfdDim: "rgba(44,232,216,0.15)",
  amber: "#ffb000",
  amberHi: "#ffd76a",
  amberDim: "rgba(255,176,0,0.15)",
  ice: "#5cb8ff",
  iceDim: "rgba(92,184,255,0.16)",
  red: "#ff3b30",
  green: "#3aff8c",
  text: "#eaf6f4",
  mid: "#8ea6a3",
  dim: "#46565a",
  segOff: "#10171a",
};

// ─── Vector icon set (crisp at any size) ──────────────────────
function Icon({ name, size = 30, color = C.mid, sw = 1.8, glow = false }) {
  const P = {
    face:    ["M14 5.5 a2 2 0 1 0 0.01 0", "M14 8 v5 l-2.5 5.5", "M14 10 h-3.5", "M4 8 h4.5 M7 5.5 L4.5 8 L7 10.5"],
    bilevel: ["M14 5.5 a2 2 0 1 0 0.01 0", "M14 8 v5 l-2.5 5.5", "M14 10 h-3.5", "M4 6 h4 M6.5 4 L4 6 L6.5 8", "M4 16.5 h4 M6.5 14.5 L4 16.5 L6.5 18.5"],
    feet:    ["M14 5.5 a2 2 0 1 0 0.01 0", "M14 8 v5 l-2.5 5.5", "M14 10 h-3.5", "M4 17.5 h4.5 M7 15 L4.5 17.5 L7 20"],
    defrost: ["M4 20 c6 0 11 -2.5 16 -8.5", "M7.5 14 c0 -2 1.5 -2 1.5 -4.5 M11.5 12.7 c0 -2 1.5 -2 1.5 -4.5 M15.5 11 c0 -2 1.5 -2 1.5 -4.5"],
    fan:     ["M12 12 m-1.7 0 a1.7 1.7 0 1 0 3.4 0 a1.7 1.7 0 1 0 -3.4 0",
              "M12 10.3 C12 5.8 15.2 4.9 16.7 6.6 C18.1 8.2 15.9 10.6 13.4 11",
              "M13.5 13.1 C17.4 15.3 16.7 18.5 14.6 19.1 C12.5 19.8 11.3 16.7 12.4 14.4",
              "M10.5 13.1 C6.6 15.3 4.7 12.6 5.5 10.6 C6.3 8.6 9.6 9.4 10.9 11.5"],
    snow:    ["M12 3 v18 M12 3.5 l-2.3 2.3 M12 3.5 l2.3 2.3 M12 20.5 l-2.3 -2.3 M12 20.5 l2.3 -2.3",
              "M4.2 7.5 l15.6 9 M4.6 7.7 l3.2 -0.85 M4.6 7.7 l0.85 3.2 M19.4 16.3 l-3.2 0.85 M19.4 16.3 l-0.85 -3.2",
              "M19.8 7.5 l-15.6 9 M19.4 7.7 l-3.2 -0.85 M19.4 7.7 l-0.85 3.2 M4.6 16.3 l3.2 0.85 M4.6 16.3 l0.85 -3.2"],
    heat:    ["M6.5 20 c0 -3 2 -3 2 -6 c0 -2 -1 -2.5 -1 -4.5 c0 -2 2 -4 2 -4",
              "M13 20 c0 -3 2 -3 2 -6 c0 -2 -1 -2.5 -1 -4.5 c0 -2 2 -4 2 -4"],
    fresh:   ["M3 12 h11.5 M11.5 8.5 L15 12 L11.5 15.5", "M17.5 5 c3 2 4 4.8 4 7 c0 2.2 -1 5 -4 7"],
    recirc:  ["M12 5 a7 7 0 1 1 -6.4 4", "M5.3 4.3 v4.7 h4.7"],
    seat:    ["M7.5 3.5 c-1.6 0 -2.1 1.1 -2 2.6 l0.7 8.4 c0.15 1.5 1 2 2.3 2 h5.2 l3.2 3.7",
              "M15.2 12.5 c0.5 -1.6 -0.7 -2.1 -0.35 -3.7 M18.4 12.5 c0.5 -1.6 -0.7 -2.1 -0.35 -3.7"],
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"
      style={glow ? { filter: `drop-shadow(0 0 5px ${color})` } : undefined}>
      {(P[name] || []).map((d, i) => <path key={i} d={d} />)}
    </svg>
  );
}

// ─── Fixed-cell numerals ──────────────────────────────────────
// Orbitron is NOT a tabular font. Measured from the font file itself:
// "1" has an advance of 0.391 em while "0" and "8" are 0.834 em — less
// than half. At the 210px setpoint that is a ~92px swing from a single
// character, so 71 -> 72 visibly shoved the whole centre column.
//
// font-variant-numeric: tabular-nums cannot help; Orbitron ships no
// "tnum" feature, so the declaration is silently ignored. The only
// reliable fix is to give every glyph its own fixed cell, which is also
// how a real segmented display behaves.
const ORB_CELL_EM = 0.834;   // widest digit advance, measured

function Digits({ value, size }) {
  return String(value).split("").map((ch, i) => (
    <span key={i} style={{
      display: "inline-block", width: size * ORB_CELL_EM, textAlign: "center",
    }}>{ch}</span>
  ));
}

// ─── Segmented VFD bar ────────────────────────────────────────
function Segs({ value, max = 100, n = 24, color = C.vfd, h = 14, vertical = false }) {
  const lit = Math.round((Math.max(0, Math.min(max, value)) / max) * n);
  const cells = Array.from({ length: n });
  return (
    <div style={{
      display: "flex", gap: 3, width: vertical ? h : "100%", height: vertical ? "100%" : h,
      flexDirection: vertical ? "column-reverse" : "row",
    }}>
      {cells.map((_, i) => {
        const on = i < lit;
        return <div key={i} style={{
          flex: 1, borderRadius: 2,
          background: on ? color : C.segOff,
          boxShadow: on ? `0 0 7px ${color}90` : "inset 0 1px 2px rgba(0,0,0,0.65)",
          transform: vertical ? "skewY(6deg)" : "skewX(-8deg)",
          transition: "background 0.12s, box-shadow 0.12s",
        }} />;
      })}
    </div>
  );
}

// ─── LED annunciator lamp ─────────────────────────────────────
function Lamp({ label, on, color = C.green, blink = false }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <div style={{
        width: 12, height: 12, borderRadius: 2, flexShrink: 0,
        background: on ? color : C.segOff,
        boxShadow: on ? `0 0 10px ${color}` : "inset 0 1px 2px rgba(0,0,0,0.7)",
        transition: "all 0.25s",
        animation: on && blink ? "pulse 1s ease-in-out infinite" : "none",
      }} />
      <span style={{
        fontFamily: "'Rajdhani',sans-serif", fontSize: 18, fontWeight: 700,
        letterSpacing: 1.8, color: on ? C.text : C.dim, whiteSpace: "nowrap",
      }}>{label}</span>
    </div>
  );
}

// ─── Directional chevrons (flow toward commanded target) ──────
function Chevrons({ dir, color, size = 24 }) {
  const n = 3;
  return (
    <div style={{ display: "flex", gap: 1, alignItems: "center" }}>
      {Array.from({ length: n }).map((_, i) => {
        const order = dir > 0 ? i : n - 1 - i; // stagger so the flow points the travel way
        return (
          <svg key={i} width={size * 0.62} height={size} viewBox="0 0 18 26" fill="none">
            <path d={dir > 0 ? "M5 5 L12 13 L5 21" : "M13 5 L6 13 L13 21"}
              stroke={color} strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round"
              style={{
                animation: "flapChev 0.8s ease-in-out infinite",
                animationDelay: `${order * 0.13}s`,
                filter: `drop-shadow(0 0 4px ${color})`,
              }} />
          </svg>
        );
      })}
    </div>
  );
}

// ─── Flap track: segmented actual fill + commanded-target caret ─
function FlapTrack({ actual, target, base, dirColor, dir, n = 22, h = 16 }) {
  const lo = Math.min(actual, target);
  const hi = Math.max(actual, target);
  const tgt = Math.max(0, Math.min(100, target));
  const markColor = dir === 0 ? base : dirColor;
  return (
    <div style={{ position: "relative", paddingTop: 10 }}>
      {/* commanded-target caret */}
      <div style={{
        position: "absolute", top: 0, left: `${tgt}%`, transform: "translateX(-50%)",
        width: 0, height: 0, borderLeft: "6px solid transparent", borderRight: "6px solid transparent",
        borderTop: `8px solid ${markColor}`,
        filter: `drop-shadow(0 0 4px ${markColor})`,
        transition: "left 0.25s ease",
      }} />
      <div style={{ display: "flex", gap: 3, height: h }}>
        {Array.from({ length: n }).map((_, i) => {
          const c = ((i + 0.5) / n) * 100;
          const solid = c <= lo;                        // guaranteed position
          const inDelta = dir !== 0 && c > lo && c <= hi; // sweep zone — only while driving
          return (
            <div key={i} style={{
              flex: 1, borderRadius: 2,
              background: solid ? base : inDelta ? dirColor : C.segOff,
              boxShadow: solid ? `0 0 7px ${base}90`
                : inDelta ? `0 0 6px ${dirColor}80`
                : "inset 0 1px 2px rgba(0,0,0,0.65)",
              transform: "skewX(-8deg)",
              animation: inDelta ? "flapSweep 0.9s ease-in-out infinite" : "none",
              animationDelay: inDelta ? `${(dir >= 0 ? i : n - i) * 0.05}s` : "0s",
              transition: "background 0.12s, box-shadow 0.12s",
            }} />
          );
        })}
      </div>
    </div>
  );
}

// ─── iDrive knob mirror ───────────────────────────────────────
// Mirrors the physical BMW knob on the console. The ring rotates one
// tick per detent, so the on-screen knob turns exactly as your hand
// does — the dashboard becomes a readout for a control you cannot see
// while driving.
//
// Values shown are only those the Pi genuinely knows. The head unit's
// volume is owned by the radio over IR and never reaches the backend,
// so MEDIA mode reports the direction of travel rather than inventing
// a number.
const IDRIVE_MODES = {
  radio: { label: "RADIO", color: C.vfd,     param: "VOLUME" },
  hvac:  { label: "HVAC",  color: C.amber,   param: "SETPOINT" },
  illum: { label: "ILLUM", color: "#9c40ff", param: "BRIGHTNESS" },
  gauge: { label: "GAUGE", color: C.ice,     param: "AUX PAGE" },
};

function KnobMirror({ mode, detents, action, active, setpoint, auxDisplay, illumCh1 }) {
  const m = IDRIVE_MODES[mode] || IDRIVE_MODES.radio;
  const tint = active ? m.color : C.dim;
  const ticks = 24;
  const angle = (detents % ticks) * (360 / ticks);

  let value = "—";
  if (mode === "hvac") value = `${Math.round(setpoint)}°`;
  else if (mode === "gauge") value = auxDisplay === "gmeter" ? "G" : "CLK";
  else if (mode === "illum") value = `${Math.round((illumCh1 / 255) * 100)}%`;
  else if (mode === "radio") {
    if (action === "VOL_UP") value = "▲";
    else if (action === "VOL_DOWN") value = "▼";
    else if (action === "MUTE") value = "MUTE";
    else if (action === "NEXT") value = "▶▶";
    else if (action === "PREV") value = "◀◀";
  }

  return (
    <div style={{ width: 190, display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 10 }}>
      <span style={{
        fontFamily: "'Rajdhani',sans-serif", fontSize: 19, fontWeight: 700,
        letterSpacing: 3, color: tint,
        textShadow: active ? `0 0 10px ${m.color}80` : "none",
      }}>{m.label}</span>

      <div style={{ position: "relative", width: 132, height: 132 }}>
        <svg width="132" height="132" viewBox="0 0 132 132"
          style={{ transform: `rotate(${angle}deg)`, transition: "transform 140ms linear" }}>
          {Array.from({ length: ticks }).map((_, i) => {
            const a = (i / ticks) * Math.PI * 2 - Math.PI / 2;
            const rOut = 62, rIn = i % 6 === 0 ? 48 : 54;
            return (
              <line key={i}
                x1={66 + Math.cos(a) * rIn}  y1={66 + Math.sin(a) * rIn}
                x2={66 + Math.cos(a) * rOut} y2={66 + Math.sin(a) * rOut}
                stroke={tint} strokeWidth={i % 6 === 0 ? 2.6 : 1.4}
                strokeLinecap="round" opacity={i % 6 === 0 ? 1 : 0.55} />
            );
          })}
        </svg>
        <div style={{
          position: "absolute", inset: 0, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 2,
        }}>
          <span style={{
            fontFamily: "'Orbitron',monospace", fontWeight: 700,
            fontSize: value.length > 3 ? 22 : 34, lineHeight: 1,
            color: tint, fontVariantNumeric: "tabular-nums",
            textShadow: active ? `0 0 16px ${m.color}70` : "none",
          }}>{value}</span>
        </div>
      </div>

      <span style={{
        fontFamily: "'Rajdhani',sans-serif", fontSize: 15, fontWeight: 600,
        letterSpacing: 2, color: active ? C.text : C.dim,
      }}>{m.param}</span>
    </div>
  );
}

// ─── Column divider (machined groove) ─────────────────────────
function Groove() {
  return <div style={{
    width: 2, alignSelf: "stretch", flexShrink: 0,
    background: `linear-gradient(180deg, transparent, ${C.line} 12%, ${C.line} 88%, transparent)`,
    boxShadow: "1px 0 0 rgba(255,255,255,0.03)",
  }} />;
}

// ═══════════════════════════════════════════════════════════════
// ════════════════════════════════════════════════════════════════
// SYSTEM STATUS — link topology (BACK button on the iDrive)
// ════════════════════════════════════════════════════════════════
// Colour is state, layout is the car: a broken link is a PLACE, so you
// find it by looking rather than by reading nine rows.
//
// Three states, and the third one is the point. "unknown" is not a
// softer red — it means this link has no feedback path and never will,
// so we cannot claim to have checked it. IR is write-only; the MS3 feed
// and the ESP-NOW hop both live on hardware this Pi cannot see. Drawing
// those green would be the exact failure this screen exists to prevent:
// a wall of green that sends you to the wrong half of the car.
const S_OK = "ok", S_BAD = "fault", S_UNK = "unknown";
const stColor = (st) => (st === S_OK ? C.green : st === S_BAD ? C.red : C.dim);

// Seconds since a link last spoke, as something you can read at speed.
// The backend sends -1 for "has never spoken at all", which must not
// render as a confident "0s".
function ageText(a) {
  if (a === undefined || a === null || a < 0) return "--";
  if (a < 10) return `${a.toFixed(1)}s`;
  if (a < 600) return `${Math.round(a)}s`;
  return `${Math.round(a / 60)}m`;
}

function SysNode({ x, y, w = 250, h = 64, title, sub, st }) {
  const col = stColor(st);
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={7} fill="#0C1416"
        stroke={col} strokeWidth={st === S_BAD ? 3 : 2} />
      <text x={x + w / 2} y={y + (sub ? 28 : 40)} textAnchor="middle"
        fontFamily="'Orbitron',monospace" fontSize={23} fontWeight={700}
        fill={st === S_UNK ? C.mid : C.text}>{title}</text>
      {sub && (
        <text x={x + w / 2} y={y + 50} textAnchor="middle"
          fontFamily="'Rajdhani',sans-serif" fontSize={18} fill={col}>{sub}</text>
      )}
    </g>
  );
}

function SysLink({ d, st, label, lx, ly }) {
  const col = stColor(st);
  return (
    <g>
      <path d={d} fill="none" stroke={col} strokeWidth={st === S_BAD ? 5 : 3}
        markerEnd="url(#sysArrow)"
        strokeDasharray={st === S_UNK ? "7 5" : undefined} />
      {label && (
        <text x={lx} y={ly} textAnchor="middle" fontFamily="'Orbitron',monospace"
          fontSize={15} fill={C.dim}>{label}</text>
      )}
    </g>
  );
}

// The knob's mode, mirrored here on purpose. You may well be reading this
// page while the knob is pointed at the lighting board or the TunerStudio
// dash, and without this there is nothing on screen telling you which — so
// a turn would go somewhere you did not expect. Colours match the
// controller's own NeoPixel exactly, so the LED in your hand and the badge
// on the screen always agree.
const MODE_TINT = {
  radio:  "#2CE8D8",   // phosphor teal
  hvac:   "#FFB000",   // amber
  illum:  "#9C40FF",   // violet
  gauge:  "#5CB8FF",   // ice blue
  tsdash: "#3AFF8C",   // spring green
};

function KnobBadge({ mode, action, active }) {
  const tint = MODE_TINT[mode] || C.mid;
  return (
    <g>
      <rect x="700" y="24" width="520" height="46" rx="8"
        fill={active ? `${tint}1A` : "none"} stroke={tint} strokeWidth={active ? 3 : 2} />
      <text x="726" y="54" fontFamily="'Rajdhani',sans-serif" fontSize="19"
        fill={C.mid} letterSpacing="2">KNOB</text>
      <text x="806" y="54" fontFamily="'Orbitron',monospace" fontSize="25"
        fontWeight="800" fill={tint}>{(mode || "?").toUpperCase()}</text>
      <text x="1196" y="53" textAnchor="end" fontFamily="'Rajdhani',sans-serif"
        fontSize="18" fill={C.dim}>{action || "—"}</text>
    </g>
  );
}

function SystemStatus({ st, onClose }) {
  // ── Derive each link's state from what the backend can actually see ──
  const flapFault = st.mixFault || st.defFault || st.footFault;
  const L = {
    can:    st.idriveOnline ? (st.idriveAction ? S_OK : S_UNK) : S_UNK,
    // "never spoken since boot" is not the same claim as "was working, now
    // silent", and only the second is a fault. An iDrive still running
    // firmware older than 1.8.0 has no heartbeat at all, so it lands in the
    // first case — grey and labelled, rather than a red that is not earned.
    uart:   st.idriveOnline ? S_OK : st.idriveAge < 0 ? S_UNK : S_BAD,
    ir:     S_UNK,                                   // write-only, always
    hw:     st.onewireOk && st.adsOk && !flapFault ? S_OK : S_BAD,
    panel:  st.wsConnected ? S_OK : S_BAD,           // we are drawing, so it is up
    aux:    S_UNK,                                   // no return path
    light:  st.illumOnline ? S_OK : S_BAD,
    espnow: S_UNK,                                   // knob talks to the board, not us
    bridge: st.tsdashOnline ? S_OK : S_BAD,
    hid:    !st.tsdashOnline ? S_UNK : st.tsdashUsb ? S_OK : S_BAD,
    ms3:    S_UNK,                                   // on the other Pi
  };
  const vals = Object.values(L);
  const nBad = vals.filter((v) => v === S_BAD).length;
  const nUnk = vals.filter((v) => v === S_UNK).length;
  const nOk  = vals.filter((v) => v === S_OK).length;

  // Worst first. Unknowns are listed too — quietly, because they are
  // permanent facts about the wiring rather than things to go and fix.
  const attention = [];
  if (L.hid === S_BAD) attention.push([C.red, "BRIDGE -> TSDASH",
    st.tsdashInit ? "stack up (init:1), no host on the native port" : "USB stack failed to start"]);
  if (L.uart === S_BAD) attention.push([C.red, "iDRIVE -> Pi",
    `heartbeat stopped ${ageText(st.idriveAge)} ago`]);
  if (L.uart === S_UNK) attention.push([C.dim, "iDRIVE -> Pi",
    "no heartbeat since boot - needs firmware 1.8.0"]);
  if (L.bridge === S_BAD) attention.push([C.red, "Pi -> DASH BRIDGE", "/dev/tsdash not answering"]);
  if (L.light === S_BAD) attention.push([C.red, "Pi -> LIGHTING", "/dev/lighting not answering"]);
  if (L.hw === S_BAD) attention.push([C.red, "HVAC HARDWARE",
    flapFault ? "flap travel fault" : !st.onewireOk ? "1-Wire bus down" : "ADS1115 not answering"]);
  attention.push([C.dim, "HEAD UNIT - IR", "write-only, no feedback path"]);
  attention.push([C.dim, "MS3 -> TSDASH", "not visible from this Pi"]);

  return (
    <div onClick={onClose} style={{
      position: "absolute", inset: 0, zIndex: 30, background: C.bg, cursor: "pointer",
    }}>
      <svg viewBox="0 0 1920 720" width="100%" height="100%"
        role="img" aria-label="System status: link topology">
        <defs>
          <marker id="sysArrow" markerWidth="8" markerHeight="8" refX="7" refY="3"
            orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L7,3 z" fill="context-stroke" />
          </marker>
        </defs>

        {/* header */}
        <line x1="0" y1="92" x2="1920" y2="92" stroke={C.dim} strokeWidth="2" />
        <text x="44" y="52" fontFamily="'Orbitron',monospace" fontSize="34"
          fontWeight="800" fill={C.vfd} letterSpacing="3">SYSTEM STATUS</text>
        <text x="44" y="77" fontFamily="'Rajdhani',sans-serif" fontSize="19"
          fill={C.mid} letterSpacing="3">LINK TOPOLOGY - LIVE</text>
        <KnobBadge mode={st.idriveMode} action={st.idriveAction} active={st.idriveActive} />
        <text x="1876" y="48" textAnchor="end" fontFamily="'Orbitron',monospace"
          fontSize="30" fontWeight="800" fill={nBad ? C.red : C.green}>
          {nBad ? `${nBad} FAULT${nBad > 1 ? "S" : ""}` : "ALL LINKS OK"}
        </text>
        <text x="1876" y="77" textAnchor="end" fontFamily="'Rajdhani',sans-serif"
          fontSize="19" fill={C.mid} letterSpacing="2">
          {nOk} OK - {nUnk} NO FEEDBACK PATH
        </text>

        {/* links */}
        <SysLink d="M296,146 L336,146"   st={L.can}    label="CAN"  lx={316} ly={136} />
        <SysLink d="M596,146 L636,146"   st={L.ir}     label="IR"   lx={616} ly={136} />
        <SysLink d="M466,178 L466,246"   st={L.uart}   label="UART" lx={506} ly={220} />
        <SysLink d="M596,286 L636,250"   st={L.hw} />
        <SysLink d="M596,306 L636,330"   st={L.panel} />
        <SysLink d="M596,326 L636,410"   st={L.aux} />
        <SysLink d="M466,350 L466,556"   st={L.light}  label="USB"  lx={504} ly={470} />
        <SysLink d="M596,330 L636,494"   st={L.bridge} />
        <SysLink d="M896,522 L936,522"   st={L.hid}    label="HID"  lx={916} ly={506} />
        <SysLink d="M1456,522 L1196,522" st={L.ms3}    label="FTDI" lx={1326} ly={506} />
        <SysLink d="M296,588 L336,588"   st={L.espnow} label="NOW"  lx={316} ly={578} />
        <SysLink d="M596,588 L636,588"   st={L.light} />

        {/* nodes */}
        <SysNode x={46}   y={114} title="iDRIVE KNOB"   st={L.can} />
        <SysNode x={336} y={114} w={260} title="iDRIVE ESP32"
          sub={st.idriveOnline ? ageText(st.idriveAge)
               : st.idriveAge < 0 ? "no heartbeat" : "silent"} st={L.uart} />
        <SysNode x={636}  y={114} title="HEAD UNIT"     st={L.ir} />
        <SysNode x={336}  y={246} w={260} h={104} title="HVAC Pi"
          sub={`up ${Math.floor(st.uptime / 3600)}h ${Math.floor((st.uptime % 3600) / 60)}m`}
          st={S_OK} />
        <SysNode x={636}  y={218} title="HVAC HARDWARE" st={L.hw} />
        <SysNode x={636}  y={298} title="TOUCHSCREEN"   st={L.panel} />
        <SysNode x={636}  y={378} title="AUX SCREEN"    st={L.aux} />
        <SysNode x={636}  y={490} w={260} title="DASH BRIDGE"
          sub={st.tsdashOnline ? ageText(st.tsdashAge) : "offline"} st={L.bridge} />
        <SysNode x={936}  y={490} w={260} title="TSDASH Pi"
          sub={L.hid === S_OK ? "host up" : L.hid === S_BAD ? "no host - usb:0" : "unknown"}
          st={L.hid} />
        <SysNode x={1456} y={490} title="MS3-PRO EVO"   st={L.ms3} />
        <SysNode x={46}   y={556} title="LIGHT KNOB"    st={L.espnow} />
        <SysNode x={336}  y={556} w={260} title="LIGHT ESP32"
          sub={st.illumOnline ? ageText(st.illumAge) : "offline"} st={L.light} />
        <SysNode x={636}  y={556} title="LED LOADS"     st={L.light} />

        {/* needs-attention rail */}
        <line x1="1236" y1="120" x2="1236" y2="452" stroke={C.dim} strokeWidth="2" />
        <text x="1276" y="146" fontFamily="'Rajdhani',sans-serif" fontSize="19"
          fill={C.mid} letterSpacing="3">NEEDS ATTENTION</text>
        {attention.slice(0, 4).map(([col, head, body], i) => (
          <g key={head}>
            <rect x="1276" y={168 + i * 74} width="6" height="52" fill={col} />
            <text x="1300" y={192 + i * 74} fontFamily="'Orbitron',monospace"
              fontSize="21" fontWeight="700" fill={col === C.dim ? C.mid : col}>{head}</text>
            <text x="1300" y={214 + i * 74} fontFamily="'Rajdhani',sans-serif"
              fontSize="18" fill={C.dim}>{body}</text>
          </g>
        ))}

        {/* legend */}
        <line x1="0" y1="656" x2="1920" y2="656" stroke={C.dim} strokeWidth="2" />
        <g fontFamily="'Rajdhani',sans-serif" fontSize="19" fill={C.mid}>
          <rect x="44" y="681" width="26" height="6" fill={C.green} />
          <text x="82" y="694">HEALTHY</text>
          <rect x="230" y="681" width="26" height="6" fill={C.red} />
          <text x="268" y="694">FAULT</text>
          <rect x="392" y="681" width="26" height="6" fill={C.dim} />
          <text x="430" y="694">NO FEEDBACK PATH</text>
          <text x="1876" y="694" textAnchor="end" fill={C.dim}>
            BACK BUTTON OR TAP TO EXIT
          </text>
        </g>
      </svg>
    </div>
  );
}

export default function HVACDashboard() {
  // ─── WebSocket ────────────────────────────────────────────
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const pendingRef = useRef({}); // fields we've just commanded, awaiting backend echo
  const [wsConnected, setWsConnected] = useState(false);

  // ─── Synced state ─────────────────────────────────────────
  const [setpoint, setSetpoint] = useState(72);
  const [fanSpeed, setFanSpeed] = useState("LOW");
  const [acOn, setAcOn] = useState(false);
  const [heatValve, setHeatValve] = useState(false);
  const [outsideAir, setOutsideAir] = useState(true);
  const [ventMode, setVentMode] = useState("face");
  const [maxAc, setMaxAc] = useState(false);
  const [driverSeatHeat, setDriverSeatHeat] = useState(0);
  const [passengerSeatHeat, setPassengerSeatHeat] = useState(0);
  const [mixTemp, setMixTemp] = useState(68.4);
  const [extTemp, setExtTemp] = useState(47);
  const [interiorTemp, setInteriorTemp] = useState(72);
  const [testOverride, setTestOverride] = useState(false);
  const [testInteriorTemp, setTestInteriorTemp] = useState(72);
  const [auxDisplay, setAuxDisplay] = useState("clock");
  const [mixFlap, setMixFlap] = useState(35);
  const [defrostFlap, setDefrostFlap] = useState(0);
  const [footFlap, setFootFlap] = useState(0);
  const [mixFlapTarget, setMixFlapTarget] = useState(50);
  const [defrostFlapTarget, setDefrostFlapTarget] = useState(0);
  const [footFlapTarget, setFootFlapTarget] = useState(0);
  const [mixFlapFault, setMixFlapFault] = useState(false);
  const [defrostFlapFault, setDefrostFlapFault] = useState(false);
  const [footFlapFault, setFootFlapFault] = useState(false);
  const [onewireOk, setOnewireOk] = useState(false);
  const [adsOk, setAdsOk] = useState(false);
  const [controlActive, setControlActive] = useState(false);
  const [time, setTime] = useState(new Date());
  const [stageScale, setStageScale] = useState(1);
  const [idriveMode, setIdriveMode] = useState("radio");

  // ─── System status page ───────────────────────────────────
  const [systemView, setSystemView] = useState(false);
  const [idriveOnline, setIdriveOnline] = useState(false);
  const [idriveAge, setIdriveAge] = useState(-1);
  const [illumOnline, setIllumOnline] = useState(false);
  const [illumAge, setIllumAge] = useState(-1);
  const [tsdashOnline, setTsdashOnline] = useState(false);
  const [tsdashAge, setTsdashAge] = useState(-1);
  const [tsdashInit, setTsdashInit] = useState(false);
  const [tsdashUsb, setTsdashUsb] = useState(false);
  const [uptime, setUptime] = useState(0);
  const [idriveDetents, setIdriveDetents] = useState(0);
  const [idriveAction, setIdriveAction] = useState("");
  const [idriveActive, setIdriveActive] = useState(false);
  const [illumCh1, setIllumCh1] = useState(0);

  const sendCmd = useCallback((cmd) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      // Remember what we just commanded so stale in-flight broadcasts for these
      // fields can't momentarily revert the UI before the backend confirms.
      const expires = Date.now() + 800;
      for (const k in cmd) pendingRef.current[k] = { value: cmd[k], expires };
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  useEffect(() => {
    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${window.location.host}/ws`);
      ws.onopen = () => {
        setWsConnected(true);
        if (reconnectRef.current) { clearInterval(reconnectRef.current); reconnectRef.current = null; }
      };
      ws.onmessage = (event) => {
        try {
          const s = JSON.parse(event.data);
          const now = Date.now();
          // Apply a field unless we have an unconfirmed command for it. This
          // drops stale in-flight echoes that would briefly revert a control
          // you just pressed, until the backend confirms the new value (or 800ms).
          const apply = (key, setter) => {
            if (s[key] === undefined) return;
            const p = pendingRef.current[key];
            if (p) {
              if (now <= p.expires && s[key] !== p.value) return; // stale echo — ignore
              delete pendingRef.current[key];                     // confirmed or timed out
            }
            setter(s[key]);
          };
          apply("setpoint_f", setSetpoint);
          apply("fan_speed", setFanSpeed);
          apply("ac_on", setAcOn);
          apply("heat_valve", setHeatValve);
          apply("outside_air", setOutsideAir);
          apply("vent_mode", setVentMode);
          apply("mix_chamber_temp_f", setMixTemp);
          apply("exterior_temp_f", setExtTemp);
          apply("interior_temp_f", setInteriorTemp);
          apply("test_override", setTestOverride);
          apply("test_interior_temp_f", setTestInteriorTemp);
          apply("aux_display", setAuxDisplay);
          apply("idrive_mode", setIdriveMode);
          apply("idrive_detents", setIdriveDetents);
          apply("idrive_action", setIdriveAction);
          apply("idrive_active", setIdriveActive);
          apply("illum_ch1", setIllumCh1);
          apply("mix_flap_pos", setMixFlap);
          apply("defrost_flap_pos", setDefrostFlap);
          apply("footwell_flap_pos", setFootFlap);
          apply("mix_flap_target", setMixFlapTarget);
          apply("defrost_flap_target", setDefrostFlapTarget);
          apply("footwell_flap_target", setFootFlapTarget);
          apply("mix_flap_fault", setMixFlapFault);
          apply("defrost_flap_fault", setDefrostFlapFault);
          apply("footwell_flap_fault", setFootFlapFault);
          apply("seat_heat_driver", setDriverSeatHeat);
          apply("seat_heat_passenger", setPassengerSeatHeat);
          apply("onewire_ok", setOnewireOk);
          apply("ads_ok", setAdsOk);
          apply("control_active", setControlActive);
          apply("system_view", setSystemView);
          apply("idrive_online", setIdriveOnline);
          apply("idrive_age_s", setIdriveAge);
          apply("illum_online", setIllumOnline);
          apply("illum_age_s", setIllumAge);
          apply("tsdash_online", setTsdashOnline);
          apply("tsdash_age_s", setTsdashAge);
          apply("tsdash_init", setTsdashInit);
          apply("tsdash_usb", setTsdashUsb);
          apply("uptime_s", setUptime);
        } catch (e) { /* ignore */ }
      };
      ws.onclose = () => {
        setWsConnected(false);
        wsRef.current = null;
        if (!reconnectRef.current) reconnectRef.current = setInterval(connect, 2000);
      };
      ws.onerror = () => ws.close();
      wsRef.current = ws;
    };
    connect();
    return () => {
      if (reconnectRef.current) clearInterval(reconnectRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEffect(() => {
    const iv = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(iv);
  }, []);

  // Fit the fixed 1920x720 stage into whatever viewport we are in.
  useEffect(() => {
    const fit = () => setStageScale(Math.min(
      window.innerWidth / DESIGN_W, window.innerHeight / DESIGN_H));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  // ─── Commands ─────────────────────────────────────────────
  const cmdSetpoint = (v) => {
    const val = Math.max(60, Math.min(90, v));
    setSetpoint(val); sendCmd({ setpoint_f: val });
  };
  const cmdFanSpeed = (v) => { setFanSpeed(v); sendCmd({ fan_speed: v }); };
  // Tap-to-dismiss mirrors the BACK button. Sent as an explicit false rather
  // than "toggle" so a tap can never race the knob into re-opening the page.
  const cmdCloseSystem = () => { setSystemView(false); sendCmd({ system_view: false }); };
  const cmdAcOn = (v) => { setAcOn(v); sendCmd({ ac_on: v }); };
  const cmdHeatValve = (v) => { setHeatValve(v); sendCmd({ heat_valve: v }); };
  const cmdOutsideAir = (v) => { setOutsideAir(v); sendCmd({ outside_air: v }); };
  const cmdVentMode = (v) => { setVentMode(v); sendCmd({ vent_mode: v }); };
  const cmdDriverSeatHeat = (v) => { setDriverSeatHeat(v); sendCmd({ seat_heat_driver: v }); };
  const cmdPassengerSeatHeat = (v) => { setPassengerSeatHeat(v); sendCmd({ seat_heat_passenger: v }); };
  const cmdTestOverride = (v) => {
    setTestOverride(v);
    if (v) {
      const seed = Math.round(interiorTemp); // start from the current cabin reading
      setTestInteriorTemp(seed);
      sendCmd({ test_override: true, test_interior_temp_f: seed });
    } else {
      sendCmd({ test_override: false });
    }
  };
  const cmdAuxDisplay = (v) => { setAuxDisplay(v); sendCmd({ aux_display: v }); };
  const cmdTestInteriorTemp = (v) => {
    const val = Math.max(20, Math.min(140, Math.round(v)));
    setTestInteriorTemp(val); sendCmd({ test_interior_temp_f: val });
  };

  // Hold-to-repeat for setpoint
  const holdRef = useRef(null);
  const spRef = useRef(setpoint);
  spRef.current = setpoint;
  const startHold = (dir) => {
    cmdSetpoint(spRef.current + dir);
    holdRef.current = setInterval(() => cmdSetpoint(spRef.current + dir), 170);
  };
  const stopHold = () => clearInterval(holdRef.current);

  const toggleMaxAc = () => {
    if (!maxAc) {
      setMaxAc(true);
      sendCmd({ setpoint_f: 60, fan_speed: "HI", ac_on: true, heat_valve: false, outside_air: false });
    } else {
      setMaxAc(false);
      sendCmd({ setpoint_f: 72, fan_speed: "LOW" });
    }
  };
  useEffect(() => {
    if (maxAc && (!acOn || fanSpeed !== "HI")) setMaxAc(false);
  }, [acOn, fanSpeed, maxAc]);

  // ─── Derived ──────────────────────────────────────────────
  const modeLabel = maxAc ? "MAX A/C" : fanSpeed === "OFF" ? "SYSTEM OFF"
    : acOn ? "COOLING" : heatValve ? "HEATING" : "VENTILATION";
  const modeColor = maxAc ? C.ice : heatValve ? C.amber : acOn ? C.ice
    : fanSpeed !== "OFF" ? C.vfd : C.red;
  const spColor = setpoint > 80 ? C.amber : setpoint < 68 ? C.ice : C.vfd;
  const fanPct = fanSpeed === "HI" ? 100 : fanSpeed === "LOW" ? 50 : 0;
  const seatColor = (v) => v > 66 ? C.amber : v > 33 ? "#ffc23d" : v > 0 ? "#ffd97a" : C.dim;
  const anyFlapFault = mixFlapFault || defrostFlapFault || footFlapFault;

  // ─── Shared styles ────────────────────────────────────────
  const labelStyle = {
    fontFamily: "'Rajdhani',sans-serif", fontSize: 25, fontWeight: 700,
    letterSpacing: 3, color: C.mid, textTransform: "uppercase",
  };
  const bigBtn = (active, color) => ({
    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
    gap: 6, flex: 1, height: "100%", minWidth: 0, borderRadius: 8,
    border: `1.5px solid ${active ? color : C.line}`,
    background: active
      ? `linear-gradient(180deg, ${color}24, ${color}0d)`
      : `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
    boxShadow: active
      ? `0 0 20px ${color}35, inset 0 0 24px ${color}10`
      : "inset 0 1px 0 rgba(255,255,255,0.04), 0 2px 6px rgba(0,0,0,0.45)",
    transition: "all 0.18s ease",
  });
  const btnText = (active, color) => ({
    fontFamily: "'Rajdhani',sans-serif", fontSize: 26, fontWeight: 700,
    letterSpacing: 2.2, textTransform: "uppercase",
    color: active ? color : C.mid,
    textShadow: active ? `0 0 9px ${color}70` : "none",
  });
  const testBtn = {
    width: 78, height: 62, borderRadius: 9, flexShrink: 0,
    border: `1.5px solid ${C.amber}66`,
    background: `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
    color: C.amber, fontSize: 42, fontFamily: "'Orbitron',monospace", fontWeight: 700,
    textShadow: `0 0 10px ${C.amber}60`, userSelect: "none", WebkitUserSelect: "none",
  };

  return (
    <>
      <style>{`
        *{margin:0;padding:0;box-sizing:border-box}
        html,body,#root{width:100%;height:100%;overflow:hidden;background:${C.bg}}
        button{cursor:pointer;outline:none;font-family:inherit}
        button:active{transform:scale(0.97)}
        input[type=range]{background:transparent}
        input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:3px;background:${C.segOff}}
        input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:26px;height:26px;border-radius:5px;margin-top:-10px;background:linear-gradient(180deg,#3d4854,#1e252c);border:1px solid #4d5a66;box-shadow:0 2px 6px rgba(0,0,0,0.6)}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.35}}
        @keyframes flapSweep{0%,100%{opacity:0.3}50%{opacity:0.95}}
        @keyframes flapChev{0%{opacity:0.12}50%{opacity:1}100%{opacity:0.12}}
        @keyframes powerOn{0%{opacity:0;filter:brightness(2.6)}45%{opacity:1;filter:brightness(1.5)}100%{opacity:1;filter:brightness(1)}}
        .band{animation:powerOn 0.8s ease both}
      `}</style>

      {/* Fixed-size stage, scaled to fit whatever viewport it lands in.
          The panel is exactly 1920x720, so the layout is ALWAYS computed at
          that size and then scaled — never reflowed. Without this the root
          was width:100%, so in any window narrower than 1920 the BAND 2
          columns (400px temps, 190px knob mirror) were over-subscribed and
          shrank; flex then redistributed on every content change, which is
          what made the whole screen twitch when a value changed. On the real
          panel the scale is exactly 1, so this is a no-op there — and in a
          browser it now previews pixel-faithfully. */}
      <div style={{
        width: "100%", height: "100%", overflow: "hidden", background: C.bg,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
      <div style={{
        width: DESIGN_W, height: DESIGN_H, flex: "0 0 auto",
        transform: `scale(${stageScale})`, transformOrigin: "center center",
        display: "grid", gridTemplateRows: "70px 1fr 240px",
        color: C.text, fontFamily: "'Rajdhani',sans-serif",
        position: "relative", overflow: "hidden",
      }}>
        {/* ════ SYSTEM STATUS ════
            Sits above the bands but BELOW the glass overlay, so it picks up
            the same scanlines as everything else and reads as part of the
            panel rather than a web page pasted over it. */}
        {systemView && (
          <SystemStatus
            onClose={cmdCloseSystem}
            st={{
              idriveOnline, idriveAge, idriveAction, idriveMode, idriveActive,
              illumOnline, illumAge,
              tsdashOnline, tsdashAge, tsdashInit, tsdashUsb,
              onewireOk, adsOk, wsConnected, uptime,
              mixFault: mixFlapFault, defFault: defrostFlapFault, footFault: footFlapFault,
            }}
          />
        )}

        {/* glass + scanline atmosphere over everything */}
        <div style={{
          position: "absolute", inset: 0, pointerEvents: "none", zIndex: 20,
          background: `linear-gradient(180deg, rgba(255,255,255,0.03), transparent 10%),
            repeating-linear-gradient(0deg, transparent 0 3px, rgba(0,0,0,0.08) 3px 4px)`,
        }} />

        {/* ════ BENCH-TEST OVERRIDE PANEL ════ */}
        {testOverride && (
          <div style={{
            position: "absolute", top: 82, left: 22, zIndex: 30, width: 452,
            padding: "14px 18px 16px", borderRadius: 12,
            border: `2px solid ${C.amber}`,
            background: "linear-gradient(180deg, #1b1408, #0a0e13)",
            boxShadow: `0 0 26px ${C.amber}40, 0 10px 34px rgba(0,0,0,0.6)`,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontFamily: "'Orbitron',monospace", fontSize: 17, fontWeight: 700,
                letterSpacing: 2.5, color: C.amber, textShadow: `0 0 10px ${C.amber}70` }}>
                BENCH TEST · CABIN TEMP</span>
              <button onClick={() => cmdTestOverride(false)} style={{
                padding: "5px 13px", borderRadius: 6, border: `1.5px solid ${C.amber}`,
                background: "transparent", color: C.amber, fontFamily: "'Rajdhani',sans-serif",
                fontSize: 15, fontWeight: 700, letterSpacing: 2 }}>EXIT</button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <button onClick={() => cmdTestInteriorTemp(testInteriorTemp - 1)} style={testBtn}>−</button>
              <div style={{ flex: 1, textAlign: "center", lineHeight: 0.9 }}>
                <span style={{ fontFamily: "'Orbitron',monospace", fontSize: 64, fontWeight: 800,
                  color: C.amber, textShadow: `0 0 18px ${C.amber}60`, fontVariantNumeric: "tabular-nums" }}>
                  {Math.round(testInteriorTemp)}</span>
                <span style={{ fontSize: 22, color: C.mid, fontWeight: 600 }}>°F</span>
              </div>
              <button onClick={() => cmdTestInteriorTemp(testInteriorTemp + 1)} style={testBtn}>+</button>
            </div>
            <input type="range" min={20} max={140} value={Math.round(testInteriorTemp)}
              onChange={(e) => cmdTestInteriorTemp(Number(e.target.value))}
              style={{ width: "100%", height: 26, appearance: "none", WebkitAppearance: "none",
                cursor: "pointer", accentColor: C.amber, margin: "6px 0 0" }} />
            <span style={{ display: "block", marginTop: 6, fontFamily: "'Rajdhani',sans-serif",
              fontSize: 14, fontWeight: 600, letterSpacing: 0.4, color: C.mid }}>
              Injecting a fake interior reading — the temp PID and INTERIOR gauge use this. Resets on reboot.</span>
          </div>
        )}

        {/* ════ BAND 1 — HEADER RAIL ════ */}
        <div className="band" style={{
          display: "flex", alignItems: "center", gap: 26, padding: "0 28px",
          background: `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
          borderBottom: `1px solid ${C.lineHi}`,
          boxShadow: "0 3px 12px rgba(0,0,0,0.5)",
        }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
            <span style={{ fontFamily: "'Orbitron',monospace", fontSize: 23, fontWeight: 800,
              letterSpacing: 6, color: C.text }}>PORSCHE 944S</span>
            <span style={{ ...labelStyle, fontSize: 18, color: C.dim }}>Electronic Climate Control</span>
          </div>

          <div style={{ flex: 1 }} />

          {/* Annunciator lamps in header */}
          <div style={{ display: "flex", gap: 20 }}>
            <Lamp label="LINK" on={wsConnected} color={C.green} />
            <Lamp label="LOOP" on={controlActive} color={C.vfd} />
            <Lamp label="1-WIRE" on={onewireOk} color={C.green} />
            <Lamp label="ADC" on={adsOk} color={C.green} />
            <Lamp label="HEAT VLV" on={heatValve} color={C.amber} />
            <Lamp label="A/C CLU" on={acOn} color={C.ice} />
            <Lamp label="FLAP" on={anyFlapFault} color={C.red} blink />
          </div>

          {/* Round auxiliary screen selector */}
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 16, fontWeight: 700,
              letterSpacing: 2, color: C.dim, whiteSpace: "nowrap" }}>AUX</span>
            <div style={{ display: "flex", border: `1.5px solid ${C.line}`,
              borderRadius: 7, overflow: "hidden" }}>
              {[{ k: "clock", l: "CLOCK" }, { k: "gmeter", l: "G-METER" }].map((o) => {
                const on = auxDisplay === o.k;
                return (
                  <button key={o.k} onClick={() => cmdAuxDisplay(o.k)} style={{
                    padding: "9px 15px", border: "none",
                    background: on ? C.vfdDim : "transparent",
                    color: on ? C.vfd : C.mid,
                    fontFamily: "'Rajdhani',sans-serif", fontSize: 19, fontWeight: 700,
                    letterSpacing: 1.6, whiteSpace: "nowrap",
                    textShadow: on ? `0 0 9px ${C.vfd}70` : "none",
                    transition: "all 0.15s",
                  }}>{o.l}</button>
                );
              })}
            </div>
          </div>

          <button onClick={() => cmdTestOverride(!testOverride)} style={{
            padding: "7px 15px", borderRadius: 6, whiteSpace: "nowrap",
            border: `1.5px solid ${testOverride ? C.amber : C.line}`,
            background: testOverride ? `${C.amber}1e` : "transparent",
            color: testOverride ? C.amber : C.mid,
            fontFamily: "'Rajdhani',sans-serif", fontSize: 16, fontWeight: 700, letterSpacing: 2,
            textShadow: testOverride ? `0 0 8px ${C.amber}70` : "none",
            boxShadow: testOverride ? `0 0 14px ${C.amber}40` : "none",
            animation: testOverride ? "pulse 1.6s ease-in-out infinite" : "none",
          }}>TEST</button>

          <div style={{ width: 2, height: 36, background: C.line }} />

          <span style={{ fontFamily: "'Orbitron',monospace", fontSize: 34, fontWeight: 700,
            color: C.vfd, textShadow: `0 0 12px ${C.vfd}50`, fontVariantNumeric: "tabular-nums" }}>
            {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>

        {/* ════ BAND 2 — MAIN INSTRUMENT BAND ════ */}
        <div className="band" style={{
          display: "flex", alignItems: "stretch", gap: 22, padding: "18px 28px",
          minHeight: 0,
        }}>
          {/* — Temperatures (left) — */}
          <div style={{ width: 400, display: "flex", flexDirection: "column",
            justifyContent: "space-evenly", gap: 10 }}>
            {[
              { label: "OUTSIDE", val: extTemp, min: -20, max: 120, color: C.vfd },
              { label: "INTERIOR", val: interiorTemp, min: 20, max: 140,
                color: interiorTemp > 82 ? C.amber : interiorTemp < 62 ? C.ice : C.vfd,
                override: testOverride },
              { label: "DUCT", val: mixTemp, min: 32, max: 180, color: mixTemp > 100 ? C.amber : C.vfd },
            ].map((t) => (
              <div key={t.label} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={labelStyle}>{t.label}</span>
                    {t.override && <span style={{
                      fontFamily: "'Rajdhani',sans-serif", fontSize: 13, fontWeight: 700,
                      letterSpacing: 1.5, color: C.amber, border: `1px solid ${C.amber}`,
                      borderRadius: 4, padding: "0 6px", textShadow: `0 0 6px ${C.amber}70`,
                    }}>TEST</span>}
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span style={{
                      fontFamily: "'Orbitron',monospace", fontSize: 66, fontWeight: 700, lineHeight: 0.95,
                      color: t.color, textShadow: `0 0 16px ${t.color}70, 0 0 44px ${t.color}25`,
                      // Two separate problems. <Digits> fixes varying digit
                      // WIDTH (Orbitron's "1" is half-width); minWidth fixes
                      // varying digit COUNT (71 -> 100, or a minus sign on the
                      // exterior reading). 3 cells at 66px = 165px, measured.
                      minWidth: 168, textAlign: "right",
                    }}><Digits value={Math.round(t.val)} size={66} /></span>
                    <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 26, fontWeight: 600,
                      color: C.mid }}>°F</span>
                  </div>
                </div>
                <Segs value={((t.val - t.min) / (t.max - t.min)) * 100} n={26} color={t.color} h={12} />
              </div>
            ))}
          </div>

          <Groove />

          {/* — Setpoint command center (center, dominant) — */}
          <div style={{ flex: 1, display: "flex", alignItems: "stretch", gap: 18, minWidth: 0 }}>
            {/* minus */}
            <button onPointerDown={() => startHold(-1)} onPointerUp={stopHold} onPointerLeave={stopHold}
              style={{
                width: 120, borderRadius: 10, border: `1.5px solid ${C.line}`,
                background: `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
                color: C.vfd, fontSize: 66, fontFamily: "'Orbitron',monospace", fontWeight: 700,
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05), 0 3px 10px rgba(0,0,0,0.5)",
                userSelect: "none", WebkitUserSelect: "none", textShadow: `0 0 14px ${C.vfd}60`,
              }}>−</button>

            {/* giant readout */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 6, minWidth: 0 }}>
              <span style={{ ...labelStyle, fontSize: 25, letterSpacing: 5 }}>Set Temperature</span>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, lineHeight: 0.9 }}>
                <span style={{
                  fontFamily: "'Orbitron',monospace", fontSize: 210, fontWeight: 800,
                  color: spColor, lineHeight: 0.9,
                  textShadow: `0 0 24px ${spColor}70, 0 0 80px ${spColor}30`,
                }}><Digits value={Math.round(setpoint)} size={210} /></span>
                <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 52, fontWeight: 600,
                  color: C.mid }}>°F</span>
              </div>
              <div style={{ width: "88%", marginTop: 4 }}>
                <Segs value={((setpoint - 60) / 30) * 100} n={30} color={spColor} h={13} />
              </div>
              {/* mode annunciator window */}
              {/* Fixed width, sized for the longest label ("VENTILATION").
                  Without it the box resizes with its text, and because it is
                  centred it moves on BOTH sides at once — most visibly when
                  the setpoint crosses 80F, which auto-engages heat and flips
                  VENTILATION (11 chars) to HEATING (7), jumping ~90px. */}
              <div style={{
                marginTop: 8, padding: "7px 34px", borderRadius: 6, minWidth: 380,
                border: `1px solid ${modeColor}55`, background: `${modeColor}0e`,
              }}>
                <span style={{
                  fontFamily: "'Orbitron',monospace", fontSize: 28, fontWeight: 700,
                  letterSpacing: 6, color: modeColor, textShadow: `0 0 12px ${modeColor}70`,
                  display: "block", textAlign: "center",
                }}>{modeLabel}</span>
              </div>
            </div>

            {/* plus */}
            <button onPointerDown={() => startHold(1)} onPointerUp={stopHold} onPointerLeave={stopHold}
              style={{
                width: 120, borderRadius: 10, border: `1.5px solid ${C.line}`,
                background: `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
                color: C.vfd, fontSize: 66, fontFamily: "'Orbitron',monospace", fontWeight: 700,
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05), 0 3px 10px rgba(0,0,0,0.5)",
                userSelect: "none", WebkitUserSelect: "none", textShadow: `0 0 14px ${C.vfd}60`,
              }}>+</button>
          </div>

          <Groove />

          {/* — Blower + actuators (right) — */}
          <div style={{ width: 430, display: "flex", flexDirection: "column",
            justifyContent: "space-between", gap: 12 }}>
            {/* Blower */}
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <Icon name="fan" size={40} color={fanSpeed !== "OFF" ? C.vfd : C.dim}
                  glow={fanSpeed !== "OFF"} />
                <span style={labelStyle}>Blower</span>
                <div style={{ flex: 1 }}>
                  <Segs value={fanPct} n={16} color={C.vfd} h={13} />
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, height: 74 }}>
                {["OFF", "LOW", "HI"].map((lvl) => (
                  <button key={lvl} onClick={() => cmdFanSpeed(lvl)} style={{
                    flex: 1, borderRadius: 7,
                    border: `1.5px solid ${fanSpeed === lvl ? C.vfd : C.line}`,
                    background: fanSpeed === lvl ? C.vfdDim
                      : `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
                    color: fanSpeed === lvl ? C.vfd : C.mid,
                    fontFamily: "'Rajdhani',sans-serif", fontSize: 27, fontWeight: 700,
                    letterSpacing: 3, transition: "all 0.18s",
                    boxShadow: fanSpeed === lvl ? `0 0 16px ${C.vfd}30` : "none",
                  }}>{lvl}</button>
                ))}
              </div>
            </div>

            {/* Actuator flaps — position + commanded direction */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                { label: "Blend", val: mixFlap, target: mixFlapTarget, fault: mixFlapFault,
                  base: mixFlap > 60 ? C.amber : mixFlap < 40 ? C.ice : C.vfd,
                  hi: { word: "HOT", color: C.amber }, lo: { word: "COLD", color: C.ice } },
                { label: "Defrost", val: defrostFlap, target: defrostFlapTarget, fault: defrostFlapFault,
                  base: C.amber,
                  hi: { word: "OPEN", color: C.amber }, lo: { word: "SHUT", color: C.mid } },
                { label: "Footwell", val: footFlap, target: footFlapTarget, fault: footFlapFault,
                  base: C.vfd,
                  hi: { word: "OPEN", color: C.vfd }, lo: { word: "SHUT", color: C.mid } },
              ].map((a) => {
                const delta = a.target - a.val;
                const TH = 1.5; // deadband — below this the flap is holding
                // only show drive direction when the control loop is actually driving
                const dir = controlActive ? (delta > TH ? 1 : delta < -TH ? -1 : 0) : 0;
                const dd = dir > 0 ? a.hi : dir < 0 ? a.lo : null;
                const dirColor = dd ? dd.color : a.base;
                const eff = a.fault ? 0 : dir; // no sweep animation while faulted
                return (
                  <div key={a.label} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ ...labelStyle, fontSize: 22, width: 118, flexShrink: 0 }}>{a.label}</span>
                      {/* commanded-direction indicator */}
                      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6,
                        justifyContent: "flex-end" }}>
                        {a.fault ? (
                          <span style={{
                            fontFamily: "'Rajdhani',sans-serif", fontSize: 19, fontWeight: 800,
                            letterSpacing: 2.5, color: C.red, textShadow: `0 0 10px ${C.red}`,
                            animation: "pulse 1s ease-in-out infinite",
                          }}>FAULT</span>
                        ) : (
                          <>
                            {dir < 0 && <Chevrons dir={-1} color={dirColor} />}
                            <span style={{
                              fontFamily: "'Rajdhani',sans-serif", fontSize: 19, fontWeight: 700,
                              letterSpacing: 2, minWidth: 52, textAlign: "center",
                              color: dd ? dirColor : C.dim,
                              textShadow: dd ? `0 0 8px ${dirColor}70` : "none",
                            }}>{dd ? dd.word : "HOLD"}</span>
                            {dir > 0 && <Chevrons dir={1} color={dirColor} />}
                          </>
                        )}
                      </div>
                      <span style={{
                        fontFamily: "'Orbitron',monospace", fontSize: 25, fontWeight: 700,
                        color: a.base, width: 74, textAlign: "right",
                        textShadow: `0 0 8px ${a.base}50`, fontVariantNumeric: "tabular-nums",
                      }}>{Math.round(a.val)}<span style={{ fontSize: 12, color: C.mid }}>%</span></span>
                    </div>
                    <FlapTrack actual={a.val} target={a.target} base={a.base}
                      dirColor={dirColor} dir={eff} />
                  </div>
                );
              })}
            </div>
          </div>

          <Groove />

          {/* — iDrive knob mirror (right) — */}
          <KnobMirror mode={idriveMode} detents={idriveDetents} action={idriveAction}
            active={idriveActive} setpoint={setpoint} auxDisplay={auxDisplay}
            illumCh1={illumCh1} />
        </div>

        {/* ════ BAND 3 — CONTROL RAIL ════ */}
        <div className="band" style={{
          display: "flex", alignItems: "stretch", gap: 20, padding: "16px 28px 20px",
          background: `linear-gradient(180deg, ${C.fascia}, #060a0d 130%)`,
          borderTop: `1px solid ${C.lineHi}`,
          minHeight: 0,
        }}>
          {/* Air distribution */}
          <div style={{ flex: 4.4, display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
            <span style={{ ...labelStyle, fontSize: 22 }}>Air Distribution</span>
            <div style={{ display: "flex", gap: 10, flex: 1 }}>
              {[
                { key: "face", label: "Face", icon: "face" },
                { key: "bilevel", label: "Bi-Level", icon: "bilevel" },
                { key: "feet", label: "Feet", icon: "feet" },
                { key: "defrost", label: "Defrost", icon: "defrost", color: C.amber },
              ].map((m) => {
                const active = ventMode === m.key;
                const col = m.color || C.vfd;
                return (
                  <button key={m.key} onClick={() => cmdVentMode(m.key)} style={bigBtn(active, col)}>
                    <Icon name={m.icon} size={60} color={active ? col : C.mid} sw={1.6} glow={active} />
                    <span style={btnText(active, col)}>{m.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <Groove />

          {/* Function switches */}
          <div style={{ flex: 4.4, display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
            <span style={{ ...labelStyle, fontSize: 22 }}>Function</span>
            <div style={{ display: "flex", gap: 10, flex: 1 }}>
              <button onClick={() => { cmdAcOn(!acOn); if (maxAc) setMaxAc(false); }}
                style={bigBtn(acOn, C.ice)}>
                <Icon name="snow" size={54} color={acOn ? C.ice : C.mid} glow={acOn} />
                <span style={btnText(acOn, C.ice)}>A/C</span>
              </button>
              <button onClick={toggleMaxAc} style={{
                ...bigBtn(maxAc, C.ice), flex: 1.25,
                border: `2px solid ${maxAc ? C.ice : C.lineHi}`,
              }}>
                <Icon name="snow" size={54} color={maxAc ? C.ice : C.mid} sw={2.1} glow={maxAc} />
                <span style={{ ...btnText(maxAc, C.ice), fontFamily: "'Orbitron',monospace",
                  fontSize: 22, letterSpacing: 2.5 }}>MAX A/C</span>
              </button>
              <button onClick={() => cmdHeatValve(!heatValve)} style={bigBtn(heatValve, C.amber)}>
                <Icon name="heat" size={54} color={heatValve ? C.amber : C.mid} glow={heatValve} />
                <span style={btnText(heatValve, C.amber)}>Heat</span>
              </button>
              <button onClick={() => cmdOutsideAir(true)} style={bigBtn(outsideAir, C.green)}>
                <Icon name="fresh" size={54} color={outsideAir ? C.green : C.mid} glow={outsideAir} />
                <span style={btnText(outsideAir, C.green)}>Fresh</span>
              </button>
              <button onClick={() => cmdOutsideAir(false)} style={bigBtn(!outsideAir, C.vfd)}>
                <Icon name="recirc" size={54} color={!outsideAir ? C.vfd : C.mid} glow={!outsideAir} />
                <span style={btnText(!outsideAir, C.vfd)}>Recirc</span>
              </button>
            </div>
          </div>

          <Groove />

          {/* Heated seats */}
          <div style={{ flex: 3.6, display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
            <span style={{ ...labelStyle, fontSize: 22 }}>Heated Seats</span>
            <div style={{ display: "flex", gap: 12, flex: 1 }}>
              {[
                { label: "DRIVER", val: driverSeatHeat, set: cmdDriverSeatHeat },
                { label: "PASS", val: passengerSeatHeat, set: cmdPassengerSeatHeat },
              ].map((s) => {
                const col = seatColor(s.val);
                const on = s.val > 0;
                return (
                  <div key={s.label} style={{
                    flex: 1, display: "flex", flexDirection: "column", gap: 6,
                    padding: "9px 11px", borderRadius: 8,
                    border: `1px solid ${on ? `${C.amber}45` : C.line}`,
                    background: on ? "rgba(255,176,0,0.05)"
                      : `linear-gradient(180deg, ${C.fasciaHi}, ${C.fascia})`,
                    transition: "all 0.25s", minWidth: 0,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <Icon name="seat" size={34} color={on ? col : C.mid} glow={on} />
                        <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 21,
                          fontWeight: 700, letterSpacing: 1.8, color: on ? C.text : C.mid }}>{s.label}</span>
                      </div>
                      <span style={{ fontFamily: "'Orbitron',monospace", fontSize: 20, fontWeight: 700,
                        color: on ? col : C.dim }}>{Math.round(s.val)}%</span>
                    </div>
                    <Segs value={s.val} n={12} color={col} h={9} />
                    <div style={{ display: "flex", gap: 4 }}>
                      {[{ n: "OFF", v: 0 }, { n: "LO", v: 33 }, { n: "MED", v: 66 }, { n: "HI", v: 100 }].map((p) => {
                        const sel = (p.v === 0 && s.val === 0) || (p.v > 0 && Math.abs(s.val - p.v) < 5);
                        return (
                          <button key={p.n} onClick={() => s.set(p.v)} style={{
                            flex: 1, padding: "13px 0", borderRadius: 5,
                            border: `1px solid ${sel ? col : C.line}`,
                            background: sel ? `${col}1e` : "transparent",
                            color: sel ? col : C.mid, fontFamily: "'Rajdhani',sans-serif",
                            fontSize: 19, fontWeight: 700, letterSpacing: 1.2,
                            transition: "all 0.15s",
                          }}>{p.n}</button>
                        );
                      })}
                    </div>
                    <input type="range" min={0} max={100} value={s.val}
                      onChange={(e) => s.set(Number(e.target.value))}
                      style={{ width: "100%", height: 24, appearance: "none",
                        WebkitAppearance: "none", cursor: "pointer", accentColor: col, margin: 0 }} />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
      </div>
    </>
  );
}
