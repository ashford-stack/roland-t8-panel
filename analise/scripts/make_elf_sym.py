import struct
import sys

# Variant of make_elf.py that adds a .symtab with STT_FUNC symbols
# (thumb bit set in st_value) so Ghidra creates the callback-only functions.

EHDR_SIZE = 52
PHDR_SIZE = 32
SHDR_SIZE = 40
SYM_SIZE = 16

# (name, address) — callback/fptr-only functions missing from Ghidra's analysis
SYMBOLS = [
    ("stm32_default", 0x080000ea),
    ("stm32_1ac", 0x080001ac),
    ("cb_1f0", 0x080001f0),
    ("weak_28ec", 0x080028ec),
    ("weak_2932", 0x08002932),
    ("weak_2934", 0x08002934),
    ("weak_2936", 0x08002936),
    ("weak_2938", 0x08002938),
    ("weak_2970", 0x08002970),
    ("rxisr_16_2cc4", 0x08002cc4),
    ("rxisr_16_2e7c", 0x08002e7c),
    ("rxisr_9_3204", 0x08003204),
    ("txisf_46_3246", 0x08003246),
    ("rxisr_9_329e", 0x0800329e),
    ("txisf_9_32dc", 0x080032dc),
    ("cb_3954", 0x08003954),
    ("cb_3970", 0x08003970),
    ("cb_3a04", 0x08003a04),
    ("adc_interp", 0x08003a78),
    ("led_set", 0x08003c50),
    ("thunk_4ab0", 0x08004ab0),
    ("cmd_tree", 0x08004ab8),
    ("big_4d0c", 0x08004d0c),
]


def build_elf_arm_sym(payload: bytes, base_addr: int, entry: int) -> bytes:
    num_ph = 1
    data_off = EHDR_SIZE + PHDR_SIZE * num_ph  # 84 = 0x54
    data_size = len(payload)

    shstrtab = b"\x00.text\x00.shstrtab\x00.symtab\x00.strtab\x00"
    data_end = data_off + data_size

    shstrtab_off = data_end
    shstrtab_size = len(shstrtab)

    strtab_off = shstrtab_off + shstrtab_size
    strtab = b"\x00"
    name_offsets = {}
    for name, _ in SYMBOLS:
        name_offsets[name] = len(strtab)
        strtab += name.encode() + b"\x00"
    strtab_size = len(strtab)

    symtab_off = (strtab_off + strtab_size + 3) & ~3
    symtab_size = SYM_SIZE * (1 + len(SYMBOLS))  # NULL symbol + FUNCs

    sh_off = (symtab_off + symtab_size + 3) & ~3
    num_sh = 5  # NULL, .text, .shstrtab, .symtab, .strtab

    e_ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
    ehdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        e_ident,
        2,          # ET_EXEC
        40,         # EM_ARM
        1,          # version
        entry,
        EHDR_SIZE,  # e_phoff
        sh_off,
        0,          # flags
        EHDR_SIZE,
        PHDR_SIZE,
        num_ph,
        SHDR_SIZE,
        num_sh,
        2,          # e_shstrndx = .shstrtab
    )

    phdr = struct.pack(
        "<8I",
        1,                # PT_LOAD
        data_off,         # p_offset
        base_addr,        # p_vaddr
        base_addr,        # p_paddr
        data_size,        # p_filesz
        data_size,        # p_memsz
        5,                # p_flags R+X
        4,                # p_align
    )

    symbol_count = len(SYMBOLS)
    symtab = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)  # NULL symbol
    for name, addr in SYMBOLS:
        symtab += struct.pack(
            "<IIIBBH",
            name_offsets[name],
            addr | 1,     # thumb bit
            0,            # st_size unknown
            0x12,         # STB_GLOBAL | STT_FUNC
            0,            # st_other
            1,            # st_shndx = .text
        )

    shstrtab_name = 7
    sh_symtab_name = 16
    sh_strtab_name = 24

    def shdr(name, sh_type, flags, addr, offset, size, link, info, align, entsize):
        return struct.pack(
            "<10I", name, sh_type, flags, addr, offset, size, link, info, align, entsize
        )

    shdrs = shdr(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    shdrs += shdr(1, 1, 0x6, base_addr, data_off, data_size, 0, 0, 4, 0)          # .text
    shdrs += shdr(shstrtab_name, 3, 0, 0, shstrtab_off, shstrtab_size, 0, 0, 1, 0)  # .shstrtab
    shdrs += shdr(sh_symtab_name, 2, 0, 0, symtab_off, symtab_size, 4, 1, 4, SYM_SIZE)  # .symtab
    shdrs += shdr(sh_strtab_name, 3, 0, 0, strtab_off, strtab_size, 0, 0, 1, 0)   # .strtab

    out = bytearray(ehdr + phdr + payload)
    assert len(out) == data_end

    def pad_to(offset):
        while len(out) < offset:
            out.append(0)

    pad_to(shstrtab_off)
    out += shstrtab
    pad_to(strtab_off)
    out += strtab
    pad_to(symtab_off)
    out += symtab
    pad_to(sh_off)
    out += shdrs

    return bytes(out)


def main():
    payload_path, out_path, base, entry = sys.argv[1:5]
    with open(payload_path, "rb") as f:
        payload = f.read()
    out = build_elf_arm_sym(payload, int(base, 16), int(entry, 16))
    with open(out_path, "wb") as f:
        f.write(out)
    print("wrote %s: %d bytes, base=%s, entry=%s, %d symbols" % (out_path, len(out), base, entry, len(SYMBOLS)))


if __name__ == "__main__":
    main()
