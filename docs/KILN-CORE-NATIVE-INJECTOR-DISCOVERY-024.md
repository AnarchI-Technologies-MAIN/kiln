# Kiln Core Native Injector Discovery 024R

Core 024R corrects identifier-component discovery.

The prior implementation used regex word boundaries.

Python-style underscores are word characters, so token_revoked did not expose revoked as a carrier component.

Core 024R uses alphanumeric boundaries instead.

This admits separators such as underscore, hyphen, dot, and whitespace while refusing longer alphanumeric substrings.

Discovery remains evidence only.

No candidate is authorized for injection during this phase.
