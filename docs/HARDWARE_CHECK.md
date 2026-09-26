# Hardware Check

Hardware Check tests every part of the phone and saves a report. It's how ucrom proves itself on real hardware.

Open **Hardware Check**, tap **Run checks**. Each part gets one of:

| Result | Meaning |
|---|---|
| PASS | present and answered |
| FAIL | the device profile says it should be there, but it didn't work |
| ABSENT | not on this machine (normal in the emulator) |
| ASK | only you can tell: tap **Test**, then **Yes** or **No** |

What it checks: ucrom system info, touchscreen, keyboard/mouse blocking, power/volume buttons, display and refresh rates (90 Hz on the 7T Pro), GPU, Wi-Fi scan, Bluetooth, mobile network, speaker and microphone, cameras, pop-up camera motor, fingerprint, sensors, vibration, flashlight, NFC, GPS, battery and charging, alert slider.

Checks never fake a pass. Anything software can't prove (did you hear the bell?) is asked.

The report is saved to `~/ucrom-hardware-report.html` and `~/ucrom-hardware-report.json`. From a computer: `ucrom-hwcheck --auto` prints the automatic part as JSON.
