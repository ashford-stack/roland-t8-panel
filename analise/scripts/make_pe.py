import struct
import sys
import time

IMAGE_FILE_MACHINE_ARM = 0x01C0
IMAGE_FILE_MACHINE_THUMB = 0x01C2
IMAGE_FILE_MACHINE_ARMNT = 0x01C4  # ARMv7 (Thumb-2) little endian

def align(value, al):
    return (value + al - 1) // al * al

def build_pe_arm(payload: bytes, image_base: int, entry_rva: int, machine=IMAGE_FILE_MACHINE_ARMNT) -> bytes:
    FILE_ALIGN = 0x200
    SECT_ALIGN = 0x1000

    dos_stub = bytearray(64)
    dos_stub[0:2] = b"MZ"
    e_lfanew_off = 0x3C
    # e_lfanew filled below

    section_name = b".text\x00\x00\x00"
    num_sections = 1

    coff_header_size = 20
    opt_header_size = 224  # PE32 optional header (no data dirs beyond 16*8=128 + 96 fixed) standard size
    # Standard PE32 optional header size = 96 (standard fields+windows fields portion varies);
    # We'll build explicitly below instead of relying on this constant.

    # --- Build optional header (PE32, 32-bit) ---
    # Standard fields
    magic = 0x10B  # PE32
    major_linker = 14
    minor_linker = 0
    size_of_code = align(len(payload), FILE_ALIGN)
    size_of_init_data = 0
    size_of_uninit_data = 0
    address_of_entry_point = entry_rva
    base_of_code = SECT_ALIGN
    base_of_data = SECT_ALIGN  # not critical for analysis

    # Windows-specific fields
    image_base_v = image_base
    section_alignment = SECT_ALIGN
    file_alignment = FILE_ALIGN
    major_os = 6
    minor_os = 0
    major_image = 0
    minor_image = 0
    major_subsys = 6
    minor_subsys = 0
    win32_version = 0
    size_of_headers = None  # computed below
    checksum = 0
    subsystem = 1  # native
    dll_characteristics = 0
    size_of_stack_reserve = 0x100000
    size_of_stack_commit = 0x1000
    size_of_heap_reserve = 0x100000
    size_of_heap_commit = 0x1000
    loader_flags = 0
    num_rva_and_sizes = 16

    # Compute header sizes to know SizeOfHeaders
    dos_header_size = 64
    pe_sig_size = 4
    coff_size = coff_header_size
    opt_size = 96 + 16 * 8  # standard(28)+windows(68)=96 fixed fields for PE32 + 16 data dirs *8 bytes
    section_table_size = 40 * num_sections

    headers_size_raw = dos_header_size + pe_sig_size + coff_size + opt_size + section_table_size
    size_of_headers_v = align(headers_size_raw, FILE_ALIGN)

    section_raw_offset = size_of_headers_v
    section_raw_size = align(len(payload), FILE_ALIGN)
    section_virtual_size = len(payload)
    section_rva = SECT_ALIGN

    size_of_image = align(section_rva + align(section_virtual_size, SECT_ALIGN), SECT_ALIGN)

    # --- COFF header ---
    timestamp = int(time.time())
    characteristics = 0x0002 | 0x0100 | 0x0010  # EXECUTABLE_IMAGE | 32BIT_MACHINE | LARGE_ADDRESS... use EXECUTABLE+LINE_NUMS_STRIPPED etc keep simple
    characteristics = 0x0102  # EXECUTABLE_IMAGE | 32BIT_MACHINE_MASK(approx) -> use standard 0x0102
    coff = struct.pack(
        "<HHIIIHH",
        machine,
        num_sections,
        timestamp,
        0,  # PointerToSymbolTable
        0,  # NumberOfSymbols
        opt_size,  # SizeOfOptionalHeader
        characteristics,
    )

    # --- Optional header standard fields ---
    opt_std = struct.pack(
        "<HBBIIIIII",
        magic,
        major_linker,
        minor_linker,
        size_of_code,
        size_of_init_data,
        size_of_uninit_data,
        address_of_entry_point,
        base_of_code,
        base_of_data,
    )

    opt_win = struct.pack(
        "<IIIHHHHHHIIIIHHIIIIII",
        image_base_v,
        section_alignment,
        file_alignment,
        major_os,
        minor_os,
        major_image,
        minor_image,
        major_subsys,
        minor_subsys,
        win32_version,
        size_of_image,
        size_of_headers_v,
        checksum,
        subsystem,
        dll_characteristics,
        size_of_stack_reserve,
        size_of_stack_commit,
        size_of_heap_reserve,
        size_of_heap_commit,
        loader_flags,
        num_rva_and_sizes,
    )

    data_dirs = b"\x00" * (8 * 16)

    opt_header = opt_std + opt_win + data_dirs
    assert len(opt_header) == opt_size, (len(opt_header), opt_size)

    # --- Section header ---
    sect_characteristics = 0x60000020  # CODE | EXECUTE | READ
    section_hdr = struct.pack(
        "<8sIIIIIIHHI",
        section_name,
        section_virtual_size,
        section_rva,
        section_raw_size,
        section_raw_offset,
        0, 0, 0, 0,
        sect_characteristics,
    )

    e_lfanew = dos_header_size
    dos_stub[e_lfanew_off:e_lfanew_off + 4] = struct.pack("<I", e_lfanew)

    out = bytearray()
    out += dos_stub
    out += b"PE\x00\x00"
    out += coff
    out += opt_header
    out += section_hdr
    # pad to section_raw_offset
    out += b"\x00" * (section_raw_offset - len(out))
    out += payload
    out += b"\x00" * (section_raw_size - len(payload))

    return bytes(out)


if __name__ == "__main__":
    in_path, out_path, base_hex, entry_rva_hex = sys.argv[1:5]
    base = int(base_hex, 16)
    entry_rva = int(entry_rva_hex, 16)
    with open(in_path, "rb") as f:
        payload = f.read()
    pe = build_pe_arm(payload, base, entry_rva)
    with open(out_path, "wb") as f:
        f.write(pe)
    print(f"wrote {out_path}: {len(pe)} bytes, base=0x{base:08x}, entry_rva=0x{entry_rva:08x}")
