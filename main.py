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
    dice = max(dice, -dice)  # remove negative values
    if dice == 0 or dice > 1000000:
        dice = 20  # remove incorrect
    res = random.randrange(dice) + 1
    if dice in stats:
        stats[dice][res] = 1 + (stats[dice][res] if res in stats[dice] else 0)
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
    ts = update.message.text.split(' ', 1)
    mod_act, mod, rolls_cnt, rolls_dice, comment = None, None, 1, 20, ''  # default values
    if len(ts) > 1:  # not only `r`
        # cut out comment
        split_pos = sanity_bound(ts[1], DICE_NOTATION)
        command, comment = ts[1][:split_pos].strip().lower(), ts[1][split_pos:].strip()

        # cut out appendix (+6, *4, etc.)
        for i in range(len(command)):
            if command[i] in '+-*/':
                mod_act = command[i]
                if mod_act == '/':
                    mod_act = '//'
                command, mod = [s.strip() for s in command.split(command[i], 1)]
                split_pos = sanity_bound(mod, ONLY_DIGITS)  # remove other actions
                mod, comment = mod[:split_pos], mod[split_pos:] + comment
                break

        command = command.split('d')
        rolls_cnt = to_int(command[0], default=1, max_v=1000)
        if len(command) > 1:
            rolls_dice = to_int(command[1], default=20, max_v=1000000)

    try:
        # get numbers and generate text
        rolls = [rnd(rolls_dice) for _ in range(rolls_cnt)]
        rolls_info = ' + '.join(str(r) for r in rolls)
        if mod_act is not None:
            if mod == 'h':
                rolls_info = 'Max of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(max(rolls))
            elif mod == 'l':
                rolls_info = 'Min of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(min(rolls))
            elif sanity_bound(mod, ONLY_DIGITS):
                rolls_info = '(' + rolls_info + ') ' + mod_act + ' ' + mod + ' = ' + str(
                    eval(str(sum(rolls)) + mod_act + mod))
            else:
                comment = mod_act + mod + comment
        text = name + ': ' + comment + '\n' + rolls_info
        if rolls_cnt > 1 and mod_act is None:
            text += '\nSum: ' + str(sum(rolls))
        update.message.reply_text(text if len(text) < 3991 else (text[:3990] + "..."))
    except Exception as e:
        print(e)
        update.message.reply_text(name + ': ' + update.message.text[2:] + '\n' + str(rnd(20)))


def roll3d6(update, _):
    ts = update.message.text.split(' ', 1)
    comment = '' if len(ts) == 1 else ts[1]
    rolls = [rnd(6) for _ in range(3)]
    text = get_user_name(update) + ': ' + comment + '\n' + \
           ' + '.join(str(r) for r in rolls) + '\nSum: ' + str(sum(rolls))
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
            ('c', roll3d6),
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
