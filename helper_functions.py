import random
import os

ONLY_DIGITS = ''.join(str(i) for i in range(10))
DICE_NOTATION = ONLY_DIGITS + 'dD%+-*/hHlL '


# get creator of chat with chat_id
def get_chat_creator_id(context, chat_id):
    return list(filter(lambda a: a.status == a.CREATOR, context.bot.getChatAdministrators(chat_id)))[0].user.id


# get number in [1, max_val] using "true" random
def get_random_num(max_val: int) -> int:
    bin_len = len(bin(max_val)) - 2
    num_cnt, mask = bin_len // 8, (1 << (bin_len % 8)) - 1
    for _ in range(1000):  # 1k tries for "true" cryptographic random
        nums = list(os.urandom(num_cnt + 1))
        nums[0] &= mask
        n = 0
        for i in nums:
            n = (n << 8) + i
        if n != 0 and n <= max_val:
            return n
    # fallback - use default python random
    return random.randrange(max_val) + 1


def reply_to_message(update, text, is_markdown=False):
    while len(text) > 4095:
        last = text[:4096].rfind('\n')
        if last == -1:
            update.message.reply_text(text[:4092] + '...')
            text = text[4092:]
        else:
            update.message.reply_text(text[:last])
            text = text[last + 1:]
    update.message.reply_text(text, parse_mode=("MarkdownV2" if is_markdown else None))


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
    rest, s = s[i:], s[:i].strip()
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


# return: [command_text, comment, count, dice, mod_act, mod_num]
def parse_simple_roll(text, cnt=1, rolls_dice=20, mod_act=None, mod_num=None):
    # separating comment and roll params
    ts = text.split(' ', 1)
    rolls_cnt, comment = cnt, ''
    command_text = ts[0]
    if len(ts) > 1:  # not only `r`
        # cut out comment
        split_pos = sanity_bound(ts[1], DICE_NOTATION)
        command, comment = ts[1][:split_pos].strip().lower(), ts[1][split_pos:].strip()
        command_text += ' ' + command
        # cut out appendix (+6, *4, etc.)
        for i in range(len(command)):
            if command[i] in '+-*/':
                mod_act = command[i]
                if mod_act == '/':
                    mod_act = '//'
                command, mod_num = [s.strip() for s in command.split(command[i], 1)]
                split_pos = sanity_bound(mod_num, ONLY_DIGITS)  # remove other actions
                mod_num, comment = mod_num[:split_pos], mod_num[split_pos:] + comment
                break

        command = command.split('d')
        rolls_cnt = to_int(command[0], default=1, max_v=1000) * cnt
        if len(command) > 1:
            rolls_dice = to_int(command[1], default=None, max_v=1000000)
    return [command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num]
