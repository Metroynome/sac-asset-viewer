# Secret Agent Clank asset viewer

Run `start.cmd`, then open http://127.0.0.1:8766. Requires Python 3 and a WebGL browser. Assets are read from `../test/sac/extracted`; use `python -B browse.py --root PATH` to select another extraction.

Browse textures, mobys, animation libraries and named code symbols. Models support LOD selection, textures, wireframe, orbit, pan and zoom. Matching animation libraries support clip selection, playback and scrubbing. Unlit displays texture colors without preview lighting.

The SAC decoder reads cooked IFF scenes, PS2 indexed textures and palettes, VIF triangle strips, bone palettes, authored vertex normals and compressed animation tracks. The preview uses the base texture layer and simplified lighting; game shader effects and animation events are not reproduced. Libraries without a matching skeleton remain unavailable for playback.

After changing decoder code, restart the server and refresh the browser. `--rebuild --build-only` rebuilds the asset catalog. Generated output and research captures are ignored by Git.

## Levels

The Levels sidebar opens 30 assembled scenes, including Level 1 - Museum / Exterior. The viewer combines cooked GINS placements with BOG gameplay objects, resolves model names using each level's REL registry, and reuses shared mesh buffers. WebGL 2 is required.

Drag to look, use W/A/S/D to fly, Space to move up and Control to move down along the Y axis, and Shift to move faster. Scroll changes flight speed. Overview resets the camera; Find a placed object and Focus object jump to an instance. Layer toggles cover terrain/scenery, props, foliage, mobys, sky, and inactive templates. Fullscreen is available.

The scene shows authored placements in their saved poses. It does not execute gameplay scripts, procedural spawns, moving-object logic, or all game shaders. Some levels select player skins and construct objects at runtime; unresolved references are counted and listed in Assembly details. Layer labels are name-based presentation groups, not a claim that SAC uses the original trilogy's tie/shrub file layout. Inactive templates are hidden by default to avoid piling library models at the origin.

Restart the server after updating Python files; no asset extraction or catalog rebuild is required for Levels.

Levels preserve baked vertex colors and transparency, and approximate saved ambient/directional lights on meshes with authored normals. Unlit disables scene lighting; Vertex colors toggles baked colors for inspection. Runtime lights, fog, shadows, and secondary shader passes are not reproduced.
