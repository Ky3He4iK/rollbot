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
def simple_roll(update, _, cnt=1, dice=20):
    # separating comment and roll params
    ts = update.message.text.split(' ', 1)
    mod_act, mod, rolls_cnt, rolls_dice, comment = None, None, cnt, dice, ''  # default values
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
        rolls_cnt = to_int(command[0], default=1, max_v=1000) * cnt
        if len(command) > 1:
            rolls_dice = to_int(command[1], default=dice, max_v=1000000)

    try:
        # get numbers and generate text
        rolls = [rnd(rolls_dice) for _ in range(rolls_cnt)]
        rolls_info = ' + '.join(str(r) for r in rolls)
        if mod_act is not None:
            if mod == 'h':
                rolls_info = 'Max of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(max(rolls))
            elif mod == 'l':
                rolls_info = 'Min of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(min(rolls))
            elif sanity_bound(mod, ONLY_DIGITS) == len(mod) > 0:  # PyCharm says it's ok. I hope so
                rolls_info = '(' + rolls_info + ') ' + mod_act + ' ' + mod + ' = ' + \
                             str(eval(str(sum(rolls)) + mod_act + mod))
            else:
                comment = mod_act + mod + comment
        text = get_user_name(update) + ': ' + comment + '\n' + rolls_info
        if rolls_cnt > 1 and mod_act is None:
            text += '\nSum: '
            if cnt != 1:
                text += '(' + ' + '.join(str(sum(rolls[i * cnt:(i + 1) * cnt])) for i in range(rolls_cnt // cnt)) \
                        + ') = '
            text += str(sum(rolls))
        update.message.reply_text(text if len(text) < 3991 else (text[:3990] + "..."))
    except Exception as e:
        update.message.reply_text(get_user_name(update) + ': ' + update.message.text[2:] + '\n' + str(rnd(20)))
        raise e


def custom_roll_wrapper(cnt, dice):
    return lambda update, context: simple_roll(update, context, cnt, dice)


def equation_roll(update, _):
    s, rolls, rest = roll_processing(update.message.text[2:], random_generator=rnd)
    r = calc(s)
    reply_to_message(update, get_user_name(update) + ': ' + rest + '\n' + s + '\n' +
                     (r[1] if r[0] is None else (' = ' + str(r[0]))))


# just ping
def ping(update, _):
    update.message.reply_text('Pong!')
    print('ping!')


# get stats only to d20
def get_stats(update, _):
    ts = update.message.text.split(' ', 2)
    if len(ts) > 1:
        dice = to_int(ts[1], default=20, max_v=1000000000)
    else:
        dice = 20
    if dice in stats:
        overall = sum(stats[dice].values())
        msg = "Stats for this bot:\nUptime: {} hours\nd20 stats (%): from {} rolls".format(
            (time.time() - start_time) / 3600, overall)
        for i in range(1, dice + 1):
            if i in stats[dice]:
                msg += "\n{}: {}".format(i, stats[dice][i] / overall * 100)
    else:
        msg = "No information for this dice!"
    reply_to_message(update, msg)


# get all stats
def get_full_stats(update, _):
    msg = "Stats for this bot:\nUptime: {} hours".format((time.time() - start_time) / 3600)
    for key in stats:
        overall = sum(stats[key].values())
        msg += "\nd{} stats (%): from {} rolls".format(key, overall)
        for i in range(1, key + 1):
            if i in stats[key]:
                addition = "\n{}: {}".format(i, stats[key][i] / overall * 100)
                if len(msg) + len(addition) > 4000:
                    reply_to_message(update, msg)
                    msg = ''
                msg += addition
    reply_to_message(update, msg)


def help_handler(update, _):
    reply_to_message(update, "Available commands:\n`/r 5d20+7`\\- roll 5d20 and add 7\\. Default dice is 1d20\n"
                             "`/r d20` and `/r 5` and `/r +7` are fine too\nAlso can understand: `/c` \\- default 3d6\n"
                             "`/s` \\- 1d11\n`/p` \\- 1d100\n`/p2` \\- 1d200\n`/p3` \\- 1d300\n\n"
                             "And `/d *equation*` \\- evaluate \\*equation\\* with dice rolls in it",
                     parse_mode="MarkdownV2")


# log all errors
def error_handler(update, context):
    logger.error('Error: {} ({} {}) caused.by {}'.format(context, type(context.error), context.error, update))
    print("Error: " + str(context.error))
    if update.message is not None:
        update.message.reply_text("Error")
        context.bot.send_message(chat_id=MASTER_ID, text="Error: {} {} for message {}".format(
            str(type(context.error))[:1000], str(context.error)[:2000], str(update.message.text)[:1000]))


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
            ('3d6', custom_roll_wrapper(3, 6)),
            ('c', custom_roll_wrapper(3, 6)),
            ('s', custom_roll_wrapper(1, 11)),
            ('p', custom_roll_wrapper(1, 100)),
            ('p2', custom_roll_wrapper(1, 200)),
            ('p3', custom_roll_wrapper(1, 300)),
            ('d', equation_roll),
            ('stats', get_stats),
            ('statsall', get_full_stats),
            ('help', help_handler)
    ):
        updater.dispatcher.add_handler(CommandHandler(command, func))
    updater.dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()
    print("Stopping")

    # saving stats
    f = open("stats.json", 'w')
    f.write(json.dumps(stats))
    f.close()


if __name__ == '__main__':
    print("Started", time.time())
    init(rollbot_secret_token.token)
