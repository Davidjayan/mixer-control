#!/usr/bin/env python3
"""Talk directly to a Soundcraft Ui mixer: read state, read meters, apply changes.

Commands:
  status                         connection, soundcheck, master, singers
  meter [--seconds N]            real levels (active signal only)
  backup [--label NAME]          save every setting to a file
  plan NAME [--seconds N]        measure and calculate a leader change; changes nothing
  apply PLANFILE                 apply a fresh plan, refusing if the mixer has moved
  set KEY=VALUE ... [--allow-master] [--allow-mute] [--allow-gain]
  restore FILE [--dry-run]       put back the leader-related settings from a backup
  seek SECONDS --length SECONDS  jump the multitrack player

Levels in the meter output are dBFS, 95th percentile while the channel is active.
"""
import argparse
import asyncio
import base64
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import websockets

RIG = json.loads((Path(__file__).resolve().parent.parent / "rig.json").read_text())
# A relative backup_dir is measured from the project root, so the repo works from any path.
RIG["backup_dir"] = str(Path(__file__).resolve().parents[4] / RIG["backup_dir"])
HOST = RIG["host"]

# value <-> dB pairs read from the mixer's own fader display. Same curve for faders and sends.
CURVE = [
    (0.24, -33.7), (0.2758, -29.0), (0.2994, -26.0), (0.3399, -23.0), (0.37, -21.0),
    (0.4543, -14.3), (0.4683, -13.4), (0.4882, -12.2), (0.5189, -10.5), (0.5284, -10.0),
    (0.5468, -9.0), (0.571, -7.8), (0.5954, -6.7), (0.6123, -5.9), (0.6312, -5.1),
    (0.6579, -4.0), (0.6921, -2.7), (0.738, -0.9), (0.7647, 0.0), (0.7913, 1.0),
    (0.8179, 2.0), (0.8442, 3.0), (0.8599, 3.6), (0.8998, 5.3), (0.919, 6.1),
    (0.9628, 8.1), (0.9915, 9.6), (1.0, 10.0),
]


def db_to_value(db):
    if db >= CURVE[-1][1]:
        return 1.0
    if db <= CURVE[0][1]:
        return CURVE[0][0]
    for (v0, d0), (v1, d1) in zip(CURVE, CURVE[1:]):
        if d0 <= db <= d1:
            return round(v0 + (v1 - v0) * (db - d0) / (d1 - d0), 4)
    raise ValueError(db)


def value_to_db(value):
    value = float(value)
    if value <= 0:
        return float("-inf")
    if value <= CURVE[0][0]:
        return CURVE[0][1]
    for (v0, d0), (v1, d1) in zip(CURVE, CURVE[1:]):
        if v0 <= value <= v1:
            return round(d0 + (d1 - d0) * (value - v0) / (v1 - v0), 1)
    return CURVE[-1][1]


def byte_db(byte):
    return None if byte == 0 else round(byte / 3 - 80, 1)


class Mixer:
    def __init__(self):
        self.ws = None
        self.state = {}
        self.vu = []
        self.keep_vu = False
        self._reader = None

    async def __aenter__(self):
        handshake = await asyncio.to_thread(
            lambda: urllib.request.urlopen(f"http://{HOST}/socket.io/1/", timeout=5).read().decode()
        )
        sid = handshake.split(":")[0]
        self.ws = await websockets.connect(f"ws://{HOST}/socket.io/1/websocket/{sid}", ping_interval=None)
        self._reader = asyncio.create_task(self._read())
        self._alive = asyncio.create_task(self._keep_alive())
        await asyncio.sleep(3)  # the mixer sends its whole state on connect
        if len(self.state) < 1000:
            raise RuntimeError(f"Only {len(self.state)} settings received; not trusting this connection")
        return self

    async def __aexit__(self, *_):
        self._reader.cancel()
        self._alive.cancel()
        await self.ws.close()

    async def _keep_alive(self):
        # Without this the mixer stops streaming meters a few seconds after connecting.
        while True:
            await self.ws.send("3:::ALIVE")
            await asyncio.sleep(1)

    async def _read(self):
        async for message in self.ws:
            if message.startswith("2::"):
                await self.ws.send("2::")
                continue
            for line in message.removeprefix("3:::").split("\n"):
                parts = line.split("^")
                if parts[0] in ("SETD", "SETS") and len(parts) >= 3:
                    self.state[parts[1]] = "^".join(parts[2:])
                elif parts[0] == "VU2" and self.keep_vu:
                    self.vu.append(base64.b64decode(parts[1]))

    async def send(self, key, value):
        await self.ws.send(f"3:::SETD^{key}^{value}")
        self.state[key] = str(value)  # the mixer does not echo to the sender


def check_host_ok(mixer):
    """Stop if the meter layout differs from the one this tool was built against."""
    if mixer.vu and list(mixer.vu[0][:7]) != [24, 2, 6, 4, 10, 2, 2]:
        sys.exit(f"Unexpected meter layout {list(mixer.vu[0][:8])}; refusing to report levels.")


def active_p95(frames, offset, gate_offset=None, gate=66):
    use = [f[offset] for f in frames if gate_offset is None or f[gate_offset] >= gate]
    if len(use) < max(5, len(frames) * 0.15):
        return None
    return byte_db(sorted(use)[int((len(use) - 1) * 0.95)])


async def cmd_status(_):
    async with Mixer() as m:
        s = m.state
        print(f"Mixer {HOST}: {len(s)} settings, snapshot {s.get('var.currentSnapshot')}")
        print(f"Soundcheck: {'ON (channels play the RECORDING, not live mics)' if s.get('var.mtk.soundcheck', s.get('var.soundcheck')) == '1' else 'off'}")
        print(f"Master: {value_to_db(s['m.mix'])} dB")
        for name, sub in RIG["subgroups"].items():
            print(f"{name} subgroup: {value_to_db(s[f's.{sub}.mix'])} dB")
        for label, buses in RIG["aux"].items():
            print(f"{label} aux fader: {value_to_db(s[f'a.{buses[0]}.mix'])} dB")
        for name in RIG["singers"]:
            c = RIG["channels"][name]
            mon = RIG["aux"]["monitors"][0]
            print(f"{name}: fader {value_to_db(s[f'i.{c}.mix'])} dB, mute={s[f'i.{c}.mute']}, "
                  f"monitor send {value_to_db(s[f'i.{c}.aux.{mon}.value'])} dB, "
                  f"FX1 send {value_to_db(s[f'i.{c}.fx.0.value'])} dB")
        leader_file = Path(RIG["backup_dir"]) / "current-leader.txt"
        print(f"Leader on record: {leader_file.read_text().strip() if leader_file.exists() else 'not recorded'}")


async def cmd_meter(args):
    async with Mixer() as m:
        m.keep_vu = True
        await asyncio.sleep(args.seconds)
        check_host_ok(m)
        frames = list(m.vu)
    if len(frames) < args.seconds * 4:
        sys.exit(f"Only {len(frames)} meter frames in {args.seconds}s, so this reading covers too little. Not reporting levels.")
    print(f"{len(frames)} frames over {args.seconds}s. '-' means silent.")
    for name, c in RIG["channels"].items():
        base = 8 + c * 6
        print(f"  {name:11s} input {active_p95(frames, base, base) or '-':>6}  output {active_p95(frames, base + 2, base) or '-':>6}")
    for name, sub in RIG["subgroups"].items():
        o = 164 + sub * 7
        print(f"  {name + ' sub':11s} after fader L {active_p95(frames, o + 2) or '-':>6}  R {active_p95(frames, o + 3) or '-':>6}")
    for name, buses in RIG["aux"].items():
        o = 234 + buses[0] * 5
        peak = max(f[o + 1] for f in frames)
        print(f"  {name:11s} output {active_p95(frames, o + 1) or '-':>6}  peak {byte_db(peak)}")
    print(f"  {'master':11s} output {active_p95(frames, 285) or '-':>6}  peak {byte_db(max(f[285] for f in frames))}")


def write_backup(state, label):
    folder = Path(RIG["backup_dir"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.json"
    path.write_text(json.dumps(state, sort_keys=True))
    return path


async def cmd_backup(args):
    async with Mixer() as m:
        print(write_backup(m.state, args.label))


def leader_keys():
    """Every setting a leader change may touch. Never the master, mutes, EQ or mic gain."""
    keys = []
    for singer in RIG["singers"]:
        c = RIG["channels"][singer]
        keys.append(f"i.{c}.mix")
        keys.extend(f"i.{c}.aux.{bus}.value" for bus in RIG["aux"]["monitors"])
        keys.append(f"i.{c}.fx.0.value")
    return keys


def clamp_move(current, wanted):
    t = RIG["targets"]
    limited = max(current - t["max_move_db"], min(current + t["max_move_db"], wanted))
    return min(t["max_fader_db"], limited)


def build_plan(name, state, levels, previous):
    """Calculate moves from what the mixer holds and what the meters measured just now."""
    t = RIG["targets"]
    notes, to, rows = [], {}, []
    lead_c = RIG["channels"][name]
    lead_now = value_to_db(state[f"i.{lead_c}.mix"])
    lead_new = clamp_move(lead_now, lead_now + t["lead_output_db"] - levels[name])
    lead_result = levels[name] + lead_new - lead_now
    if lead_result < t["lead_output_db"] - 0.5:
        notes.append(f"{name} reaches {lead_result:.1f} dB, short of the {t['lead_output_db']} dB goal. "
                     "Raising the mic gain live is the fix; it needs the user's approval.")
    for singer in RIG["singers"]:
        c = RIG["channels"][singer]
        now = value_to_db(state[f"i.{c}.mix"])
        lead = singer == name
        if lead:
            new = lead_new
        elif levels[singer] is None:
            new = now
            notes.append(f"{singer} is silent, so the fader stays at {now} dB. Re-plan once they sing.")
        else:
            new = clamp_move(now, now + (lead_result - t["support_gap_db"]) - levels[singer])
        move = new - now
        if abs(move) >= 0.3:
            to[f"i.{c}.mix"] = db_to_value(new)
        # Sends follow the fader: undo the fader move, then lift the new leader and
        # drop the previous one, so nobody jumps in the monitors.
        bump = t["monitor_lead_bump_db"] * ((lead and previous != name) - (singer == previous and not lead))
        for bus in RIG["aux"]["monitors"]:
            send_now = value_to_db(state[f"i.{c}.aux.{bus}.value"])
            send_new = min(10.0, send_now - move + bump)
            if abs(send_new - send_now) >= 0.3:
                to[f"i.{c}.aux.{bus}.value"] = db_to_value(send_new)
        fx_new = t["fx1_lead_send_db"] if lead else t["fx1_support_send_db"]
        if abs(fx_new - value_to_db(state[f"i.{c}.fx.0.value"])) >= 1.0:
            to[f"i.{c}.fx.0.value"] = db_to_value(fx_new)
        level = levels[singer]
        rows.append(f"  {singer:6s} measured {level if level is not None else 'silent'}  "
                    f"fader {now} -> {round(new, 1)} dB  "
                    f"expected output {round(level + move, 1) if level is not None else 'unknown'}")
    return to, rows, notes


async def apply_targets(m, targets, steps=10):
    """Fade level changes so the room never hears a jump; set everything else directly."""
    ramp = {k: (float(m.state[k]), v) for k, v in targets.items() if k.endswith((".mix", ".value"))}
    # Bring levels down before bringing the new leader up.
    order = sorted(ramp, key=lambda k: ramp[k][1] - ramp[k][0])
    for step in range(1, steps + 1):
        for key in order:
            start, end = ramp[key]
            await m.send(key, round(start + (end - start) * step / steps, 4))
        await asyncio.sleep(0.12)
    for key, value in targets.items():
        if key not in ramp:
            await m.send(key, value)


async def verify(targets):
    await asyncio.sleep(0.5)
    async with Mixer() as check:
        return [f"{k}: wanted {v}, mixer has {check.state.get(k)}"
                for k, v in targets.items()
                if abs(float(check.state.get(k, "nan")) - float(v)) > 0.002]


def show_plan(m, targets):
    for key, value in targets.items():
        old = m.state.get(key)
        if old is not None and abs(float(old) - float(value)) <= 0.002:
            continue
        unit = f"  ({value_to_db(old)} -> {value_to_db(value)} dB)" if key.endswith((".mix", ".value")) else ""
        print(f"  {key}: {old} -> {value}{unit}")


async def cmd_plan(args):
    """Measure and calculate. Changes nothing on the mixer."""
    name = args.name.lower()
    if name not in RIG["singers"]:
        sys.exit(f"Unknown leader {name}. Choose from {', '.join(RIG['singers'])}.")
    async with Mixer() as m:
        m.keep_vu = True
        await asyncio.sleep(args.seconds)
        check_host_ok(m)
        frames, state = list(m.vu), dict(m.state)
    if len(frames) < args.seconds * 4:
        sys.exit(f"Only {len(frames)} meter frames in {args.seconds}s. Nothing changed.")
    levels = {}
    print("Live inputs:")
    for singer in RIG["singers"]:
        base = 8 + RIG["channels"][singer] * 6
        levels[singer] = active_p95(frames, base + 2, base)
        print(f"  {singer:6s} input {active_p95(frames, base, base) or 'silent'}")
    if levels[name] is None:
        sys.exit(f"{name} is not singing, so there is nothing to measure. Nothing changed; plan again once they sing.")
    leader_file = Path(RIG["backup_dir"]) / "current-leader.txt"
    previous = leader_file.read_text().strip() if leader_file.exists() else None
    to, rows, notes = build_plan(name, state, levels, previous)
    if any(k.startswith("m.") or ".mute" in k for k in to):
        sys.exit("Refusing: a leader change must not touch the master or mutes.")
    plan = {"leader": name, "created": time.time(), "to": to, "from": {k: state[k] for k in to}, "rows": rows, "notes": notes}
    folder = Path(RIG["backup_dir"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"plan-{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(plan, indent=1))
    print(f"Plan for {name} (previous leader on record: {previous}). Nothing has changed yet.")
    print(*rows, sep="\n")
    show_plan(type("Now", (), {"state": state}), to)
    for note in notes:
        print("Note:", note)
    print("Plan file:", path)


async def cmd_apply(args):
    plan = json.loads(Path(args.file).read_text())
    age = time.time() - plan["created"]
    if age > RIG["plan_valid_seconds"]:
        sys.exit(f"Plan is {age:.0f}s old. Levels may have changed, so measure and plan again.")
    async with Mixer() as m:
        moved = [k for k, v in plan["from"].items() if abs(float(m.state[k]) - float(v)) > 0.003]
        if moved:
            sys.exit(f"Refusing: these changed after the plan was made, so plan again: {moved}")
        print("Backup:", write_backup(m.state, f"before-{plan['leader']}"))
        await apply_targets(m, plan["to"])
    problems = await verify(plan["to"])
    if problems:
        print("NOT VERIFIED:", *problems, sep="\n  ")
        sys.exit(1)
    (Path(RIG["backup_dir"]) / "current-leader.txt").write_text(plan["leader"] + "\n")
    print(f"Verified: {len(plan['to'])} settings on the mixer. Master untouched. Now confirm by screenshot and meter.")


async def cmd_set(args):
    targets = {}
    for pair in args.pairs:
        key, _, value = pair.partition("=")
        if key.startswith("m.") and not args.allow_master:
            sys.exit(f"Refusing {key}: the master needs --allow-master, and the user asking for it.")
        if ".mute" in key and not args.allow_mute:
            sys.exit(f"Refusing {key}: mutes need --allow-mute.")
        if key.startswith("hw.") and not args.allow_gain:
            sys.exit(f"Refusing {key}: mic gain needs --allow-gain.")
        targets[key] = float(value)
    async with Mixer() as m:
        missing = [k for k in targets if k not in m.state]
        if missing:
            sys.exit(f"Unknown settings, nothing changed: {missing}")
        show_plan(m, targets)
        print("Backup:", write_backup(m.state, "before-set"))
        await apply_targets(m, targets)
    problems = await verify(targets)
    if problems:
        print("NOT VERIFIED:", *problems, sep="\n  ")
        sys.exit(1)
    print(f"Verified: {len(targets)} settings.")


async def cmd_restore(args):
    saved = json.loads(Path(args.file).read_text())
    keys = set(leader_keys())
    targets = {k: float(saved[k]) for k in keys if k in saved}
    async with Mixer() as m:
        show_plan(m, targets)
        if args.dry_run:
            print("Dry run: nothing changed.")
            return
        await apply_targets(m, targets)
    problems = await verify(targets)
    if problems:
        print("NOT VERIFIED:", *problems, sep="\n  ")
        sys.exit(1)
    print(f"Restored and verified: {len(targets)} settings.")


async def cmd_seek(args):
    if not 0 <= args.seconds < args.length:
        sys.exit("Position must be inside the recording.")
    async with Mixer() as m:
        await m.ws.send(f"3:::MTK_JUMP_TO^{args.seconds / args.length}")
        await asyncio.sleep(0.5)
    print(f"Jumped to {args.seconds}s of {args.length}s.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(run=cmd_status)
    p = sub.add_parser("meter"); p.add_argument("--seconds", type=int, default=20); p.set_defaults(run=cmd_meter)
    p = sub.add_parser("backup"); p.add_argument("--label", default="manual"); p.set_defaults(run=cmd_backup)
    p = sub.add_parser("plan"); p.add_argument("name"); p.add_argument("--seconds", type=int, default=15); p.set_defaults(run=cmd_plan)
    p = sub.add_parser("apply"); p.add_argument("file"); p.set_defaults(run=cmd_apply)
    p = sub.add_parser("set"); p.add_argument("pairs", nargs="+")
    for flag in ("--allow-master", "--allow-mute", "--allow-gain"):
        p.add_argument(flag, action="store_true")
    p.set_defaults(run=cmd_set)
    p = sub.add_parser("restore"); p.add_argument("file"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(run=cmd_restore)
    p = sub.add_parser("seek"); p.add_argument("seconds", type=float); p.add_argument("--length", type=float, required=True); p.set_defaults(run=cmd_seek)
    args = parser.parse_args()
    asyncio.run(args.run(args))


if __name__ == "__main__":
    main()
