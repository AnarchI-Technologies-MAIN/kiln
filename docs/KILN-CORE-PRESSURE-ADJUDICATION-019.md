# Kiln Core Pressure Adjudication 019

Core 019 adjudicates bounded pressure observations.

Complete survival of 1x, 2x, 4x, 8x, and 16x becomes PRESSURE_ENVELOPE_SURVIVED.

The first failed level becomes PRESSURE_FRACTURE.

A fracture records the highest previously survived level.

A fracture does not authorize repair.
