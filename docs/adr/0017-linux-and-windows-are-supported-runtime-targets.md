# 0017 - Linux And Windows Are Supported Runtime Targets

Status: Accepted

## Context

Pixel OPs started as a local Python runtime for a small USB display, but the useful development loop is not tied to one operating system.

The runtime has three different portability surfaces:

- file outputs, such as preview PNG and GIF;
- desktop window output through pygame;
- physical TURZX/Turing USB display output through PyUSB/libusb.

The first two should work cross-platform with normal Python and Node dependencies. USB display output is platform-specific because device driver and permission models differ between Linux, Windows, and macOS.

## Decision

Linux and Windows are first-class runtime targets for `preview`, `gif`, and `window` outputs.

The TURZX USB backend remains a shared PyUSB transport, but platform setup is documented separately:

- Linux uses libusb plus udev permissions for device `1a86:5722`;
- Windows uses a WinUSB/libusb-compatible driver, typically installed with Zadig.

Platform checks live in scripts:

- `scripts/linux_check.py`;
- `scripts/windows_check.py`.

CI runs separate Linux and Windows workflows that install dependencies, run Python tests, build Config Studio, and render an offline preview.

Platform-specific PC stats detection is allowed inside the `pc_stats` data source, but unavailable metrics must degrade to `unknown` instead of failing the display loop.

## Consequences

Preview, GIF, Config Studio, integration loading, and Pokemon rendering should stay path-portable and avoid shell-specific assumptions.

Hardware support is documented as a setup concern rather than hidden in application logic. Runtime errors for USB claim failures should point to the likely platform-specific fix.

Any new feature that uses local commands or system paths must include a no-crash fallback and should be covered by platform-neutral tests where possible.
