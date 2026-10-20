"""Base class for reusable device and interface fixtures."""


class Fixture:
    """Common lifecycle interface for project-specific fixtures.

    Fixture hooks default to no-ops so a subclass only needs to override the
    lifecycle stages it uses. Override :meth:`self_test` to return ``False``
    when a connected fixture fails its health check.

    Configuration mapping treats parameters annotated with a ``Fixture``
    subclass as references to other configured fixtures.
    """

    def setup(self) -> None:
        """Connect to the device and perform one-time setup."""

    def self_test(self) -> bool:
        """Check that the fixture is ready for use."""
        return True

    def start(self) -> None:
        """Prepare the fixture before each testcase that uses it."""

    def stop(self) -> None:
        """Stop per-test activity after a testcase uses this fixture."""

    def lazy_stop(self) -> None:
        """Stop a fixture that was needed by the previous testcase only."""

    def disconnect(self) -> None:
        """Safely disconnect this fixture from other equipment."""

    def teardown(self) -> None:
        """Release resources after the fixture is no longer needed."""
