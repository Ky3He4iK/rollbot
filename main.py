import logging
import random
import time
import json
import os.path

from telegram.ext import Updater, CommandHandler

import rollbot_secret_token

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO, filename="rollbot.log")

logger = logging.getLogger(__name__)
start_time = time.time()
stats = {20: {i: 0 for i in range(1, 21)}}
MASTER_ID = 351693351


# возвращает рандомное число от 1 до dice включительно и добавляет результат в статистику
def rnd(dice):
    global stats
    if dice < 0:
        dice = -dice
    elif dice == 0 or dice > 1000000:
        dice = 20
    res = random.randrange(dice) + 1
    if dice in stats:
        if res in stats[dice]:
            stats[dice][res] += 1
        else:
            stats[dice][res] = 1
    else:
        stats[dice] = {res: 1}
    return res


# преобразует строку (любой контейнер, к которому можно применить len() и int()) в число
# И ограничивает значениями от min_v до max_v
# Если не получилось, возвращает default
def to_int(data, *_, default=20, min_v=1, max_v=1000000):
    if len(data) == 0:
        return default
    try:
        return min(max(int(data), min_v), max_v)
    except (TypeError, ValueError):
        return default


# принимает update и context
def roll(update, _):
    # получение имени пользователя (в первую очередь юзернейм)
    name = str(update.message.from_user.name)
    if name == 'None':
        name = str(update.message.from_user.firstname)

    # отделение комментария и получение инфы о броске
    ts = update.message.text.split(' ', 2)
    if len(ts) == 1:  # если только /d
        rolls_cnt = 1
        rolls_dice = 20
        comment = ''
    else:
        data = ts[1].split('d')
        comment = ts[2] if len(ts) == 3 else ''
        if len(data) == 1 and data[0].isnumeric():  # если d в записи нет и это число - кол-во роллов d20
            rolls_cnt = to_int(data[0], default=1, max_v=1000)
            rolls_dice = 20
        # d встречается только 1 раз и это запись вида 5d7
        elif len(data) == 2 and data[0].isnumeric() and data[1].isnumeric():
            rolls_cnt = to_int(data[0], default=1, max_v=1000)
            rolls_dice = to_int(data[1], default=20)
            if data[1] == '%':
                rolls_dice = 100
        else:  # иначе это просто часть коммента
            rolls_cnt = 1
            rolls_dice = 20
            comment = ts[1] + ' ' + comment

    # получение роллов и генерация текста
    rolls = [rnd(rolls_dice) for _ in range(rolls_cnt)]
    text = name + ': ' + comment + '\n' + ' + '.join(str(r) for r in rolls)
    update.message.reply_text(text if len(text) < 4000 else (text[:3996] + "..."))


def r2(update, _):
    # todo: round for [], div with floor
    n = str(update.message.from_user.name)
    if n == 'None':
        n = str(update.message.from_user.firstname)

    def roll(s):
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
                    cnt = min(max(int(s[j + 1:i]), 1), 1000)
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
                        mod = int(s[i + 1:k])
                        k -= 1
                    else:
                        k = i
                        mod = 20
                for _ in range(cnt):
                    rolls.append(str(rnd(mod)))
                added = '(' + '+'.join(rolls[len(rolls) - cnt:]) + ')'
                s = s[:j + 1] + added + s[k + 1:]
                i = i + j - k + len(added)
            i += 1
        return s, rolls, rest

    def calc(s, si, ei):
        def subsearch(i):
            j = i - 1
            ws = False
            while j >= 0 and (s[j].isnumeric() or (s[j] == ' ' and not ws)):
                ws |= s[j] == ' '
                j -= 1
            fn = int(s[j + 1:i].strip())
            k = i + 1
            ws = False
            while k < ei and (s[k].isnumeric() or (s[k] == ' ' and not ws)):
                ws |= s[k] == ' '
                k += 1
            sn = int(s[i + 1:k].strip())
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

        return int(s[si:ei])

    s, rolls, rest = roll(update.message.text)
    r = calc(s, 0, len(s))
    text = n + ': ' + rest + '\n' + s + '\n = ' + str(r)
    update.message.reply_text(text if len(text) < 4000 else (text[:3996] + "..."))


# просто пинг
def ping(update, _):
    update.message.reply_text('Pong!')
    print('ping!')


# получение стат (только d20)
def get_stats(update, _):
    msg = "Stats for this bot:\nUptime: {} hours\nd20 stats (%):".format(str((time.time() - start_time) / 3600))
    overall = sum(stats[20].values())
    for i in range(1, 21):
        msg += "\n{}: {}".format(str(i), str(stats[20][i] / overall * 100))
    update.message.reply_text(msg)


# получение всех стат
def get_full_stats(update, _):
    msg = "Stats for this bot:\nUptime: {} hours".format(str((time.time() - start_time) / 3600))
    for key in stats:
        msg += "\nd{} stats (%)".format(str(key))
        overall = sum(stats[key].values())
        for i in range(1, key + 1):
            if i in stats[key]:
                msg += "\n{}: {}".format(str(i), str(stats[key][i] / overall * 100))
    update.message.reply_text(msg)


# логгировать все ошибки
def error_handler(update, context):
    logger.error('Error: ' + str(context) + " (" + str(context.error) + ") caused by " + str(update))
    print("Error: " + str(context.error))
    if update.message is not None:
        update.message.reply_text("Error")
        context.bot.send_message(chat_id=MASTER_ID, text="Error: " + str(context.error)[:3000] + " for message " + str(
            update.message.text)[:3000])


# старт бота
def init(token):
    # загрузка стат
    global stats
    if os.path.isfile("stats.json"):
        stats = json.loads(open("stats.json").read())

    updater = Updater(token=token, use_context=True)
    # добавление обработчиков команд
    for command, func in (
            ('ping', ping),
            ('r', roll),
            ('d', r2),
            ('stats', get_stats),
            ('statsall', get_full_stats),
    ):
        updater.dispatcher.add_handler(CommandHandler(command, func))
    updater.dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

    # сохранение статистики в файл
    f = open("stats.json", 'w')
    f.write(json.dumps(stats))
    f.close()


if __name__ == '__main__':
    print("Started", time.time())
    init(rollbot_secret_token.token)
