---
name: wake-sprite
description: Wake the Fly.io Sprite named cli-sprite-1 when the user asks to wake their Sprite.
metadata:
  original-author: "John Egan"
---

# Wake the Sprite

Run one short command against `cli-sprite-1` to wake it from inactivity:

```bash
sprite exec -s cli-sprite-1 --no-stdin --no-port-forward -- true
```

If the command succeeds, tell the user the Sprite is awake. If it fails, report the CLI error without claiming it woke up. Do not start a persistent session or keepalive process; the Sprite may sleep again after it becomes idle.
