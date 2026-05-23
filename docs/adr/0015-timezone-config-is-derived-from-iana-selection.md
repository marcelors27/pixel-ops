# 0015 - Timezone Config Is Derived From IANA Selection

Status: Accepted

## Context

People/timezone config previously exposed several low-level fields in Config Studio:

- display key, such as `IST`;
- country code, such as `IN`;
- timezone label;
- standard and daylight abbreviations.

Those fields are easy to mistype and consume horizontal space in the editor. The runtime only needs stable JSON values, while the UI can derive most of them from a valid IANA timezone.

## Decision

Config Studio treats the IANA timezone as the primary editable value.

The UI presents timezones from `Intl.supportedValuesOf("timeZone")`, with a small fallback list for older browser runtimes.

Timezone fields are entered through a searchable combobox. When a valid timezone is chosen, the Studio derives:

- `key`;
- `timezone_label`;
- `standard_key`;
- `daylight_key`;
- known country code and `show_flag` when the timezone has a configured mapping.

The people list order is user-controlled and stored by reordering the `people` array in `pixel_ops/config/people.json`.

## Consequences

The HUD renderer still receives the same JSON shape and does not need to know about Config Studio UI behavior.

The editor has fewer manual fields and a wider timezone selector.

Country inference is intentionally conservative. Unknown IANA zones keep an empty country code rather than guessing.

If full country inference becomes important, add an explicit timezone-to-country data source instead of deriving it from string prefixes.
