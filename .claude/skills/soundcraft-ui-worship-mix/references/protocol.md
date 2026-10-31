# Soundcraft Ui protocol notes

Worked out from the live mixer at 192.168.0.133. Everything here was observed on that unit.

## Connection

1. `GET http://HOST/socket.io/1/` returns `SID:5:5:websocket`.
2. Open `ws://HOST/socket.io/1/websocket/SID`.
3. Answer `2::` with `2::` to stay connected.
4. Messages start with `3:::` and may hold several lines. The full state arrives on connect.

## Messages

- `SETD^key^value` and `SETS^key^value`: settings. Send `3:::SETD^key^value` to change one.
- The mixer does not echo a change to the sender, but other clients get it. A page that sends through its own socket shows old values until reloaded.
- `VU2^base64`: meters.
- `RTA^base64`: analyser data.
- `3:::MTK_JUMP_TO^fraction`: jump the multitrack player, 0 to 1.

## Keys

| Key | Meaning |
|---|---|
| `i.N.mix`, `.mute`, `.pan` | Input N, counted from 0: fader, mute, pan |
| `i.N.aux.A.value`, `.mute`, `.pan`, `.post` | Send to aux A, counted from 0. Aux 3 is A=2 |
| `i.N.fx.F.value`, `.mute` | Send to FX unit F |
| `i.N.eq.bB.freq`, `.gain`, `.q` | EQ bands 1-5 |
| `i.N.eq.hpf.freq`, `.lpf.freq` | Low and high cut |
| `i.N.gate.thresh`, `.dyn.*`, `.subgroup`, `.stereoIndex` | Gate, compressor, routing, stereo link |
| `s.N.mix`, `s.N.fx.F.value` | Subgroup fader and FX send |
| `f.N.mix`, `f.N.aux.A.value` | FX return and its send to an aux |
| `a.N.mix`, `a.N.dyn.*` | Aux fader and compressor |
| `m.mix` | Master fader |
| `hw.N.gain` | Mic gain |

There is no `s.N.aux.*` key: subgroups do not feed auxes.

## Value scales

- Frequency: `f = 20 * 10^(x * 3.0414)`, so x=0.32869 is 200 Hz and x=0.55843 is 1 kHz.
- EQ gain: `dB = (x - 0.5) * 40`.
- Faders and sends: read from the mixer's display; see `CURVE` in `scripts/ui_mixer.py`. 0.7647 is 0 dB.
- A compressor ratio of 0 appears to act as a limiter (the "NO CLIP" preset). This is inferred from the meters.

## VU2 layout

Header is 8 bytes: `24 2 6 4 10 2 2 0`. dB is `byte / 3 - 80`, and 0 means silence.

| Offset | Block | Bytes each | Meaning |
|---|---|---|---|
| 8 | 24 inputs | 6 | 0 input, 1 after processing, 2 after fader |
| 152 | 2 players | 6 | |
| 164 | 6 subgroups | 7 | 0/1 before fader L/R, 2/3 after fader L/R |
| 206 | 4 FX | 7 | Meaning not confirmed |
| 234 | 10 auxes | 5 | 0 before fader, 1 after fader, 3 is not the output |
| 284 | 2 master | 5 | 0 before fader, 1 after fader |
| 294 | 2 line inputs | 6 | |

The aux output is byte 1. Byte 3 does not move with the aux fader.
