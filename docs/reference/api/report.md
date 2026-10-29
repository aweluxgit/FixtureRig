# `fixturerig.report`

```{eval-rst}
.. automodule:: fixturerig.report
   :no-members:
```

## The report stream

```{eval-rst}
.. autodata:: fixturerig.report.report
   :annotation:

   The global report proxy. It forwards every call to the stream that is active
   for the current run, so tests, fixtures and steps can import it once at
   module level. It has the same reporting methods as :class:`ReportStream`.

.. autofunction:: fixturerig.report.current_stream

.. autoclass:: fixturerig.report.ReportStream
   :members:
```

## Report modules

```{eval-rst}
.. autoclass:: fixturerig.report.ReportModule
   :members:

.. autoclass:: fixturerig.report.RecordingReport
   :members:

.. autoclass:: fixturerig.report.console.ConsoleReport

.. autoclass:: fixturerig.report.console.ColoredConsoleReport

.. autoclass:: fixturerig.report.json_report.JsonReport

.. autoclass:: fixturerig.report.html.HtmlReport

.. autoclass:: fixturerig.report.allure.AllureReport

.. autoclass:: fixturerig.report.excel.ExcelReport

.. autoclass:: fixturerig.report.pdf.PdfReport

.. autoclass:: fixturerig.report.pdf.PdfTestSpecReport

.. autofunction:: fixturerig.report.loader.build_report_stream

.. autofunction:: fixturerig.report.loader.create_report_module
```

## Report elements

```{eval-rst}
.. automodule:: fixturerig.report.elements
   :members:
```

## Events

```{eval-rst}
.. automodule:: fixturerig.report.events
   :members:
   :exclude-members: kind
```
