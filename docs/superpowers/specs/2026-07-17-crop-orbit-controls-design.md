# Crop orbit controls design

The crop preview will support free orbit rotation by wrapping yaw and allowing
pitch through the full vertical range while keeping the camera outside the mesh.
It will add Reset, Front, Back, Top, and Bottom buttons. Each control updates
the same camera projection used by the flat crop plane and crop service, so
presets cannot desynchronize visible geometry from crop output.

Tests will cover named preset angles and ensure pitch is no longer clamped to
the prior +/-1.35 radians limit.
