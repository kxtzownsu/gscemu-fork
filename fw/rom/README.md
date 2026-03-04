# Contains all ROM resources for gscemulator

- haven.rom
  - Original ROM extracted from a production H1B3C chip with RMASmoke
- haven_no_hashcheck.rom
  - Original ROM, but 0x1214 - 0x1237 is a nopsled to disable hashchecking
    against the SignedHeader of an image. This does not modify the values
    passed to SB_BL_SIG
- haven_C_source.rom
  - Haven ROM rewritten from the original ROM's assembly. Compiled from
    <https://github.com/HavenOverflow/Cr50/tree/main/chip/haven/rom>
