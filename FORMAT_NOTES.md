# SAC format evidence

Level assembly follows the named loader routines in the extracted `BIN/LEVEL1.REL`. Addresses below are module/file offsets, not relocated EE addresses.

- `LoadGeomHdrIFFCB` (0x2108d0) reads GINH: two version bytes, x basis at +2, z basis +14, position +26, scale +38, flags +50, name hash +54, animation hash +58, 32-byte name +62, definition hash +94, parent hash +98, parent-part hash +102. `ApeObj::Serialize` (0x20d400) constructs y = z cross x and applies scale. Instances with visibility bit zero are available under Inactive / templates.
- `BOG_LoadFile` (0x185a08) requires version 58. Header +44/+48 identifies the 80-byte type array; +52/+56 identifies the 128-byte moby array. A moby begins with a column-major matrix, type pointer at +64, form byte +68, original signature +92, and flags +100. Unused pool records have zero original signature. Type +4 points to 52-byte forms and +72 gives the form count.
- The loader at 0x1b7960 finds a 136-byte REL registry record by type signature: signature, type-info pointer, then 32 model-name pointers. Both animated and static forms resolve through this table (static branch 0x1b7e7c). Table candidates are bounded and validated against their type-info name and all string pointers. No nearest-name matching is used.
- `LoadHdrIFFCB` for materials (0x1c5c20) identifies MTLH blend/cull/flags at +57/+58/+59, diffuse RGBA +60, and texture clamp bytes +72/+73. The level preview supports opaque/cutout, alpha, and additive material passes. More specialized shader behavior remains approximate.

Museum's WAD is `level01_Museum/level01_museum.mb.wad`; its corresponding cooked scene is `Level01_Exterior/Level.san.cooked`. Other scene-to-WAD matches use the folder name without case sensitivity. Geometry resolution prioritizes the level, then shared banks, then actor banks. Runtime-only forms, missing references and unsupported parent-part attachments are reported instead of fabricated.

Binary level geometry is little-endian: interleaved float32 position/normal/UV (32-byte stride) and uint32 triangle indices. Instances reference shared geometry and carry their own transforms. Only LOD 0 is assembled. Camera bounds exclude sky and inactive templates.


### Level lighting and material audit (2026-09-29)

VIF stream 3 contains baked RGBA for V4-5/V4-8 packets, not normals.
`ReadRGBA` at REL 0x1e1fc0/0x1e2080 and `AddVifCompressedRGBAPacket`
show that GS unity is 128. Preserve RGB / 128 and alpha / 128; dividing by
255 would incorrectly halve the baked light. V3-16 instead carries LitProp
normals (signed fixed point / 32768). UV2 V bit 0 is ADC strip metadata and
must be cleared before dividing the UV by 4096. Skinned UV3 is unchanged.

Level binary version 2 uses 48-byte vertices: position3, normal3, UV2,
RGBA4 floats. Each part records whether it has baked colors or authored
normals for scene lighting. Baked geometry is not dynamically lit again.
The standalone model preview also bypasses its inspection light for baked
geometry. Materials are deduplicated by their complete state, not just
name/texture, and model responses copy scene materials before attaching URLs.
Cross-archive texture fallback requires a unique signature match.

All 30 saved scenes contain an ambient and a directional LITB/LINS pair.
LITH v1 stores type +1, group +2, RGB +6, intensity +10, definition hash +26;
LINH v1 uses GINH transforms and definition hash +94. Light serialization
at 0x2099b8 square-roots intensity; ProcessLights at 0x211b20 clamps ambient
intensity to one and uses negative world Z for directional vectors. The
preview approximates the game lighting with ambient plus Lambert diffuse;
animated/runtime lights, fog, shadows and secondary shader passes remain
unsupported. All audited saved lights have no parent; their group masks
are retained and matched against GINH +110.

Material serialization at 0x1c4b38 uses flags bit 4 for depth writes and
bit 3 for depth comparison (enabled: nearer-or-equal, otherwise always).
Blend modes 2/3/4 correspond to alpha/additive/reverse-subtractive blending.
The preview retains alpha fades instead of forcing opaque vertex colors.
