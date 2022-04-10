import random
import os
import re
from typing import Union, List, Optional, Iterable, Tuple

from telegram import Chat, Update
from telegram.ext import CallbackContext

from database import Database
from StringsStorage import StringsStorage, String


class Helper:
    MASTER_ID = 351693351
    ONLY_DIGITS = ''.join(str(i) for i in range(10))
    DICE_NOTATION = ONLY_DIGITS + 'dD%+-*/hHlL '
    # Scary regex. For "/r 1d20+5 asd" will match:
    # {'cmd': 'r', 'roll': '1', 'dice': '20', 'mod_act': '+', 'mod_val': '5', 'mod_sel': None, 'comment': 'asd'}
    # for "/r 2h": {'cmd': 'r', 'roll': '2', 'mod_sel': 'h'} (None fields are skipped)
    COMMAND_REGEX = re.compile(r"/(?P<cmd>\w+)(@(?P<botname>\w+))?(?# command)"
                               r"\s?(?P<throw>(?P<count>\d+)?(d(?P<dice>\d+|%))?(?# throw)"
                               r"(((?P<mod_act>[+\-*/])(?P<mod_num>\d+))|(?P<mod_sel>[hl]))?)?(?# mods)"
                               r"(?P<comment>.*)?(?#comment)", re.IGNORECASE)

    def __init__(self):
        self.db = Database()
        self.ss = StringsStorage()

    # get creator of chat with chat_id
    @staticmethod
    def get_chat_creator_id(context: CallbackContext, chat_id: int, chat_type: str) -> int:
        if chat_type == Chat.PRIVATE:
            return chat_id
        return list(filter(lambda a: a.status == a.CREATOR, context.bot.getChatAdministrators(chat_id)))[0].user.id

    # get number in [1, max_val] using "true" random
    @staticmethod
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

    # returns an integer from 1 to dice inclusively and add result to stats
    def rnd(self, dice: int) -> int:
        dice = abs(dice)  # remove negative values
        if dice == 0 or dice > 1000000:
            dice = 20  # remove incorrect
        res = self.get_random_num(dice)
        self.db.increment_stat(dice, res)
        return res

    @staticmethod
    def reply_to_message(update: Update, text: Union[str, String], is_markdown: bool = False):
        if isinstance(text, String):
            text = text(update)
        while len(text) > 4095:
            last = text[:4096].rfind('\n')
            if last == -1:
                update.message.reply_text(text[:4092] + '...')
                text = text[4092:]
            else:
                update.message.reply_text(text[:last])
                text = text[last + 1:]
        update.message.reply_text(text, parse_mode=("MarkdownV2" if is_markdown else None))

    @staticmethod
    def get_user_name(update: Update) -> str:
        return str(update.message.from_user.name or update.message.from_user.first_name)

    # checks for sanity string. Returns first not sane index
    @staticmethod
    def sanity_bound(string: str, allowed: Iterable[str]) -> int:
        for i in range(len(string)):
            if string[i] not in allowed:
                return i
        return len(string)

    # converts string to integer bounded to [min_v, max_v]. Returns default on fault
    @staticmethod
    def to_int(data, *_, default: int, max_v: int, min_v: int = 1):
        if data is None:
            return default
        try:
            return min(max(int(data), min_v), max_v)
        except (TypeError, ValueError):
            return default

    # s - string with some expression and dices in format `5d9`
    #   (one or both arguments may be missing. Default value is 1d20; `d%` is `d100`)
    def roll_processing(self, s: str) -> Tuple[str, List[int], str]:
        i = Helper.sanity_bound(s, Helper.ONLY_DIGITS + 'd% +-*/()')
        rest, s = s[i:], s[:i].strip()
        if len(s) == 0:
            s = 'd'
        i, rolls = 0, []
        while i < len(s):
            if s[i] == 'd':  # found dice
                j = i - 1  # j is left border for dice count
                while j >= 0 and s[j].isnumeric():
                    j -= 1
                cnt = Helper.to_int(s[j + 1:i], max_v=1000, default=1)
                k = i + 1  # k is right border for dice max value
                if i + 1 < len(s) and s[i + 1] == '%':
                    mod = 100
                else:
                    while k < len(s) and s[k].isnumeric():
                        k += 1
                    mod = Helper.to_int(s[i + 1:k], max_v=1000000, default=20)
                    k -= 1
                rolls += [str(self.rnd(mod)) for _ in range(cnt)]
                added = '(' + '+'.join(rolls[len(rolls) - cnt:]) + ')'
                s = s[:j + 1] + added + s[k + 1:]
                i = j + len(added)
            i += 1
        return s, rolls, rest

    @staticmethod
    def calc(expression: str) -> Tuple[Optional[int], Optional[str], str]:  # -> [result, error, comment_prefix]
        # check item type
        def is_int(item):
            return type(item) == int

        def is_str(item):
            return type(item) == str

        # First part gets string and deletes whitespace
        # Then it creates the list and adds each individual character to the list
        expr_list = [int(ch) if ch.isnumeric() else ch for ch in expression.replace(' ', '')]
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
                    if is_int(expr_list[0]) and all(map(is_str, expr_list[1:])):
                        return int(expr_list[0]), None, ''.join(map(str, expr_list[1:]))
                    return None, "Invalid expression", ""
            if is_int(expr_list[0]):
                return int(expr_list[0]), None, ""
            return None, "Invalid expression", ""
        except ZeroDivisionError:
            return None, "Division by zero", ""

    # return: [command_text, comment, count, dice, mod_act, mod_num]
    @staticmethod
    def parse_simple_roll(text: str, default_count: int = 1, default_dice: int = 20,
                          default_mod_act: Optional[str] = None, default_mod_num: Optional[Union[str, int]] = None) -> \
            Tuple[str, str, int, int, Optional[str], Optional[Union[int, str]]]:
        def eq(a, b) -> bool:
            if b is None:
                return a is None
            return a == b

        def get(d: dict, name: str) -> Optional[str]:
            if name in d:
                return d[name]
            return None

        match = Helper.COMMAND_REGEX.match(text).groupdict()
        command_shortcut = get(match, 'cmd') or ''
        rolls_cnt = Helper.to_int(get(match, 'count'), default=1, max_v=1000) * default_count
        if get(match, 'dice') == '%':
            rolls_dice = 100
        else:
            rolls_dice = Helper.to_int(get(match, 'dice'), default=default_dice, max_v=1000_000)
        mod_act = get(match, 'mod_act') or default_mod_act
        if mod_act == '/':
            mod_act = '//'
        mod_num = get(match, 'mod_num') or get(match, 'mod_sel') or default_mod_num
        if mod_num is not None:
            mod_num = mod_num.lower()
        comment = get(match, 'comment') or ''

        if rolls_dice == default_dice and rolls_cnt == default_count and eq(mod_act, default_mod_act) and \
                eq(mod_num, default_mod_num):
            command_text = command_shortcut
        else:
            command_text = "{} {}d{}".format(command_shortcut, rolls_cnt, rolls_dice)
            if mod_act is not None:
                command_text += mod_act + mod_num
            elif mod_num is not None:
                command_text += mod_num
        return command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num

    def is_user_has_stats_access(self, update: Update, context: CallbackContext) -> Tuple[bool, int, int]:
        # has_access, chat_id, user_id
        chat_id, user_id = update.message.chat_id, update.message.from_user.id
        is_admin = user_id == Helper.MASTER_ID or (
                chat_id != user_id and Helper.get_chat_creator_id(context, chat_id, update.message.chat.type) == user_id
        )
        if update.message.reply_to_message is not None:
            target_id = update.message.reply_to_message.from_user.id
        else:
            target_id = user_id
        if not is_admin and user_id != target_id:
            Helper.reply_to_message(update, self.ss.CHAT_CREATOR_ONLY(update))
            return False, chat_id, target_id
        return True, chat_id, target_id

    def stats_to_dict(self):
        stats = {}
        for stat in self.db.get_all_stats():
            if stat.dice not in stats:
                stats[stat.dice] = {}
            stats[stat.dice][stat.result] = stat.count
        return stats

    def create_rolls_message(self, update: Update, rolls: List[int], default_cnt: int, default_dice: int,
                             command_text: str, comment: str, rolls_cnt: int, rolls_dice: int,
                             mod_act: Optional[str], mod_num: Optional[Union[int, str]]) -> str:
        # def simple_roll(self, update: Update, context, cnt=1, default_dice=20, mod_act=None, mod_num=None):
        #     parsed = self.parse_simple_roll(update.message.text, cnt, default_dice, mod_act, mod_num)
        #     command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
        rolls_info = ' + '.join(str(r) for r in rolls)
        if rolls_cnt > 1:
            if default_cnt > 1:
                rolls_sums = '(' + ') + ('.join(str(sum(rolls[i * default_cnt:(i + 1) * default_cnt])) for i in
                                                range(rolls_cnt // default_cnt)) + ')'
            else:
                rolls_sums = '(' + ' + '.join(str(roll) for roll in rolls) + ')'
        else:
            rolls_sums = str(rolls[0])
        if mod_num is not None:
            if mod_num == 'h':
                rolls_info = 'Max of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(max(rolls))
            elif mod_num == 'l':
                rolls_info = 'Min of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(min(rolls))
            elif self.sanity_bound(mod_num, self.ONLY_DIGITS) == len(mod_num) > 0:
                rolls_info = rolls_sums + ' ' + mod_act + ' ' + mod_num + ' = ' + \
                             str(eval(str(sum(rolls)) + mod_act + mod_num))
            else:
                comment = mod_act + mod_num + comment
        text = self.get_user_name(update) + ': ' + comment + '\n' + rolls_info
        if rolls_cnt > 1 and mod_num is None:
            text += '\nSum: '
            if default_cnt != 1:
                text += rolls_sums + ' = '
            text += str(sum(rolls))
        criteria = self.db.get_counting_criteria(update.message.chat_id, command_text.split()[0])
        if criteria is not None and default_dice == rolls_dice:
            for i in range(rolls_cnt // default_cnt):
                i_sum = sum(rolls[i * default_cnt:(i + 1) * default_cnt])
                if criteria.min_value <= i_sum <= criteria.max_value:
                    self.db.increment_counting_data(update.message.chat_id, update.message.from_user.id,
                                                    command_text)
        return text
