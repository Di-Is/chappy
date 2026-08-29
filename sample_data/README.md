# Bundled Sample Spectrum

Quasar Q0329-385 (J033106-382404), VLT/UVES continuum-normalized spectrum.

- `J033106-382404_f.fits`: normalized flux
- `J033106-382404_e.fits`: flux error

Used by the first-run tutorial. A known C IV λλ1548/1550 absorption system at
z_abs ≈ 2.076 (observed ~4763/4771 Å) serves as the tutorial checkpoint
(Bergeron et al. 2002, A&A 396, 11; Muzahid et al. 2012, MNRAS 421, 446).

## Resolving Power

The tutorial applies R = 54,000 to this sample automatically. The SQUAD DR1
catalogue (`DR1_quasars_master.csv`, column `ResPowerNom`) tabulates the
nominal resolving power at five wavelengths; for this quasar it is 55,800 at
4500 Å and 47,800 at 5500 Å, and 54,000 is the linear interpolation at the
tutorial's C IV region (~4763 Å).

## Attribution

This spectrum originates from the UVES Spectral Quasar Absorption Database
(SQUAD) Data Release 1, licensed under CC-BY-4.0:

> Murphy M. T., Kacprzak G. G., Savorgnan G. A. D., Carswell R. F., 2019,
> MNRAS, 482, 3458. DOI: 10.5281/zenodo.1345974
> https://github.com/MTMurphy77/UVES_SQUAD_DR1

Based on observations collected at the European Southern Observatory under
ESO programme 166.A-0106.
