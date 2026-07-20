# Card dashboard visual refresh design

## Goal

Rebuild the scanner desktop presentation to closely match the approved light card-dashboard mockup: a dark-blue sidebar, bright content surface, rounded cards, a clear visual hierarchy, and a high-emphasis action for the current scan step.

## Scope

The change replaces only the desktop presentation layer. Camera preflight, camera profile selection, RTAB-Map process launching, Pause/Resume, auto-pause monitoring, session discovery, OBJ export, crop, GLB opening, output locations, and controller validation remain unchanged.

The window will use CustomTkinter for the app shell, cards, labels, buttons, status chips, and navigation. Existing `ttk.Treeview` widgets remain for session, camera-detail, and crop-output tables, styled to match the light dashboard. No scan algorithms, RTAB-Map options, camera modes, export formats, or persistence are added.

## Visual system

The application is locked to light appearance. The sidebar is dark navy with white product text, muted section labels, and a single blue active route. The main surface is a warm off-white/very-light neutral. Cards are white with a thin neutral border, 10-12 px corner radius, restrained shadow, and 16-20 px internal padding.

Use Segoe UI throughout: a 24 px page title, 16 px card title, 13-14 px body copy, and 11-12 px uppercase metadata labels. One blue primary button appears in the current-action card. Secondary actions are quiet outline or transparent buttons. Green/blue status chips communicate readiness; error states use the existing status message with a visible destructive chip.

The implementation must preserve the 860x640 minimum window size. Main content cards stack vertically below 900 px wide; no primary action or table is clipped horizontally.

## Application shell

The shell has a fixed 220 px left sidebar and a scrollable main content region. The sidebar has the brand `3D Scanner`, a small `KHÔNG GIAN LÀM VIỆC` label, and the existing four routes: Quét mới, Camera, Phiên & kết quả, and Công cụ nâng cao. Route switching only replaces main content; it never reinitializes services or changes scanner state.

The main header has an eyebrow `MÁY QUÉT 3D`, the page title, and a readiness chip populated from existing `DashboardState`. The chip describes the active runtime state and uses neutral/ready/error styling without introducing a second source of truth.

## Page design

### Quét mới

Quét mới follows the approved mockup exactly in structure:

1. A large hero card shows the current numbered stage, title, concise explanation, and the single primary action. The existing pure `GuidedWorkflow` decides whether the action is Kiểm tra camera, Bắt đầu quét, or Tạm dừng.
2. Three equal cards summarize Camera, Phiên quét, and Kết quả. They show existing data only and direct the operator to Camera or Phiên & kết quả; they do not duplicate controller actions.
3. A two-card lower row shows device/runtime detail and quick links. It collapses to one column in a narrow window.

### Camera

Camera uses a control card for profile selection, Kiểm tra thiết bị, and Áp dụng & mở RTAB-Map. A separate detail card contains the existing settings table. The original camera locks still apply during RTAB-Map operation.

### Phiên & kết quả

The session catalog and its refresh/export actions appear in a titled card. The cropped-output table and crop/open actions appear in a second titled card. The buttons retain their current selection guards and error messages.

### Công cụ nâng cao

The page has three cards: runtime state, Pause/Resume control, and Auto-pause. It explicitly labels auto-pause as experimental and retains its existing availability/error message.

## Component boundaries

Create `src/scanner_app/visualization/dashboard_theme.py` as the sole owner of color, typography, CustomTkinter appearance configuration, ttk Treeview style configuration, and reusable card/status-chip constructors. It has no RTAB-Map, camera, or export dependency.

`Scanner3DWindow` remains the composition root. It obtains the existing `DashboardState`, maps it through `GuidedWorkflow`, and provides callbacks to presentational widgets. It owns route frame lifetime but does not acquire hardware or launch services outside existing controller methods.

## State and errors

`DashboardState` remains the only source for runtime, auto-pause, profile, snapshot, and camera-lock state. Session and crop collections remain owned by `Scanner3DWindow` exactly as before. A small presentational status mapping converts current status text into chip styling; it cannot alter actions or state.

Controller and file-action errors retain their original messages. The shell surfaces the latest message in the header status chip and a compact visible status region under the page header. No errors are discarded on route changes or refresh.

## Verification

Add pure theme/status tests and preserve all existing navigation, guided-workflow, camera lock, preflight, Pause/Resume, auto-pause, session, export, crop, and viewer-opening tests. Add UI tests for the primary workflow action, readiness-chip derivation, and route switching without controller calls.

Run focused tests, the full pytest suite, and Ruff for the changed UI files. Launch the Windows application manually and compare Quét mới against the approved mockup: fixed sidebar, header chip, large hero card, three summary cards, lower two-card row, light theme, and responsive stacking at the minimum window size.
