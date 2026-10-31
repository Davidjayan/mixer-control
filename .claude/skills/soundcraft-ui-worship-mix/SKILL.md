---
name: soundcraft-ui-worship-mix
description: Run the church's Soundcraft Ui mixer at 192.168.0.133. Use this whenever the user names or changes the worship leader ("worship leader is uncle", "aunty is leading now", "David leads next"), or asks to mix, balance, check or fix the room mix, YouTube live feed (Aux 3/4), stage monitors (Aux 1/2), choir, drums, EQ or reverb, or to play and mix a recorded multitrack session, even if they don't say "mixer" or "Soundcraft".
---

# Soundcraft Ui worship mix

You are the church's audio engineer. Listen to what the user reports, and take responsibility for the whole sound in the room, on YouTube and on stage.

**Never assume a value.** Faders, sends and singers' levels change between services and during them, and the user may be mixing at the same time. Every change is seen, measured and tested on the live mixer first. `rig.json` holds channel names and goals only, never stored mix settings.

Use Playwright MCP to see the mixer and `scripts/ui_mixer.py` to measure, change and verify. The script talks directly to the mixer and fades level changes.

```bash
S="$(git rev-parse --show-toplevel)/.claude/skills/soundcraft-ui-worship-mix/scripts/ui_mixer.py"
python3 $S status
python3 $S meter --seconds 20
python3 $S plan uncle       # measures and calculates; changes nothing
python3 $S apply PLANFILE   # refuses an old plan, or one the mixer has moved away from
```

## Every change follows these steps

1. **See.** In Playwright, open or reload `http://192.168.0.133/mixer.html` and screenshot each view involved. The page holds old values until reloaded, so always reload first. Screenshot before every click, because the layout changes and the user may have switched views. Aux Sends is reached from the top bar, then the aux tab.
2. **Check inputs, then measure.** Before any adjustment, including every mix switch, run `status` and `meter`, and read the live input of each channel involved along with its output, while those people are performing. A weak, silent or unexpected input changes the right move. `plan` prints inputs too.
3. **Plan.** Calculate moves from those readings, and list them with the before and after values.
4. **Check before applying.** Compare the plan's starting values with the screenshots. If they disagree, stop and find out why. Check the expected result makes sense: leader on top, nothing beyond a limit, no large raise going to the monitors.
5. **Apply** with `apply`, or `set` for other changes. Both back up first and read back from the mixer.
6. **Confirm.** Reload, screenshot the same views, and meter again. A readback only proves the value was stored; the meter proves the result.

## The rig

| Output | Bus | Fed by |
|---|---|---|
| Room | Master | Channels, and the Choir and Drums subgroups |
| YouTube live | Aux 3/4 | Channels directly, post-fader, with no subgroups |
| Stage monitors | Aux 1/2 | Channels directly, post-fader; drums stay muted here |

David, Aunty and Uncle can each lead. Choir 1 and 2 sing in tune and carry the choir. Choir 3 and 4 sing flat, so they stay lower and darker. Danny, Song and Keyboard 2 have not been heard in any recording yet, so their balance is unproven.

## Changing the worship leader

When the user says who is leading, follow the steps above straight away, because this can happen mid-service:

- `plan NAME` measures all three singers now, then works out each fader from the real level: leader to the goal, support singers 8 dB under. It moves the larger reverb send to the leader, and offsets monitor sends so a fader move does not reach the wedges, with a 3 dB lift for the leader. It touches only those singers' faders, monitor sends and FX1 sends.
- If the new leader is not singing, `plan` stops without changing anything, because there is nothing to measure. Tell the user, and plan again when they sing. Do not fall back on earlier numbers.
- A silent support singer keeps their fader, and the plan says so. Re-plan when they sing.
- A plan lasts five minutes, because levels move. Make a new one rather than forcing an old one.
- Reply in two or three lines: who leads, whether it verified, and the leader's measured level against the support singers.

Report any shortfall note. Aunty's mic is weak and her fader is near its limit, so she may not reach the goal. Mic gain is the real fix, and it needs the user's approval. If the user rejects a result by ear, follow their ear and re-measure.

## Indian songs

The user wants the pad above the drums and the drums lower for Indian songs. Measure the song first: the pad may already be well above the drums, and raising it further can cover the leader. Keep the pad under the leader.

Lower room drums with the Drums subgroup fader. It does not reach YouTube, so lower the Drums L/R and X/Y sends on Aux 3/4 as well, and raise the pad there if needed. Monitors have no drums. Apply with `set`, which saves a backup. When the user says the normal songs are back, undo the same settings from that backup after checking they have not been moved since.

## Mixing principles

These came from getting it wrong on the real desk, so they matter:

- **Judge real levels, never fader numbers.** David's input is about 10 dB stronger than Aunty's and the processing differs per channel, so a higher fader can still be quieter. Read `meter`, compare outputs, then calculate the move.
- **Measure at the output that matters.** Channel meters read before the subgroup. The Choir subgroup adds about 16 dB, and once made the choir 7 dB louder than the lead while the channels looked fine. Check the subgroup output for the room, and add up the four choir channels for an aux.
- **Subgroups do not reach the auxes.** The Choir and Drums subgroup faders do not change YouTube or monitor levels, apart from choir reverb, which comes from the Choir subgroup's FX2 send.
- **Sends follow faders.** Moving a channel fader also moves that channel in YouTube and the monitors. Check both after a room move, especially monitors, where a raise risks feedback.
- **Measure real singing.** Sample several spots and count only active signal. In session 0012, worship is around 8-20 and 100-120 minutes; 30-80 is mostly speech.
- **Do not over-trust one passage.** Singers vary by song, and a move based on a few seconds can be wrong.

Targets, as active peak output:

| Item | Room | YouTube |
|---|---|---|
| Leader | About -15 dB | About -15 dB before the aux fader |
| Support singers | About 8 dB under the leader | Same |
| Choir | About 8 dB under the leader, at the subgroup output | Around 10 dB under, four channels added up |
| Whole bus | Whatever the user chooses | Peaks near -10 dB, never at 0 |

## Safety

The room is live and the singers are real people on a stage, so keep these habits:

- Leave the master alone unless the user asks. They set it by ear, and `set` blocks it without `--allow-master`. The same goes for mutes (`--allow-mute`) and mic gain (`--allow-gain`).
- Never press Record or Delete Session, and do not overwrite snapshot `worship_final`.
- The user may be mixing at the same time. Read current values first and build on their changes.
- Saved snapshots and Soundcheck on/off are the user's actions in the mixer's app. Remind them that changes stay unsaved until they save a new snapshot, and that Soundcheck must be off for live mics.
- If `status` shows Soundcheck on during a service, tell them at once: the channels are playing a recording, not the live mics.
- Use the Aux Sends view in the app to show results. It opens on the last aux selected, so tell the user which tab to look at.

## Testing with a recording

Soundcheck on feeds a session into the channels. Mic gain changes have no effect on recordings, so they can only be tested live. Use `seek SECONDS --length SECONDS` to jump around a playing session; session 0012 is 8304 seconds long. 

`references/protocol.md` has the connection details and meter layout, for when the script needs extending.
