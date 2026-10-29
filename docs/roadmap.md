# Roadmap

Planned, roughly in priority order. None of this is available yet.

- **Device fixtures** for power supplies, CAN, Ethernet and XIL, with replaceable drivers (for example open-source and commercial CAN adapters behind one interface).
- **`--param` overrides** with a defined precedence model.
- **Device simulation** over shared memory: a simulated DUT in one process, with tests attaching to it through simulated fixtures, or several processes connected to a simulated bus.
- **A local web UI** for device configuration, interactive tests and monitoring.

## Open design questions

These are deliberately undecided. Current behaviour is the conservative choice and may change:

- How generic and complex types behave across subclasses.
- How `None`, f-strings and other special values are represented in config.
- The precedence of inherited, group and local parameters.
- How partial runs and non-test config entries are reported.
- A canonical API for plugins to access host state.
- How external frameworks call tests and consume results.
