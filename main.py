import logging
import random
import time
import json
import os.path

from telegram.ext import Updater, CommandHandler

import rollbot_secret_token
from helper_functions import *

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO, filename="rollbot.log")

logger = logging.getLogger(__name__)
start_time = time.time()
stats = {20: {i: 0 for i in range(1, 21)}}
MASTER_ID = 351693351


# returns an integer from 1 to dice inclusively and add result to stats
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


# params: update and context
def simple_roll(update, _):
    # get username or user's name
    name = str(update.message.from_user.name)
    if name == 'None':
        name = str(update.message.from_user.firstname)

    # separating comment and roll params
    ts = update.message.text.split(' ', 2)
    mod_act, mod = None, None
    if len(ts) == 1:  # only `/r`
        rolls_cnt = 1
        rolls_dice = 20
        comment = ''
    elif not is_sane(ts[1], DICE_NOTATION):
        rolls_cnt = 1
        rolls_dice = 20
        comment = ' '.join(ts[1:])
    else:
        if 'd' in ts[1]:
            data = ts[1].split('d')
        else:
            data = ts[1].split('D')
        comment = ts[2] if len(ts) == 3 else ''
        if len(data) == 1 and data[0].isnumeric():  # if there is no `d`
            rolls_cnt = to_int(data[0], default=1, max_v=1000)
            rolls_dice = 20
        # d is occupied only once and this is something like 4d7 or 9d%
        elif len(data) == 2 and (data[0].isnumeric() or len(data[0]) == 0):
            for act in '+-*/':
                if act in data[1]:
                    mod_act = act
                    data[1], mod = [s.strip() for s in data[1].split(act, 1)]
                    break

            if data[1].isnumeric() or data[1] == '%' or len(data[1]) == 0:
                rolls_cnt = to_int(data[0], default=1, max_v=1000)
                rolls_dice = to_int(data[1], default=20)
                if data[1] == '%':
                    rolls_dice = 100
            else:
                rolls_cnt = 1
                rolls_dice = 20
                comment = ts[1] + ' ' + comment
        else:  # otherwise its only part of the comment
            rolls_cnt = 1
            rolls_dice = 20
            comment = ts[1] + ' ' + comment

    # get numbers and generate text
    rolls = [rnd(rolls_dice) for _ in range(rolls_cnt)]
    rolls_info = ' + '.join(str(r) for r in rolls)
    if mod_act is not None:
        if mod.capitalize() == 'H':
            rolls_info = 'Max of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(max(rolls))
        elif mod.capitalize() == 'L':
            rolls_info = 'Min of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(min(rolls))
        elif is_sane(mod, ONLY_DIGITS):
            rolls_info = '(' + rolls_info + ') ' + mod_act + ' ' + mod + ' = ' + str(eval(str(sum(rolls)) + mod_act + mod))
    text = name + ': ' + comment + '\n' + rolls_info
    if rolls_cnt > 1:
        text += '\nSum: ' + str(sum(rolls))
    update.message.reply_text(text if len(text) < 3991 else (text[:3990] + "..."))


def roll3d6(update, _):
    name = str(update.message.from_user.name)
    if name == 'None':
        name = str(update.message.from_user.firstname)
    ts = update.message.text.split(' ', 1)
    if len(ts) == 1:
        comment = ''
    else:
        comment = ts[1]
    rolls = [rnd(6) for _ in range(3)]
    text = name + ': ' + comment + '\n' + ' + '.join(str(r) for r in rolls) + '\nSum: ' + str(sum(rolls))
    update.message.reply_text(text if len(text) < 3991 else (text[:3990] + "..."))


def r2(update, _):
    name = str(update.message.from_user.name)
    if name == 'None':
        name = str(update.message.from_user.firstname)

    s, rolls, rest = roll_processing(update.message.text, random_generator=rnd)
    r = calc(s, 0, len(s))
    text = name + ': ' + rest + '\n' + s + '\n = ' + str(r)
    update.message.reply_text(text if len(text) < 4000 else (text[:3996] + "..."))


# just ping
def ping(update, _):
    update.message.reply_text('Pong!')
    print('ping!')


# get stats only to d20
def get_stats(update, _):
    overall = sum(stats[20].values())
    msg = "Stats for this bot:\nUptime: {} hours\nd20 stats (%): from {} rolls".format(
        str((time.time() - start_time) / 3600), str(overall))
    for i in range(1, 21):
        if i in stats[20]:
            msg += "\n{}: {}".format(str(i), str(stats[20][i] / overall * 100))
    update.message.reply_text(msg)


# get all stats
def get_full_stats(update, _):
    msg = "Stats for this bot:\nUptime: {} hours".format(str((time.time() - start_time) / 3600))
    for key in stats:
        overall = sum(stats[key].values())
        msg += "\nd{} stats (%): from {} rolls".format(str(key), str(overall))
        for i in range(1, key + 1):
            if i in stats[key]:
                msg += "\n{}: {}".format(str(i), str(stats[key][i] / overall * 100))
    update.message.reply_text(msg)


# log all errors
def error_handler(update, context):
    logger.error('Error: {} ({} {}) caused.by {}'.format(
        str(context), str(type(context.error)), str(context.error), str(update)))
    print("Error: " + str(context.error))
    if update.message is not None:
        update.message.reply_text("Error")
        context.bot.send_message(chat_id=MASTER_ID,
                                 text="Error: {} {} for message {}".format(str(type(context.error))[:1000],
                                                                           str(context.error)[:3000],
                                                                           str(update.message.text)[:3000]))


# start
def init(token):
    # stats loading
    global stats
    if os.path.isfile("stats.json"):
        # convert dict's keys from str to int
        stats_t = json.loads(open("stats.json").read())
        stats = {int(dice): {int(res): stats_t[dice][res] for res in stats_t[dice]} for dice in stats_t}

    updater = Updater(token=token, use_context=True)
    # adding handlers
    for command, func in (
            ('ping', ping),
            ('r', simple_roll),
            ('3d6', roll3d6),
            ('d', r2),
            ('stats', get_stats),
            ('statsall', get_full_stats),
    ):
        updater.dispatcher.add_handler(CommandHandler(command, func))
    updater.dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

    # saving stats
    f = open("stats.json", 'w')
    f.write(json.dumps(stats))
    f.close()


if __name__ == '__main__':
    print("Started", time.time())
    init(rollbot_secret_token.token)
