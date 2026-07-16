import { useState, useEffect, useCallback, useRef } from "react";

// ═══════════════════════════════════════════════════════════════
// 944S ELECTRONIC CLIMATE CONTROL — Horizontal Console
// Clean-sheet design for 1920×720. One continuous fascia:
//   BAND 1 (70px):  header rail — ID, annunciator, clock
//   BAND 2 (fills): instrument band — temps | setpoint | blower
//   BAND 3 (240px): control rail — modes, functions, seats
// Every band stretches edge-to-edge. No dead space.
// ═══════════════════════════════════════════════════════════════

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

// ─── Column divider (machined groove) ─────────────────────────
function Groove() {
  return <div style={{
    width: 2, alignSelf: "stretch", flexShrink: 0,
    background: `linear-gradient(180deg, transparent, ${C.line} 12%, ${C.line} 88%, transparent)`,
    boxShadow: "1px 0 0 rgba(255,255,255,0.03)",
  }} />;
}

// ═══════════════════════════════════════════════════════════════
export default function HVACDashboard() {
  // ─── WebSocket ────────────────────────────────────────────
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
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

  const sendCmd = useCallback((cmd) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
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
          if (s.setpoint_f !== undefined) setSetpoint(s.setpoint_f);
          if (s.fan_speed !== undefined) setFanSpeed(s.fan_speed);
          if (s.ac_on !== undefined) setAcOn(s.ac_on);
          if (s.heat_valve !== undefined) setHeatValve(s.heat_valve);
          if (s.outside_air !== undefined) setOutsideAir(s.outside_air);
          if (s.vent_mode !== undefined) setVentMode(s.vent_mode);
          if (s.mix_chamber_temp_f !== undefined) setMixTemp(s.mix_chamber_temp_f);
          if (s.exterior_temp_f !== undefined) setExtTemp(s.exterior_temp_f);
          if (s.interior_temp_f !== undefined) setInteriorTemp(s.interior_temp_f);
          if (s.test_override !== undefined) setTestOverride(s.test_override);
          if (s.test_interior_temp_f !== undefined) setTestInteriorTemp(s.test_interior_temp_f);
          if (s.mix_flap_pos !== undefined) setMixFlap(s.mix_flap_pos);
          if (s.defrost_flap_pos !== undefined) setDefrostFlap(s.defrost_flap_pos);
          if (s.footwell_flap_pos !== undefined) setFootFlap(s.footwell_flap_pos);
          if (s.mix_flap_target !== undefined) setMixFlapTarget(s.mix_flap_target);
          if (s.defrost_flap_target !== undefined) setDefrostFlapTarget(s.defrost_flap_target);
          if (s.footwell_flap_target !== undefined) setFootFlapTarget(s.footwell_flap_target);
          if (s.mix_flap_fault !== undefined) setMixFlapFault(s.mix_flap_fault);
          if (s.defrost_flap_fault !== undefined) setDefrostFlapFault(s.defrost_flap_fault);
          if (s.footwell_flap_fault !== undefined) setFootFlapFault(s.footwell_flap_fault);
          if (s.seat_heat_driver !== undefined) setDriverSeatHeat(s.seat_heat_driver);
          if (s.seat_heat_passenger !== undefined) setPassengerSeatHeat(s.seat_heat_passenger);
          if (s.onewire_ok !== undefined) setOnewireOk(s.onewire_ok);
          if (s.ads_ok !== undefined) setAdsOk(s.ads_ok);
          if (s.control_active !== undefined) setControlActive(s.control_active);
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

  // ─── Commands ─────────────────────────────────────────────
  const cmdSetpoint = (v) => {
    const val = Math.max(60, Math.min(90, v));
    setSetpoint(val); sendCmd({ setpoint_f: val });
  };
  const cmdFanSpeed = (v) => { setFanSpeed(v); sendCmd({ fan_speed: v }); };
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
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;600;700;800;900&family=Rajdhani:wght@500;600;700&display=swap');
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

      <div style={{
        width: "100%", height: "100%",
        display: "grid", gridTemplateRows: "70px 1fr 240px",
        background: C.bg, color: C.text, fontFamily: "'Rajdhani',sans-serif",
        position: "relative", overflow: "hidden",
      }}>
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
                      fontVariantNumeric: "tabular-nums",
                    }}>{Math.round(t.val)}</span>
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
                  fontVariantNumeric: "tabular-nums",
                }}>{Math.round(setpoint)}</span>
                <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 52, fontWeight: 600,
                  color: C.mid }}>°F</span>
              </div>
              <div style={{ width: "88%", marginTop: 4 }}>
                <Segs value={((setpoint - 60) / 30) * 100} n={30} color={spColor} h={13} />
              </div>
              {/* mode annunciator window */}
              <div style={{
                marginTop: 8, padding: "7px 34px", borderRadius: 6,
                border: `1px solid ${modeColor}55`, background: `${modeColor}0e`,
              }}>
                <span style={{
                  fontFamily: "'Orbitron',monospace", fontSize: 28, fontWeight: 700,
                  letterSpacing: 6, color: modeColor, textShadow: `0 0 12px ${modeColor}70`,
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
    </>
  );
}
