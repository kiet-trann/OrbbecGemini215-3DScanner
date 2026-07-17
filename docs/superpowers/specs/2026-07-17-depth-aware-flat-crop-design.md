# Depth-aware flat crop design

The flat crop canvas will build a low-resolution depth buffer from projected
mesh faces after the 3D view settles. It will draw only sampled vertices whose
depth matches the nearest surface at their screen cell. This hides rear faces
and background layers that currently collapse onto the 2D crop projection.

The buffer runs only after right-button release, uses the existing settled
camera projection, and does not change crop geometry, OBJ files, or textures.
Tests will verify that two points projected to the same cell retain only the
nearer depth.
