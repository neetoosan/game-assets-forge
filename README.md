# Game Asset Forge (Blender 4.2+ extension)

Generates rigged anime characters and seeded game props, then cleans and exports them for Godot / web (GLB) or FBX.

## Install
Blender → Edit → Preferences → Get Extensions → ▾ (top right) → **Install from Disk…** → pick `game_asset_forge-1.0.0.zip`.
Open the sidebar in the 3D Viewport (**N**) → **Game Forge** tab.

## Panels
**Anime Character** – presets (Silver Spiky, Wild Spikes, Long Hair, Casual Short, Messy Blond) or set everything yourself:
height, head size, body width, skin/eye colors, eye shape, mouth, 5 hair styles, top (tee+turtleneck / tee / long sleeve),
shorts or pants, stripes, shoes. 🎲 button randomizes the look. Builds at the 3D cursor:
- painted anime face texture, gradient-shaded hair, ink outline (inverted hull)
- 53-bone skeleton using **Godot humanoid bone names** (Hips, LeftUpperArm, LeftIndexProximal …) so Godot's
  retargeting maps it automatically; skin weights max 4 bones/vertex
- Smoothness 0 ≈ 12k tris (mobile), 1 ≈ 45–50k tris (PC)
- Re-clicking Generate with the same name rebuilds that character. It never overwrites collections it didn't create.

**Props** – Crate, Barrel, Rock, Tree (round/pine), Fence, Treasure Chest, Sword, Potion. Seeded, so the same seed
gives the same prop; Count makes a row of variations; **Pack** makes one of each.

**Game-Ready & Export** (works on any mesh, not just generated ones)
- Make Game Ready: apply rot/scale, merge duplicates, fix normals, remove loose geometry, auto-UV if missing,
  optional triangulate / origin-to-bottom
- Generate LODs (hidden decimated copies; Godot can also auto-generate LODs on import)
- Add Collision: child mesh named `<name>-convcolonly` → Godot makes a ConvexPolygonShape3D on import
- Check: triangles per asset vs. budget, materials, missing UVs, non-manifold edges
- Export: GLB / glTF / FBX, one file per asset, outline hull skipped by default

## Scripting
```python
from bl_ext.user_default.game_asset_forge import character, props, pipeline   # installed extension path
rig, builder = character.build_character(name="Hero", hair_style='UPWARD', hair_color=(0.1, 0.1, 0.1), height=1.6)
barrel = props.build_prop('BARREL', seed=42, size=1.0)
pipeline.export_assets([rig, barrel], "//exports", fmt='GLB')
```
