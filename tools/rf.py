def main():
    d = input("> ")

    a = []
    while True:
        line = input()
        if not line.strip():
            break
        a.append(line)

    for i, line in enumerate(a):
        line:str
        arr = line.split("\t")
        a[i] = arr

    d = f"GC_{d}_"

    b = int(a[0][1], 16) >> 16 << 16

    for c in a:
        if d not in c[0]:
            print(f"err at: {c}")
            return
        
        print(
            f'"{c[0].replace(d, "", 1)}": 0x{(int(c[1], 16) - b):x},'
        )


main()