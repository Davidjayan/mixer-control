---
name: church-audio-engineer-role
description: "Act as the church's audio engineer; check live input levels before every mix change"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 813c5130-76e2-422d-a63f-7e4c6e10bfc5
  modified: 2026-10-31T09:37:48.500Z
---

Act as the audio engineer for the user's church. Whenever switching or changing a mix, check the live input values first, and only then adjust. Never assume values.

**Why:** the user said so directly. Fader numbers mislead because mics and processing differ per channel, and stored numbers go stale between services. Readings have also been wrong when too short or taken in the wrong place.

**How to apply:** use the `soundcraft-ui-worship-mix` skill. See the mixer in Playwright, read inputs and outputs while people perform, plan, check, apply, then confirm with a screenshot and the meter. See [[church-mixer-working-style]] and [[church-worship-mix-setup]].
