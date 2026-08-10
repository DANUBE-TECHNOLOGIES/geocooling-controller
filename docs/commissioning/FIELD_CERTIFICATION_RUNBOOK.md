# GeoCooling — Field Certification Runbook

## Scope

Final physical commissioning after EV and M11/M13 are wired to the Waveshare.
This procedure does not bypass any software gate and must never be used before
`FIELD_CERTIFICATION_REQUIRED` is reached.

## Preconditions

The read-only preflight must pass:

```bash
bash scripts/commissioning/field-certification-preflight.sh
```

Expected state:

- commissioning state: `FIELD_CERTIFICATION_REQUIRED`
- telemetry: 5/5 required roles ready
- physical sensor identification confirmed
- field certification not yet confirmed
- controller OFF
- autopilot OFF
- ordinary controller START forbidden
- no commissioning test active
- EV and M11/M13 physically wired and electrically verified

## Safety order

The physical sequence is always:

1. EV open
2. wait for hydraulic opening
3. M11/M13 start together
4. M11/M13 stop
5. EV close

Never start M11/M13 against a closed EV.

## Test 1 — EV only

Temporarily enable commissioning tests in the local runtime configuration only
after wiring has been checked. Keep the normal controller sequence and autopilot
disabled.

The API request requires the exact confirmation text:

`JE CONFIRME LE TEST GEOCOOLING`

Use the timed commissioning endpoint for the valve. The test manager automatically
closes EV at the end and forces safe outputs in its cleanup path.

During the test, physically verify:

- the intended Waveshare relay changes state;
- the correct transfer relay/contactor operates;
- EV actually opens;
- no M11/M13 start occurs;
- EV returns closed automatically;
- the software test result is `COMPLETED` with no cleanup errors.

If any mismatch is observed, cancel immediately through the commissioning cancel
endpoint and investigate before proceeding.

## Test 2 — M11/M13 group

Only after the EV-only test passes, run the timed pump commissioning test.

The test manager must:

1. open EV;
2. wait the configured pre-open delay;
3. start the grouped M11/M13 actuator;
4. stop M11/M13 after the timed interval;
5. close EV;
6. force outputs safe in cleanup.

Physically verify both circulators correspond to the intended circuit and stop
at the end of the test.

## Test 3 — cancellation / safe-stop

Start a short commissioning test and exercise the cancel endpoint while active.
Verify that:

- M11/M13 stop if running;
- EV closes;
- the test reports `CANCELLED` rather than remaining active;
- no relay stays energized unintentionally.

## Certification evidence

Record, at minimum:

- date/time;
- operator;
- EV relay number and observed function;
- M11/M13 relay number and observed function;
- EV-only test result;
- M11/M13 timed test result;
- cancellation/safe-stop result;
- any cleanup warnings;
- current commissioning-readiness snapshot.

Only after these physical observations pass may
`GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED=true` be set locally.

## Post-certification safe defaults

After certification, disable the commissioning-test window again and leave these
safe unless deliberate production activation is being performed:

```text
GEOCOOLING_COMMISSIONING_TESTS_ENABLED=false
GEOCOOLING_HARDWARE_ARMED=false
GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false
GEOCOOLING_AUTOPILOT_ENABLED=false
GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false
```

The expected commissioning state then becomes `READY_FOR_RELEASE`. Release
readiness should still require safe runtime defaults before declaring deployment
ready.

## Abort criteria

Abort physical commissioning immediately on any of the following:

- wrong relay actuates;
- EV does not move as expected;
- M11/M13 operate before EV is open;
- a circulator fails to stop;
- relay feedback disagrees with the physical state;
- thermal telemetry becomes stale;
- commissioning gate leaves `FIELD_CERTIFICATION_REQUIRED` unexpectedly;
- any cleanup error is reported.

Do not compensate for a failed physical test by manually setting the field
certification flag.
