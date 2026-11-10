# {{PROJECT_NAME}} design contract

<!-- kit: DESIGN.md is normative, not descriptive: it states what new work must look like, and a
change to the look or copy updates it in the same PR/MR. Fill the sections from the current
implementation (tokens, components, copy rules) and mark known deviations as debt with their
issue numbers. For a project without a user interface, keep the file and let it govern the
user-facing surface that exists instead: CLI output, API shapes, error codes, file formats. -->

DESIGN.md is the authoritative design contract for {{PROJECT_NAME}}: layout, tokens, components
and their behaviour, states, copy and formats. Define visual changes here before implementation
tweaks land. New screens follow this contract; changes to the look or copy update it in the same
{{HOST_PR_ABBR}}. Named implementation deviations are documented below as known debt with their
issue numbers. New work follows the contract.

Source files: <!-- the token file, the global stylesheet, the component kit directory, the app
shell components; one line each -->

## How to build a screen

<!-- Which styling layers exist and which one new work uses; where a screen's parts come from. -->

## Foundations

### Contract ownership and verification

- One fact has one visual place: show a status, result or action on the surface that owns it.
  An equivalent hidden accessible label may repeat it.
- Enforce the contract's behaviour and copy with interaction tests next to the area's code;
  browser scenarios in `features/` verify geometry and journeys that a DOM test cannot check.
- When the look changes, update this contract and the screenshots under `docs/assets/design/`
  in the same {{HOST_PR_ABBR}}.

### Colour

<!-- Named tokens with values and their one permitted use each (surface, text, accent, success,
warning, danger). No raw colour values outside the token file. -->

### Typography

<!-- Font families, the size scale, where each size is used, line heights. -->

### Spacing, radius, elevation

<!-- The spacing scale, radii, shadows; which component uses which. -->

### Icons

<!-- Icon set, sizes, when an icon stands alone and when it carries a label. -->

### Interaction

<!-- Focus, hover, pressed, disabled; keyboard behaviour; motion limits. -->

## Layout

### App shell

<!-- Navigation, header, content width, where global actions live. -->

### Page patterns

<!-- List page, detail page, form page, wizard: their fixed structure. -->

### Responsive behaviour

<!-- Breakpoints, what collapses, minimum supported width (the project's narrow screenshot width). -->

## Components

<!-- One subsection per component kit primitive: purpose, variants, states, source file; then the
recurring composites built from them. Only the layers named in "How to build a screen". -->

## States

<!-- Loading, empty, error and success states: what each shows and in which words; a state is
never faked ("everything OK" only when there is something to report). -->

## Copy and formats

### Tone and wording

<!-- Language of the UI ({{SOFTWARE_LANGUAGE}}), address form, button verbs, how errors speak
to the user, forbidden phrasings. -->

### Number, money, date and size formats

<!-- One table: what, format, example. The code reads these from one formatting module. -->

## Screenshots

<!-- Reference screenshots under docs/assets/design/, named after the screen, desktop and
narrow width, taken with synthetic data. Replace them in the PR/MR that changes the look. -->
