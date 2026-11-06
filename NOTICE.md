# Notice

This repository contains independent reverse-engineering notes about the panel
microcontroller firmware of a **Roland T-8** that the author owns. It is published for
interoperability, documentation and educational purposes.

- **No Roland firmware binaries are included.** The raw images (`T8_UPD.BIN`,
  `DD010_app.bin`, `DD010_pnl.bin`), the extracted payload, and the ELF/PE repackagings
  of them are excluded. Only original analysis — disassembly, decompiler output, written
  notes, tooling and a clean-room-style protocol simulator — is published here.
- **Roland** and **T-8** are trademarks of their respective owner. This project is not
  affiliated with, endorsed by, or sponsored by Roland.
- Roland's software EULAs for products in this line generally prohibit reverse
  engineering, and in some jurisdictions (e.g. the US, DMCA §1201) circumventing access
  controls on firmware can carry separate legal implications. This is typically tolerated
  for personal modification of a device you own ("right to repair"), but distributing a
  modified firmware is a different matter. Nothing here is legal advice; consult a
  professional before relying on it.

If you are a rights holder and have a concern about anything in this repository, please
open an issue.
