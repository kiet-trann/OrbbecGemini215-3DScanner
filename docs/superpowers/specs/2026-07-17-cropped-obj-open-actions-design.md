# Cropped OBJ open actions design

## Goal

Let an operator open the latest successfully created cropped OBJ or its output
folder directly from 3D Scanner, without copying paths from the status log.

## User interface

The main window gains two disabled buttons below the crop action:

- `Open cropped OBJ` opens the latest successful crop with the Windows default
  application for `.obj` files.
- `Open output folder` opens the directory that contains that OBJ, its MTL, and
  texture files.

Both become enabled only after `_crop_worker` has produced a real `CropResult`.
They remain disabled before a crop and after a crop error, so the app never
opens a stale or guessed path.

## Data flow and failure handling

`Scanner3DWindow` stores the result OBJ path only on the Tk event loop,
after its background crop worker succeeds. The open actions verify the stored
file/directory still exists before invoking the Windows shell. A missing file or
an operating-system launch failure is reported in the existing status area.

Opening uses `os.startfile` on Windows, which delegates to the user-configured
viewer. The scanner does not bundle, choose, or control a 3D viewer. If no OBJ
association is configured, Windows shows its normal app-choice prompt; opening
the output folder remains available independently.

## Testing

Extract a small, injectable `OpenActionService` that verifies target existence
and calls an injected launcher. Unit tests cover an existing OBJ, its existing
parent folder, and missing targets without using a real shell or GUI.
