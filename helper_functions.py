ONLY_DIGITS = ''.join(str(i) for i in range(10))
DICE_NOTATION = ONLY_DIGITS + 'dD%+-*/hHlL '


def reply_to_message(update, text, parse_mode=None):
    while len(text) > 4095:
        last = text[:4096].rfind('\n')
        if last == -1:
            update.message.reply_text(text[:4092] + '...')
            text = text[4092:]
        else:
            update.message.reply_text(text[:last])
            text = text[last + 1:]
    update.message.reply_text(text, parse_mode=parse_mode)


def get_user_name(update):
    return str(update.message.from_user.name) if update.message.from_user.name is not None \
        else str(update.message.from_user.firstname)


# checks for sanity string. Returns first not sane index
def sanity_bound(string, allowed):
    for i in range(len(string)):
        if string[i] not in allowed:
            return i
    return len(string)


# converts string to integer bounded to [min_v, max_v]. Returns default on fault
def to_int(data, *_, default, max_v, min_v=1):
    try:
        return min(max(int(data), min_v), max_v)
    except (TypeError, ValueError):
        return default


# s - string with some expression and dices in format `5d9`
#   (one or both arguments may be missing. Default value is 1d20; `d%` is `d100`)
# random_generator - function that returns value from 1 to given argument inclusively
def roll_processing(s, random_generator):
    i = sanity_bound(s, ONLY_DIGITS + 'd% +-*/()')
    rest, s = s[i:], s[2:i].strip()
    if len(s) == 0:
        s = 'd'
    i, rolls = 0, []
    while i < len(s):
        if s[i] == 'd':  # found dice
            j = i - 1  # j is left border for dice count
            while j >= 0 and s[j].isnumeric():
                j -= 1
            cnt = to_int(s[j + 1:i], max_v=1000, default=1)
            k = i + 1  # k is right border for dice max value
            if i + 1 < len(s) and s[i + 1] == '%':
                mod = 100
            else:
                while k < len(s) and s[k].isnumeric():
                    k += 1
                mod = to_int(s[i + 1:k], max_v=1000000, default=20)
                k -= 1
            rolls += [str(random_generator(mod)) for _ in range(cnt)]
            added = '(' + '+'.join(rolls[len(rolls) - cnt:]) + ')'
            s = s[:j + 1] + added + s[k + 1:]
            i = j + len(added)
        i += 1
    return s, rolls, rest


def calc(expression):
    # check item type
    def is_int(item):
        return type(item) == int

    def is_str(item):
        return type(item) == str

    # First part gets string and deletes whitespace
    # Then it creates the list and adds each individual character to the list
    expr_list = [int(ch) if ord('0') <= ord(ch) <= ord('9') else ch for ch in expression.replace(' ', '')]
    pos = 1
    # combine numbers together and check expression
    while pos < len(expr_list):
        if is_int(expr_list[pos - 1]) and expr_list[pos] == "(":
            expr_list.insert(pos, '*')  # insert missing asterisk
        elif is_int(expr_list[pos - 1]) and is_int(expr_list[pos]):
            expr_list[pos - 1] = expr_list[pos - 1] * 10 + expr_list[pos]
            del expr_list[pos]
        else:
            pos += 1

    # If the length of the list is 1, there is only 1 number, meaning an answer has been reached.
    try:
        while len(expr_list) != 1:
            changed = False  # if the are no changes then something is wrong. Preferably expression
            # remove parentheses around a single item
            pos = 2
            while pos < len(expr_list):
                if expr_list[pos - 2] == "(" and expr_list[pos] == ")":
                    expr_list = expr_list[:pos - 2] + [expr_list[pos - 1]] + expr_list[pos + 1:]
                    changed = True
                pos += 1
            # */
            pos = 1
            while pos < len(expr_list) - 1:
                if is_str(expr_list[pos]) and is_int(expr_list[pos + 1]) and is_int(expr_list[pos - 1]) \
                        and expr_list[pos] in "*/":
                    if expr_list[pos] == '*':
                        expr_list[pos - 1] *= expr_list[pos + 1]
                    elif expr_list[pos] == '/':
                        expr_list[pos - 1] //= expr_list[pos + 1]
                    expr_list = expr_list[:pos] + expr_list[pos + 2:]
                    changed = True
                else:
                    pos += 1
            # +-
            pos = 1
            while pos < len(expr_list) - 1:
                if is_str(expr_list[pos]) and is_int(expr_list[pos + 1]) and is_int(expr_list[pos - 1]) \
                        and expr_list[pos] in "+-":
                    if expr_list[pos] == '+':
                        expr_list[pos - 1] += expr_list[pos + 1]
                    elif expr_list[pos] == '-':
                        expr_list[pos - 1] -= expr_list[pos + 1]
                    expr_list = expr_list[:pos] + expr_list[pos + 2:]
                    changed = True
                else:
                    pos += 1
            if not changed:
                return None, "Invalid expression"
        return int(expr_list[0]), ""
    except ZeroDivisionError:
        return None, "Division by zero"
