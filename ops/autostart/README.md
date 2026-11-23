# Keep Leadnius running (macOS)

Leadnius only sends LinkedIn requests, emails and reads replies while its backend is running. These two files make
macOS start the backend (port 8000) and the app (port 3001) at login and restart them if they stop.

## Turn it on

Run this once in Terminal:

```bash
mkdir -p ~/Library/Logs/Leadnius
cp "$HOME/Desktop/Lead Gen/ops/autostart/"in.leadnius.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/in.leadnius.backend.plist
launchctl load ~/Library/LaunchAgents/in.leadnius.frontend.plist
```

If macOS asks whether "node" or "python" may access files in your Desktop folder, choose Allow.

## Check it

- Open http://localhost:3001.
- Logs are in `~/Library/Logs/Leadnius/`.

## After a code change

```bash
launchctl kickstart -k gui/$(id -u)/in.leadnius.backend     # backend
npm --prefix "$HOME/Desktop/Lead Gen/lead-gen-frontend" run build && launchctl kickstart -k gui/$(id -u)/in.leadnius.frontend
```

## Turn it off

```bash
launchctl unload ~/Library/LaunchAgents/in.leadnius.backend.plist ~/Library/LaunchAgents/in.leadnius.frontend.plist
rm ~/Library/LaunchAgents/in.leadnius.backend.plist ~/Library/LaunchAgents/in.leadnius.frontend.plist
```

## Notes

- The Mac must be awake. A sleeping Mac sends nothing; sending resumes when it wakes.
- Stop any copy started by hand first, or the ports will already be taken.
