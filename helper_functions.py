ONLY_DIGITS = ''.join(str(i) for i in range(10))
DIGITS_WITH_D_PERCENT = ONLY_DIGITS + 'dD%'
DICE_NOTATION = DIGITS_WITH_D_PERCENT + '+-*/hHlL '


# checks for sanity string
def is_sane(string, allowed):
    for i in range(len(string)):
        if string[i] not in allowed:
            return i
    return len(string)


# converts string to integer bounded to [min_v, max_v]. Returns default on fault
def to_int(data, *_, default=20, min_v=1, max_v=1000000):
    data = data.strip()
    if len(data) == 0:
        return default
    try:
        return min(max(int(data), min_v), max_v)
    except (TypeError, ValueError):
        return default


def roll_processing(s, random_generator):
    i = 2
    allow = 'd1234567890% +-*/^()[]'
    while i < len(s) and s[i] in allow:
        i += 1
    rest = s[i:]
    s = s[2:i].strip()
    i = 0
    rolls = []
    while i < len(s):
        if s[i] == 'd':
            j = i - 1
            while j >= 0 and s[j].isnumeric():
                j -= 1
            if j + 1 < i:
                cnt = to_int(s[j + 1:i], max_v=1000, default=1)
            else:
                cnt = 1
            if i + 1 == len(s):
                mod = 20
                k = i
            else:
                if s[i + 1] == '%':
                    mod = 100
                    k = i + 1
                elif s[i + 1].isnumeric():
                    k = i + 1
                    while k < len(s) and s[k].isnumeric():
                        k += 1
                    mod = to_int(s[i + 1:k], max_v=1000000, default=20)
                    k -= 1
                else:
                    k = i
                    mod = 20
            for _ in range(cnt):
                rolls.append(str(random_generator(mod)))
            added = '(' + '+'.join(rolls[len(rolls) - cnt:]) + ')'
            s = s[:j + 1] + added + s[k + 1:]
            i = j + len(added)
        i += 1
    return s, rolls, rest


def calc(s, si, ei):
    def subsearch(i):
        j = i - 1
        ws = False
        while j >= 0 and (s[j].isnumeric() or (s[j] == ' ' and not ws)):
            ws |= s[j] == ' '
            j -= 1
        fn = to_int(s[j + 1:i].strip(), max_v=1000, default=1)
        k = i + 1
        ws = False
        while k < ei and (s[k].isnumeric() or (s[k] == ' ' and not ws)):
            ws |= s[k] == ' '
            k += 1
        sn = to_int(s[i + 1:k].strip(), max_v=1000000, default=20)
        return j + 1, k, fn, sn

    # parentheses
    pc, spc, pcs, spcs = 0, 0, 0, 0
    i = si
    while i < ei:
        if s[i] == '(':
            if pc == 0:
                pcs = i
            pc += 1
        elif s[i] == ')':
            pc -= 1
            if pc == 0:
                r = calc(s, pcs + 1, i)
                dr = i - pcs - len(str(r)) + 1
                s = s[:pcs] + str(r) + s[i + 1:]
                ei -= dr
                i = i + 1
        elif s[i] == '[':
            if spc == 0:
                spcs = i
            spc += 1
        elif s[i] == ']':
            spc -= 1
            if spc == 0:
                r = calc(s, spcs + 1, i)
                dr = i - pcs - len(str(r)) + 1
                s = s[:spcs] + str(r) + s[i + 1:]
                ei -= dr
                i = i + 1
        i += 1
    # actual math
    # ^
    i = si
    while i < ei:
        if s[i] == '^':
            j, k, fn, sn = subsearch(i)
            n = str(fn ** sn)
            r = len(s) - ei
            s = s[:j] + n + s[k:]
            ei = len(s) - r
            i = j + len(n) - 1
        i += 1
    # */
    i = si
    while i < ei:
        if s[i] == '*' or s[i] == '/':
            j, k, fn, sn = subsearch(i)
            if s[i] == '*':
                n = str(fn * sn)
            else:
                n = str(fn // sn)
            r = len(s) - ei
            s = s[:j] + n + s[k:]
            ei = len(s) - r
            i = j + len(n) - 1
        i += 1
    # +-
    i = si
    while i < ei:
        if s[i] == '+' or s[i] == '-':
            j, k, fn, sn = subsearch(i)
            if s[i] == '+':
                n = str(fn + sn)
            else:
                n = str(fn - sn)
            r = len(s) - ei
            s = s[:j] + n + s[k:]
            ei = len(s) - r
            i = j + len(n) - 1
        i += 1

    return to_int(s[si:ei], default="Error")
