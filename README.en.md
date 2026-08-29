# chappy — Code for Handling Absorption Profiles with PYthon

[日本語](README.md) | **English**

[![CI](https://github.com/Di-Is/qso-chappy/actions/workflows/ci.yml/badge.svg)](https://github.com/Di-Is/qso-chappy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)

Light from a distant quasar passes through countless clouds of gas on its way to Earth.
Along the way, specific wavelengths are absorbed, leaving dark features — absorption lines — in the spectrum.

chappy is a desktop application that measures the shape of those lines to estimate how much gas
blocked the light, and how fast and how hot that gas was.
It is built for everyone from high-school students and citizen scientists to graduate students and
researchers who use it daily.

## What you can do

- **View spectra** — Load spectroscopic data in FITS format and pan and zoom across wavelength
- **Fit the continuum** — Interactively set the continuum level that absorption measurements are made against
- **Model absorption lines** — Overlay Voigt profiles to estimate column density, Doppler parameter, and radial velocity
- **Optimize automatically** — Refine your hand-placed initial guesses into a best-fit solution
- **Identify absorbers** — Work out which element or ion produced a feature from the pattern of wavelengths
- **Keep your results** — Save an analysis as a project to resume, share, or export later

The interface is available in Japanese and English.

## Getting started

1. Get the latest build from [Releases](https://github.com/Di-Is/qso-chappy/releases)
2. Follow the steps in [INSTALL.en.md](INSTALL.en.md)

You do not need to install Python yourself — the required Python version and dependencies are
downloaded automatically on first launch.

**A tutorial starts automatically the first time you launch the app.**
A sample quasar spectrum (Q0329-385, observed with VLT/UVES) is bundled, so you can walk through
loading data and fitting an absorption line without preparing your own observations.
You can restart the tutorial at any time from **Help > Tutorial**.

## Learning the interface

Open **Help > User Guide** in the app for screen-by-screen instructions.
The manual ships with the release package and opens in whichever language the interface is set to.

## Requirements

- Windows / macOS / Linux
- Python 3.12 or later (installed automatically; no prior setup needed)

## Getting help

If something does not work, or you are unsure how to proceed, open an issue on
[Issues](https://github.com/Di-Is/qso-chappy/issues).
No astronomy or programming background is required — just tell us what you were trying to do and
what happened instead.

## Contributing

Bug reports, feature suggestions, and pull requests are welcome.
See [CONTRIBUTING.en.md](CONTRIBUTING.en.md) for development setup and coding conventions.

## License

MIT License — free to use, modify, and redistribute for research, education, or any other purpose.
See [LICENSE](LICENSE) for details.

## About this project

Provenance and observing details for the bundled sample data are documented in
[sample_data/README.md](sample_data/README.md).
