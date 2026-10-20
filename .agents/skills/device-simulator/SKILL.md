---
name: device-simulator
description: This skill contains a description of the device simulaton
---


There are two types of simulated devices:
- The hardware get's simulated in one process and the test process attaches via shared memory to that simulation.
- The simulator just simulates a bus and different processes connect to that bus.


The basic idea is to use shm-comm to broadcast and receive messsages send between a simulated DUT and the test process.
https://pypi.org/project/shm-comm/


In the first case the simulated device could be a DUT, emulated in a different process.
The test code would usually interact with that DUT via test devices like sensors, power supply, and actors.
Instead of these physical fixtures the idea here is to have a simulated fixture that uses shared memory to
connect to the process running the DUT.


This approach can also be useful to attach monitoring to existing fixtures.

