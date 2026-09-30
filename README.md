# Secret Agent Clank asset viewer

A local browser for Secret Agent Clank PS2 levels, mobys, textures, animations, and REL code symbols.

## Start the viewer

Requires Python 3 with Tkinter and a browser supporting WebGL 2. The extraction launcher supports the USA PS2 disc, **SCUS-97623**.

1. Double-click `start.cmd` to open the launcher.
2. For a new extraction, choose your ISO and a new or empty destination folder, then click **Extract and open**. Progress appears in the window; the first preview build takes longer.
3. To reuse assets, select **Open existing extraction...** or a **Recent folders** entry and click **Open**. The repository's `test/sac/extracted` folder appears automatically on first launch.
4. The browser opens when ready. Choose **Levels**, **Mobys**, **Textures**, or **Animation** in the sidebar.

Keep the launcher open while viewing. **Open browser** returns to the running viewer. Closing the launcher stops only its own server. It uses an available local port and can run alongside the Size Matters viewer.

Extraction does not overwrite existing files. If an extraction fails, its partial files remain available for inspection; choose a fresh or empty folder to retry.

## View assets

Models offer LOD selection, textures, wireframe, and Unlit inspection. Drag to orbit, Shift-drag to pan, and scroll to zoom. Matching animation libraries offer clip selection, playback, speed adjustment, and scrubbing. Libraries without a matching skeleton cannot play.

The Levels category contains 30 assembled scenes from the supplied extraction. Scenes combine saved terrain, props, foliage, mobys, and sky geometry. Layer switches control visibility; inactive templates start hidden. Search for a placed object and select **Focus object** to jump to it. **Overview**, **Ground view**, and **Fullscreen** provide other viewing options.

| Level control | Action |
| --- | --- |
| Drag | Look around |
| W / A / S / D | Fly |
| Space | Move up along Y |
| Control | Move down along Y |
| Shift | Fly faster |
| Scroll | Change flight speed |

Click the view before using keyboard controls.

Levels preserve baked vertex colors and alpha, with approximate saved ambient/directional lighting on meshes with authored normals. **Unlit** disables scene lighting; **Vertex colors** toggles baked colors for inspection.

## Files and caches

- `launcher.py` and `start.cmd`: extraction and viewing window.
- `browse.py`, decoder modules, and `web/`: asset catalog, local server, and browser interface.
- `FORMAT_NOTES.md`: format evidence and implementation details.
- `output/`: generated previews, catalog, and recent-folder settings for the default extraction. Other extraction folders keep their preview cache in `.viewer`.
- `tools/`: bundled ISO/WAD extractor, verification utility, and upstream TJZIP decoder. See `tools/README.md` for commands and attribution.
- `../test/sac/extracted/`: the default extracted game data.

All viewer and extraction code is contained in this repository. The existing game data remains at `../test/sac/extracted/`; you can also extract or open game data in any chosen folder using the launcher. New extraction destinations suggested by the launcher are inside `data/`. No external tools folder is required.

## Command-line use

Run these commands from `sac-asset-viewer`:

```bat
python -B browse.py
python -B browse.py --root "D:\path\to\extracted"
python -B browse.py --rebuild --build-only
python -B tools/extract_sac.py "D:/PS2/ISOs/Secret Agent Clank.iso" --output "data/sac-extracted"
python -B tools/verify_sac.py "data/sac-extracted"
```

The command-line server defaults to http://127.0.0.1:8766. `start.cmd --root "D:\path\to\extracted"` also starts the command-line server. Use `--out PATH` to choose a separate cache for another extraction. Restart the server and refresh the browser after updating Python decoder files.

## Preview limitations

Scenes show saved placements and poses. Gameplay scripts, runtime spawns, moving-object logic, runtime lights, fog, shadows, secondary shader passes, and animation events are not simulated. Some levels assemble objects or select forms at runtime; unresolved placements are listed in **Assembly details**. Terrain/prop/foliage labels are inferred from names. The viewer does not reproduce the game's complete rendering engine.
