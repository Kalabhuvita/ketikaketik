"""Patah baris ala Obsidian.

Di markdown standar, satu baris baru di dalam paragraf dianggap spasi. Obsidian
(dan banyak penulis) memperlakukannya sebagai patah baris: 1x Enter = baris
baru, 2x Enter = paragraf baru.

Fungsi ini menyiapkan teks untuk *render* dan *ekspor* -- bukan untuk file .md,
yang tetap bersih tanpa spasi tambahan. Aturan yang dipakai adalah hard break
CommonMark: dua spasi di akhir baris.
"""
FENCE = ("```", "~~~")


def with_hard_breaks(text: str) -> str:
    lines = text.split("\n")
    out = []
    in_fence = False

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith(FENCE):
            in_fence = not in_fence
            out.append(line)
            continue

        if in_fence:
            out.append(line)
            continue

        following = lines[index + 1] if index + 1 < len(lines) else ""
        # baris berisi teks yang langsung diikuti baris berisi teks = patah baris
        if stripped and following.strip():
            out.append(line.rstrip() + "  ")
        else:
            out.append(line)

    return "\n".join(out)