# Cropped OBJ catalog design

## Goal

Let an operator reopen any previously created cropped OBJ after restarting 3D
3D Scanner, without relying on in-memory state from the latest crop.

## Discovery service

Create a read-only crop-output catalog that recursively finds only files named
`*_cropped.obj` beneath `outputs/scanner_3d`. It returns existing files as
immutable records containing their OBJ path, containing output directory, size,
and last-modified time, sorted newest first. Raw native OBJ exports are excluded.

## User interface

The main window adds a `Cropped OBJ outputs` list below the saved RTAB-Map
session list. Its rows show the cropped OBJ name, output-folder name, size, and
last modified time. The catalog refreshes at application start, through a
refresh control, and after a crop succeeds. After successful crop, the new row
is selected automatically.

Selecting a row makes `Open cropped OBJ` and `Open output folder` act on that
row. Before a selection they remain disabled. The buttons no longer depend on
the crop created in the current process.

## Failure handling and tests

Discovery ignores unreadable/missing files rather than failing the window.
The existing validated shell action still verifies the chosen target at click
time, so an externally deleted output produces a status message instead of a
shell error. Tests cover recursive discovery, raw-export exclusion, newest-first
ordering, and source-file immutability.
